"""S1 question 7: OSM segment (way id + junction node pair) -> Valhalla directed edge ids.

Method: Valhalla built with mjolnir.keep_osm_node_ids=true reports for every matched edge its way_id, its begin
OSM node (edge "node_id") and its end OSM node (end_node.node_id). We edge-walk the segment's own OSM geometry
forward and reversed (trace_attributes, walk_or_snap) and read the edge keys back.

  S1_WORK=<work dir with blr/, blr2/, data/, blr_v2.osm.pbf.perturb.json> python exp_mapping.py   -> results/mapping.json
"""
import collections
import json
import os
import shutil
import time
from pathlib import Path

import vh

WORK = Path(os.environ["S1_WORK"])
RES = Path(__file__).parent / "results"
RES.mkdir(exist_ok=True)
segs = json.loads((WORK / "data" / "segments_sample.json").read_text())
FILTERS = ["edge.id", "edge.way_id", "edge.begin_osm_node_id", "edge.end_osm_node_id", "edge.length",
           "edge.source_percent_along", "edge.target_percent_along", "node.type"]


def trace(c, coords, extra=None):
    body = {"shape": [{"lat": la, "lon": lo} for lo, la in coords], "costing": "auto", "shape_match": "walk_or_snap",
            **(extra or {}), "filters": {"attributes": FILTERS, "action": "include"}}
    t0 = time.perf_counter()
    st, js, _ = c.post("trace_attributes", body)
    return st, js, (time.perf_counter() - t0) * 1000


def classify(seg, edges, fwd):
    """exact: an edge of the segment's way whose OSM begin/end nodes are the segment's.
    split: several full edges chain from the segment's first node to its last.
    inside_longer_edge: Valhalla's edge is longer than our segment (it only partially matches).
    no_edge: nothing on that way. Slivers under 2 m are ignored: the walk often appends a zero-length
    piece of the opposing edge where its last point lands on the end node."""
    begin = lambda e: e.get("node_id")  # noqa: E731
    end = lambda e: e.get("end_node", {}).get("node_id")  # noqa: E731
    own = [e for e in edges if e["way_id"] == seg["way"] and e["length"] * 1000 >= 2.0]
    if not own:
        return "no_edge", []
    s, t = (seg["a"], seg["b"]) if fwd else (seg["b"], seg["a"])
    full = lambda e: e.get("source_percent_along", 0) == 0 and e.get("target_percent_along", 1) == 1  # noqa: E731
    ex = [e for e in own if begin(e) == s and end(e) == t]
    if ex:
        return "exact", ex[:1]
    if len(own) > 1 and begin(own[0]) == s and end(own[-1]) == t and all(full(e) for e in own):
        return "split", own
    return "inside_longer_edge", own


def map_all(c, items, tag):
    res, ms = [], []
    for i, seg in enumerate(items):
        row = {"i": i, "way": seg["way"], "a": seg["a"], "b": seg["b"], "oneway": seg["oneway"], "hw": seg["hw"]}
        for fwd in (True, False):
            coords = seg["coords"] if fwd else seg["coords"][::-1]
            if len(coords) < 2 or seg["len_m"] < 1:
                row["fwd" if fwd else "rev"] = {"cls": "degenerate", "edges": []}
                continue
            st, js, dt = trace(c, coords)
            ms.append(dt)
            if st != 200:
                row["fwd" if fwd else "rev"] = {"cls": f"error_{js.get('error_code')}", "edges": []}
                continue
            cls, own = classify(seg, js["edges"], fwd)
            row["fwd" if fwd else "rev"] = {"cls": cls, "edges": [e["id"] for e in own],
                                            "keys": [[e["way_id"], e.get("node_id"), e.get("end_node", {}).get("node_id")] for e in own]}
        res.append(row)
    ms.sort()
    print(tag, "calls", len(ms), "ms p50", round(ms[len(ms) // 2], 1), "p95", round(ms[int(len(ms) * 0.95)], 1), flush=True)
    return res, {"calls": len(ms), "ms_p50": round(ms[len(ms) // 2], 2), "ms_p95": round(ms[int(len(ms) * 0.95)], 2)}


def summarize(res):
    out = {"fwd": collections.Counter(r["fwd"]["cls"] for r in res), "rev": collections.Counter(r["rev"]["cls"] for r in res)}
    ow = collections.defaultdict(collections.Counter)
    for r in res:
        key = r["oneway"] or "unset"
        ow[key][("fwd_" + r["fwd"]["cls"] if r["fwd"]["cls"] != "exact" else "fwd_exact", "rev_" + r["rev"]["cls"] if r["rev"]["cls"] != "exact" else "rev_exact")] += 1
    out["by_oneway_tag"] = {k: {f"{a}|{b}": n for (a, b), n in v.items()} for k, v in ow.items()}
    return {k: (dict(v) if isinstance(v, collections.Counter) else v) for k, v in out.items()}


def main():
    out = {"segments": len(segs)}
    G1, G2 = WORK / "blr", WORK / "blr2"
    t1 = G1 / "traffic_map.tar"
    shutil.copyfile(G1 / "traffic.tar", t1)
    with vh.Service(G1, 8501, G1 / "valhalla_tiles.tar", t1, concurrency=2, name="map1") as s1:
        c1 = vh.Client(8501)
        m1, timing = map_all(c1, segs, "v1")
        out["v1"] = {"summary": summarize(m1), "timing": timing}
        print(json.dumps(out["v1"]["summary"]["fwd"]), json.dumps(out["v1"]["summary"]["rev"]))

        # failure mode: mapping while the edge is closed in the overlay
        tt = vh.TrafficTar(t1)
        ex = [r for r in m1 if r["fwd"]["cls"] == "exact"][:100]
        res = {"with_date_time_closed": 0, "without_date_time_closed": 0, "n": len(ex)}
        for r in ex:
            seg = segs[r["i"]]
            eid = r["fwd"]["edges"][0]
            tt.apply([(eid, None, True)])
            st, js, _ = trace(c1, seg["coords"], extra=vh.CURRENT)
            res["with_date_time_closed"] += st == 200 and classify(seg, js["edges"], True)[0] == "exact"
            st, js, _ = trace(c1, seg["coords"])
            res["without_date_time_closed"] += st == 200 and classify(seg, js["edges"], True)[0] == "exact"
            tt.apply([(eid, None, False)])
        out["map_while_closed_exact_count"] = res
        tt.close()
        print("map while closed", res, flush=True)
    json.dump(m1, open(WORK / "map_v1.json", "w"))

    # ---- rebuild from a newer (perturbed) extract ------------------------------------------------------
    t2 = G2 / "traffic_map.tar"
    shutil.copyfile(G2 / "traffic.tar", t2)
    with vh.Service(G2, 8502, G2 / "valhalla_tiles.tar", t2, concurrency=2, name="map2") as s2:
        c2 = vh.Client(8502)
        m2, timing2 = map_all(c2, segs, "v2")
    out["v2"] = {"summary": summarize(m2), "timing": timing2}
    truth = json.loads((WORK / "blr_v2.osm.pbf.perturb.json").read_text())
    dropped = set(truth["dropped"])
    split = {int(k): v for k, v in truth["split"].items()}
    cmp_ = collections.Counter()
    key_ok = collections.Counter()
    for r1, r2, seg in zip(m1, m2, segs):
        w = seg["way"]
        kind = "dropped_way" if w in dropped else "split_way" if w in split else "untouched_way"
        for d in ("fwd", "rev"):
            e1, e2 = r1[d], r2[d]
            if e1["cls"] != "exact":
                continue  # only compare what was cleanly mapped in v1
            cmp_[(kind, "n")] += 1
            if e2["edges"] == e1["edges"]:
                cmp_[(kind, "same_edge_id")] += 1
            if e2["cls"] == "exact" and e2["keys"] == e1["keys"]:
                cmp_[(kind, "same_key_exact")] += 1
                key_ok[kind] += 1
            if e2["cls"] in ("exact", "split") and [k[1:] for k in e2["keys"]][0][0] == seg["a" if d == "fwd" else "b"]:
                cmp_[(kind, "node_pair_chain_found")] += 1
            if e2["cls"] == "no_edge":
                cmp_[(kind, "no_edge")] += 1
            if e2["cls"] == "split":
                cmp_[(kind, "now_split")] += 1
    table = collections.defaultdict(dict)
    for (kind, k), n in cmp_.items():
        table[kind][k] = n
    out["rebuild_compare"] = table
    print("rebuild compare", json.dumps(table), flush=True)
    (RES / "mapping.json").write_text(json.dumps(out, indent=1, default=str))
    print("wrote", RES / "mapping.json")


if __name__ == "__main__":
    main()
