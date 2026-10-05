"""Shared fakes for the ingest tests: no network, and no database unless a test asks for one.

Fixtures under fixtures/sachet are real SACHET responses fetched on 2026-10-05, one request per second
(the RSS file keeps 8 of the 99 items and the real channel header; the polygon files are whole). The feed
carries `<copyright>public domain</copyright>`. fixtures/metno holds one real Locationforecast response.
"""

# Keyword dict(...) reads better than literals in these tables.
# ruff: noqa: C408

import contextlib
from datetime import UTC, datetime
from pathlib import Path

from floodroute.ingest import common, metno, sachet
from floodroute.ingest.common import HttpStatusError, TooLarge

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 5, 20, 30, tzinfo=UTC)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def norm(sql: str) -> str:
    return " ".join(sql.split())


class Cur:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def executemany(self, sql, rows):
        for row in rows:
            self.conn.execute(sql, row)


class FakeConn:
    """Records statements and applies the three upserts the adapters use, keyed like the real tables."""

    autocommit = True

    def __init__(self):
        self.alerts: dict[str, tuple] = {}
        self.rain: dict[tuple, tuple] = {}
        self.health: dict[str, dict] = {}
        self.calls: list[tuple[str, tuple]] = []
        self.lock_free = True
        self.fail_on: str | None = None
        self.zones: list[tuple] = []

    def transaction(self):
        return contextlib.nullcontext()

    def cursor(self):
        cur = Cur()
        cur.conn = self
        return cur

    def execute(self, sql, params=()):
        s, params = norm(sql), tuple(params)
        self.calls.append((s, params))
        if self.fail_on and self.fail_on in s:
            raise RuntimeError(f"simulated database failure on {self.fail_on!r}")
        if s.startswith("select pg_try_advisory_lock"):
            return Cur([(self.lock_free,)])
        if s.startswith("select pg_advisory_unlock"):
            return Cur([(True,)])
        if s == norm(sachet.SEEN_SQL):
            keys = set(params[1])
            return Cur((a[-1].obj["rss_key"],) for a in self.alerts.values()
                       if a[-1].obj["rss_key"] in keys)
        if s == norm(metno.POINTS_SQL):
            return Cur(self.zones)
        if s.startswith("insert into official_alert"):
            self.alerts[params[0]] = params
        elif s.startswith("insert into rain_fcst"):
            self.rain[params[:4]] = params
        elif s == norm(common.OK_SQL):
            source, last_ok, err, lag = params
            self.health[source] = {"last_ok": last_ok, "last_error": err, "lag_s": lag}
        elif s == norm(common.FAIL_SQL):
            source, err = params
            row = self.health.setdefault(source, {"last_ok": None, "last_error": None, "lag_s": None})
            row.update(last_error=err, lag_s=None)
        else:
            raise AssertionError(f"FakeConn does not know {s!r}")
        return Cur()


class FakeHttp:
    """Stands in for common.Http: routes maps url to bytes or to an exception to raise."""

    def __init__(self, routes: dict):
        self.routes = dict(routes)
        self.calls: list[str] = []

    def get(self, url: str, max_bytes: int) -> bytes:
        self.calls.append(url)
        result = self.routes[url]
        if isinstance(result, Exception):
            raise result
        if len(result) > max_bytes:
            raise TooLarge(f"body over {max_bytes} bytes")
        return result

    def close(self):
        pass


GUIDS = {  # fixture file -> RSS guid
    "cap_karnataka_en.xml": "1791229078945019",
    "cap_uttarakhand_en_hi.xml": "1791229518905009",
    "cap_andhra_en_te.xml": "1791227005191008",
    "cap_cwc_flood_en.xml": "1791205725481016",
    "cap_maharashtra_en_mr.xml": "1791207808206029",
    "cap_kerala_ml_en.xml": "1791201232335006",
    "cap_karnataka_en_kn.xml": "1791194123192019",
    "cap_westbengal_en_bn.xml": "1791204453036017",
}
POLYGON_FILES = {
    "1791205725481016": "sachet/polygon_cwc_circle.xml",
    "1791229518905009": "sachet/polygon_uttarakhand.xml",
}


def polygon_url(guid: str) -> str:
    return f"{sachet.BASE}FetchPolygonXMLFile?identifier={guid}"


def sachet_routes(rss: bytes | None = None, polygons: dict | None = None) -> dict:
    """RSS, every CAP fixture, and polygon documents (404 where there is no fixture)."""
    routes = {sachet.RSS_URL: rss or fixture("sachet/rss_india_subset.xml")}
    for name, guid in GUIDS.items():
        routes[sachet.CAP_URL.format(guid)] = fixture(f"sachet/{name}")
        routes[polygon_url(guid)] = HttpStatusError(404, polygon_url(guid))
    for guid, name in POLYGON_FILES.items():
        routes[polygon_url(guid)] = fixture(name)
    routes.update(polygons or {})
    return routes


def cap_xml(*, infos=None, identifier="IN-1_1", sender="Test-SDMA", sent="2026-10-05T18:00:00+05:30",
            status="Actual", msg_type="Alert", scope="Public", references=None) -> bytes:
    """A small CAP 1.2 alert. A None value drops the element; `area` and `extra` are raw XML."""
    base = dict(
        language="en-IN", category="Met", event="Heavy Rain", urgency="Expected", severity="Severe",
        certainty="Likely", effective="2026-10-05T18:00:00+05:30", onset="2026-10-05T18:10:00+05:30",
        expires="2026-10-05T21:00:00+05:30", headline="Heavy rain likely", description="d",
        instruction="i", area="<cap:area><cap:areaDesc>Somewhere</cap:areaDesc></cap:area>", extra="",
    )
    out = ['<cap:alert xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">']
    for tag, value in (("identifier", identifier), ("sender", sender), ("sent", sent),
                       ("status", status), ("msgType", msg_type), ("scope", scope),
                       ("references", references)):
        if value is not None:
            out.append(f"<cap:{tag}>{value}</cap:{tag}>")
    for override in [{}] if infos is None else infos:
        info = {**base, **override}
        out.append("<cap:info>")
        for tag in ("language", "category", "event", "urgency", "severity", "certainty", "effective",
                    "onset", "expires", "headline", "description", "instruction"):
            if info[tag] is not None:
                out.append(f"<cap:{tag}>{info[tag]}</cap:{tag}>")
        out.append(info["extra"] + info["area"] + "</cap:info>")
    out.append("</cap:alert>")
    return "".join(out).encode()
