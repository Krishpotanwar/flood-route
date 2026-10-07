"""Seed CSV (curated, with provenance) -> hotspot CSV with coordinates and confidence.

    python -m floodroute.inventory.hotspots SEED.csv OUT.csv CITY CACHE_DIR

A seed row keeps its source (name, URL, date, kind, verbatim text) and optionally the coordinates the
source itself printed (src_lat, src_lon) and a hand-written geocoder query. Rules, in order:
  1. Source coordinates inside the city box are kept. They are checked against other seed rows with a
     similar name from a different source: within AGREE_M of one = high, farther than CONFLICT_M = low
     (the sources disagree), otherwise medium. A coordinate printed for several names is capped at
     medium (the lists repeat one point for neighbouring entries).
  2. Source coordinates outside the city box (typos) or missing: take the point of a similar-named
     row from another source (medium), else ask Nominatim (see geocode.py).
  3. Extent stretch, road or area caps Nominatim confidence at low: that point is not a segment.
     A query with no result is retried once without structure words (underpass, railway, ...).
low and none rows get needs_review.
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict

from floodroute.inventory import CITIES
from floodroute.inventory.geocode import Geocoder, confidence, simplify
from floodroute.inventory.match import dist_m, tokens

COLS = [
    "name",
    "ward_or_area",
    "source_name",
    "source_url",
    "source_date",
    "list_kind",
    "raw_text",
    "lat",
    "lon",
    "geocode_method",
    "geocode_confidence",
    "needs_review",
]
REQUIRED = ("name", "source_name", "source_url", "source_date", "list_kind", "raw_text")
AGREE_M, CONFLICT_M = 150.0, 500.0
SAME_NAME = 0.6  # Jaccard of distinctive tokens to call two rows the same place
AREA_KINDS = {"low_lying_area", "gcc_chronic_low_lying", "bmc_chronic_low_lying"}  # area-level points: never better than medium
EXTENT_CAPPED = ("stretch", "road", "area")  # linear/area extents are not segments: capped at low


def validate(rows):
    """Trust boundary: no row without provenance, no non-http URL, no malformed date,
    no non-numeric source coordinates, no unknown extent vocabulary."""
    bad = []
    for i, r in enumerate(rows, 2):  # 2 = first data line of the CSV
        if any(not (r.get(k) or "").strip() for k in REQUIRED):
            bad.append(f"line {i}: missing one of {REQUIRED}")
        elif not re.match(r"https?://", r["source_url"]):
            bad.append(f"line {i}: source_url is not http(s)")
        elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["source_date"]):
            bad.append(f"line {i}: source_date is not YYYY-MM-DD")
        elif (r.get("src_lat") or r.get("src_lon")) and (
            num(r.get("src_lat")) is None or num(r.get("src_lon")) is None
        ):
            bad.append(f"line {i}: src_lat/src_lon are not both numeric")
        elif "extent" in r and (r.get("extent") or "") not in ("point", "stretch", "road", "area", ""):
            bad.append(f"line {i}: extent is not one of point/stretch/road/area")
    if bad:
        raise ValueError("invalid seed:\n" + "\n".join(bad[:20]))


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def inside(lat, lon, box):
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


def build(rows, city, geocoder):
    """Return (output rows, stats). rows: seed dicts; geocoder: Geocoder or anything with .search/.box."""
    box = CITIES[city]
    pts = []  # per row: (lat, lon) when the source coordinate is inside the box, else None
    for r in rows:
        la, lo = num(r.get("src_lat")), num(r.get("src_lon"))
        pts.append((la, lo) if la is not None and lo is not None and inside(la, lo, box) else None)
    toks = [tokens(r["name"]) for r in rows]
    names_at = defaultdict(set)
    for p, r in zip(pts, rows):
        if p:
            names_at[p].add(r["name"].strip().lower())

    def peers(i):
        return [
            j
            for j, p in enumerate(pts)
            if p
            and j != i
            and rows[j]["source_url"] != rows[i]["source_url"]
            and jaccard(toks[i], toks[j]) >= SAME_NAME
        ]

    def source_outcome(i):
        """Confidence for a row whose own source coordinates fall inside the box."""
        r = rows[i]
        lat, lon = pts[i]
        d = [dist_m(lat, lon, [(pts[j][1], pts[j][0])]) for j in peers(i)]
        if d and min(d) <= AGREE_M:
            method, conf = f"source_latlon;agrees_with_other_source_{round(min(d))}m", "high"
        elif d and min(d) > CONFLICT_M:
            method, conf = f"source_latlon;conflicts_with_other_source_{round(min(d))}m", "low"
        else:
            method, conf = (
                ("source_latlon;other_source_" + f"{round(min(d))}m" if d else "source_latlon"),
                "medium",
            )
        if (
            len(names_at[pts[i]]) > 1
        ):  # one printed point for several names: co-located, not exact
            method += f";shared_by_{len(names_at[pts[i]])}_names"
            conf = "medium" if conf == "high" else conf
        if r["list_kind"] in AREA_KINDS and conf == "high":
            conf = "medium"
        if r.get("extent") in EXTENT_CAPPED and conf != "low":
            method += f";capped_extent_{r['extent']}"
            conf = "low"
        return lat, lon, method, conf

    out, stats = [], Counter()
    for i, r in enumerate(rows):
        lat = lon = None
        method, conf = "", "none"
        if pts[i]:
            lat, lon, method, conf = source_outcome(i)
        else:
            src_lat_raw, src_lon_raw = r.get("src_lat"), r.get("src_lon")
            note = ""
            if src_lat_raw or src_lon_raw:
                la, lo = num(src_lat_raw), num(src_lon_raw)
                if la is None or lo is None:
                    note = f"source_latlon_rejected({src_lat_raw},{src_lon_raw} invalid coordinates);"
                elif not inside(la, lo, box):
                    note = f"source_latlon_rejected({src_lat_raw},{src_lon_raw} outside city box);"
            near = peers(i)
            good = [j for j in near if source_outcome(j)[3] in ("high", "medium")]
            if good:
                j = max(good, key=lambda j: jaccard(toks[i], toks[j]))
                lat, lon = pts[j]
                method, conf = f"{note}name_match_{rows[j]['list_kind']}", "medium"
            else:
                q = (r.get("geocode_query") or "").strip() or f"{r['name']}, {city.title()}"
                rs = geocoder.search(q)
                conf, why = confidence(rs, q.split(",")[0], box)
                method = f"{note}nominatim:q={q!r}"
                if conf == "none" and (q2 := simplify(q)):
                    rs = geocoder.search(q2)
                    conf, why = confidence(rs, q2.split(",")[0], box)
                    method += f";retry_q={q2!r}"
                    stats[("retry", "hit" if conf != "none" else "miss")] += 1
                method += f";{why}" if why else ""
                if conf != "none":
                    lat, lon = float(rs[0]["lat"]), float(rs[0]["lon"])
        if r.get("extent") in EXTENT_CAPPED and conf in ("high", "medium"):
            conf, method = "low", method + f";capped_extent_{r['extent']}"
        out.append(
            {
                "name": r["name"],
                "ward_or_area": r.get("ward_or_area", ""),
                "source_name": r["source_name"],
                "source_url": r["source_url"],
                "source_date": r["source_date"],
                "list_kind": r["list_kind"],
                "raw_text": r["raw_text"],
                "lat": "" if lat is None else f"{lat:.6f}",
                "lon": "" if lon is None else f"{lon:.6f}",
                "geocode_method": method,
                "geocode_confidence": conf,
                "needs_review": "true" if conf in ("low", "none") else "false",
            }
        )
        stats[(r["list_kind"], conf)] += 1
    return out, stats


def main(seed, out, city, cache):
    with open(seed, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    validate(rows)
    g = Geocoder(cache, CITIES[city])
    res, stats = build(rows, city, g)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, COLS)
        w.writeheader()
        w.writerows(res)
    print(
        json.dumps(
            {
                "rows": len(res),
                "nominatim_requests_sent": g.requests,
                "kind|confidence": {f"{k}|{c}": n for (k, c), n in sorted(stats.items())},
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main(*sys.argv[1:5])
