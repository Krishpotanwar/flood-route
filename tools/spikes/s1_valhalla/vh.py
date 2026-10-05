"""Shared helpers for spike S1: Valhalla config, traffic.tar overlay writer, tiny HTTP client.

Stdlib only, plus `valhalla` (pyvalhalla 3.9.0) for the default config and GraphId maths.
Layout facts below are verified against Valhalla 3.9.0 sources (valhalla/baldr/traffictile.h,
pyvalhalla's valhalla_build_extract.py), not guessed.
"""
import http.client
import json
import mmap
import os
import struct
import tarfile
import time
from pathlib import Path

import valhalla
from valhalla.baldr import GraphId  # noqa: F401 (re-exported)

BIN = Path(valhalla.PYVALHALLA_DIR) / "bin"

# --- traffic.tar layout -------------------------------------------------------------------
# tar: index.bin first, then one member per tile "L/AAA/BBB/CCC.gph".
# tile = 32-byte header "<2Q4I" (tile_id, last_update, directed_edge_count, version=3, 0, 0)
#        + directed_edge_count * 8-byte TrafficSpeed (bit-field, see pack_speed).
HDR = struct.Struct("<2Q4I")
UNKNOWN = 0  # all-zero record: breakpoint1 == 0 means "no live data", static speed is used


def pack_speed(kph: float | None, closed: bool = False) -> int:
    """TrafficSpeed as one little-endian uint64. kph has 2 kph resolution, 2..252.

    closed -> overall speed 0 with breakpoint1 255 (TrafficSpeed::closed()).
    kph None -> back to "no live data" (all zero).
    Single sub-segment covering the whole edge (breakpoint1 = 255), congestion unknown.
    """
    if kph is None and not closed:
        return 0
    enc = 0 if closed else max(1, min(126, round(kph / 2)))  # 127 is "unknown"
    # overall:7 s1:7 s2:7 s3:7 b1:8 b2:8 c1:6 c2:6 c3:6 incidents:1 spare:1
    return enc | enc << 7 | 127 << 14 | 127 << 21 | 255 << 28


def unpack_speed(v: int) -> dict:
    return {"overall_kph": (v & 127) * 2, "b1": (v >> 28) & 255, "closed": (v >> 28) & 255 != 0 and v & 127 == 0}


class TrafficTar:
    """In-place editor for a Valhalla traffic.tar through a shared writable mmap.

    The router maps the same file MAP_SHARED read-only, so stores here are visible to a running
    router with no restart and no graph rebuild.
    """

    def __init__(self, path):
        self.path = str(path)
        self.f = open(self.path, "r+b")
        self.mm = mmap.mmap(self.f.fileno(), 0)
        self.tiles = {}  # GraphId.value of tile base -> (offset of header, edge count)
        with tarfile.open(self.path, "r") as tar:
            for m in tar:
                if m.name.endswith(".gph"):
                    gid = GraphId.from_tile_path(m.name).value
                    n = HDR.unpack_from(self.mm, m.offset_data)[2]
                    self.tiles[gid] = (m.offset_data, n)

    def _off(self, edge_gid: int) -> int:
        g = GraphId(edge_gid)
        base, n = self.tiles[g.tile_base().value]
        if g.id() >= n:
            raise IndexError(f"edge {g} beyond tile edge count {n}")
        return base + HDR.size + 8 * g.id()

    def set(self, edge_gid: int, kph: float | None, closed: bool = False):
        struct.pack_into("<Q", self.mm, self._off(edge_gid), pack_speed(kph, closed))

    def get(self, edge_gid: int) -> int:
        return struct.unpack_from("<Q", self.mm, self._off(edge_gid))[0]

    def apply(self, changes):
        """changes: iterable of (edge_gid, kph|None, closed). Closures are written first, so any
        intermediate state is at least as conservative as the old or the new state."""
        ch = sorted(changes, key=lambda c: not c[2])
        stamp = int(time.time())
        touched = set()
        for gid, kph, closed in ch:
            self.set(gid, kph, closed)
            touched.add(GraphId(gid).tile_base().value)
        for t in touched:  # last_update is informational in 3.9.0 routing code
            struct.pack_into("<Q", self.mm, self.tiles[t][0] + 8, stamp)

    def flush(self):
        self.mm.flush()

    def clear(self):
        for off, n in self.tiles.values():
            self.mm[off + HDR.size: off + HDR.size + 8 * n] = bytes(8 * n)

    def close(self):
        self.mm.close()
        self.f.close()


# --- config ---------------------------------------------------------------------------------
def make_config(tile_dir, tile_extract="", traffic_extract="", admin="", port=8002, concurrency=4,
                keep_osm_node_ids=True, verbose=False, **service_limits):
    Path(tile_dir).mkdir(parents=True, exist_ok=True)
    cfg = valhalla.get_config(tile_extract="", tile_dir=tile_dir, verbose=verbose)
    m = cfg["mjolnir"]
    m.update(tile_extract=str(tile_extract), traffic_extract=str(traffic_extract), admin=str(admin),
             timezone="", landmarks="", transit_dir="", transit_feeds_dir="",
             keep_osm_node_ids=keep_osm_node_ids, concurrency=concurrency)
    cfg["additional_data"]["elevation"] = ""
    cfg["httpd"]["service"]["listen"] = f"tcp://*:{port}"
    for k in ("loki", "thor", "odin", "meili"):  # unique ipc sockets so several services can coexist
        cfg[k]["service"]["proxy"] = f"ipc:///tmp/vh_{port}_{k}"
    cfg["httpd"]["service"]["loopback"] = f"ipc:///tmp/vh_{port}_loopback"
    cfg["httpd"]["service"]["interrupt"] = f"ipc:///tmp/vh_{port}_interrupt"
    cfg["service_limits"].update(service_limits)
    return cfg


def write_config(cfg, path):
    Path(path).write_text(json.dumps(cfg, indent=1))
    return str(path)


# --- tiny HTTP client (keep-alive per instance) -------------------------------------------------
class Client:
    def __init__(self, port, host="127.0.0.1", timeout=120):
        self.c = http.client.HTTPConnection(host, port, timeout=timeout)

    def post(self, action, body):
        data = json.dumps(body)
        t0 = time.perf_counter()
        self.c.request("POST", f"/{action}", data, {"Content-Type": "application/json"})
        r = self.c.getresponse()
        raw = r.read()
        dt = time.perf_counter() - t0
        try:
            js = json.loads(raw)
        except ValueError:
            js = {"raw": raw[:200].decode("utf-8", "replace")}
        return r.status, js, dt


def decode_polyline6(s):
    """Valhalla polyline with 6 digits -> [(lon, lat)]."""
    out, i, lat, lon = [], 0, 0, 0
    while i < len(s):
        for which in (0, 1):
            shift = res = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                res |= (b & 31) << shift
                shift += 5
                if b < 32:
                    break
            d = ~(res >> 1) if res & 1 else res >> 1
            if which == 0:
                lat += d
            else:
                lon += d
        out.append((lon / 1e6, lat / 1e6))
    return out


def encode_polyline6(pts):
    """[(lon, lat)] -> Valhalla polyline with 6 digits."""
    out, plat, plon = [], 0, 0
    for lon, lat in pts:
        la, lo = round(lat * 1e6), round(lon * 1e6)
        for d in (la - plat, lo - plon):
            v = ~(d << 1) if d < 0 else d << 1
            while v >= 32:
                out.append(chr((32 | (v & 31)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        plat, plon = la, lo
    return "".join(out)


def haversine_m(a, b):
    from math import asin, cos, radians, sin, sqrt
    (lo1, la1), (lo2, la2) = a, b
    dla, dlo = radians(la2 - la1), radians(lo2 - lo1)
    h = sin(dla / 2) ** 2 + cos(radians(la1)) * cos(radians(la2)) * sin(dlo / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p


# --- running a router instance ----------------------------------------------------------------
import signal
import subprocess


class Service:
    """One valhalla_service process (own port, own traffic.tar, shared read-only tile tar)."""

    def __init__(self, work, port, tile_extract, traffic_extract, concurrency=4, name=None, **limits):
        self.port, self.concurrency, self.name = port, concurrency, name or f"svc{port}"
        self.cfg_path = Path(work) / f"{self.name}.cfg.json"
        cfg = make_config(Path(work) / "tiles", tile_extract=tile_extract, traffic_extract=traffic_extract,
                          port=port, concurrency=concurrency, **limits)
        write_config(cfg, self.cfg_path)
        self.log = open(Path(work) / f"{self.name}.log", "w")
        self.p = None

    def __enter__(self):
        self.p = subprocess.Popen([str(BIN / "valhalla_service"), str(self.cfg_path), str(self.concurrency)],
                                  stdout=self.log, stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < 120:
            try:
                st, js, _ = Client(self.port, timeout=2).post("status", {})
                if st == 200:
                    self.ready_s = time.time() - t0
                    return self
            except OSError:
                pass
            if self.p.poll() is not None:
                raise RuntimeError(f"valhalla_service exited early, see {self.log.name}")
            time.sleep(0.2)
        raise RuntimeError("valhalla_service did not become ready")

    def __exit__(self, *a):
        self.p.send_signal(signal.SIGTERM)
        try:
            self.p.wait(10)
        except subprocess.TimeoutExpired:
            self.p.kill()
        self.log.close()

    def smaps(self):
        """Rss and Pss (kB) of the whole service (parent + workers are threads of one process)."""
        out = {}
        for line in Path(f"/proc/{self.p.pid}/smaps_rollup").read_text().splitlines():
            k, _, v = line.partition(":")
            if k in ("Rss", "Pss", "Shared_Clean", "Private_Clean", "Private_Dirty", "Shared_Dirty"):
                out[k] = int(v.split()[0])
        return out


# --- request helpers --------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone

# Valhalla 3.9.0 ignores the whole live overlay (speeds AND closures) unless the request carries a
# date_time: speed_types "current" is dropped from the flow mask when time is absent.
# Verified: sif/autocost.cc unit-test table and an A/B run in exp_overlay.py.
CURRENT = {"date_time": {"type": 0}}


def depart_at(minutes_from_now: float) -> dict:
    """date_time depart_at (type 1). No tz database is configured, so Valhalla treats the string as UTC."""
    t = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return {"date_time": {"type": 1, "value": t.strftime("%Y-%m-%dT%H:%M")}}


def loc(lon, lat, **kw):
    return {"lon": lon, "lat": lat, **kw}


def route(client, o, d, costing="auto", extra=None, directions=False):
    """o, d are (lon, lat). Returns (status, summary_or_error, shape_or_None, seconds)."""
    body = {"locations": [loc(*o), loc(*d)], "costing": costing, **CURRENT, **(extra or {})}
    if not directions:
        body["directions_type"] = "none"
    st, js, dt = client.post("route", body)
    if st != 200:
        return st, js, None, dt
    leg = js["trip"]["legs"][0]
    return st, leg["summary"], leg["shape"], dt


TRACE_FILTERS = ["edge.id", "edge.way_id", "edge.begin_osm_node_id", "edge.end_osm_node_id", "edge.length",
                 "edge.speed", "edge.begin_shape_index", "edge.end_shape_index", "node.elapsed_time",
                 "node.type"]


def edges_of(client, shape, costing="auto", extra=None, filters=TRACE_FILTERS, shape_match="walk_or_snap"):
    """Edges of a route shape. Each edge: id (GraphId value), way_id, node_id (begin OSM node),
    end_node.node_id, end_node.elapsed_time (arrival at the end of the edge, incl. turn costs).
    edge_walk alone fails (error 443) on about 1% of routes, e.g. routes containing a U-turn;
    walk_or_snap (Valhalla's default) falls back to map matching, which is about 20x slower."""
    body = {"encoded_polyline": shape, "costing": costing, "shape_match": shape_match, **CURRENT,
            **(extra or {}), "filters": {"attributes": filters, "action": "include"}}
    st, js, dt = client.post("trace_attributes", body)
    return st, js, dt
