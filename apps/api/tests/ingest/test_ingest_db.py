"""The adapters against the real schema (PostgreSQL 16 and PostGIS), as the DML-only app role.

Uses the shared fixtures in tests/conftest.py: a throwaway database cloned from a fully migrated
template, so these skip with the reason when no server is reachable (CI fails instead of skipping).
"""

import math
import zlib
from datetime import datetime

import psycopg
import pytest
from ingest_testkit import NOW, FakeHttp, cap_xml, fixture, polygon_url, rss_one, sachet_routes

from floodroute.ingest import __main__ as cli
from floodroute.ingest import common, metno, sachet
from floodroute.ingest.common import FetchError

ZONE = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
BLR = fixture("metno/locationforecast_compact_bengaluru.json")
CWC = "IN-1791205725481016_5"
UTTARAKHAND = "IN-1791229518905009_9"


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s)


@pytest.fixture
def app(app_db):
    """The floodroute_app role (DML only), the way the cron jobs will connect."""
    return app_db


def alerts(conn):
    return conn.execute(
        "select cap_id, sender, event, severity, certainty, onset, expires, ST_AsEWKT(area), raw"
        " from official_alert order by cap_id"
    ).fetchall()


def ingest_all(conn, routes=None, **kw):
    return sachet.ingest(conn, FakeHttp(routes or sachet_routes()), now=NOW, max_new=50, **kw)


def add_zone(conn, zone_id=1):
    conn.execute(
        "insert into zone (zone_id, city_id, geom, params) values (%s, 1, %s, '{}')",
        (zone_id, ZONE),
    )


def test_alerts_are_stored_once_with_a_correct_geometry(app):
    out = ingest_all(app)
    assert out.summary["stored"] == 8
    first = alerts(app)
    assert len(first) == 8

    again = ingest_all(app)  # the seen check runs against the real table
    assert again.summary["new"] == 0 and again.summary["stored"] == 0
    assert alerts(app) == first  # idempotent: nothing duplicated, nothing rewritten

    row = app.execute(
        "select ST_GeometryType(area), ST_SRID(area), ST_IsValid(area),"
        " ST_Contains(area, ST_SetSRID(ST_MakePoint(85.85, 26.33), 4326)),"
        " ST_Contains(area, ST_SetSRID(ST_MakePoint(26.33, 85.85), 4326)),"
        " ST_Area(area::geography) from official_alert where cap_id = %s",
        (CWC,),
    ).fetchone()
    # the gauge (lat 26.33, lon 85.85) is inside; the same numbers the wrong way round are not
    assert row[:5] == ("ST_MultiPolygon", 4326, True, True, False)
    # polygon_cwc_circle.xml is a circle of radius 0.043262 degrees ((26.373262 - 26.286738) / 2)
    expected = math.pi * 0.043262**2 * 111_195**2 * math.cos(math.radians(26.33))
    assert row[5] == pytest.approx(expected, rel=0.03)  # about 65 square km

    uk = app.execute(
        "select ST_NumGeometries(area), ST_XMin(area), ST_XMax(area), ST_YMin(area), ST_YMax(area)"
        " from official_alert where cap_id = %s",
        (UTTARAKHAND,),
    ).fetchone()
    assert uk[0] == 2  # four rings in the document, two distinct
    assert 79.0 < uk[1] < uk[2] < 81.0 and 28.5 < uk[3] < uk[4] < 30.5  # x is lon, y is lat

    no_polygon = app.execute(
        "select count(*), count(area), count(*) filter (where raw->>'area_error' is not null)"
        " from official_alert"
    ).fetchone()
    assert no_polygon == (8, 2, 6)


def test_columns_and_raw_hold_what_was_published(app):
    ingest_all(app)
    sender, event, severity, certainty, onset, expires, raw = app.execute(
        "select sender, event, severity, certainty, onset, expires, raw from official_alert"
        " where cap_id = %s",
        (CWC,),
    ).fetchone()
    assert (sender, event, severity, certainty) == ("CWC", "Flood", "Severe", "Possible")
    assert onset == utc("2026-10-05T13:08:45+00:00") and expires == utc("2026-10-06T00:30:00+00:00")
    assert raw["cap_xml"] == fixture("sachet/cap_cwc_flood_en.xml").decode()
    assert raw["rss_key"] == "1791205725481016@20261005T130846Z"
    assert raw["cap"]["infos"][0]["headline"].startswith("River Adhwara Group at Kamtaul")
    raw = app.execute(
        "select raw from official_alert where cap_id = %s", (UTTARAKHAND,)
    ).fetchone()[0]
    assert [i["language"] for i in raw["cap"]["infos"]] == ["en-IN", "HI"]
    assert raw["cap"]["infos"][1]["headline"].startswith("[2026/10/06 01:12] अगले 3 घंटो")
    assert raw["cap"]["references"][0]["identifier"] == "IN-1791229518905009_65"


def test_a_reissued_item_adds_a_row_and_keeps_the_old_one(app):
    ingest_all(app)
    rss = fixture("sachet/rss_india_subset.xml").replace(
        b"Mon, 05 Oct 2026 19:55:05 GMT", b"Mon, 05 Oct 2026 20:10:00 GMT"
    )
    routes = sachet_routes(rss=rss)
    routes[sachet.CAP_URL.format("1791229078945019")] = fixture(
        "sachet/cap_karnataka_en.xml"
    ).replace(b"IN-1791229078945019_19", b"IN-1791229078945019_20")
    assert ingest_all(app, routes).summary["stored"] == 1
    ids = [r[0] for r in alerts(app)]
    assert len(ids) == 9 and {"IN-1791229078945019_19", "IN-1791229078945019_20"} <= set(ids)


def test_test_messages_are_stored_without_a_severity(app):
    guid, item = "1791229078999999", fixture("sachet/rss_india_subset.xml")
    item = item.replace(b"1791229078945019", guid.encode())
    routes = sachet_routes(rss=item)
    routes[sachet.CAP_URL.format(guid)] = cap_xml(
        identifier=f"IN-{guid}_19", status="Test", infos=[{"severity": "Extreme"}]
    )
    routes[polygon_url(guid)] = common.HttpStatusError(404, "https://sachet.ndma.gov.in/x")
    ingest_all(app, routes)
    event, severity, status = app.execute(
        "select event, severity, raw->'cap'->>'status' from official_alert where cap_id = %s",
        (f"IN-{guid}_19",),
    ).fetchone()
    assert (event, severity, status) == ("Heavy Rain", None, "Test")


def test_a_self_intersecting_polygon_is_stored_as_a_valid_multipolygon(app):
    bow_tie = (
        "<cap:area><cap:areaDesc>x</cap:areaDesc><cap:polygon>"
        "12.9,77.5 13.1,77.7 13.1,77.5 12.9,77.7 12.9,77.5</cap:polygon></cap:area>"
    )
    guid = "1791229078999998"
    routes = {
        sachet.RSS_URL: rss_one(guid),
        sachet.CAP_URL.format(guid): cap_xml(identifier=f"IN-{guid}_1", infos=[{"area": bow_tie}]),
    }
    ingest_all(app, routes)
    row = app.execute(
        "select ST_GeometryType(area), ST_IsValid(area), ST_NumGeometries(area),"
        " ST_SRID(area) from official_alert"
    ).fetchone()
    assert row == ("ST_MultiPolygon", True, 2, 4326)  # two triangles after ST_MakeValid


def test_health_rows_on_the_real_table(app):
    http = FakeHttp(sachet_routes())

    def read():
        return app.execute(
            "select last_ok, last_error, lag_s from source_health where source = 'sachet'"
        ).fetchone()

    assert (
        common.run(
            app, "sachet", lambda c: sachet.ingest(c, http, now=NOW, max_new=50), clock=lambda: NOW
        )
        == 0
    )
    last_ok, last_error, lag = read()
    assert last_ok == NOW and lag == 2095
    assert last_error.startswith("warning: 3 active alert(s) have no area")

    down = FakeHttp({sachet.RSS_URL: FetchError("ConnectError: Connection reset by peer")})
    later = NOW.replace(minute=31)
    assert (
        common.run(app, "sachet", lambda c: sachet.ingest(c, down, now=later), clock=lambda: later)
        == 1
    )
    last_ok, last_error, lag = read()
    assert last_ok == NOW  # still the last time it worked
    assert lag is None  # unknown, not 2095
    assert (
        last_error
        == "2026-10-05T20:31:00Z failed: FetchError: ConnectError: Connection reset by peer"
    )

    assert (
        common.run(app, "sachet", lambda c: sachet.ingest(c, http, now=later), clock=lambda: later)
        == 0
    )
    last_ok, last_error, lag = read()
    assert (last_ok, lag) == (later, 2155)  # lag is the feed's age at that run
    assert last_error.startswith(
        "warning: 3 active alert(s) have no area"
    )  # still true, still said


def test_rain_forecast_for_zones_read_from_the_zone_table(app):
    add_zone(app)
    http = FakeHttp(
        {"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=13.0000&lon=77.6000": BLR}
    )
    out = metno.ingest(app, http, now=NOW)  # points come from ST_PointOnSurface on the real table
    assert out.summary == {"zones": 1, "rows": 64} and out.lag_s == 4246
    rows = app.execute(
        "select source, zone_id, issued, valid, mm_per_h, ensemble_spread"
        " from rain_fcst order by valid"
    ).fetchall()
    assert len(rows) == 64 and {r[:3] for r in rows} == {
        ("metno", 1, utc("2026-10-05T19:00:00+00:00"))
    }
    assert rows[0][3:] == (utc("2026-10-05T20:00:00+00:00"), 0.0, None)
    assert max(r[4] for r in rows) == pytest.approx(2.7)

    metno.ingest(app, FakeHttp(http.routes), now=NOW)
    assert (
        app.execute("select count(*) from rain_fcst").fetchone()[0] == 64
    )  # same issue: no new rows


def test_a_zone_that_fails_does_not_undo_the_zones_before_it(app):
    add_zone(app)
    points = [(1, 13.0, 77.6), (99, 13.0, 77.6)]  # zone 99 does not exist: foreign key
    http = FakeHttp(
        {"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=13.0000&lon=77.6000": BLR}
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        metno.ingest(app, http, points=points, now=NOW)
    counts = app.execute("select zone_id, count(*) from rain_fcst group by 1").fetchall()
    assert counts == [(1, 64)]  # committed per zone, and zone 99 left nothing behind

    code = common.run(
        app, "metno", lambda c: metno.ingest(c, http, points=points, now=NOW), clock=lambda: NOW
    )
    assert code == 1
    error = app.execute("select last_error from source_health where source = 'metno'").fetchone()[0]
    assert "ForeignKeyViolation" in error


def test_a_second_process_cannot_run_the_same_adapter(app, db):
    key = zlib.crc32(b"floodroute.ingest.sachet")
    db.execute("select pg_advisory_lock(%s)", (key,))  # another session holds the lock
    called = []
    assert common.run(app, "sachet", lambda c: called.append(1) or common.Outcome({}, 1)) == 0
    assert called == [] and db.execute("select count(*) from source_health").fetchone()[0] == 0
    assert (
        common.run(app, "metno", lambda c: common.Outcome({}, 1), clock=lambda: NOW) == 0
    )  # not blocked
    db.execute("select pg_advisory_unlock(%s)", (key,))
    assert common.run(app, "sachet", lambda c: called.append(1) or common.Outcome({}, 1)) == 0
    assert called == [1]
    assert (
        app.execute(
            "select count(*) from pg_locks where locktype = 'advisory'"
            " and database = (select oid from pg_database where datname = current_database())"
        ).fetchone()[0]
        == 0
    )  # released when the run ended


@pytest.fixture
def cli_env(db_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_url)

    def use(http):
        monkeypatch.setattr(cli, "Http", lambda hosts: http)

    return use


def test_command_line_stores_alerts_and_exits_zero(cli_env, db):
    cli_env(FakeHttp(sachet_routes()))
    assert cli.main(["sachet", "--once"]) == 0
    assert (
        db.execute("select count(*) from official_alert").fetchone()[0] == 8
    )  # fits the budget of 10
    assert db.execute(
        "select last_error is null or last_error like 'warning%' from source_health"
        " where source = 'sachet'"
    ).fetchone()[0]


def test_without_once_the_command_line_loops_at_the_adapter_cadence(cli_env, db, monkeypatch):
    cli_env(FakeHttp(sachet_routes()))
    naps = []

    def stop(seconds):
        naps.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", stop)
    assert cli.main(["sachet"]) == 0
    assert (
        naps == [sachet.INTERVAL_S]
        and db.execute("select count(*) from official_alert").fetchone()[0] == 8
    )


def test_command_line_exits_one_and_says_so_in_source_health(cli_env, db, capsys):
    cli_env(FakeHttp({sachet.RSS_URL: common.HttpStatusError(403, sachet.RSS_URL)}))
    assert cli.main(["sachet", "--once"]) == 1
    last_ok, error = db.execute(
        "select last_ok, last_error from source_health where source = 'sachet'"
    ).fetchone()
    assert last_ok is None and "failed: HttpStatusError: HTTP 403 from sachet.ndma.gov.in" in error
    assert "HTTP 403" in capsys.readouterr().err
