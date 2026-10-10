"""Match hotspot rows to OSM structure candidates by name and by distance.

Rule, applied per hotspot, first hit wins:
  name+distance  a candidate whose name overlaps the hotspot name (score >= NAME_MIN) lies within
                 NAME_R metres. Best = highest score, then nearest.
  name           a candidate of a real structure type (underpass, low_bridge, culvert) whose own name says
                 so (Underpass, Flyover, Bridge, ...) overlaps the name strongly (>= NAME_ONLY) and is
                 within NAME_FAR_R, or the hotspot has no coordinates. A hotspot name that says underpass or
                 subway only takes underpass candidates; one that says bridge, culvert, vent, nala or drain
                 only takes low_bridge and culvert. A road that merely shares a locality name never matches.
  distance       no name hit, but some candidate lies within DIST_R[confidence] metres (high 50 m, medium
                 100 m). Low or no geocode confidence never gets a distance-only match.
  none           nothing qualifies.
Tokens that occur in many candidate names ('outer', 'ring', ...) are dropped before comparing, so
'Outer Ring Road Underpass' cannot match every underpass on the ring road. Candidates with structure
'none' (building passages) are never matched. Only a clean name+distance match skips human review.
Failure modes and chance baseline: docs/spikes/S5-hotspot-inventory.md.
"""

import math
import re
from collections import Counter
from itertools import pairwise

NAME_MIN, NAME_ONLY, NAME_R, NAME_FAR_R = 0.5, 0.67, 300.0, 800.0
DIST_R = {"high": 50.0, "medium": 100.0}
COMMON_DF = 30  # a token in this many candidate names or more carries no identity
STRUCTURES = {"underpass", "low_bridge", "culvert"}
STRUCT_NAME = re.compile(
    r"under ?pass|under ?bridge|subway|bridge|flyover|culvert|tunnel|\bvents?\b"
)
HINTS = [  # words in a hotspot name that say what kind of structure it is
    (re.compile(r"under ?pass|under ?bridge|subway"), {"underpass"}),
    (re.compile(r"bridge|culvert|\bvents?\b|nala|drain"), {"low_bridge", "culvert"}),
]
GENERIC = {
    "road",
    "rd",
    "main",
    "cross",
    "junction",
    "jn",
    "circle",
    "cir",
    "underpass",
    "underbridge",
    "flyover",
    "bridge",
    "railway",
    "rail",
    "vehicle",
    "layout",
    "near",
    "the",
    "of",
    "in",
    "at",
    "on",
    "to",
    "and",
    "ward",
    "no",
    "opp",
    "behind",
    "beside",
    "back",
    "side",
    "area",
    "front",
    "stretch",
    "between",
    "from",
    "below",
    "signal",
    "service",
    "highway",
    "street",
    "st",
    "lane",
    "nh",
    "bengaluru",
    "bangalore",
    "chennai",
    "mumbai",
    "bombay",
    "gurugram",
    "gurgaon",
    "delhi",
    "pune",
    "hyderabad",
}
SPELL = {
    "mehkri": "mekhri",
    "mekri": "mekhri",
    "nagara": "nagar",
    "lyt": "layout",
    "lout": "layout",
}


def tokens(name):
    """Distinctive lower-case tokens of a place name; single letters merge ('K R' -> 'kr')."""
    s = re.sub(r"\bward\.?\s*(?:no\.?)?\s*[-.]?\s*\d+(?:/\d+)?", " ", name.lower())
    s = re.sub(r"[\u2019'`]", "", s).replace("&", " and ")
    out, run = [], []
    for t in [*re.findall(r"[a-z0-9]+", s), ""]:
        if len(t) == 1 and t.isalpha():
            run.append(t)
            continue
        if run:
            out.append("".join(run))
            run = []
        if t:
            out.append(SPELL.get(t, t))
    return {t for t in out if t not in GENERIC}


def overlap(a, b):
    """|A and B| / min(|A|, |B|); 0 when either side has no distinctive tokens."""
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def dist_m(lat, lon, pts):
    """Metres from a point to a polyline of (lon, lat) vertices (local equirectangular)."""
    kx, ky = 111320.0 * math.cos(math.radians(lat)), 110540.0
    p = [((x - lon) * kx, (y - lat) * ky) for x, y in pts]
    if len(p) == 1:
        return math.hypot(*p[0])
    best = math.inf
    for (ax, ay), (bx, by) in pairwise(p):
        dx, dy = bx - ax, by - ay
        n = dx * dx + dy * dy
        t = 0.0 if n == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / n))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def prepare(cands):
    """Drop structure 'none', add name tokens minus tokens common to many candidates: (cands, common)."""
    cands = [c for c in cands if c["structure"] != "none"]
    df = Counter(t for c in cands for t in tokens(c.get("name", "")))
    common = {t for t, n in df.items() if n >= COMMON_DF}
    return [
        {
            **c,
            "toks": tokens(c.get("name", "")) - common,
            "names_structure": bool(STRUCT_NAME.search(c.get("name", "").lower())),
        }
        for c in cands
    ], common


def match(h, cands, common=frozenset()):
    """h: {name, lat, lon, geocode_confidence}; cands, common: from prepare().

    ponytail: O(candidates) per hotspot with a bbox prefilter; add a grid index above ~100k candidates.
    """
    ht = tokens(h["name"]) - common
    conf = h.get("geocode_confidence", "none")
    has_xy = h.get("lat") not in (None, "") and h.get("lon") not in (None, "")
    lat, lon = (float(h["lat"]), float(h["lon"])) if has_xy else (0.0, 0.0)
    pad = 0.0085  # degrees, about 0.9 km: covers NAME_FAR_R, the largest radius used
    scored = []
    for c in cands:
        d = None
        if has_xy:
            xs, ys = [p[0] for p in c["pts"]], [p[1] for p in c["pts"]]
            if min(xs) - pad <= lon <= max(xs) + pad and min(ys) - pad <= lat <= max(ys) + pad:
                d = dist_m(lat, lon, c["pts"])
        scored.append((overlap(ht, c["toks"]), d, c))
    near = [x for x in scored if x[1] is not None]
    kinds = next((k for rx, k in HINTS if rx.search(h["name"].lower())), STRUCTURES)
    hit = [x for x in near if x[0] >= NAME_MIN and x[1] <= NAME_R]
    named = [
        x
        for x in scored
        if x[0] >= NAME_ONLY
        and x[2]["structure"] in kinds
        and x[2]["names_structure"]
        and (x[1] is not None and x[1] <= NAME_FAR_R if has_xy else True)
    ]
    close = [x for x in near if conf in DIST_R and x[1] <= DIST_R[conf]]
    if hit:
        best, mtype = max(hit, key=lambda x: (x[0], -x[1])), "name+distance"
    elif named:
        best, mtype = max(named, key=lambda x: (x[0], -(x[1] if x[1] is not None else 1e9))), "name"
    elif close:
        best, mtype = min(close, key=lambda x: x[1]), "distance"
    else:
        return {
            "match_type": "none",
            "needs_review": True,
            "n_in_radius": len([x for x in near if x[1] <= NAME_R]),
        }
    s, d, c = best
    # how many candidates compete: same-named ones for a name hit (two carriageways = 2), else those in radius
    n_in = len(hit) if mtype == "name+distance" else len(named) if mtype == "name" else len(close)
    clean = mtype == "name+distance" and s >= 0.8 and d <= 150 and conf in DIST_R and n_in <= 2
    return {
        "match_type": mtype,
        "candidate_id": c["candidate_id"],
        "osm_way_id": c["osm_way_id"],
        "way_name": c.get("name", ""),
        "structure": c["structure"],
        "dist_m": None if d is None else round(d),
        "name_score": round(s, 2),
        "n_in_radius": n_in,
        "needs_review": not clean,
    }


OUT_COLS = [
    "hotspot_row",
    "name",
    "list_kind",
    "lat",
    "lon",
    "geocode_confidence",
    "match_type",
    "candidate_id",
    "osm_way_id",
    "way_name",
    "structure",
    "dist_m",
    "name_score",
    "n_in_radius",
    "needs_review",
]


def main(hotspots_csv, candidates_geojson, out_csv):
    """python -m floodroute.inventory.match HOTSPOTS.csv CANDIDATES.geojson OUT.csv"""
    import csv
    import json

    with open(candidates_geojson, encoding="utf-8") as fh:
        raw = [
            {**f["properties"], "pts": f["geometry"]["coordinates"]}
            for f in json.load(fh)["features"]
        ]
    cands, common = prepare(raw)
    with open(hotspots_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, OUT_COLS, restval="")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            m = match(r, cands, common)
            m.update(
                hotspot_row=i,
                name=r["name"],
                list_kind=r["list_kind"],
                lat=r["lat"],
                lon=r["lon"],
                geocode_confidence=r["geocode_confidence"],
            )
            w.writerow(m)


if __name__ == "__main__":
    import sys

    main(*sys.argv[1:4])
