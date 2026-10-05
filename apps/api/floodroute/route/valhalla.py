"""Minimal Valhalla /route client and response mapping.

Request and response shapes follow https://valhalla.github.io/valhalla/api/route/api-reference/
(read 2026-10-05). The mapping is checked only against a hand-written sample until spike S1
runs it against a live Valhalla.

ponytail: /route returns maneuvers, not graph edges. A maneuver can span several segments, so an
underpass inside a long maneuver is invisible to `segment_of`. S1 should replace this with an
edge walk (trace_attributes) and the segment_edge table; Route and validate.py do not change.
Also for S1: Valhalla caps the size of exclude_polygons in its service limits (recalled, [U]); up
to 3 re-queries of box rings per request may need that limit raised.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime

import httpx

from floodroute.route.models import Edge, LatLon, Polygon, Route

# Costing per vehicle class (TRD 7.1). ambulance and heavy share an instance but not a costing.
COSTING = {"two_wheeler": "motor_scooter", "car": "auto", "ambulance": "auto", "heavy": "truck"}

# Valhalla error_code values that mean "no path" (docs error table): 170 unconnected regions,
# 171 no suitable edges near location, 441 location unreachable, 442 no path found. The JSON
# field name `error_code` is recalled, not in the API page [U]: S1 to confirm on a live server.
NO_ROUTE_CODES = frozenset({170, 171, 441, 442})

SegmentOf = Callable[[Sequence[LatLon]], int | None]


def decode_polyline6(s: str) -> list[LatLon]:
    """Decode Valhalla's encoded polyline (6 digits, lat first) into (lat, lon) pairs."""
    out: list[LatLon] = []
    i, n = 0, len(s)
    lat = lon = 0
    while i < n:
        for axis in (0, 1):
            shift = result = 0
            while True:
                if i >= n:
                    raise ValueError("truncated polyline")
                b = ord(s[i]) - 63
                i += 1
                if not 0 <= b < 64:
                    raise ValueError(f"invalid polyline character {s[i - 1]!r}")
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        out.append((lat / 1e6, lon / 1e6))
    return out


def encode_polyline6(points: Iterable[LatLon]) -> str:
    out: list[str] = []
    plat = plon = 0
    for lat, lon in points:
        la, lo = round(lat * 1e6), round(lon * 1e6)
        for d in (la - plat, lo - plon):
            v = ~(d << 1) if d < 0 else d << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        plat, plon = la, lo
    return "".join(out)


def request_body(
    origin: LatLon, dest: LatLon, vclass: str, exclude_polygons: Sequence[Polygon] = ()
) -> dict:
    body: dict = {
        "locations": [{"lat": origin[0], "lon": origin[1]}, {"lat": dest[0], "lon": dest[1]}],
        "costing": COSTING[vclass],
        "directions_type": "maneuvers",
        "units": "kilometers",
    }
    if exclude_polygons:  # exterior rings as [lon, lat] pairs
        body["exclude_polygons"] = [[[lon, lat] for lat, lon in ring] for ring in exclude_polygons]
    return body


def route_from_response(resp: dict, segment_of: SegmentOf) -> Route:
    """Map a /route JSON response to a Route, one Edge per maneuver. Raises ValueError if the
    response is not shaped as documented (fail closed: never guess a route)."""
    try:
        edges: list[Edge] = []
        for leg in resp["trip"]["legs"]:
            shape = decode_polyline6(leg["shape"])
            for m in leg["maneuvers"]:
                seconds, km = float(m["time"]), float(m["length"])
                if seconds == 0 and km == 0:  # depart and arrive markers
                    continue
                i, j = m["begin_shape_index"], m["end_shape_index"]
                if not 0 <= i <= j < len(shape):
                    raise ValueError(
                        f"maneuver indexes {i}..{j} outside a {len(shape)} point shape"
                    )
                geometry = tuple(shape[i : j + 1])
                edges.append(Edge(segment_of(geometry), geometry, seconds, km * 1000.0))
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"unexpected Valhalla response: {exc!r}") from exc
    if not edges:
        raise ValueError("Valhalla response has no travel")
    return Route(tuple(edges))


class ValhallaRouter:
    """A `router` for validate.plan: POST /route, None when Valhalla finds no path.

    Any other failure (timeout, 5xx, bad body) raises, so no route is ever returned unchecked.
    `segment_of` has no default on purpose: without it every edge would read as unassessed.
    """

    def __init__(
        self,
        base_url: str,
        segment_of: SegmentOf,
        client: httpx.Client | None = None,
        timeout_s: float = 3.0,
    ):
        self.segment_of = segment_of
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout_s)

    def __call__(
        self,
        origin: LatLon,
        dest: LatLon,
        vclass: str,
        depart: datetime,  # ponytail: unused, the traffic overlay is time-invariant (TRD 7.2)
        exclude_polygons: Sequence[Polygon] = (),
    ) -> Route | None:
        r = self.client.post("/route", json=request_body(origin, dest, vclass, exclude_polygons))
        if r.status_code == 400 and _error_code(r) in NO_ROUTE_CODES:
            return None
        r.raise_for_status()
        return route_from_response(r.json(), self.segment_of)


def _error_code(r: httpx.Response) -> int | None:
    try:
        return int(r.json()["error_code"])
    except (ValueError, KeyError, TypeError):
        return None
