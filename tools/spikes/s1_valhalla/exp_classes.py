"""S1 question 5: three router instances (motor_scooter, auto, truck) share one read-only tile tar but
each has its own traffic.tar. Shows isolation of overlays and the memory actually shared.

  S1_WORK=<work dir with blr/ and data/> python exp_classes.py        -> results/classes.json
"""
import json
import os
import re
import shutil
from pathlib import Path

import vh

WORK = Path(os.environ["S1_WORK"])
G = WORK / "blr"
RES = Path(__file__).parent / "results"
RES.mkdir(exist_ok=True)
pairs = json.loads((WORK / "data" / "od_pairs.json").read_text())
CLASSES = {"motor_scooter": 8211, "auto": 8212, "truck": 8213}
TILES = G / "valhalla_tiles.tar"


def mapping_stats(pid, needle):
    """Rss/Pss/Shared of the mapping of one file, from /proc/PID/smaps."""
    blocks = re.split(r"\n(?=[0-9a-f]+-[0-9a-f]+ )", Path(f"/proc/{pid}/smaps").read_text())
    tot = {}
    for b in blocks:
        if needle in b.split("\n", 1)[0]:
            for k in ("Size", "Rss", "Pss", "Shared_Clean", "Private_Clean", "Shared_Dirty", "Private_Dirty"):
                m = re.search(rf"^{k}:\s+(\d+) kB", b, re.M)
                tot[k] = tot.get(k, 0) + (int(m.group(1)) if m else 0)
    return tot


def first_edge_mid(c, shape, costing):
    st, js, _ = vh.edges_of(c, shape, costing=costing)
    E = js["edges"]
    mid = [e for e in E[len(E) // 3: 2 * len(E) // 3] if e["speed"] >= 30] or E[len(E) // 3: 2 * len(E) // 3]
    return max(mid, key=lambda e: e["length"])


def main():
    out = {}
    tars = {}
    for cls in CLASSES:
        tars[cls] = G / f"traffic_{cls}.tar"
        shutil.copyfile(G / "traffic.tar", tars[cls])

    svcs = {cls: vh.Service(G, port, TILES, tars[cls], concurrency=2, name=f"cls_{cls}") for cls, port in CLASSES.items()}
    for s in svcs.values():
        s.__enter__()
    try:
        cl = {cls: vh.Client(port) for cls, port in CLASSES.items()}
        ed = {cls: vh.TrafficTar(tars[cls]) for cls in CLASSES}

        # warm every instance with the same 150 routes so the tile pages they use are resident
        for cls in CLASSES:
            for p in pairs[:150]:
                vh.route(cl[cls], (p[0], p[1]), (p[2], p[3]), costing=cls)
        mem = {}
        for cls, s in svcs.items():
            mem[cls] = {"process": s.smaps(), "tiles_tar": mapping_stats(s.p.pid, "valhalla_tiles.tar"),
                        "traffic_tar": mapping_stats(s.p.pid, f"traffic_{cls}.tar")}
        out["memory_kb"] = mem
        out["sum_rss_kb"] = sum(m["process"]["Rss"] for m in mem.values())
        out["sum_pss_kb"] = sum(m["process"]["Pss"] for m in mem.values())
        out["tile_tar_file_kb"] = TILES.stat().st_size // 1024
        print("memory", json.dumps({k: v["process"] for k, v in mem.items()}), out["sum_rss_kb"], out["sum_pss_kb"], flush=True)

        # isolation matrix
        iso = {"pairs": 0, "trials": 0, "target_class_avoids": 0, "other_classes_unchanged": 0, "other_trials": 0,
               "cross_costing_request_sees_overlay_of_the_instance": 0, "cross_trials": 0, "baselines_differ_between_classes": 0}
        for p in pairs[1000:1400]:
            if iso["pairs"] >= 30:
                break
            o, d = (p[0], p[1]), (p[2], p[3])
            base = {}
            for cls in CLASSES:
                st, s, sh, _ = vh.route(cl[cls], o, d, costing=cls)
                if st != 200:
                    break
                base[cls] = (s, sh)
            if len(base) < 3 or base["auto"][0]["length"] < 3:
                continue
            iso["pairs"] += 1
            iso["baselines_differ_between_classes"] += len({v[1] for v in base.values()}) > 1
            for cls in CLASSES:
                e = first_edge_mid(cl[cls], base[cls][1], cls)
                ed[cls].apply([(e["id"], None, True)])
                iso["trials"] += 1
                st, s, sh, _ = vh.route(cl[cls], o, d, costing=cls)
                st2, js2, _ = vh.edges_of(cl[cls], sh, costing=cls) if st == 200 else (0, {"edges": []}, 0)
                iso["target_class_avoids"] += st == 200 and all(x["id"] != e["id"] for x in js2["edges"])
                for other in CLASSES:
                    if other == cls:
                        continue
                    iso["other_trials"] += 1
                    st3, s3, sh3, _ = vh.route(cl[other], o, d, costing=other)
                    iso["other_classes_unchanged"] += st3 == 200 and sh3 == base[other][1]
                ed[cls].apply([(e["id"], None, False)])
            # the overlay belongs to the process, not to the costing: close an edge of the auto route in the
            # scooter instance's file, then ask the scooter instance for an auto route
            e = first_edge_mid(cl["auto"], base["auto"][1], "auto")
            ed["motor_scooter"].apply([(e["id"], None, True)])
            iso["cross_trials"] += 1
            st4, s4, sh4, _ = vh.route(cl["motor_scooter"], o, d, costing="auto")
            st5, s5, sh5, _ = vh.route(cl["auto"], o, d, costing="auto")
            ed["motor_scooter"].apply([(e["id"], None, False)])
            avoid = False
            if st4 == 200:
                avoid = all(x["id"] != e["id"] for x in vh.edges_of(cl["motor_scooter"], sh4, costing="auto")[1]["edges"])
            iso["cross_costing_request_sees_overlay_of_the_instance"] += avoid and sh5 == base["auto"][1]
        out["isolation"] = iso
        print("isolation", iso, flush=True)
        for t in ed.values():
            t.close()
    finally:
        for s in svcs.values():
            s.__exit__()
    (RES / "classes.json").write_text(json.dumps(out, indent=1))
    print("wrote", RES / "classes.json")


if __name__ == "__main__":
    main()
