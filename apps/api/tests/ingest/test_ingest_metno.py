"""MET Norway rainfall adapter: parser on a real response, hostile JSON, and the zone loop on fakes."""

import itertools
import json
from datetime import datetime, timedelta

import httpx
import pytest
from ingest_testkit import NOW, FakeConn, FakeHttp, fixture

from floodroute.ingest import common, metno
from floodroute.ingest.common import FetchError, Http, IngestError, Rejected

BLR = fixture("metno/locationforecast_compact_bengaluru.json")
BLR_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=12.9716&lon=77.5946"


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s)


def tweak(change) -> bytes:
    doc = json.loads(BLR)
    change(doc)
    return json.dumps(doc).encode()


# Expected values were read off the fixture by hand: 64 hourly steps from 20:00Z, the wettest hours
# 07:00 to 09:00Z on 6 Oct (2.7, 2.3, 1.8 mm), updated_at 19:19:14Z.
def test_real_response_parses():
    updated, issued, hourly = metno.parse_forecast(BLR, NOW)
    assert updated == utc("2026-10-05T19:19:14+00:00")
    assert issued == utc("2026-10-05T19:00:00+00:00")  # floored to the hour
    assert len(hourly) == 64
    assert hourly[0] == (utc("2026-10-05T20:00:00+00:00"), 0.0)
    assert hourly[-1] == (utc("2026-10-08T11:00:00+00:00"), 0.1)
    assert dict(hourly)[utc("2026-10-06T07:00:00+00:00")] == 2.7
    gaps = {b[0] - a[0] for a, b in itertools.pairwise(hourly)}
    assert gaps == {timedelta(hours=1)}  # only the hourly part, no 6 hourly tail
    assert round(sum(mm for _, mm in hourly), 1) == 8.1


def test_two_backends_with_slightly_different_stamps_give_the_same_issue():
    other = tweak(lambda d: d["properties"]["meta"].update(updated_at="2026-10-05T19:19:25Z"))
    assert metno.parse_forecast(other, NOW)[1] == metno.parse_forecast(BLR, NOW)[1]


@pytest.mark.parametrize(
    "name, change",
    [
        (
            "unit is inches",
            lambda d: d["properties"]["meta"]["units"].update(precipitation_amount="in"),
        ),
        (
            "negative amount",
            lambda d: d["properties"]["timeseries"][0]["data"]["next_1_hours"]["details"].update(
                precipitation_amount=-0.1
            ),
        ),
        (
            "absurd amount",
            lambda d: d["properties"]["timeseries"][0]["data"]["next_1_hours"]["details"].update(
                precipitation_amount=5000
            ),
        ),
        (
            "string amount",
            lambda d: d["properties"]["timeseries"][0]["data"]["next_1_hours"]["details"].update(
                precipitation_amount="2.0"
            ),
        ),
        (
            "bool amount",
            lambda d: d["properties"]["timeseries"][0]["data"]["next_1_hours"]["details"].update(
                precipitation_amount=True
            ),
        ),
        (
            "null amount",
            lambda d: d["properties"]["timeseries"][0]["data"]["next_1_hours"]["details"].update(
                precipitation_amount=None
            ),
        ),
        (
            "missing amount",
            lambda d: d["properties"]["timeseries"][0]["data"]["next_1_hours"]["details"].clear(),
        ),
        ("no properties", lambda d: d.pop("properties")),
        ("no meta", lambda d: d["properties"].pop("meta")),
        ("no timeseries", lambda d: d["properties"].pop("timeseries")),
        ("timeseries is a string", lambda d: d["properties"].update(timeseries="x")),
        (
            "naive timestamp",
            lambda d: d["properties"]["timeseries"][0].update(time="2026-10-05T20:00:00"),
        ),
        ("bad timestamp", lambda d: d["properties"]["timeseries"][0].update(time="tomorrow")),
        (
            "updated_at missing offset",
            lambda d: d["properties"]["meta"].update(updated_at="2026-10-05T19:19:14"),
        ),
        (
            "updated_at in the future",
            lambda d: d["properties"]["meta"].update(updated_at="2026-10-06T19:19:14Z"),
        ),
        (
            "forecast two days old",
            lambda d: d["properties"]["meta"].update(updated_at="2026-10-03T19:19:14Z"),
        ),
        (
            "no hourly steps",
            lambda d: [t["data"].pop("next_1_hours", None) for t in d["properties"]["timeseries"]],
        ),
        (
            "too many entries",
            lambda d: d["properties"].update(timeseries=d["properties"]["timeseries"] * 5),
        ),
    ],
)
def test_unexpected_or_hostile_json_is_refused(name, change):
    with pytest.raises(Rejected):
        metno.parse_forecast(tweak(change), NOW)


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        b"[]",
        b"{}",
        b'{"properties": null}',
        b"\xff\xfe",
        b"null",
        (
            b'{"properties": {"meta": {"units": {"precipitation_amount": "mm"},'
            b' "updated_at": "2026-10-05T19:19:14Z"}, "timeseries": [{"time": "2026-10-05T20:00:00Z",'
            b' "data": {"next_1_hours": {"details": {"precipitation_amount": NaN}}}}]}}'
        ),
        b"[" * 100_000 + b"]" * 100_000,  # deep nesting must not crash the run
    ],
)
def test_garbage_bodies_are_refused(body):
    with pytest.raises(Rejected):
        metno.parse_forecast(body, NOW)


@pytest.mark.parametrize(
    "args",
    [
        (
            1,
            77.59,
            12.97,
        ),  # lon,lat swapped: this is how a zone with lat and lon the wrong way round looks
        (1, None, 77.0),
        (1, 12.0, None),
        (1, float("nan"), 77.0),
        (1, "x", 77.0),
        (1, 12.0, float("inf")),
        (True, 12.9, 77.5),
        ("7", 12.9, 77.5),
        (None, 12.9, 77.5),
        (1, 51.0, 77.5),
        (1, 12.9, 120.0),
    ],
)
def test_bad_zone_points_are_refused(args):
    with pytest.raises(Rejected):
        metno.check_point(*args)
    assert metno.check_point(1, 12.9716, 77.5946) == (12.9716, 77.5946)


def routes(*points, body=BLR):
    return {metno.URL.format(lat, lon): body for _, lat, lon in points}


def test_zones_are_fetched_with_four_decimals_and_stored_idempotently():
    conn = FakeConn()
    points = [(1, 12.9716, 77.5946), (2, 13.123456789, 77.6)]
    http = FakeHttp(routes(*points))
    out = metno.ingest(conn, http, points=points, now=NOW)
    assert http.calls == [
        BLR_URL,
        "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=13.1235&lon=77.6000",
    ]
    assert out.summary == {"zones": 2, "rows": 128} and out.warn is None
    assert out.lag_s == int((NOW - utc("2026-10-05T19:19:14+00:00")).total_seconds()) == 4246
    assert len(conn.rain) == 128
    snapshot = dict(conn.rain)
    row = conn.rain[
        ("metno", 1, utc("2026-10-05T19:00:00+00:00"), utc("2026-10-06T07:00:00+00:00"))
    ]
    assert row == (
        "metno",
        1,
        utc("2026-10-05T19:00:00+00:00"),
        utc("2026-10-06T07:00:00+00:00"),
        2.7,
        None,
    )

    metno.ingest(conn, FakeHttp(routes(*points)), points=points, now=NOW)  # same issue again
    assert conn.rain == snapshot  # same keys, same values: nothing new


def test_a_new_issue_adds_rows_and_leaves_the_old_ones():
    conn = FakeConn()
    points = [(1, 12.9716, 77.5946)]
    metno.ingest(conn, FakeHttp(routes(*points)), points=points, now=NOW)
    later = tweak(lambda d: d["properties"]["meta"].update(updated_at="2026-10-06T01:20:00Z"))
    metno.ingest(
        conn, FakeHttp(routes(*points, body=later)), points=points, now=NOW + timedelta(hours=6)
    )
    assert len(conn.rain) == 128 and {k[2] for k in conn.rain} == {
        utc("2026-10-05T19:00:00+00:00"),
        utc("2026-10-06T01:00:00+00:00"),
    }


def test_zone_points_come_from_the_zone_table_when_not_given():
    conn = FakeConn()
    conn.zones = [(7, 12.9716, 77.5946)]
    out = metno.ingest(conn, FakeHttp({BLR_URL: BLR}), now=NOW)
    assert out.summary["zones"] == 1 and {k[1] for k in conn.rain} == {7}


def test_no_zones_is_a_failure_not_a_quiet_success():
    with pytest.raises(IngestError, match="zone table is empty"):
        metno.ingest(FakeConn(), FakeHttp({}), now=NOW)


def test_a_bad_response_for_one_zone_fails_the_run_but_the_other_zones_are_stored():
    conn = FakeConn()
    points = [(1, 12.9716, 77.5946), (2, 13.0, 77.6), (3, 13.1, 77.7)]
    table = routes(*points)
    table[metno.URL.format(13.0, 77.6)] = b'{"properties": {}}'
    with pytest.raises(IngestError, match=r"1 of 3 zones failed: zone 2: unexpected JSON shape"):
        metno.ingest(conn, FakeHttp(table), points=points, now=NOW)
    assert {k[1] for k in conn.rain} == {1, 3}


def test_a_point_outside_india_fails_that_zone_without_a_request():
    conn, http = FakeConn(), FakeHttp(routes((1, 12.9716, 77.5946)))
    points = [(1, 12.9716, 77.5946), (2, 77.59, 12.97)]
    with pytest.raises(IngestError, match="zone 2: point 77.59,12.97 is outside India"):
        metno.ingest(conn, http, points=points, now=NOW)
    assert http.calls == [BLR_URL] and {k[1] for k in conn.rain} == {1}


def test_a_network_failure_stops_the_run_at_once():
    conn = FakeConn()
    points = [(1, 12.9716, 77.5946), (2, 13.0, 77.6)]
    http = FakeHttp({BLR_URL: FetchError("ConnectError: reset"), **routes(points[1])})
    with pytest.raises(FetchError):
        metno.ingest(conn, http, points=points, now=NOW)
    assert http.calls == [BLR_URL] and conn.rain == {}


def test_one_request_per_second_across_zones_and_a_failed_run_reports_itself(capsys):
    clock, stamps = [0.0], []

    def handler(request: httpx.Request) -> httpx.Response:
        stamps.append(clock[0])
        return httpx.Response(200, content=BLR)

    http = Http(
        metno.HOSTS,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        clock=lambda: clock[0],
    )
    points = [(i, 12.0 + i / 100, 77.5) for i in range(1, 6)]
    metno.ingest(FakeConn(), http, points=points, now=NOW)
    assert len(stamps) == 5
    assert all(b - a >= 1.0 - 1e-9 for a, b in itertools.pairwise(stamps))

    conn = FakeConn()
    code = common.run(
        conn, "metno", lambda c: metno.ingest(c, FakeHttp({}), now=NOW), clock=lambda: NOW
    )
    assert code == 1 and "zone table is empty" in conn.health["metno"]["last_error"]
