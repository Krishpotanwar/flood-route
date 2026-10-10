"""SACHET adapter: the CAP parser on real fixtures, hostile input, and the ingest loop on fakes."""

# Keyword dict(...) reads better than literals in these tables.

import itertools
import math
import re
import time
from datetime import datetime

import httpx
import pytest
from ingest_testkit import (
    GUIDS,
    NOW,
    FakeConn,
    FakeHttp,
    cap_xml,
    fixture,
    polygon_url,
    sachet_routes,
)

from floodroute.ingest import common, sachet
from floodroute.ingest.common import (
    FetchError,
    Http,
    HttpStatusError,
    IngestError,
    Rejected,
    TooLarge,
)


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s)


# Expected values were read off the fixture files by hand, not produced by the parser.
REAL = {
    "cap_karnataka_en.xml": dict(
        ident="IN-1791229078945019_19",
        sender="Karnataka-SNDMC",
        msg="Update",
        langs=["en-IN"],
        event="Thunderstorm with Lightning",
        severity="Moderate",
        certainty="Possible",
        onset="2026-10-05T19:55:04+00:00",
        expires="2026-10-05T22:37:00+00:00",
        geocodes=10,
        references=[("IMD-Bengaluru", "IN-1791229078945019_51", "2026-10-06T01:07:41+05:30")],
    ),
    "cap_uttarakhand_en_hi.xml": dict(
        ident="IN-1791229518905009_9",
        sender="Uttarakhand-SDMA",
        msg="Update",
        langs=["en-IN", "HI"],
        event="Thunderstorm with Lightning",
        severity="Moderate",
        certainty="Likely",
        onset="2026-10-05T19:48:19+00:00",
        expires="2026-10-05T22:42:00+00:00",
        geocodes=0,
    ),
    "cap_andhra_en_te.xml": dict(
        ident="IN-1791227005191008_8",
        sender="Andhra-Pradesh-SDMA",
        msg="Alert",
        langs=["en-IN", "TL"],
        event="Lightning",
        severity="Severe",
        certainty="Likely",
        onset="2026-10-05T19:04:07+00:00",
        expires="2026-10-05T21:00:00+00:00",
        geocodes=0,
    ),
    "cap_cwc_flood_en.xml": dict(
        ident="IN-1791205725481016_5",
        sender="CWC",
        msg="Alert",
        langs=["en-IN"],
        event="Flood",
        severity="Severe",
        certainty="Possible",
        onset="2026-10-05T13:08:45+00:00",
        expires="2026-10-06T00:30:00+00:00",
        geocodes=0,
    ),
    "cap_maharashtra_en_mr.xml": dict(
        ident="IN-1791207808206029_29",
        sender="Maharashtra-SDMA",
        msg="Update",
        langs=["en-IN", "MR"],
        event="Low Cloud to Ground Lightning",
        severity="Moderate",
        certainty="Likely",
        onset="2026-10-05T13:47:53+00:00",
        expires="2026-10-05T16:30:00+00:00",
        geocodes=6,
    ),
    "cap_kerala_ml_en.xml": dict(  # Malayalam block first: the English event must still win
        ident="IN-1791201232335006_6",
        sender="Kerala-SDMA",
        msg="Update",
        langs=["ML", "en-IN"],
        event="Moderate Thunderstorms with surface wind",
        severity="Severe",
        certainty="Likely",
        onset="2026-10-05T11:59:59+00:00",
        expires="2026-10-05T14:30:00+00:00",
        geocodes=1,
    ),
    "cap_karnataka_en_kn.xml": dict(
        ident="IN-1791194123192019_19",
        sender="Karnataka-SNDMC",
        msg="Update",
        langs=["en-IN", "KN"],
        event="Thunder shower",
        severity="Moderate",
        certainty="Possible",
        onset="2026-10-05T10:03:13+00:00",
        expires="2026-10-05T12:54:00+00:00",
        geocodes=1,
    ),
    "cap_westbengal_en_bn.xml": dict(
        ident="IN-1791204453036017_17",
        sender="West-Bengal-SDMA",
        msg="Update",
        langs=["en-IN", "BN"],
        event="Flood",
        severity="Severe",
        certainty="Likely",
        onset="2026-10-05T13:00:08+00:00",
        expires="2026-10-07T02:30:00+00:00",
        geocodes=0,
    ),
}


@pytest.mark.parametrize("name", sorted(REAL))
def test_real_caps_parse(name):
    want = REAL[name]
    alert = sachet.parse_cap(fixture(f"sachet/{name}"))
    assert (alert.identifier, alert.sender, alert.msg_type) == (
        want["ident"],
        want["sender"],
        want["msg"],
    )
    assert alert.status == "Actual" and alert.scope == "Public"
    assert [i["language"] for i in alert.infos] == want["langs"]
    assert (alert.event, alert.severity, alert.certainty) == (
        want["event"],
        want["severity"],
        want["certainty"],
    )
    assert alert.onset == utc(want["onset"]) and alert.expires == utc(want["expires"])
    assert sum(len(a["geocodes"]) for a in alert.infos[0]["areas"]) == want["geocodes"]  # per info
    assert alert.polygon_urls == [polygon_url(GUIDS[name])]  # real CAPs carry a URL, no polygon
    assert alert.rings == [] and alert.area_errors == []
    if "references" in want:
        got = [(r["sender"], r["identifier"], r["sent"]) for r in alert.references]
        assert got == want["references"]


def test_languages_survive_verbatim():
    hindi = sachet.parse_cap(fixture("sachet/cap_uttarakhand_en_hi.xml")).infos[1]
    assert hindi["language"] == "HI"
    assert hindi["headline"].startswith("[2026/10/06 01:12] अगले 3 घंटो के दौरान")
    telugu = sachet.parse_cap(fixture("sachet/cap_andhra_en_te.xml")).infos[1]
    assert telugu["language"] == "TL"
    assert telugu["headline"].startswith("మీ ప్రాంతంలో పిడుగులు పడే అవకాశం ఉంది")


def test_polygon_documents_swap_lat_lon_and_drop_repeated_rings():
    rings, errors = sachet.parse_polygon_doc(
        fixture("sachet/polygon_cwc_circle.xml"), "IN-1791205725481016_5"
    )
    assert errors == [] and len(rings) == 1 and len(rings[0]) == 33 and rings[0][0] == rings[0][-1]
    assert rings[0][0] == (85.892431, 26.32156)  # the file says 26.32156,85.892431 (lat,lon)
    lon = sum(x for x, _ in rings[0][:-1]) / 32
    lat = sum(y for _, y in rings[0][:-1]) / 32
    assert (round(lon, 2), round(lat, 2)) == (85.85, 26.33)  # the gauge: CAP altitude, ceiling
    rings, _ = sachet.parse_polygon_doc(
        fixture("sachet/polygon_uttarakhand.xml"), "IN-1791229518905009_9"
    )
    assert len(rings) == 4  # the document repeats two of its rings
    wkt = sachet.to_wkt(rings)
    assert wkt.startswith("MULTIPOLYGON(((79.32219 28.998644,")
    assert len(re.findall(r"\)\),\(\(", wkt)) == 1  # two distinct polygons remain


def test_polygon_document_for_another_alert_is_refused():
    with pytest.raises(Rejected, match="not for this alert"):
        sachet.parse_polygon_doc(fixture("sachet/polygon_cwc_circle.xml"), "IN-1_1")


def test_swapped_polygon_is_not_accepted():
    # lon,lat order (what GeoJSON uses) written into a lat,lon field lands outside India
    with pytest.raises(Rejected, match="outside India"):
        sachet.ring_from_text("77.5,12.9 77.6,12.9 77.6,13.0 77.5,12.9")
    ring = sachet.ring_from_text("12.9,77.5 12.9,77.6 13.0,77.6")  # not closed: closed for us
    assert ring[0] == (77.5, 12.9) and ring[-1] == ring[0] and len(ring) == 4


@pytest.mark.parametrize(
    "text",
    [
        "",
        "1,2",
        "12.9,77.5 12.9,77.6",
        "12.9,77.5 13.0,77.6 13.1,77.7 12.9,77.5",
        "12.9,77.5 12.9,77.5 12.9,77.5 12.9,77.5",
        "a,b c,d e,f",
        "12.9,77.5,3 12.9,77.6 13,77.6",
        "nan,77.5 12.9,77.6 13,77.6",
        "12.9,inf 12.9,77.6 13,77.6",
    ],
)
def test_bad_rings_are_refused(text):
    with pytest.raises(Rejected):
        sachet.ring_from_text(text)


def test_inline_polygons_circles_and_several_areas():
    area = (
        "<cap:area><cap:areaDesc>A</cap:areaDesc>"
        "<cap:polygon>12.9,77.5 12.9,77.7 13.1,77.7 13.1,77.5 12.9,77.5</cap:polygon>"
        "<cap:polygon>19.0,72.8 19.0,73.0 19.2,73.0 19.0,72.8</cap:polygon></cap:area>"
        "<cap:area><cap:areaDesc>B</cap:areaDesc><cap:circle>26.33,85.85 5.0</cap:circle>"
        "<cap:polygon>1,2 3,4 5,6 1,2</cap:polygon></cap:area>"  # outside India: dropped
    )
    alert = sachet.parse_cap(cap_xml(infos=[dict(area=area)]))
    assert len(alert.rings) == 3 and len(alert.infos[0]["areas"]) == 2
    assert alert.rings[0][0] == (77.5, 12.9)
    circle = alert.rings[2]
    assert len(circle) == 33 and circle[0] == circle[-1]
    for lon, lat in circle:  # every vertex about 5 km from the centre
        dy = (lat - 26.33) * 111.195
        dx = (lon - 85.85) * 111.195 * math.cos(math.radians(26.33))
        assert math.hypot(dx, dy) == pytest.approx(5.0, rel=0.01)
    assert len(alert.area_errors) == 1 and "outside India" in alert.area_errors[0]


def test_languages_are_merged_towards_the_cautious_side():
    infos = [
        dict(
            language="HI",
            severity="Severe",
            certainty="Possible",
            event="Hindi event",
            onset="2026-10-05T18:05:00+05:30",
            expires="2026-10-05T22:00:00+05:30",
        ),
        dict(
            language="en-IN",
            severity="Minor",
            certainty="Observed",
            event="English event",
            onset="2026-10-05T18:20:00+05:30",
            expires="2026-10-05T21:00:00+05:30",
        ),
    ]
    alert = sachet.parse_cap(cap_xml(infos=infos))
    assert (alert.event, alert.severity, alert.certainty) == ("English event", "Severe", "Observed")
    assert alert.onset == utc("2026-10-05T12:35:00+00:00")  # earliest
    assert alert.expires == utc("2026-10-05T16:30:00+00:00")  # latest


def test_missing_optional_fields():
    alert = sachet.parse_cap(
        cap_xml(
            infos=[
                dict(
                    language=None,
                    onset=None,
                    effective=None,
                    expires=None,
                    description=None,
                    instruction=None,
                    headline=None,
                    urgency=None,
                    area="",
                )
            ]
        )
    )
    assert alert.onset == alert.sent == utc("2026-10-05T12:30:00+00:00")  # falls back to sent
    assert alert.expires is None and alert.infos[0]["language"] is None
    assert alert.infos[0]["areas"] == [] and alert.references == []
    alert = sachet.parse_cap(
        cap_xml(infos=[dict(onset=None, effective="2026-10-05T18:05:00+05:30")])
    )
    assert alert.onset == utc("2026-10-05T12:35:00+00:00")  # falls back to effective


def test_cancel_without_info_is_kept_and_alert_without_info_is_refused():
    cancel = sachet.parse_cap(
        cap_xml(infos=[], msg_type="Cancel", references="S,IN-1_1,2026-10-05T17:00:00+05:30")
    )
    assert (cancel.event, cancel.severity, cancel.expires) == (None, None, None)
    assert cancel.references[0]["identifier"] == "IN-1_1"
    with pytest.raises(Rejected, match="without an info block"):
        sachet.parse_cap(cap_xml(infos=[]))


def test_non_actual_messages_never_carry_a_severity():
    item = sachet.RssItem("1791229078945019", utc("2026-10-05T19:55:05+00:00"), None)
    for status in ("Test", "Exercise", "Draft", "System"):
        alert = sachet.parse_cap(cap_xml(status=status, infos=[dict(severity="Extreme")]))
        row = sachet.build_row(alert, item, "<xml/>", [], [])
        assert row[3] is None and row[2] == "Heavy Rain"
        assert row[-1].obj["cap"]["status"] == status
    actual = sachet.parse_cap(cap_xml(infos=[dict(severity="Extreme")]))
    assert sachet.build_row(actual, item, "<xml/>", [], [])[3] == "Extreme"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(infos=[dict(severity="Catastrophic")]), "severity"),
        (dict(infos=[dict(certainty="Maybe")]), "certainty"),
        (dict(infos=[dict(severity=None)]), "severity"),
        (dict(infos=[dict(event=None)]), "event missing"),
        (dict(infos=[dict(expires="2026-10-05T21:00:00")]), "no UTC offset"),
        (dict(infos=[dict(onset="yesterday")]), "ISO 8601"),
        (dict(infos=[dict(expires="2026-12-31T00:00:00+05:30")]), "31 days"),
        (dict(sent="2026-10-05"), "no UTC offset"),
        (dict(sent=None), "sent missing"),
        (dict(identifier="IN 1 1"), "identifier"),
        (dict(identifier="a,b"), "identifier"),
        (dict(sender=None), "sender missing"),
        (dict(status="Real"), "status"),
        (dict(msg_type="Delete"), "msgType"),
        (dict(scope=None), "scope"),
        (dict(infos=[{}] * 33), "info blocks"),
    ],
)
def test_invalid_alerts_are_refused(kwargs, message):
    with pytest.raises(Rejected, match=message):
        sachet.parse_cap(cap_xml(**kwargs))


def test_other_cap_versions_and_documents_are_refused():
    with pytest.raises(Rejected, match=r"not a CAP 1\.2"):
        sachet.parse_cap(cap_xml().replace(b"cap:1.2", b"cap:1.1"))
    with pytest.raises(Rejected, match=r"not a CAP 1\.2"):
        sachet.parse_cap(b"<alert><identifier>x</identifier></alert>")


def test_untrusted_polygon_urls_are_ignored():
    def alert_with(url):
        extra = (
            "<cap:parameter><cap:valueName>Polygon URL</cap:valueName>"
            f"<cap:value>{url}</cap:value></cap:parameter>"
        )
        return sachet.parse_cap(cap_xml(infos=[dict(extra=extra)]))

    good = f"{sachet.BASE}FetchPolygonXMLFile?identifier=1791229078945019"
    assert alert_with(good).polygon_urls == [good]
    host = "sachet.ndma.gov.in/cap_public_website/FetchPolygonXMLFile?identifier=1791229078945019"
    for evil in (
        "http://" + host,
        "https://evil.example/cap_public_website/FetchPolygonXMLFile?identifier=1791229078945019",
        "https://sachet.ndma.gov.in/other?identifier=1791229078945019",
        "https://" + host + "&amp;x=1",
        "file:///etc/passwd",
        "https://169.254.169.254/latest/meta-data",
    ):
        alert = alert_with(evil)
        assert alert.polygon_urls == [] and alert.area_errors == ["untrusted Polygon URL ignored"]


# ---------------------------------------------------------------- hostile XML


def _laughs() -> bytes:
    entities = [b'<!ENTITY lol "lol">']
    for i in range(1, 10):
        previous = b"&lol;" if i == 1 else b"&lol%d;" % (i - 1)
        entities.append(b'<!ENTITY lol%d "%s">' % (i, previous * 10))
    return b'<?xml version="1.0"?><!DOCTYPE lolz [' + b"".join(entities) + b"]><lolz>&lol9;</lolz>"


HOSTILE = {
    "xxe": b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>',
    "billion laughs": _laughs(),
    "quadratic blowup": b'<!DOCTYPE a [<!ENTITY x "'
    + b"A" * 50_000
    + b'">]><a>'
    + b"&x;" * 2_000
    + b"</a>",
    "external dtd": b'<!DOCTYPE a SYSTEM "http://127.0.0.1:9/x.dtd"><a/>',
    "parameter entity": b'<!DOCTYPE a [<!ENTITY % p SYSTEM "http://127.0.0.1:9/p.dtd"> %p;]><a/>',
    "lowercase doctype": b"<!doctype a><a/>",
    "doctype in utf-16": '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE a><a/>'.encode("utf-16"),
    "doctype under a latin-1 declaration": b'<?xml version="1.0" encoding="ISO-8859-1"?><!DOCTYPE a><a/>',
    "undefined entity": b"<a>&nope;</a>",
    "malformed": b"<a><b></a>",
    "empty": b"",
    "html error page": b"<html><body>Error Code: 403</body>",
    "not utf-8": b"<a>\xff\xfe</a>",
    "nul byte": b"<a>\x00</a>",
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_hostile_xml_is_refused_quickly(name):
    started = time.monotonic()
    with pytest.raises(Rejected):
        sachet.parse_xml(HOSTILE[name], 1 << 20)
    assert time.monotonic() - started < 1.0


def test_oversized_documents_are_refused_before_parsing():
    with pytest.raises(Rejected, match="over 100 bytes"):
        sachet.parse_xml(b"<a>" + b"x" * 1000 + b"</a>", 100)


def test_deep_nesting_is_harmless_under_the_size_cap():
    depth = sachet.MAX_CAP // 7  # "<a></a>" is 7 bytes per level
    assert sachet.parse_xml(b"<a>" * depth + b"</a>" * depth, sachet.MAX_CAP).tag == "a"


def test_hostile_rss_and_cap_documents_are_refused():
    with pytest.raises(Rejected):
        sachet.parse_rss(HOSTILE["xxe"])
    with pytest.raises(Rejected, match="not an RSS"):
        sachet.parse_rss(b"<feed/>")
    with pytest.raises(Rejected):
        sachet.parse_cap(HOSTILE["billion laughs"])


# ---------------------------------------------------------------- RSS


def test_rss_real_subset():
    items, bad = sachet.parse_rss(fixture("sachet/rss_india_subset.xml"))
    assert bad == 0 and len(items) == 8
    karnataka = next(i for i in items if i.guid == "1791229078945019")
    assert karnataka.pub == utc("2026-10-05T19:55:05+00:00")
    assert karnataka.key == "1791229078945019@20261005T195505Z"
    assert karnataka.author == "controlroom@ndma.gov.in (IMD Bengaluru)"


def test_rss_bad_items_are_skipped_and_counted_and_duplicates_collapse():
    def item(guid, pub):
        return f"<item><guid>{guid}</guid>{f'<pubDate>{pub}</pubDate>' if pub else ''}</item>"

    ok = "Mon, 05 Oct 2026 19:55:05 GMT"
    feed = (
        "<rss><channel>"
        + item("1791229078945019", ok)
        + item("1791229078945019", "Mon, 05 Oct 2026 19:58:00 GMT")  # reissued: newest wins
        + item("abc", ok)
        + item("1" * 30, ok)
        + item("../../etc/passwd", ok)
        + item("1791229518905009", None)
        + item("1791229518905010", "not a date")
        + "</channel></rss>"
    ).encode()
    items, bad = sachet.parse_rss(feed)
    assert [i.guid for i in items] == ["1791229078945019"] and bad == 5
    assert items[0].pub == utc("2026-10-05T19:58:00+00:00")


# ---------------------------------------------------------------- ingest loop on fakes


def run_ingest(conn, http, **kw):
    return sachet.ingest(conn, http, now=NOW, **kw)


def test_ingest_stores_every_real_alert_and_is_idempotent():
    conn, http = FakeConn(), FakeHttp(sachet_routes())
    out = run_ingest(conn, http, max_new=50)
    assert set(conn.alerts) == {r["ident"] for r in REAL.values()}
    assert out.summary == {
        "items": 8,
        "new": 8,
        "stored": 8,
        "refused": 0,
        "stored_without_area": 6,
        "bad_rss_items": 0,
    }  # 2 polygon fixtures
    snapshot, first_calls = dict(conn.alerts), len(http.calls)
    assert first_calls == 1 + 8 + 8  # feed, every CAP, every polygon URL

    again = run_ingest(conn, http, max_new=50)  # same feed again: only the feed is requested
    assert len(http.calls) == first_calls + 1 and http.calls[-1] == sachet.RSS_URL
    assert again.summary["new"] == 0 and again.summary["stored"] == 0
    assert conn.alerts == snapshot


def test_stored_row_matches_the_alert_and_the_verbatim_xml():
    conn = FakeConn()
    run_ingest(conn, FakeHttp(sachet_routes()), max_new=50)
    row = conn.alerts["IN-1791205725481016_5"]
    _, sender, event, severity, certainty, onset, expires, wkt, raw = row
    assert (sender, event, severity, certainty) == ("CWC", "Flood", "Severe", "Possible")
    assert onset == utc("2026-10-05T13:08:45+00:00") and expires == utc("2026-10-06T00:30:00+00:00")
    assert wkt.startswith("MULTIPOLYGON(((85.892431 26.32156,") and wkt.endswith("))")
    assert raw.obj["cap_xml"] == fixture("sachet/cap_cwc_flood_en.xml").decode()
    assert raw.obj["rss_key"] == "1791205725481016@20261005T130846Z"
    assert raw.obj["area_error"] is None
    assert raw.obj["cap"]["infos"][0]["description"].startswith("River Adhwara Group at Kamtaul")
    karnataka = conn.alerts["IN-1791229078945019_19"]  # no polygon fixture: kept, area NULL
    assert karnataka[7] is None and "HTTP 404" in karnataka[-1].obj["area_error"]
    assert len(karnataka[-1].obj["cap"]["infos"][0]["areas"][0]["geocodes"]) == 10


def test_a_reissued_item_is_fetched_again_and_the_old_alert_stays():
    conn = FakeConn()
    run_ingest(conn, FakeHttp(sachet_routes()), max_new=50)
    rss = fixture("sachet/rss_india_subset.xml").replace(
        b"Mon, 05 Oct 2026 19:55:05 GMT", b"Mon, 05 Oct 2026 20:10:00 GMT"
    )
    update = fixture("sachet/cap_karnataka_en.xml").replace(
        b"IN-1791229078945019_19", b"IN-1791229078945019_20"
    )
    http = FakeHttp(sachet_routes(rss=rss))
    http.routes[sachet.CAP_URL.format("1791229078945019")] = update
    out = run_ingest(conn, http, max_new=50)
    assert out.summary["new"] == 1 and out.summary["stored"] == 1
    assert {"IN-1791229078945019_19", "IN-1791229078945019_20"} <= set(conn.alerts)
    assert len(conn.alerts) == 9


def test_per_run_budget_takes_the_newest_first_and_says_it_is_catching_up():
    conn = FakeConn()
    out = run_ingest(conn, FakeHttp(sachet_routes()), max_new=3)
    assert out.summary["stored"] == 3 and "catching up, 5 new item(s)" in out.warn
    assert set(conn.alerts) == {
        "IN-1791229078945019_19",
        "IN-1791229518905009_9",
        "IN-1791227005191008_8",
    }


def test_active_alerts_without_an_area_stay_in_the_health_note_on_quiet_runs():
    conn, http = FakeConn(), FakeHttp(sachet_routes())
    first = run_ingest(conn, http, max_new=50)
    assert "3 active alert(s) have no area" in first.warn  # Karnataka, Andhra, West Bengal
    quiet = run_ingest(conn, http, max_new=50)
    assert quiet.summary["new"] == 0 and "3 active alert(s) have no area" in quiet.warn
    later = sachet.ingest(conn, http, now=utc("2026-10-07T03:00:00+00:00"), max_new=50)
    assert later.warn is None  # every alert has expired, nothing left to complain about


def test_lag_is_the_age_of_the_newest_item():
    out = run_ingest(FakeConn(), FakeHttp(sachet_routes()), max_new=50)
    assert out.lag_s == int((NOW - utc("2026-10-05T19:55:05+00:00")).total_seconds()) == 2095


def test_malformed_rss_items_reach_the_health_note():
    guid = "1791229078945019"
    feed = (
        "<rss><channel>"
        f"<item><guid>{guid}</guid><pubDate>Mon, 05 Oct 2026 19:55:05 GMT</pubDate></item>"
        "<item><guid>abc</guid><pubDate>Mon, 05 Oct 2026 19:55:05 GMT</pubDate></item>"
        f"<item><guid>{guid}</guid></item>"
        "</channel></rss>"
    ).encode()
    out = run_ingest(FakeConn(), FakeHttp(sachet_routes(rss=feed)))
    assert out.summary["bad_rss_items"] == 2
    assert "2 RSS item(s) skipped as malformed" in out.warn


def test_future_pubdate_warns_instead_of_reading_as_fresh():
    guid = "1791229078945019"
    feed = (
        "<rss><channel>"
        f"<item><guid>{guid}</guid><pubDate>Mon, 05 Oct 2026 23:00:00 GMT</pubDate></item>"
        "</channel></rss>"
    ).encode()
    out = run_ingest(FakeConn(), FakeHttp(sachet_routes(rss=feed)))
    assert out.lag_s == 0
    assert "is in the future" in out.warn


def test_seen_check_ignores_onset_so_old_alerts_are_not_refetched():
    conn, http = FakeConn(), FakeHttp(sachet_routes())
    run_ingest(conn, http, max_new=50)
    n = len(http.calls)
    out = sachet.ingest(conn, http, now=utc("2026-10-09T20:30:00+00:00"), max_new=50)
    assert out.summary["new"] == 0
    assert http.calls[n:] == [sachet.RSS_URL]


def test_scalar_fields_with_child_nodes_are_refused():
    import xml.etree.ElementTree as ET

    ns = "urn:oasis:names:tc:emergency:cap:1.2"
    el = ET.fromstring(
        f'<info xmlns="{ns}"><event>Heavy <b>rain</b>tail</event></info>'
    )
    with pytest.raises(Rejected):
        sachet._t(el, "event")


def test_truncation_past_max_items_is_logged_in_the_note():
    items = "".join(
        f"<item><guid>{1791229000000000 + i}</guid>"
        "<pubDate>Mon, 05 Oct 2026 19:00:00 GMT</pubDate></item>"
        for i in range(sachet.MAX_ITEMS + 1)
    )
    feed = f"<rss><channel>{items}</channel></rss>".encode()
    out = run_ingest(FakeConn(), FakeHttp({sachet.RSS_URL: feed}), max_new=0)
    assert out.summary["items"] == sachet.MAX_ITEMS
    assert f"considering newest {sachet.MAX_ITEMS} of {sachet.MAX_ITEMS + 1}" in out.warn


def test_hostile_items_do_not_stop_the_run():
    routes = sachet_routes()
    routes[sachet.CAP_URL.format("1791229078945019")] = HOSTILE["xxe"]
    routes[sachet.CAP_URL.format("1791229518905009")] = TooLarge("body over 131072 bytes")
    routes[sachet.CAP_URL.format("1791227005191008")] = HOSTILE["malformed"]
    routes[sachet.CAP_URL.format("1791205725481016")] = HttpStatusError(404, sachet.RSS_URL)
    conn = FakeConn()
    out = run_ingest(conn, FakeHttp(routes), max_new=50)
    assert out.summary["stored"] == 4 and out.summary["refused"] == 4
    assert "4 item(s) refused" in out.warn and "DOCTYPE" in out.warn
    assert len(conn.alerts) == 4


def test_a_run_where_everything_new_is_refused_fails():
    routes = sachet_routes()
    for guid in GUIDS.values():
        routes[sachet.CAP_URL.format(guid)] = HOSTILE["malformed"]
    conn = FakeConn()
    with pytest.raises(IngestError, match="8 new items refused, none stored"):
        run_ingest(conn, FakeHttp(routes), max_new=50)
    assert conn.alerts == {}


def test_two_refused_items_are_a_warning_not_a_failure():
    conn = FakeConn()
    run_ingest(conn, FakeHttp(sachet_routes()), max_new=50)  # everything stored
    rss = (
        fixture("sachet/rss_india_subset.xml")
        .replace(b"Mon, 05 Oct 2026 19:55:05 GMT", b"Mon, 05 Oct 2026 20:11:00 GMT")
        .replace(b"Mon, 05 Oct 2026 19:48:21 GMT", b"Mon, 05 Oct 2026 20:12:00 GMT")
    )
    routes = sachet_routes(rss=rss)
    routes[sachet.CAP_URL.format("1791229078945019")] = HOSTILE["xxe"]
    routes[sachet.CAP_URL.format("1791229518905009")] = HOSTILE["malformed"]
    out = run_ingest(conn, FakeHttp(routes), max_new=50)
    assert out.summary["refused"] == 2 and out.warn.startswith("2 item(s) refused")


def test_a_fetch_failure_stops_the_run_and_keeps_earlier_items():
    routes = sachet_routes()
    third_newest = sachet.CAP_URL.format("1791227005191008")
    routes[third_newest] = FetchError("ConnectError: reset by peer")
    conn = FakeConn()
    with pytest.raises(FetchError):
        run_ingest(conn, FakeHttp(routes), max_new=50)
    assert set(conn.alerts) == {"IN-1791229078945019_19", "IN-1791229518905009_9"}
    routes[third_newest] = fixture("sachet/cap_andhra_en_te.xml")
    out = run_ingest(conn, FakeHttp(routes), max_new=50)  # the next run picks up the rest
    assert out.summary["new"] == 6 and len(conn.alerts) == 8


def test_http_error_on_the_feed_or_a_cap_fails_the_run():
    for url in (sachet.RSS_URL, sachet.CAP_URL.format("1791229078945019")):
        routes = sachet_routes()
        routes[url] = HttpStatusError(403, url)
        with pytest.raises(HttpStatusError, match="403"):
            run_ingest(FakeConn(), FakeHttp(routes), max_new=50)


def test_polygon_endpoint_that_starts_refusing_is_asked_once_per_run():
    routes = sachet_routes()
    for guid in GUIDS.values():
        routes[polygon_url(guid)] = HttpStatusError(403, polygon_url(guid))
    conn, http = FakeConn(), FakeHttp(routes)
    out = run_ingest(conn, http, max_new=50)
    assert sum("FetchPolygon" in u for u in http.calls) == 1
    assert out.summary["stored"] == 8 and out.summary["stored_without_area"] == 8
    assert "5 active alert(s) have no area" in out.warn  # 3 of the 8 had already expired
    assert all(a[7] is None for a in conn.alerts.values())
    errors = [a[-1].obj["area_error"] for a in conn.alerts.values()]
    assert sum("HTTP 403" in e and "skipped" not in e for e in errors) == 1
    assert sum("skipped after HTTP 403" in e for e in errors) == 7


def test_empty_or_unusable_feed_fails():
    empty = b"<rss><channel><title>x</title></channel></rss>"
    with pytest.raises(IngestError, match="no usable items"):
        run_ingest(FakeConn(), FakeHttp({sachet.RSS_URL: empty}))
    with pytest.raises(Rejected):
        run_ingest(FakeConn(), FakeHttp({sachet.RSS_URL: HOSTILE["xxe"]}))


def test_a_polygon_for_the_wrong_alert_or_with_swapped_coordinates_leaves_the_area_empty():
    swapped = (
        b"<alert><identifier>IN-1791205725481016_5</identifier>"
        b"<polygon>85.89,26.32 85.80,26.32 85.80,26.40 85.89,26.32</polygon></alert>"
    )
    wrong = fixture("sachet/polygon_uttarakhand.xml")
    for body, reason in ((swapped, "outside India"), (wrong, "not for this alert")):
        conn = FakeConn()
        routes = sachet_routes(polygons={polygon_url("1791205725481016"): body})
        run_ingest(conn, FakeHttp(routes), max_new=50)
        row = conn.alerts["IN-1791205725481016_5"]
        assert row[7] is None and reason in row[-1].obj["area_error"]


def test_rate_limit_holds_across_feed_cap_and_polygon_requests():
    clock, stamps, routes = [0.0], [], sachet_routes()

    def handler(request: httpx.Request) -> httpx.Response:
        stamps.append(clock[0])
        body = routes[str(request.url)]
        if isinstance(body, Exception):
            return httpx.Response(404)
        clock[0] += 0.2  # a fast server: pacing, not latency, has to create the gaps
        return httpx.Response(200, content=body)

    http = Http(
        sachet.HOSTS,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        clock=lambda: clock[0],
    )
    sachet.ingest(FakeConn(), http, now=NOW, max_new=3)
    assert len(stamps) == 1 + 3 * 2
    assert all(b - a >= 1.0 - 1e-9 for a, b in itertools.pairwise(stamps))


def test_a_failed_run_is_recorded_and_returns_exit_code_one(capsys):
    conn = FakeConn()
    http = FakeHttp({sachet.RSS_URL: FetchError("ConnectError: reset")})
    code = common.run(conn, "sachet", lambda c: sachet.ingest(c, http, now=NOW), clock=lambda: NOW)
    health = conn.health["sachet"]
    assert code == 1
    assert health["last_error"].startswith("2026-10-05T20:30:00Z failed: FetchError")
    assert health["last_ok"] is None and health["lag_s"] is None
    assert "ConnectError" in capsys.readouterr().err
