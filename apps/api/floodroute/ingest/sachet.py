"""SACHET (NDMA, built by C-DOT) CAP 1.2 alerts into official_alert, keyed by CAP identifier.

Observed on 2026-10-05 (docs/research/01 section 3 had these as unverified):
  * Feed https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml: RSS 2.0, 99 items newest
    first (about 10 h, 54 of them from Andhra Pradesh SDMA), 81 KB. The only licence text is the channel
    element <copyright>public domain</copyright>; NDMA's commercial terms are still unconfirmed. The
    channel pubDate is stale (15 Sep), so freshness is taken from the items.
  * State feeds rss_<state>.xml exist for karnataka, kerala, maharashtra, uttarakhand (lowercase, 10
    items each). Multi-word names did not resolve (tamilnadu, tamil_nadu, tamil-nadu, andhra_pradesh,
    andhra-pradesh, andhrapradesh, west-bengal all 404). The national feed is a superset of them inside
    its window, so only the national feed is polled.
  * An item links to .../FetchXMLFile?identifier=<guid>: a CAP 1.2 alert of 2 to 4 KB with one <info>
    per language (en-IN plus HI, KN, ML, MR, TL for Telugu, BN, in any order). LGD district codes come
    as geocodes (not for CWC). There is no inline <polygon>: each <info> carries the parameter "Polygon
    URL" (.../FetchPolygonXMLFile?identifier=<guid>), a non-CAP <alert> holding one <polygon> per
    district as "lat,lon lat,lon ..." (725 B to 204 KB, one ring of 4641 points, rings can repeat).
    Both documents are fetched. Inline <polygon> and <circle> are parsed as well. For CWC the CAP
    <altitude>,<ceiling> look like the gauge's lat,lon (26.33, 85.85 is the centre of its polygon); unused.
  * After its first three answers the polygon endpoint returned HTTP 403 to every request from this
    sandbox for 40+ minutes (11 of 11), while the feed and the CAP files stayed 200 and a changed
    User-Agent or Referer did not help. Cause unknown (rate rule or access rule): ask NDMA or C-DOT.
  * A guid can be reissued with a new pubDate and a new CAP identifier (the Update references the old
    one), so an item counts as already ingested only if guid AND pubDate match (raw.rss_key).

What is stored. cap_id, sender, event, severity, certainty, onset, expires and area come from the alert;
raw keeps the verbatim CAP text (cap_xml), every <info> in every language (raw.cap.infos, with the
geocodes), references, msgType, status and the RSS fields. Across <info> blocks the row takes the first
English event, the worst severity, the most certain certainty, the earliest onset (falling back to
effective, then sent) and the latest expires. Rows are not superseded: readers must honour
raw.cap.msgType and raw.cap.references. A status other than Actual (Test, Exercise, Draft, System) is
stored with severity NULL so it can never escalate anything. A row whose expires is NULL states no
expiry. Alert text is untrusted: escape it on output.

Untrusted input: bodies are size capped before parsing; non UTF-8, NUL bytes and any DOCTYPE are
refused before the parser sees them (so no entity can expand), and the TreeBuilder hook refuses DOCTYPE
again. The standard library parser is enough, no defusedxml. URLs are built here or checked against
the one SACHET host and path, never followed blindly. Every coordinate must be finite and inside the
India box (this is what catches swapped lat,lon). Enumerations, timestamps (they must carry an offset)
and counts are validated; an alert valid for more than 31 days is refused.

Outcomes per item: stored; refused (hostile or malformed content: counted, the run continues, last_error
carries a warning); or a fetch failure after retries, which fails the run (items already stored stay).
A run in which at least SYSTEMIC_REJECTS items were refused and none stored also fails: that is a
format change or an attack, not one bad item. A polygon that cannot be had never loses the alert: the
row is stored with area NULL and raw.area_error, and the warning counts active alerts without an area.
Once the polygon endpoint answers with an error status it is not asked again in the same run.

ponytail: a refused item has no memory, so it is fetched again each run until it leaves the feed
(about 10 h); add a reject table if that noise matters. The seen check scans raw->>'rss_key' limited by
onset; add a column and index when official_alert is large. A polygon that failed is not retried
(area stays NULL; raw.cap keeps the LGD district codes); add a polygon-only repair pass if polygons
turn out to matter more than the district codes. Circles become 32 sided polygons approximated per
latitude: good for footprints, not for geodesy.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb

from floodroute.ingest.common import (
    HttpStatusError,
    IngestError,
    Outcome,
    Rejected,
    in_india,
    utcnow,
)

SOURCE = "sachet"
INTERVAL_S = 60
HOST = "sachet.ndma.gov.in"
HOSTS = {HOST}
BASE = f"https://{HOST}/cap_public_website/"
RSS_URL = BASE + "rss/rss_india.xml"
CAP_URL = BASE + "FetchXMLFile?identifier={}"
POLYGON_PATH = "/cap_public_website/FetchPolygonXMLFile"
NS = "{urn:oasis:names:tc:emergency:cap:1.2}"

MAX_RSS = 1 << 20  # seen: 81 KB
MAX_CAP = 128 << 10  # seen: at most 4 KB
MAX_POLYGONS = 4 << 20  # seen: at most 204 KB
MAX_ITEMS = 200  # newest items considered per run (feed holds about 100)
MAX_NEW_PER_RUN = 10  # new items fetched per run: 2 requests each, so a cold start takes a few runs
MAX_INFOS, MAX_AREAS, MAX_GEOCODES, MAX_PARAMS, MAX_REFERENCES = 32, 256, 1024, 64, 256
MAX_RINGS, MAX_POINTS, MAX_POLYGON_URLS = 512, 300_000, 4
MAX_VALIDITY = timedelta(days=31)
SEEN_WINDOW = timedelta(days=3)  # only recent rows are scanned for the seen check
SYSTEMIC_REJECTS = 3
EARTH_KM = 6371.0088

GUID = re.compile(r"\d{10,20}")
IDENT = re.compile(r"[^\s,<&]{1,128}")  # CAP: no spaces, commas or the characters < and &
POLYGON_QUERY = re.compile(r"identifier=\d{10,20}")

SEVERITY = ("Extreme", "Severe", "Moderate", "Minor", "Unknown")  # worst first
CERTAINTY = ("Observed", "Likely", "Possible", "Unlikely", "Unknown")  # most certain first
STATUS = ("Actual", "Exercise", "System", "Test", "Draft")
MSG_TYPE = ("Alert", "Update", "Cancel", "Ack", "Error")
SCOPE = ("Public", "Restricted", "Private")

Ring = list[tuple[float, float]]  # (lon, lat), closed


class _NoDoctype(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise Rejected("DOCTYPE is not allowed")


def parse_xml(data: bytes, max_bytes: int) -> ET.Element:
    """Parse untrusted XML. Rejects (Rejected) anything oversized, undecodable, DOCTYPE or malformed."""
    if len(data) > max_bytes:
        raise Rejected(f"document over {max_bytes} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Rejected("document is not UTF-8") from None
    if "\x00" in text or "<!doctype" in text.lower():
        raise Rejected("NUL byte or DOCTYPE in document")
    parser = ET.XMLParser(target=_NoDoctype())
    try:
        parser.feed(text)  # str, so a declared encoding cannot change what was checked above
        return parser.close()
    except ET.ParseError as e:
        raise Rejected(f"malformed XML: {e}") from None


@dataclass(frozen=True)
class RssItem:
    guid: str
    pub: datetime
    author: str | None

    @property
    def key(self) -> str:
        return f"{self.guid}@{self.pub:%Y%m%dT%H%M%SZ}"


def parse_rss(data: bytes) -> tuple[list[RssItem], int]:
    """Items (newest guid occurrence only) and the number of items skipped as malformed."""
    root = parse_xml(data, MAX_RSS)
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise Rejected("not an RSS 2.0 feed")
    items: dict[str, RssItem] = {}
    bad = 0
    for el in channel.findall("item")[:2000]:
        guid = (el.findtext("guid") or "").strip()
        try:
            pub = parsedate_to_datetime((el.findtext("pubDate") or "").strip())
        except (TypeError, ValueError):
            pub = None
        if not GUID.fullmatch(guid) or pub is None:
            bad += 1
            continue
        pub = (pub if pub.tzinfo else pub.replace(tzinfo=UTC)).astimezone(UTC)
        author = " ".join((el.findtext("author") or "").split())[:200] or None
        if guid not in items or items[guid].pub < pub:
            items[guid] = RssItem(guid, pub, author)
    return list(items.values()), bad


def _t(el: ET.Element, name: str, limit: int = 4096) -> str | None:
    child = el.find(NS + name)
    if child is None:
        return None
    if len(child):
        raise Rejected(f"{name} has child elements, expected a scalar")
    if (child.tail or "").strip():
        raise Rejected(f"{name} has trailing text after a child element")
    text = (child.text or "").strip()
    if len(text) > limit:
        raise Rejected(f"{name} longer than {limit} characters")
    return text or None


def _limit(items: list, n: int, what: str) -> list:
    if len(items) > n:
        raise Rejected(f"more than {n} {what}")
    return items


def _enum(value: str | None, allowed: tuple[str, ...], field: str) -> str:
    for ok in allowed:
        if value is not None and value.lower() == ok.lower():
            return ok
    raise Rejected(f"{field} {value!r} is not one of {allowed}")


def _dt(value: str | None, field: str, required: bool = False) -> datetime | None:
    if value is None:
        if required:
            raise Rejected(f"{field} missing")
        return None
    try:
        out = datetime.fromisoformat(value)
    except ValueError:
        raise Rejected(f"{field} {value!r} is not an ISO 8601 time") from None
    if out.tzinfo is None:
        raise Rejected(f"{field} {value!r} has no UTC offset")
    return out.astimezone(UTC)


def _closed(ring: Ring) -> Ring:
    """Close the ring if needed and refuse one that is a point or a line (no extent at all)."""
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    if len(ring) < 4:
        raise Rejected("ring has fewer than 3 distinct points")
    x0, y0 = ring[0]
    dx, dy = next(((x - x0, y - y0) for x, y in ring if (x, y) != (x0, y0)), (0.0, 0.0))
    if all(abs(dx * (y - y0) - dy * (x - x0)) < 1e-12 for x, y in ring):
        raise Rejected("ring has no area (all points on one line)")
    return ring  # self-intersections are left to ST_MakeValid


def ring_from_text(text: str) -> Ring:
    """'lat,lon lat,lon ...' as CAP and SACHET write it, to a closed ring of (lon, lat)."""
    ring: Ring = []
    for pair in text.split():
        try:
            lat_s, lon_s = pair.split(",")
            lat, lon = float(lat_s), float(lon_s)
        except ValueError:
            raise Rejected(f"bad coordinate pair {pair[:30]!r}") from None
        if not in_india(lat, lon):
            raise Rejected(f"coordinate {lat},{lon} outside India (swapped lat,lon?)")
        ring.append((lon, lat))
        if len(ring) > MAX_POINTS:
            raise Rejected("ring too long")
    return _closed(ring)


def ring_from_circle(text: str) -> Ring:
    """CAP circle 'lat,lon radius_km' as a 32 sided polygon."""
    try:
        centre, radius_s = text.split()
        lat_s, lon_s = centre.split(",")
        lat, lon, radius = float(lat_s), float(lon_s), float(radius_s)
    except ValueError:
        raise Rejected(f"bad circle {text[:40]!r}") from None
    if not in_india(lat, lon) or not 0 < radius <= 1000:
        raise Rejected(f"circle {text[:40]!r} outside India or radius not in (0, 1000] km")
    d = math.degrees(radius / EARTH_KM)
    ring = []
    for i in range(32):
        a = 2 * math.pi * i / 32
        ring.append((lon + d * math.sin(a) / math.cos(math.radians(lat)), lat + d * math.cos(a)))
    return [*ring, ring[0]]


def parse_polygon_doc(data: bytes, identifier: str) -> tuple[list[Ring], list[str]]:
    """SACHET's FetchPolygonXMLFile: <alert><identifier/><polygon>lat,lon ...</polygon>...</alert>."""
    root = parse_xml(data, MAX_POLYGONS)
    if root.tag != "alert" or (root.findtext("identifier") or "").strip() != identifier:
        raise Rejected("polygon document is not for this alert")
    polygons = _limit(root.findall("polygon"), MAX_RINGS, "polygons")
    if not polygons:
        raise Rejected("polygon document has no polygon")
    rings, errors = [], []
    for el in polygons:
        try:
            rings.append(ring_from_text(el.text or ""))
        except Rejected as e:
            errors.append(str(e))
    return rings, errors


def to_wkt(rings: list[Ring]) -> str | None:
    """WKT MULTIPOLYGON, lon lat order, identical rings dropped. None when there is no ring."""
    unique = list(dict.fromkeys(tuple(r) for r in rings))
    if sum(len(r) for r in unique) > MAX_POINTS:
        raise Rejected(f"more than {MAX_POINTS} vertices")
    if not unique:
        return None
    body = ",".join("((" + ",".join(f"{x!r} {y!r}" for x, y in r) + "))" for r in unique)
    return f"MULTIPOLYGON({body})"


def _polygon_url(value: str | None) -> str | None:
    parts = urlsplit(value or "")
    ok = parts.scheme == "https" and parts.hostname == HOST and parts.path == POLYGON_PATH
    return value if ok and POLYGON_QUERY.fullmatch(parts.query) else None


@dataclass
class Alert:
    identifier: str
    sender: str
    sent: datetime
    status: str
    msg_type: str
    scope: str
    references: list[dict]
    infos: list[dict]
    event: str | None
    severity: str | None
    certainty: str | None
    onset: datetime | None
    expires: datetime | None
    rings: list[Ring]
    polygon_urls: list[str]
    area_errors: list[str]

    def to_json(self) -> dict:
        return {
            "identifier": self.identifier,
            "sender": self.sender,
            "sent": self.sent.isoformat(),
            "status": self.status,
            "msgType": self.msg_type,
            "scope": self.scope,
            "references": self.references,
            "infos": self.infos,
        }


def _references(text: str | None) -> list[dict]:
    """CAP references: space separated 'sender,identifier,sent' triples."""
    out = []
    for token in _limit((text or "").split(), MAX_REFERENCES, "references"):
        parts = token.split(",")
        out.append(
            dict(zip(("sender", "identifier", "sent"), parts, strict=True))
            if len(parts) == 3
            else {"raw": token[:300]}
        )
    return out


def parse_cap(data: bytes) -> Alert:
    root = parse_xml(data, MAX_CAP)
    if root.tag != NS + "alert":
        raise Rejected("not a CAP 1.2 alert")
    identifier = _t(root, "identifier", 128) or ""
    if not IDENT.fullmatch(identifier):
        raise Rejected(f"bad CAP identifier {identifier[:40]!r}")
    sender = _t(root, "sender", 256)
    if not sender:
        raise Rejected("sender missing")
    sent = _dt(_t(root, "sent"), "sent", required=True)
    status = _enum(_t(root, "status"), STATUS, "status")
    msg_type = _enum(_t(root, "msgType"), MSG_TYPE, "msgType")
    scope = _enum(_t(root, "scope"), SCOPE, "scope")
    infos, rings, urls, errors = [], [], [], []
    stamps = []  # (language, event, severity, certainty, onset, expires) per info
    for el in _limit(root.findall(NS + "info"), MAX_INFOS, "info blocks"):
        language = _t(el, "language", 35)
        severity = _enum(_t(el, "severity"), SEVERITY, "severity")
        certainty = _enum(_t(el, "certainty"), CERTAINTY, "certainty")
        event = _t(el, "event", 256)
        if not event:
            raise Rejected("event missing")
        effective = _dt(_t(el, "effective"), "effective")
        onset = _dt(_t(el, "onset"), "onset") or effective or sent
        expires = _dt(_t(el, "expires"), "expires")
        if expires and expires - sent > MAX_VALIDITY:
            raise Rejected(f"expires {expires:%Y-%m-%d} is more than 31 days after sent")
        areas = []
        for a in _limit(el.findall(NS + "area"), MAX_AREAS, "areas"):
            geocodes = [
                {"name": _t(g, "valueName", 256), "value": _t(g, "value", 256)}
                for g in _limit(a.findall(NS + "geocode"), MAX_GEOCODES, "geocodes")
            ]
            areas.append({"areaDesc": _t(a, "areaDesc"), "geocodes": geocodes})
            for tag, parse in (("polygon", ring_from_text), ("circle", ring_from_circle)):
                for shape in a.findall(NS + tag):
                    try:
                        rings.append(parse((shape.text or "").strip()))
                    except Rejected as e:
                        errors.append(f"inline {tag}: {e}")
        params = []
        for p in _limit(el.findall(NS + "parameter"), MAX_PARAMS, "parameters"):
            name, value = _t(p, "valueName", 256), _t(p, "value", 2048)
            params.append({"name": name, "value": value})
            if name == "Polygon URL":
                if _polygon_url(value) is None:
                    errors.append("untrusted Polygon URL ignored")
                elif value not in urls:
                    urls.append(value)
        stamps.append((language, event, severity, certainty, onset, expires))
        infos.append(
            {
                "language": language,
                "categories": [(c.text or "").strip() for c in el.findall(NS + "category")][:16],
                "event": event,
                "urgency": _t(el, "urgency", 32),
                "severity": severity,
                "certainty": certainty,
                "effective": effective.isoformat() if effective else None,
                "onset": onset.isoformat(),
                "expires": expires.isoformat() if expires else None,
                "headline": _t(el, "headline", 4096),
                "description": _t(el, "description", 1 << 16),
                "instruction": _t(el, "instruction", 1 << 16),
                "areas": areas,
                "parameters": params,
            }
        )
    if msg_type in ("Alert", "Update") and not stamps:
        raise Rejected(f"{msg_type} without an info block")
    alert = Alert(
        identifier=identifier,
        sender=sender,
        sent=sent,
        status=status,
        msg_type=msg_type,
        scope=scope,
        references=_references(_t(root, "references", 1 << 16)),
        infos=infos,
        event=None,
        severity=None,
        certainty=None,
        onset=None,
        expires=None,
        rings=rings,
        polygon_urls=urls[:MAX_POLYGON_URLS],
        area_errors=errors,
    )
    if stamps:
        english = next((s for s in stamps if (s[0] or "").lower().startswith("en")), stamps[0])
        expiries = [s[5] for s in stamps if s[5]]
        alert.event = english[1]
        alert.severity = min((s[2] for s in stamps), key=SEVERITY.index)
        alert.certainty = min((s[3] for s in stamps), key=CERTAINTY.index)
        alert.onset = min(s[4] for s in stamps)
        alert.expires = max(expiries) if expiries else None
    return alert


UPSERT_SQL = """
insert into official_alert (cap_id, sender, event, severity, certainty, onset, expires, area, raw)
values (%s, %s, %s, %s, %s, %s, %s,
        ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromText(%s::text, 4326)), 3)), %s)
on conflict (cap_id) do update set
  sender = excluded.sender, event = excluded.event, severity = excluded.severity,
  certainty = excluded.certainty, onset = excluded.onset, expires = excluded.expires,
  area = excluded.area, raw = excluded.raw
"""
NO_AREA_SQL = """
select count(*) from official_alert
where (expires is null or expires > %s) and area is null
  and raw->'cap'->>'status' = 'Actual' and raw->'cap'->>'msgType' in ('Alert', 'Update')
"""
SEEN_SQL = """
select raw->>'rss_key' from official_alert
where raw->>'rss_key' = any(%s)
"""


def build_row(alert: Alert, item: RssItem, xml: str, rings: list[Ring], errors: list[str]) -> tuple:
    """Parameters for UPSERT_SQL. Pure, so the same input always yields the same row."""
    try:
        wkt = to_wkt(rings)
    except Rejected as e:
        wkt, errors = None, [*errors, str(e)]
    raw = {
        "rss_key": item.key,
        "rss": {"guid": item.guid, "pub": item.pub.isoformat(), "author": item.author},
        "area_error": "; ".join(errors)[:2000] or None,
        "cap": alert.to_json(),
        "cap_xml": xml,
    }
    severity = alert.severity if alert.status == "Actual" else None
    return (
        alert.identifier,
        alert.sender,
        alert.event,
        severity,
        alert.certainty,
        alert.onset,
        alert.expires,
        wkt,
        Jsonb(raw),
    )


def _polygons(http, alert: Alert, blocked: list[str]) -> tuple[list[Ring], list[str]]:
    """Rings for an alert. Once the polygon endpoint answers with an error status (it returned 403 to
    every request after the first three, while the feed and the CAP files stayed 200) it is not asked
    again in this run: the alert is kept without area and says why in raw.area_error."""
    rings, errors = list(alert.rings), list(alert.area_errors)
    for url in alert.polygon_urls:
        if blocked:
            errors.append(f"polygon fetch skipped after {blocked[0]}")
            continue
        try:
            more, bad = parse_polygon_doc(http.get(url, MAX_POLYGONS), alert.identifier)
        except (
            HttpStatusError
        ) as e:  # the host answered, so keep the alert and say the area is missing
            errors.append(f"polygon fetch: {e}")
            if e.status not in (404, 410):
                blocked.append(str(e))
        except Rejected as e:
            errors.append(f"polygon: {e}")
        else:
            rings += more
            errors += bad
    return rings, errors


def ingest(conn, http, *, now: datetime | None = None, max_new: int = MAX_NEW_PER_RUN) -> Outcome:
    now = now or utcnow()
    items, bad = parse_rss(http.get(RSS_URL, MAX_RSS))
    if not items:
        raise IngestError("feed has no usable items")
    items.sort(key=lambda i: i.pub, reverse=True)
    feed_total = len(items)
    items = items[:MAX_ITEMS]
    keys = [i.key for i in items]
    seen = {r[0] for r in conn.execute(SEEN_SQL, (keys,)).fetchall()}
    todo = [i for i in items if i.key not in seen]
    stored = no_area = 0
    refused: list[str] = []
    blocked: list[str] = []
    for item in todo[:max_new]:
        try:
            try:
                data = http.get(CAP_URL.format(item.guid), MAX_CAP)
            except HttpStatusError as e:
                if e.status not in (404, 410):
                    raise
                raise Rejected(f"CAP gone ({e})") from e
            alert = parse_cap(data)
            rings, errors = _polygons(http, alert, blocked)
            conn.execute(UPSERT_SQL, build_row(alert, item, data.decode("utf-8"), rings, errors))
            stored += 1
            no_area += bool(errors)
        except Rejected as e:
            refused.append(f"{item.guid}: {e}")
    if not stored and len(refused) >= SYSTEMIC_REJECTS:
        raise IngestError(
            f"{len(refused)} new items refused, none stored: {'; '.join(refused[:3])}"
        )
    notes = []
    if refused:
        notes.append(f"{len(refused)} item(s) refused: " + "; ".join(refused[:3]))
    if bad:
        notes.append(f"{bad} RSS item(s) skipped as malformed")
    if feed_total > MAX_ITEMS:
        notes.append(f"considering newest {MAX_ITEMS} of {feed_total} feed items")
    if items[0].pub > now + timedelta(minutes=5):
        notes.append(f"newest item pubDate {items[0].pub:%Y-%m-%dT%H:%MZ} is in the future")
    active_without_area = conn.execute(NO_AREA_SQL, (now,)).fetchone()[0]
    if active_without_area:  # stable across quiet runs: it is about the table, not this run
        notes.append(
            f"{active_without_area} active alert(s) have no area (raw.area_error says why; "
            "raw.cap keeps the LGD district codes)"
        )
    if len(todo) > max_new:
        notes.append(f"catching up, {len(todo) - max_new} new item(s) wait for the next run")
    lag = max(0, int((now - items[0].pub).total_seconds()))
    summary = {
        "items": len(items),
        "new": len(todo),
        "stored": stored,
        "refused": len(refused),
        "stored_without_area": no_area,
        "bad_rss_items": bad,
    }
    return Outcome(summary, lag, "; ".join(notes) or None)
