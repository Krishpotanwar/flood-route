"""Clip an OSM PBF to a bbox (complete highway ways + turn restrictions) with pyosmium.

  python clip_bbox.py IN.pbf OUT.pbf minlon,minlat,maxlon,maxlat [--perturb SEED]

--perturb simulates "a newer extract" for the graph-rebuild test (S1 question 7): drops 1% of
ways and splits 2% of long ways in two, giving the second half a NEW way id (what a mapper's
split does). Everything else is byte-for-byte the same data.

Why pyosmium (spike-only dependency): the stdlib cannot read PBF, and osmium-tool is not installed.
"""
import argparse
import json
import random
import sys
import time

import osmium
from osmium.filter import EntityFilter, IdFilter, KeyFilter

W, N, R = osmium.osm.WAY, osmium.osm.NODE, osmium.osm.RELATION


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("bbox")
    ap.add_argument("--perturb", type=int, default=None)
    a = ap.parse_args()
    try:
        parts = [float(p) for p in a.bbox.split(",")]
    except ValueError:
        ap.error("bbox must be four comma-separated numbers: minlon,minlat,maxlon,maxlat")
    if len(parts) != 4:
        ap.error("bbox must be four comma-separated numbers: minlon,minlat,maxlon,maxlat")
    x0, y0, x1, y1 = parts
    if not (x0 < x1 and y0 < y1):
        ap.error("bbox needs west<east and south<north")
    if not (-180 <= x0 <= 180 and -180 <= x1 <= 180 and -90 <= y0 <= 90 and -90 <= y1 <= 90):
        ap.error("bbox out of range: lon -180..180, lat -90..90")
    t0 = time.time()

    way_ids, node_ids = set(), set()
    # locations are attached natively; the filters drop nodes before Python sees them
    fp = (osmium.FileProcessor(a.src, N | W).with_locations()
          .with_filter(EntityFilter(W)).with_filter(KeyFilter("highway")))
    for w in fp:
        pts = [(n.lon, n.lat) for n in w.nodes if n.location.valid()]
        if any(x0 <= lo <= x1 and y0 <= la <= y1 for lo, la in pts):
            way_ids.add(w.id)
            node_ids.update(n.ref for n in w.nodes)
    print(f"pass1 {len(way_ids)} ways {len(node_ids)} nodes {time.time()-t0:.0f}s", file=sys.stderr)

    rng = random.Random(a.perturb)
    if not way_ids:
        ap.error("no highway ways inside the bbox: nothing to clip")
    max_way = max(way_ids)
    dropped, splits, split_log, late = set(), 0, {}, []
    with osmium.SimpleWriter(a.dst, overwrite=True) as out:
        for n in osmium.FileProcessor(a.src, N).with_filter(IdFilter(node_ids)):
            out.add_node(n)
        print(f"nodes done {time.time()-t0:.0f}s", file=sys.stderr)
        for w in osmium.FileProcessor(a.src, W).with_filter(IdFilter(way_ids)):
            if a.perturb is not None:
                r = rng.random()
                if r < 0.01:
                    dropped.add(w.id)
                    continue
                if r > 0.98 and len(w.nodes) >= 6:
                    refs = [n.ref for n in w.nodes]
                    mid = len(refs) // 2
                    tags = {t.k: t.v for t in w.tags}
                    out.add_way(osmium.osm.mutable.Way(id=w.id, nodes=refs[: mid + 1], tags=tags,
                                                       version=w.version, timestamp=w.timestamp))
                    splits += 1
                    # new ids are above every existing id, so they go after the last original way (sorted PBF)
                    late.append(osmium.osm.mutable.Way(id=max_way + splits, nodes=refs[mid:], tags=tags,
                                                       version=1, timestamp=w.timestamp))
                    split_log[w.id] = {"new_way": max_way + splits, "split_node": refs[mid]}
                    continue
            out.add_way(w)
        for w in late:
            out.add_way(w)
        print(f"ways done {time.time()-t0:.0f}s dropped={len(dropped)} split={splits}", file=sys.stderr)
        if a.perturb is not None:  # ground truth for the rebuild experiment
            with open(a.dst + ".perturb.json", "w") as f:
                json.dump({"dropped": sorted(dropped), "split": split_log}, f)
        kept_ways = way_ids - dropped
        nrel = 0
        for r in osmium.FileProcessor(a.src, R).with_filter(KeyFilter("type")):
            if not r.tags.get("type", "").startswith("restriction"):
                continue
            ok = all((m.type == "w" and m.ref in kept_ways) or (m.type == "n" and m.ref in node_ids)
                     for m in r.members)
            if ok:
                out.add_relation(r)
                nrel += 1
        print(f"relations {nrel} done {time.time()-t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
