"""Sample test data from the Bengaluru PBF: random OD pairs and OSM segments (way split at junctions).

  python osm_sample.py PBF OUT_DIR [--pairs 3000] [--segments 3000] [--seed 7]

od_pairs.json        [[lon1, lat1, lon2, lat2], ...] road nodes, great-circle distance roughly log-uniform
                     in 1..30 km (acceptance probability (1 km / d)^2 on uniformly drawn pairs)
segments_sample.json [{way, a, b, hw, oneway, bridge, tunnel, coords, len_m}, ...]
                     segment = maximal run of a way between two junction nodes (node shared by >=2
                     ways, or a way end). a and b are OSM node ids.
"""
import argparse
import collections
import json
import random
from pathlib import Path

import osmium
from osmium.filter import EntityFilter, KeyFilter

import vh

DRIVABLE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
            "living_street", "motorway_link", "trunk_link", "primary_link", "secondary_link",
            "tertiary_link", "service"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pbf")
    ap.add_argument("out")
    ap.add_argument("--pairs", type=int, default=3000)
    ap.add_argument("--segments", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    ways, use = [], collections.Counter()
    fp = (osmium.FileProcessor(a.pbf, osmium.osm.NODE | osmium.osm.WAY).with_locations()
          .with_filter(EntityFilter(osmium.osm.WAY)).with_filter(KeyFilter("highway")))
    for w in fp:
        hw = w.tags.get("highway")
        if hw not in DRIVABLE or len(w.nodes) < 2:
            continue
        pts = [(n.ref, n.lon, n.lat) for n in w.nodes if n.location.valid()]
        if len(pts) < 2:
            continue
        ways.append((w.id, hw, w.tags.get("oneway", ""), w.tags.get("bridge", ""),
                     w.tags.get("tunnel", ""), pts))
        for ref, _, _ in pts:
            use[ref] += 1
    print(len(ways), "drivable ways;", sum(1 for v in use.values() if v > 1), "shared nodes")

    segs = []
    for wid, hw, ow, br, tu, pts in ways:
        cut = [0] + [i for i in range(1, len(pts) - 1) if use[pts[i][0]] > 1] + [len(pts) - 1]
        for i, j in zip(cut, cut[1:]):
            sub = pts[i: j + 1]
            ln = sum(vh.haversine_m(sub[k][1:], sub[k + 1][1:]) for k in range(len(sub) - 1))
            segs.append({"way": wid, "a": sub[0][0], "b": sub[-1][0], "hw": hw, "oneway": ow,
                         "bridge": br, "tunnel": tu, "len_m": round(ln, 1),
                         "coords": [(round(lo, 7), round(la, 7)) for _, lo, la in sub]})
    print(len(segs), "segments")

    # stratified sample: bridges/tunnels (the flood-relevant ones) are oversampled on purpose
    special = [s for s in segs if s["bridge"] not in ("", "no") or s["tunnel"] not in ("", "no")]
    arterial = [s for s in segs if s["hw"] in ("primary", "secondary", "tertiary", "trunk")]
    local = [s for s in segs if s["hw"] in ("residential", "unclassified", "living_street")]
    other = [s for s in segs if s["hw"].endswith("_link") or s["hw"] == "service" or s["hw"] == "motorway"]
    n = a.segments
    pick = []
    for pool, k in ((special, n // 5), (arterial, n * 2 // 5), (local, n // 5), (other, n // 5)):
        pick += rng.sample(pool, min(k, len(pool)))
    print("sample", len(pick), "special pool", len(special))
    (out / "segments_sample.json").write_text(json.dumps(pick))

    nodes = [(lo, la) for *_, pts in ways for _, lo, la in pts[:: max(1, len(pts) // 2)]]
    rng.shuffle(nodes)
    pairs = []
    while len(pairs) < a.pairs:
        p, q = rng.choice(nodes), rng.choice(nodes)
        d = vh.haversine_m(p, q)
        if 1000 <= d <= 30000 and rng.random() < (1000 / d) ** 2:
            pairs.append([*p, *q])
    (out / "od_pairs.json").write_text(json.dumps(pairs))
    ds = sorted(vh.haversine_m(p[:2], p[2:]) for p in pairs)
    print("pair great-circle km p10/p50/p90:", [round(ds[int(len(ds) * f)] / 1000, 1) for f in (0.1, 0.5, 0.9)])


if __name__ == "__main__":
    main()
