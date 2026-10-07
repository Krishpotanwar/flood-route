"""Hourly rainfall forecast per zone point from MET Norway Locationforecast 2.0 into rain_fcst.

Source choice (all checked on 2026-10-05):
  * NOAA GFS through NOMADS OpenDAP ASCII is gone: the endpoint answers "OpenDAP format has been retired"
    (Service Change Notice 25-81, ended 2026-02-23). The replacement, the Grib Filter, returns GRIB2
    binary only (https://nomads.ncep.noaa.gov/info.php?page=opendap_grib_migration). GRIB2 is not
    readable with the standard library, so NOAA GFS waits for an accepted GRIB dependency (eccodes or
    wgrib2); GEFS would then also give a real ensemble spread. NOAA data itself is public domain.
  * The Unidata THREDDS server serves GFS as plain text but its terms say "data are provided solely for
    education and research purposes ... not guaranteed for use in operational or decision-making
    settings" and that commercial use may be blocked
    (https://www.unidata.ucar.edu/data/guidelines-data-use). Not usable.
  * Open-Meteo is not used: its free tier is non-commercial. No fallback is written; add one only
    behind an explicit dev-only environment flag with that licence caveat.
  * Chosen: MET Norway, a government agency. Terms read at https://api.met.no/doc/License and
    https://api.met.no/doc/TermsOfService: data under NLOD 2.0 and CC BY 4.0, credit "Data from MET
    Norway" (show it wherever forecast-derived numbers appear); identify the client with a User-Agent
    holding a contact URL or address (blocked without warning otherwise, so set FLOODROUTE_CONTACT in
    production); at most 20 requests per second per application; do not repeat a request before its
    Expires header (30 min seen); coordinates at most 4 decimals (5 or more get 403); HTTPS only;
    "no guarantees of delivery ... or possibilities to obtain an SLA"; 429 means throttled.
  * Model (https://docs.api.met.no/doc/locationforecast/datamodel): outside the Nordic area the source is
    ECMWF's high resolution model, about 9 km, updated 4 times a day, hourly steps for about 64 h then
    6 hourly to 9 days. The deterministic run has no ensemble, so ensemble_spread is always NULL.
  * Open licence question for counsel: MET says it "can only distribute model data for the Nordic and Arctic
    regions" for licensing reasons. Confirm that CC BY on its ECMWF-based point forecasts is clean for a
    commercial routing product.

What a row means. valid is the start of the hour and mm_per_h is that hour's precipitation_amount (mm in
one hour is mm/h). Only hourly steps are kept (about 64 h ahead); the 6 hourly tail would need an interval
column to be read correctly. issued is meta.updated_at floored to the hour: two MET backends reported 19:19:14
and 19:19:25 for the same run, so the exact stamp would write duplicate rows. Flooring never dates a forecast
later than it arrived. Volume is zones x about 64 rows per issue, 4 issues a day.

Input is the zone table: one point per zone (ST_PointOnSurface), (zone_id, lat, lon), each checked to be
inside the India box. Output rows are (source, zone_id, issued, valid, mm_per_h, ensemble_spread).
A response that is not what we expect (unit other than mm, negative or absurd amounts, a forecast older than
24 h, malformed JSON) rejects that zone; the other zones are still stored and the run then fails, so a zone
without a forecast is never reported as healthy. A network or HTTP failure after retries stops the run.

ponytail: one request per zone per run and no If-Modified-Since. A request per zone at 1 request/s is 200 s for
200 zones; add conditional GETs or a coarser grid shared by several zones when that is too slow.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta

from floodroute.ingest.common import IngestError, Outcome, Rejected, in_india, utcnow

logger = logging.getLogger(__name__)

SOURCE = "metno"
INTERVAL_S = 3600
HOSTS = {"api.met.no"}
URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={:.4f}&lon={:.4f}"
MAX_BYTES = 1 << 20  # seen: 3 KB compact
MAX_ENTRIES = 400  # seen: 91
MAX_MM_H = 500.0  # not a measurement limit, a "this is garbage" limit
MAX_AGE = timedelta(hours=24)

POINTS_SQL = """
select zone_id, ST_Y(p), ST_X(p)
from (select zone_id, ST_PointOnSurface(geom) as p from zone) z
order by zone_id
"""
UPSERT_SQL = """
insert into rain_fcst (source, zone_id, issued, valid, mm_per_h, ensemble_spread)
values (%s, %s, %s, %s, %s, %s)
on conflict (source, zone_id, issued, valid) do update
set mm_per_h = excluded.mm_per_h, ensemble_spread = excluded.ensemble_spread
"""


def _no_constants(name: str):
    raise ValueError(f"JSON constant {name} is not allowed")


def _utc(value) -> datetime:
    try:
        out = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise Rejected(f"{value!r} is not an ISO 8601 time") from None
    if out.tzinfo is None:
        raise Rejected(f"{value!r} has no UTC offset")
    return out.astimezone(UTC)


def check_point(zone_id, lat, lon) -> tuple[float, float]:
    if isinstance(zone_id, bool) or not isinstance(zone_id, int):
        raise Rejected("zone id is not an integer")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise Rejected("no usable point") from None
    if not in_india(lat, lon):
        raise Rejected(f"point {lat},{lon} is outside India (swapped lat,lon?)")
    return lat, lon


def parse_forecast(
    body: bytes, now: datetime
) -> tuple[datetime, datetime, list[tuple[datetime, float]]]:
    """(updated_at, issued, [(valid, mm_per_h)]) from a Locationforecast JSON body."""
    try:
        doc = json.loads(body.decode("utf-8"), parse_constant=_no_constants)
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise Rejected(f"not usable JSON: {e}") from None
    try:
        props = doc["properties"]
        if props["meta"]["units"]["precipitation_amount"] != "mm":
            raise Rejected(
                f"precipitation unit is {props['meta']['units']['precipitation_amount']!r}"
            )
        updated = _utc(props["meta"]["updated_at"])
        series = props["timeseries"]
        if len(series) > MAX_ENTRIES:
            raise Rejected(f"more than {MAX_ENTRIES} timeseries entries")
        hourly: dict[datetime, float] = {}
        for entry in series:
            step = entry["data"].get("next_1_hours")
            if step is None:
                continue
            mm = step["details"]["precipitation_amount"]
            if isinstance(mm, bool) or not isinstance(mm, int | float) or not 0 <= mm <= MAX_MM_H:
                raise Rejected(f"precipitation_amount {mm!r} is out of range")
            hourly[_utc(entry["time"])] = float(mm)
    except (KeyError, TypeError, AttributeError):
        raise Rejected("unexpected JSON shape") from None
    if updated > now + timedelta(hours=1) or now - updated > MAX_AGE:
        raise Rejected(f"forecast updated_at {updated:%Y-%m-%dT%H:%MZ} is not within 24 h of now")
    if not hourly:
        raise Rejected("no hourly precipitation in the forecast")
    return updated, updated.replace(minute=0, second=0, microsecond=0), sorted(hourly.items())


def zone_points(conn) -> list[tuple]:
    return conn.execute(POINTS_SQL).fetchall()


def ingest(conn, http, *, points=None, now: datetime | None = None) -> Outcome:
    now = now or utcnow()
    if not os.environ.get("FLOODROUTE_CONTACT", "").strip():
        logger.warning(
            "FLOODROUTE_CONTACT is unset: MET Norway blocks contact-less clients without warning"
        )
    points = zone_points(conn) if points is None else list(points)
    if not points:
        raise IngestError("no zones to forecast: the zone table is empty")
    errors: list[str] = []
    rows_total = 0
    oldest = None
    newest = None
    for zone_id, lat, lon in points:
        try:
            lat, lon = check_point(zone_id, lat, lon)
            updated, issued, hourly = parse_forecast(http.get(URL.format(lat, lon), MAX_BYTES), now)
        except Rejected as e:
            errors.append(f"zone {zone_id}: {e}")
            continue
        rows = [(SOURCE, zone_id, issued, valid, mm, None) for valid, mm in hourly]
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, rows)
        rows_total += len(rows)
        oldest = updated if oldest is None else min(oldest, updated)
        newest = updated if newest is None else max(newest, updated)
    if errors:
        raise IngestError(f"{len(errors)} of {len(points)} zones failed: " + "; ".join(errors[:3]))
    lag = max(0, int((now - oldest).total_seconds()))
    warn = None
    if newest is not None and newest > now:
        warn = f"newest forecast updated_at {newest:%Y-%m-%dT%H:%MZ} is in the future"
    return Outcome({"zones": len(points), "rows": rows_total}, lag, warn)
