"""Builders shared by the route tests. Plain functions, no fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta

from floodroute.route.models import (
    HORIZONS,
    IST,
    Edge,
    Route,
    RouteRequest,
    SegmentRisk,
)
from floodroute.route.validate import Ctx, state_from_p

T0 = datetime(2027, 5, 18, 17, 40, tzinfo=IST)  # request time, forecast issue time
LAT, LON = 12.93, 77.62  # Bengaluru, synthetic test geometry only


def mins(m: float) -> timedelta:
    return timedelta(minutes=m)


def edge(seg: int | None, minutes: float = 1.0, *, length_m: float = 100.0, turn_off: bool = True,
         dlon: float = 0.0) -> Edge:  # fmt: skip
    """A short north-going edge; dlon shifts it east so different segments do not overlap."""
    geometry = ((LAT, LON + dlon), (LAT + 0.0009, LON + dlon))
    return Edge(seg, geometry, minutes * 60.0, length_m, turn_off)


def route(*edges: Edge) -> Route:
    return Route(tuple(edges))


def risk(p, *, issued: datetime = T0, states=None, confidence="medium", age=60) -> SegmentRisk:
    """p is one number (flat over the horizons) or {horizon: p}."""
    ps = {h: p for h in HORIZONS} if isinstance(p, (int, float)) else dict(p)
    sts = states or {h: state_from_p(v) for h, v in ps.items()}
    if isinstance(sts, str):
        sts = {h: sts for h in HORIZONS}
    return SegmentRisk(issued, ps, dict(sts), confidence, age)


def risk_for(table: dict):
    """A RiskFor over {segment_id: SegmentRisk}; anything missing is outside the inventory."""
    return lambda seg, vclass: table.get(seg)


def request(vclass="car", profile="citizen", depart: datetime = T0, lang="en") -> RouteRequest:
    return RouteRequest(
        origin={"lat": 12.9166, "lon": 77.6101},
        destination={"lat": 12.9352, "lon": 77.6245},
        vclass=vclass,
        depart_at=depart,
        profile=profile,
        lang=lang,
    )


def ctx(table: dict, *, threshold=0.25, in_rain=True, now: datetime = T0, vclass="car") -> Ctx:
    return Ctx(risk_for(table), vclass, now, threshold, in_rain=in_rain)


class FakeRouter:
    """Records every call. `fn(call_number, polygons)` returns the Route (or None) to hand back."""

    def __init__(self, fn):
        self.fn = fn
        self.polygons: list[tuple] = []

    @property
    def calls(self) -> int:
        return len(self.polygons)

    def __call__(self, origin, dest, vclass, depart, exclude_polygons):
        self.polygons.append(tuple(exclude_polygons))
        return self.fn(self.calls, tuple(exclude_polygons))


# The FR-RT2 forecast: p crosses 0.25 exactly 10 min after the 30 min horizon, i.e. at t+40.
# logit(0.25) = -1.0986, which is 1/3 of the way from logit(0.10) to logit(0.75).
CLOSES_AT_40 = {0: 0.05, 30: 0.10, 60: 0.75, 120: 0.75}
