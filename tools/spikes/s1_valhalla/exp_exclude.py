"""S1 question 6: exclude_polygons behaviour, limits and latency cost.

  S1_WORK=<work dir with blr/ and data/> python exp_exclude.py        -> results/exclude.json
"""
import json
import math
import os
import shutil
import statistics as stats
from pathlib import Path

import vh

WORK = Path(os.environ["S1_WORK"])
G = WORK / "blr"
RES = Path(__file__).parent / "results"
RES.mkdir(exist_ok=True)
pairs = json.loads((WORK / "data" / "od_pairs.json").read_text())


def box_ring(lon, lat, half_m):
    dy = half_m / 111320.0
    dx = half_m / (111320.0 * math.cos(math.radians(lat)))
    return [[lon - dx, lat - dy], [lon + dx, lat - dy], [lon + dx, lat + dy], [lon - dx, lat + dy], [lon - dx, lat - dy]]


def seg_hits_ring(a, b, ring):
    """Liang-Barsky: does segment a-b touch the axis-aligned box ring? (lon, lat) tuples."""
    x0, y0 = ring[0]
    x1, y1 = ring[2]
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def route_hits(shape, ring):
    pts = vh.decode_polyline6(shape)
    return any(seg_hits_ring(a, b, ring) for a, b in zip(pts, pts[1:]))


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def mid_point(shape):
    pts = vh.decode_polyline6(shape)
    return pts[len(pts) // 2]


def post_route(c, o, d, polys=None, extra=None):
    body = {"locations": [vh.loc(*o), vh.loc(*d)], "costing": "auto", "directions_type": "none", **vh.CURRENT, **(extra or {})}
    if polys is not None:
        body["exclude_polygons"] = polys
    return c.post("route", body)


def main():
    out = {}
    tar = G / "traffic_excl.tar"
    shutil.copyfile(G / "traffic.tar", tar)
    # default limits first (this is what a stock server enforces)
    with vh.Service(G, 8401, G / "valhalla_tiles.tar", tar, concurrency=2, name="excl_default") as svc:
        c = vh.Client(8401)
        # choose a reference trip of a few km
        ref = None
        for p in pairs:
            o, d = (p[0], p[1]), (p[2], p[3])
            st, js, _ = post_route(c, o, d)
            if st == 200 and 4 <= js["trip"]["legs"][0]["summary"]["length"] <= 9:
                ref = (o, d, js["trip"]["legs"][0]["shape"], js["trip"]["legs"][0]["summary"])
                break
        o, d, sh0, s0 = ref
        mid = mid_point(sh0)
        out["reference_trip"] = {"km": s0["length"], "s": round(s0["time"])}

        # (a) size and precision: a box centred on the route centreline, and boxes offset from it
        sizes = {}
        for half in (0.5, 1, 2, 5, 10, 25):
            ring = box_ring(*mid, half)
            st, js, dt = post_route(c, o, d, [ring])
            sizes[f"on_centreline_half_{half}m"] = {"status": st, "avoids": st == 200 and not route_hits(js["trip"]["legs"][0]["shape"], ring)}
        # a box beside the road: shift north by 12 m and make it 3 m wide (does not touch the centreline)
        for shift_m in (4, 8, 12, 20):
            lon, lat = mid[0], mid[1] + shift_m / 111320.0
            ring = box_ring(lon, lat, 1.0)
            st, js, dt = post_route(c, o, d, [ring])
            same = st == 200 and js["trip"]["legs"][0]["shape"] == sh0
            sizes[f"beside_road_{shift_m}m_half_1m"] = {"status": st, "route_unchanged": same}
        out["size_and_precision"] = sizes
        print("size/precision", json.dumps(sizes), flush=True)

        # (b) direction independence: same polygon, reverse trip
        ring = box_ring(*mid, 15)
        st, js, _ = post_route(c, d, o)
        base_rev = js["trip"]["legs"][0]["shape"]
        rev_uses = route_hits(base_rev, ring)
        st2, js2, _ = post_route(c, d, o, [ring])
        out["direction"] = {"reverse_baseline_crosses_box": rev_uses,
                            "reverse_with_polygon_avoids": st2 == 200 and not route_hits(js2["trip"]["legs"][0]["shape"], ring)}

        # (c) origin or destination inside the polygon, and polygons that wall the destination in
        res = {}
        for name, centre in (("origin", o), ("destination", d)):
            ring = box_ring(*centre, 20)
            st, js, dt = post_route(c, o, d, [ring])
            res[f"{name}_inside_polygon"] = {"status": st, "error_code": js.get("error_code"), "error": js.get("error")} if st != 200 else {"status": st}
        ring = box_ring(*d, 250)
        st, js, dt = post_route(c, o, d, [ring])
        res["destination_inside_250m_polygon"] = {"status": st, "error_code": js.get("error_code"), "error": js.get("error")} if st != 200 else {"status": st}
        out["endpoints"] = res
        print("endpoints", json.dumps(res), flush=True)

        # (d) limits: stock defaults are 10 km total perimeter and 100 vertices
        lim = {}
        for n_poly, half in ((1, 400), (1, 1250), (1, 1300), (20, 60), (41, 30), (42, 30)):
            polys = []
            for i in range(n_poly):
                lon, lat = mid[0] + i * 0.002, mid[1]
                polys.append(box_ring(lon, lat, half))
            perim = n_poly * 8 * half
            st, js, dt = post_route(c, o, d, polys)
            lim[f"{n_poly}x_half{half}m_perimeter{perim}m"] = {"status": st, "error_code": js.get("error_code"), "error": (js.get("error") or "")[:90]}
        for nv in (99, 100, 101, 150):
            ring = [[mid[0] + 0.0005 * math.cos(2 * math.pi * k / nv), mid[1] + 0.0005 * math.sin(2 * math.pi * k / nv)] for k in range(nv)]
            st, js, dt = post_route(c, o, d, [ring])
            lim[f"one_polygon_{nv}_vertices"] = {"status": st, "error_code": js.get("error_code"), "error": (js.get("error") or "")[:90]}
        out["limits_default_config"] = lim
        print("limits", json.dumps(lim), flush=True)

    # raised limits for the latency scaling run
    with vh.Service(G, 8402, G / "valhalla_tiles.tar", tar, concurrency=2, name="excl_raised",
                    max_exclude_polygons_length=2_000_000, max_exclude_polygons_vertices=100_000) as svc:
        c = vh.Client(8402)
        sample = []
        for p in pairs:
            o, d = (p[0], p[1]), (p[2], p[3])
            st, js, _ = post_route(c, o, d)
            if st == 200 and js["trip"]["legs"][0]["summary"]["length"] >= 2:
                sample.append((o, d, js["trip"]["legs"][0]["shape"]))
            if len(sample) >= 150:
                break
        import random
        rng = random.Random(5)
        lat_tab = {}
        for variant in ("on_route", "off_route"):
            for n in (0, 1, 5, 20, 50, 100):
                ms, changed, fail = [], 0, 0
                for o, d, sh in sample:
                    pts = vh.decode_polyline6(sh)
                    polys = []
                    for _ in range(n):
                        if variant == "on_route":
                            lon, lat = pts[rng.randrange(len(pts))]
                        else:  # 150-400 m beside a random shape point: pure bookkeeping cost, route should not change
                            lon, lat = pts[rng.randrange(len(pts))]
                            ang = rng.uniform(0, 2 * math.pi)
                            r = rng.uniform(150, 400)
                            lon += r * math.cos(ang) / (111320 * math.cos(math.radians(lat)))
                            lat += r * math.sin(ang) / 111320
                        polys.append(box_ring(lon, lat, 30))
                    st, js, dt = post_route(c, o, d, polys if n else None)
                    if st == 200:
                        ms.append(dt * 1000)
                        changed += js["trip"]["legs"][0]["shape"] != sh
                    else:
                        fail += 1
                lat_tab[f"{variant}_{n}_polygons"] = {"ms_p50": round(stats.median(ms), 1), "ms_p95": round(pct(ms, 0.95), 1),
                                                      "route_changed": changed, "no_route_or_error": fail, "n": len(sample)}
                print(variant, n, lat_tab[f"{variant}_{n}_polygons"], flush=True)
                if variant == "off_route" and n == 0:
                    continue
        out["latency_one_client"] = lat_tab

    (RES / "exclude.json").write_text(json.dumps(out, indent=1))
    print("wrote", RES / "exclude.json")


if __name__ == "__main__":
    main()
