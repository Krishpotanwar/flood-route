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


def mid_along(coords):
    """Point halfway along the polyline (by length), not the middle vertex."""
    segs_ = [vh.haversine_m(a, b) for a, b in zip(coords, coords[1:])]
    half, acc = sum(segs_) / 2, 0.0
    for (a, b), d in zip(zip(coords, coords[1:]), segs_):
        if acc + d >= half and d > 0:
            f = (half - acc) / d
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        acc += d
    return coords[0]


def locate_map(c, seg, extra=None):
    """M2: /locate at the segment midpoint, keep edges of the segment's way and read their OSM node ids.
    Returns {"fwd": edge id or None, "rev": edge id or None, "same_way_other_nodes": [..]}."""
    lon, lat = mid_along(seg["coords"])
    body = {"locations": [vh.loc(lon, lat)], "costing": "auto", "verbose": True, **(extra or {})}
    st, js, _ = c.post("locate", body)
    res = {"fwd": None, "rev": None, "other": []}
    if st != 200:
        return res
    for e in js[0].get("edges", []):
        if e["edge_info"]["way_id"] != seg["way"]:
            continue
        ids = e["edge_info"].get("osm_node_ids") or []
        if len(ids) < 2:
            res["other"].append(e["edge_id"]["value"])
            continue
        # edge_info is shared by the two directed edges and lists nodes in storage order; edge.forward says
        # whether this directed edge runs along it or against it
        first, last = (ids[0], ids[-1]) if e["edge"]["forward"] else (ids[-1], ids[0])
        if (first, last) == (seg["a"], seg["b"]):
            res["fwd"] = e["edge_id"]["value"]
        elif (first, last) == (seg["b"], seg["a"]):
            res["rev"] = e["edge_id"]["value"]
        else:
            res["other"].append(e["edge_id"]["value"])
    return res


def cover_map(c, seg):
    """M3 (needs a graph built with keep_all_osm_node_ids): locate at every vertex of the segment, keep the
    directed edges of its way, and compare their OSM node lists with the segment's node list.
    Returns {"fwd": (cls, [edge ids]), "rev": (cls, [edge ids])} with cls in exact | edge_longer | split | partial | none."""
    S = seg["nodes"]
    found = {}
    for lon, lat in seg["coords"]:
        st, js, _ = c.post("locate", {"locations": [vh.loc(lon, lat)], "costing": "auto", "verbose": True})
        if st != 200:
            continue
        for e in js[0].get("edges", []):
            if e["edge_info"]["way_id"] != seg["way"]:
                continue
            ids = e["edge_info"].get("osm_node_ids") or []
            found[e["edge_id"]["value"]] = ids if e["edge"]["forward"] else ids[::-1]
    out = {}
    for d, seq in (("fwd", S), ("rev", S[::-1])):
        pairs = set(zip(seq, seq[1:]))
        hits, covered = [], set()
        for eid, ids in found.items():
            ov = pairs & set(zip(ids, ids[1:]))
            if ov:
                hits.append((eid, ids, ov))
                covered |= ov
        if not hits:
            out[d] = ("none", [])
        elif any(ids == seq for _, ids, _ in hits):
            out[d] = ("exact", [eid for eid, ids, _ in hits if ids == seq])
        elif any(len(ov) == len(pairs) for _, _, ov in hits):
            out[d] = ("edge_longer", [eid for eid, _, ov in hits if len(ov) == len(pairs)])
        elif covered == pairs:
            out[d] = ("split", [eid for eid, _, _ in hits])
        else:
            out[d] = ("partial", [eid for eid, _, _ in hits])
    return out


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

        # M2: locate at the midpoint
        t0 = time.perf_counter()
        loc_res = [locate_map(c1, sg) for sg in segs]
        ms_loc = (time.perf_counter() - t0) * 1000 / len(segs)
        both = {"fwd_exact_trace": 0, "fwd_exact_locate": 0, "fwd_exact_either": 0, "fwd_exact_neither": 0,
                "rev_exact_trace": 0, "rev_exact_locate": 0, "rev_exact_either": 0, "rev_exact_neither": 0,
                "locate_ids_equal_trace_ids_when_both_exact": 0, "both_exact": 0}
        short = {"n": 0, "trace_exact": 0, "locate_exact": 0}
        for r, lr, sg in zip(m1, loc_res, segs):
            for d in ("fwd", "rev"):
                t_ok = r[d]["cls"] == "exact"
                l_ok = lr[d] is not None
                both[f"{d}_exact_trace"] += t_ok
                both[f"{d}_exact_locate"] += l_ok
                both[f"{d}_exact_either"] += t_ok or l_ok
                both[f"{d}_exact_neither"] += not (t_ok or l_ok)
                if t_ok and l_ok:
                    both["both_exact"] += 1
                    both["locate_ids_equal_trace_ids_when_both_exact"] += r[d]["edges"][0] == lr[d]
            if sg["len_m"] < 15:
                short["n"] += 1
                short["trace_exact"] += r["fwd"]["cls"] == "exact"
                short["locate_exact"] += lr["fwd"] is not None
        out["locate_vs_trace_v1"] = {**both, "locate_ms_per_segment": round(ms_loc, 2), "short_segments_under_15m_fwd": short}
        print("locate vs trace", json.dumps(out["locate_vs_trace_v1"]), flush=True)
        json.dump(loc_res, open(WORK / "map_v1_locate.json", "w"))

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

    # ---- M3: graph built with keep_all_osm_node_ids ------------------------------------------------------
    GA = WORK / "blr_alln"
    ta = GA / "traffic_map.tar"
    shutil.copyfile(GA / "traffic.tar", ta)
    with vh.Service(GA, 8504, GA / "valhalla_tiles.tar", ta, concurrency=2, name="mapall") as sa:
        ca = vh.Client(8504)
        t0 = time.perf_counter()
        cov = [cover_map(ca, sg) for sg in segs]
        ms_cov = (time.perf_counter() - t0) * 1000 / len(segs)
    tot = {"fwd": collections.Counter(c_["fwd"][0] for c_ in cov), "rev": collections.Counter(c_["rev"][0] for c_ in cov)}
    out["cover_all_node_ids"] = {"ms_per_segment": round(ms_cov, 1), "fwd": dict(tot["fwd"]), "rev": dict(tot["rev"]),
                                 "tile_mb_end_nodes_only": round((WORK / "blr" / "valhalla_tiles.tar").stat().st_size / 2**20, 1),
                                 "tile_mb_all_nodes": round((GA / "valhalla_tiles.tar").stat().st_size / 2**20, 1)}
    print("cover (all node ids)", json.dumps(out["cover_all_node_ids"]), flush=True)

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
