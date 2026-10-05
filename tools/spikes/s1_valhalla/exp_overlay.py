"""S1 questions 4 and 9 (single snapshot): does an in-place traffic.tar edit change routes with no rebuild,
how long do 100 and 1,000 changed edges take to publish, and what does the overlay mean in time.

  S1_WORK=<work dir with blr/ and data/> python exp_overlay.py

Writes results/overlay.json. Needs the blr graph from build.py and od_pairs.json from osm_sample.py.
"""
import json
import os
import random
import shutil
import statistics as stats
import time
from pathlib import Path

import vh

WORK = Path(os.environ["S1_WORK"])
G = WORK / "blr"
RES = Path(__file__).parent / "results"
RES.mkdir(exist_ok=True)
rng = random.Random(11)
pairs = json.loads((WORK / "data" / "od_pairs.json").read_text())


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def edges(client, shape, **kw):
    st, js, _ = vh.edges_of(client, shape, **kw)
    assert st == 200, js
    return js["edges"]


def target_edge(E):
    """longest edge of the middle third that is not a tiny link (speed >= 30 kph)."""
    mid = [e for e in E[len(E) // 3: 2 * len(E) // 3] if e["speed"] >= 30] or E[len(E) // 3: 2 * len(E) // 3]
    return max(mid, key=lambda e: e["length"])


def main():
    out = {"valhalla": "3.9.0"}
    work_tar = G / "traffic_exp.tar"
    shutil.copyfile(G / "traffic.tar", work_tar)
    with vh.Service(G, 8301, G / "valhalla_tiles.tar", work_tar, concurrency=2, name="exp_overlay") as svc:
        c = vh.Client(8301)
        tt = vh.TrafficTar(work_tar)
        out["traffic_tiles"] = len(tt.tiles)
        out["directed_edges"] = sum(n for _, n in tt.tiles.values())

        # ---- A. closure changes the route with no rebuild, no restart -----------------------------
        rows = []
        for o_lon, o_lat, d_lon, d_lat in pairs[:400]:
            if len(rows) >= 60:
                break
            o, d = (o_lon, o_lat), (d_lon, d_lat)
            st, s0, sh0, _ = vh.route(c, o, d)
            if st != 200 or s0["length"] < 3:
                continue
            E0 = edges(c, sh0)
            e = target_edge(E0)
            body_nodt = {"locations": [vh.loc(*o), vh.loc(*d)], "costing": "auto", "directions_type": "none"}
            base_nodt = c.post("route", body_nodt)[1]["trip"]["legs"][0]["shape"]
            tt.apply([(e["id"], None, True)])
            st, s1, sh1, dt1 = vh.route(c, o, d)
            row = {"base_s": round(s0["time"]), "km": s0["length"], "edge_km": e["length"], "status": st}
            if st == 200:
                E1 = edges(c, sh1)
                row.update(avoided=all(x["id"] != e["id"] for x in E1), new_s=round(s1["time"]),
                           changed=sh1 != sh0, first_route_ms=round(dt1 * 1000, 1))
            # without date_time the overlay is ignored: this is what a naive client would see
            body = {"locations": [vh.loc(*o), vh.loc(*d)], "costing": "auto", "directions_type": "none"}
            st2, js2, _ = c.post("route", body_nodt)
            row["no_date_time_ignores_closure"] = st2 == 200 and js2["trip"]["legs"][0]["shape"] == base_nodt
            # the opposite direction of the same road must stay open (closures are per directed edge)
            st3, s3, sh3, _ = vh.route(c, d, o)
            tt.apply([(e["id"], None, False)])
            st4, s4, sh4, _ = vh.route(c, d, o)
            row["reverse_unchanged_by_forward_closure"] = (st3 == 200 and st4 == 200 and sh3 == sh4)
            st5, s5, sh5, _ = vh.route(c, o, d)
            row["restored_after_clear"] = sh5 == sh0
            rows.append(row)
        ok = [r for r in rows if r["status"] == 200]
        out["closure_rows"] = len(rows)
        out["closure"] = {
            "pairs": len(rows), "route_exists": len(ok),
            "avoided_closed_edge": sum(r.get("avoided", False) for r in ok),
            "route_changed": sum(r.get("changed", False) for r in ok),
            "no_date_time_ignores_closure": sum(r["no_date_time_ignores_closure"] for r in rows),
            "reverse_direction_unaffected": sum(r["reverse_unchanged_by_forward_closure"] for r in rows),
            "restored_after_clear": sum(r["restored_after_clear"] for r in rows),
            "extra_time_s_p50": stats.median(r["new_s"] - r["base_s"] for r in ok),
            "extra_time_s_p90": pct([r["new_s"] - r["base_s"] for r in ok], 0.9),
        }
        print("closure", out["closure"], flush=True)

        # ---- B. single snapshot: closures ignore time, speeds fade out over one hour ----------------
        snap = {k: 0 for k in ("pairs", "closed_now", "closed_in_90min", "slow_now", "slow_in_30min", "slow_in_90min",
                               "slow_no_date_time")}
        for o_lon, o_lat, d_lon, d_lat in pairs[400:900]:
            if snap["pairs"] >= 40:
                break
            o, d = (o_lon, o_lat), (d_lon, d_lat)
            st, s0, sh0, _ = vh.route(c, o, d)
            if st != 200 or s0["length"] < 3:
                continue
            e = target_edge(edges(c, sh0))
            snap["pairs"] += 1

            def avoided(extra, closed, kph=None):
                """True if the route in this time mode reacts to the overlay (route differs from the same
                mode without overlay), measured against the same request without the overlay."""
                body = {"locations": [vh.loc(*o), vh.loc(*d)], "costing": "auto", "directions_type": "none", **extra}
                st, js, _ = c.post("route", body)
                ref = js["trip"]["legs"][0]["shape"]
                tt.apply([(e["id"], kph, closed)])
                st, js, _ = c.post("route", body)
                tt.apply([(e["id"], None, False)])
                return st == 200 and js["trip"]["legs"][0]["shape"] != ref

            snap["closed_now"] += bool(avoided(vh.CURRENT, True))
            snap["closed_in_90min"] += bool(avoided(vh.depart_at(90), True))
            snap["slow_now"] += bool(avoided(vh.CURRENT, False, 4))
            snap["slow_in_30min"] += bool(avoided(vh.depart_at(30), False, 4))
            snap["slow_in_90min"] += bool(avoided(vh.depart_at(90), False, 4))
            snap["slow_no_date_time"] += bool(avoided({}, False, 4))
        out["snapshot_semantics"] = snap
        print("snapshot", snap, flush=True)

        # ---- C. publish cost: in-place edits, 100 and 1,000 changed edges -----------------------------
        all_edges = [(base, n) for base, (_, n) in tt.tiles.items()]
        weights = [n for _, n in all_edges]

        def random_changes(n):
            res = []
            for _ in range(n):
                (base, cnt) = rng.choices(all_edges, weights)[0]
                b = vh.GraphId(base)
                gid = vh.GraphId(b.tileid(), b.level(), rng.randrange(cnt)).value
                closed = rng.random() < 0.5
                res.append((gid, None if closed else rng.choice([4, 8, 12, 20]), closed))
            return res

        # sanity: GraphId(base) + (id << 25) must decode back to (tile, level, id)
        probe = vh.GraphId(random_changes(1)[0][0])
        assert probe.tile_base().value in tt.tiles, "edge id packing wrong"
        pub = {}
        for n in (100, 1000):
            apply_ms, flush_ms = [], []
            for _ in range(30):
                ch = random_changes(n)
                t0 = time.perf_counter()
                tt.apply(ch)
                t1 = time.perf_counter()
                tt.flush()
                t2 = time.perf_counter()
                apply_ms.append((t1 - t0) * 1000)
                flush_ms.append((t2 - t1) * 1000)
                tt.apply([(g, None, False) for g, _, _ in ch])
            pub[f"inplace_{n}"] = {"apply_ms_p50": round(stats.median(apply_ms), 3), "apply_ms_max": round(max(apply_ms), 3),
                                   "msync_ms_p50": round(stats.median(flush_ms), 3)}
        out["publish_inplace"] = pub
        print("publish in place", pub, flush=True)

        # ---- D. visibility latency: write one closure, poll until the router avoids it -----------------
        vis = []
        for o_lon, o_lat, d_lon, d_lat in pairs[900:1500]:
            if len(vis) >= 25:
                break
            o, d = (o_lon, o_lat), (d_lon, d_lat)
            st, s0, sh0, _ = vh.route(c, o, d)
            if st != 200 or s0["length"] < 3:
                continue
            e = target_edge(edges(c, sh0))
            tt.apply([(e["id"], None, True)])
            t_w = time.perf_counter()
            polls = 0
            while True:
                polls += 1
                st, s1, sh1, _ = vh.route(c, o, d)
                if sh1 != sh0 or polls > 50:
                    break
            vis.append({"ms": round((time.perf_counter() - t_w) * 1000, 1), "polls": polls})
            tt.apply([(e["id"], None, False)])
        out["visibility"] = {"trials": len(vis), "first_poll_already_new": sum(v["polls"] == 1 for v in vis),
                             "ms_p50": stats.median(v["ms"] for v in vis), "ms_max": max(v["ms"] for v in vis)}
        print("visibility", out["visibility"], flush=True)

        # ---- E. atomic rename of a new traffic.tar is NOT seen by a running router -----------------------
        o, d = (pairs[0][0], pairs[0][1]), (pairs[0][2], pairs[0][3])
        st, s0, sh0, _ = vh.route(c, o, d)
        e = target_edge(edges(c, sh0))
        new = G / "traffic_new.tar"
        t0 = time.perf_counter()
        shutil.copyfile(G / "traffic.tar", new)
        t_copy = time.perf_counter() - t0
        nt = vh.TrafficTar(new)
        nt.apply([(e["id"], None, True)])
        nt.flush()
        nt.close()
        t0 = time.perf_counter()
        os.replace(new, work_tar)
        t_rename = time.perf_counter() - t0
        st, s1, sh1, _ = vh.route(c, o, d)
        seen_after_rename = sh1 != sh0
        rename_info = {"copy_skeleton_s": round(t_copy, 3), "rename_ms": round(t_rename * 1000, 3),
                       "running_router_sees_renamed_file": seen_after_rename}
        tt.close()
    # restart to pick the renamed file up
    t0 = time.perf_counter()
    with vh.Service(G, 8301, G / "valhalla_tiles.tar", work_tar, concurrency=2, name="exp_overlay") as svc:
        c = vh.Client(8301)
        t_ready = time.perf_counter() - t0
        st, s1, sh1, dt_first = vh.route(c, o, d)
        rename_info.update(restart_to_ready_s=round(t_ready, 2), first_route_after_restart_ms=round(dt_first * 1000, 1),
                           router_sees_file_after_restart=sh1 != sh0)
    out["publish_by_rename"] = rename_info
    print("rename", rename_info, flush=True)

    (RES / "overlay.json").write_text(json.dumps(out, indent=1))
    print("wrote", RES / "overlay.json")


if __name__ == "__main__":
    main()
