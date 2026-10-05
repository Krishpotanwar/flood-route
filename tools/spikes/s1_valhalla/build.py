"""Build Valhalla tiles (+ tile extract + empty traffic.tar skeleton) from an OSM PBF, with timings.

  python build.py NAME PBF [--admin PATH | --build-admins] [--bbox minx,miny,maxx,maxy]
                  [--no-node-ids] [--jobs 4]

Output under $S1_WORK/NAME (default ./work/NAME):
  tiles/            valhalla tile directory
  valhalla_tiles.tar  read-only tile extract (shared by every router instance)
  traffic.tar       all-zero overlay skeleton, one fixed-size tile per graph tile
  build.json        wall seconds, user+sys CPU seconds and peak RSS per step
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import vh


def run(label, cmd, log, steps):
    t0 = time.perf_counter()
    with open(log, "w") as lf:
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
        _, status, ru = os.wait4(p.pid, 0)
    wall = time.perf_counter() - t0
    rc = os.waitstatus_to_exitcode(status)
    steps[label] = {"wall_s": round(wall, 1), "cpu_s": round(ru.ru_utime + ru.ru_stime, 1),
                    "peak_rss_mb": round(ru.ru_maxrss / 1024), "rc": rc}
    print(label, steps[label], flush=True)
    if rc:
        sys.exit(f"{label} failed, see {log}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("pbf")
    ap.add_argument("--admin", default="")
    ap.add_argument("--build-admins", action="store_true")
    ap.add_argument("--bbox", default="")
    ap.add_argument("--no-node-ids", action="store_true")
    ap.add_argument("--all-node-ids", action="store_true", help="keep_all_osm_node_ids: every shape node, not only edge ends")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()

    root = Path(os.environ.get("S1_WORK", "work")).resolve() / a.name
    root.mkdir(parents=True, exist_ok=True)
    tiles = root / "tiles"
    admin = Path(a.admin).resolve() if a.admin else root / "admin.sqlite"
    steps = {}
    # the config points at tile_dir for the build and at the extract afterwards
    cfg_path = vh.write_config(
        vh.make_config(tiles, admin=admin if (a.admin or a.build_admins) else "",
                       keep_osm_node_ids=not a.no_node_ids, keep_all_osm_node_ids=a.all_node_ids,
                       concurrency=a.jobs), root / "build.json.cfg")
    bin_ = vh.BIN
    if a.build_admins:
        run("admins", [bin_ / "valhalla_build_admins", "-c", cfg_path, a.pbf], root / "admins.log", steps)
    run("tiles", [bin_ / "valhalla_build_tiles", "-c", cfg_path, "-j", str(a.jobs), a.pbf],
        root / "tiles.log", steps)
    cmd = [Path(sys.executable).parent / "valhalla_build_extract", "-c", cfg_path, "-O", "-t",
           "--inline-config", json.dumps({"mjolnir": json.loads(Path(cfg_path).read_text())["mjolnir"]
                                          | {"tile_extract": str(root / "valhalla_tiles.tar"),
                                             "traffic_extract": str(root / "traffic.tar")}})]
    if a.bbox:
        cmd += ["--bbox", a.bbox]
    run("extract+traffic_skeleton", cmd, root / "extract.log", steps)
    out = {"name": a.name, "pbf": a.pbf, "pbf_mb": round(os.path.getsize(a.pbf) / 2**20),
           "keep_osm_node_ids": not a.no_node_ids, "keep_all_osm_node_ids": a.all_node_ids, "bbox": a.bbox,
           "steps": steps,
           "tiles_dir_mb": round(sum(f.stat().st_size for f in tiles.rglob("*.gph")) / 2**20),
           "tar_mb": round((root / "valhalla_tiles.tar").stat().st_size / 2**20),
           "traffic_tar_mb": round((root / "traffic.tar").stat().st_size / 2**20, 1)}
    (root / "build.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
