"""Valhalla /route followed by a strict graph-edge walk for flood assessment.

https://valhalla.github.io/valhalla/api/map-matching/ documents edge_walk for prior route shapes.
A failed walk never falls back to maneuvers or map matching: either would hide or change roads.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from math import isclose, isfinite

import httpx

from floodroute.route.models import IST, Edge, LatLon, Polygon, Route

# Costing per vehicle class (TRD 7.1). ambulance and heavy share an instance but not a costing.
COSTING = {"two_wheeler": "motor_scooter", "car": "auto", "ambulance": "auto", "heavy": "truck"}

# Valhalla error_code values that mean "no path" (docs error table): 170 unconnected regions,
# 171 no suitable edges near location, 441 location unreachable, 442 no path found, plus the
# exclude_polygons service limits: 167 max-avoid-edges/area exceeded, 176 max avoid locations.
# The JSON field name `error_code` is recalled, not in the API page [U]: S1 to confirm on a live server.
# 167/176 map to no-route (fail closed) instead of raising to a 502 on the flooded path.
NO_ROUTE_CODES = frozenset({167, 171, 170, 176, 441, 442})

SegmentOf = Callable[[int, Sequence[LatLon]], int | None]
TRACE_ATTRIBUTES = (
    "shape",
    "edge.way_id",
    "edge.begin_shape_index",
    "edge.end_shape_index",
    "edge.length",
    "node.elapsed_time",
)


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
    origin: LatLon,
    dest: LatLon,
    vclass: str,
    exclude_polygons: Sequence[Polygon] = (),
    depart: datetime | None = None,
) -> dict:
    body: dict = {
        "locations": [{"lat": origin[0], "lon": origin[1]}, {"lat": dest[0], "lon": dest[1]}],
        "costing": COSTING[vclass],
        "directions_type": "maneuvers",
        "units": "kilometers",
    }
    if depart is not None:
        if depart.tzinfo is None:
            raise ValueError("depart must be timezone-aware, naive input never reads as UTC")
        # Valhalla expects the origin's local clock; every supported Indian city uses IST.
        dt = depart.astimezone(IST)
        body["date_time"] = {"type": 1, "value": dt.strftime("%Y-%m-%dT%H:%M")}
    else:
        body["date_time"] = {"type": 0}
    if exclude_polygons:  # exterior rings as [lon, lat] pairs
        body["exclude_polygons"] = [[[lon, lat] for lat, lon in ring] for ring in exclude_polygons]
    return body


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Valhalla travel values must be numbers")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("Valhalla travel value exceeds finite precision") from exc
    if not isfinite(number) or number < 0:
        raise ValueError("Valhalla travel values must be finite and nonnegative")
    return number


def route_from_response(resp: dict, traces: Sequence[dict], segment_of: SegmentOf) -> Route:
    """Map every traced graph edge, requiring complete geometry and consistent cumulative ETA."""
    try:
        trip = resp["trip"]
        legs = trip["legs"]
        if trip["units"] != "kilometers" or not legs or len(legs) != len(traces):
            raise ValueError("Valhalla route units or trace count do not match")
        edges: list[Edge] = []
        leg_total = 0.0
        previous_end = None
        for leg, trace in zip(legs, traces, strict=True):
            shape = decode_polyline6(leg["shape"])
            if (
                len(shape) < 2
                or trace["units"] != "kilometers"
                or shape != decode_polyline6(trace["shape"])
            ):
                raise ValueError("Valhalla trace geometry differs from its route")
            if any(not (-90 <= lat <= 90 and -180 <= lon <= 180) for lat, lon in shape):
                raise ValueError("Valhalla shape coordinates are outside geographic bounds")
            if previous_end is not None and previous_end != shape[0]:
                raise ValueError("Valhalla route legs are disconnected")
            previous_end = shape[-1]
            traced_edges = trace["edges"]
            elapsed = 0.0
            cursor = 0
            for e in traced_edges:
                i, j, way_id = e["begin_shape_index"], e["end_shape_index"], e["way_id"]
                if (
                    type(i) is not int
                    or type(j) is not int
                    or type(way_id) is not int
                    or way_id <= 0
                    or i != cursor
                    or not i < j < len(shape)
                ):
                    raise ValueError("Valhalla graph edges do not cover the route contiguously")
                cumulative = _number(e["end_node"]["elapsed_time"])
                if cumulative < elapsed:
                    raise ValueError("Valhalla cumulative edge ETA decreased")
                km = _number(e["length"])
                geometry = tuple(shape[i : j + 1])
                edges.append(
                    Edge(segment_of(way_id, geometry), geometry, cumulative - elapsed, km * 1000.0)
                )
                elapsed, cursor = cumulative, j
            leg_time = _number(leg["summary"]["time"])
            # Valhalla serializes milliseconds; cumulative float arithmetic differs slightly
            # between routing and tracing (0.005s across the recorded 102-edge reference).
            if (
                cursor != len(shape) - 1
                or elapsed <= 0
                or not isclose(
                    elapsed, leg_time, rel_tol=0, abs_tol=0.01 + 0.001 * len(traced_edges)
                )
            ):
                raise ValueError("Valhalla graph edges do not cover the route geometry and ETA")
            leg_total += leg_time
        if not isclose(
            leg_total, _number(trip["summary"]["time"]), rel_tol=0, abs_tol=0.001 * len(legs)
        ):
            raise ValueError("Valhalla leg ETAs do not match the trip")
    except (KeyError, TypeError, IndexError, OverflowError) as exc:
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
        depart: datetime,
        exclude_polygons: Sequence[Polygon] = (),
    ) -> Route | None:
        body = request_body(origin, dest, vclass, exclude_polygons=exclude_polygons, depart=depart)
        r = self.client.post("/route", json=body)
        if r.status_code == 400 and _error_code(r) in NO_ROUTE_CODES:
            return None
        r.raise_for_status()
        try:
            response = r.json()
            legs = response["trip"]["legs"]
            traces = []
            for leg in legs:
                trace_body = {
                    "encoded_polyline": leg["shape"],
                    "shape_match": "edge_walk",
                    "filters": {"attributes": list(TRACE_ATTRIBUTES), "action": "include"},
                    **{k: body[k] for k in ("costing", "date_time", "units")},
                }
                traced = self.client.post("/trace_attributes", json=trace_body)
                traced.raise_for_status()
                traces.append(traced.json())
            return route_from_response(response, traces, self.segment_of)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            # A malformed upstream response is a routing failure, not invalid citizen input.
            raise RuntimeError(f"unexpected Valhalla response: {exc!r}") from exc


def _error_code(r: httpx.Response) -> int | None:
    try:
        return int(r.json()["error_code"])
    except (ValueError, KeyError, TypeError):
        return None
