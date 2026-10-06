"""Route domain types (frozen dataclasses) and the TRD 8.2 request/response models (pydantic).

Domain types are plain dataclasses: they are built by trusted code, validated once on
construction, and fail closed (ValueError) on malformed risk data instead of guessing.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

VClass = Literal["two_wheeler", "car", "ambulance", "heavy"]
Profile = Literal["citizen", "ambulance"]
State = Literal["clear", "watch", "risky", "impassable", "unknown"]
Confidence = Literal["low", "medium", "high"]

STATES = ("clear", "watch", "risky", "impassable", "unknown")
HORIZONS = (0, 30, 60, 120)  # minutes after SegmentRisk.issued_at (TRD 4, FR-R1)
IST = timezone(timedelta(hours=5, minutes=30))  # India has one zone and no DST

LatLon = tuple[float, float]  # (lat, lon) in degrees
Polygon = tuple[LatLon, ...]  # ring of (lat, lon); Valhalla wants lon,lat, valhalla.py swaps


@dataclass(frozen=True)
class Config:
    """Every tunable lives here (FR-R2: thresholds are configuration, not code).

    Defaults are TRD/PRD starting values, all [EST] until backtests tune them.
    Per tenant: `dataclasses.replace(cfg, thresholds={**cfg.thresholds, "citizen": 0.2})`.
    """

    thresholds: Mapping[str, float] = field(
        default_factory=lambda: {"citizen": 0.25, "ambulance": 0.45}
    )
    watch_p: float = 0.10  # state bands, TRD 6.4
    risky_p: float = 0.30
    impassable_p: float = 0.50
    max_iterations: int = 3  # re-queries after the first route, TRD 7.3
    exclude_buffer_m: float = 20.0  # placeholder pad around a violating segment, tune in S1
    max_depart_lead_min: int = 120  # forecast ends at the last horizon
    stale_s: float = 900.0  # FR-R4: a row older than this no longer vouches for "clear"
    # ETA error allowance: widen each edge's window by this fraction of the trip time elapsed.
    # 0 trusts the router's ETA exactly (the FR-RT2 reading); set from backtests, not guessed.
    eta_margin: float = 0.0
    dwell_s: float = 150.0  # FR-RT5 minimum gap between suggestions (2.5 min)
    commit_zone_m: float = 300.0  # FR-RT6
    closed_memory_s: float = 900.0  # FR-RT7 (15 min)
    min_saving_s: float = 300.0  # FR-RT5 max(5 min, 15%)
    min_saving_frac: float = 0.15

    def __post_init__(self) -> None:
        if not 0 < self.watch_p < self.risky_p < self.impassable_p <= 1:
            raise ValueError("state bands must satisfy 0 < watch < risky < impassable <= 1")
        for name, t in self.thresholds.items():
            # A threshold above the Impassable band would let a default route cross an
            # Impassable segment (FR-RT3), so no tenant override may exceed it.
            if not 0 < t <= self.impassable_p:
                raise ValueError(f"threshold {name}={t!r} must be in (0, {self.impassable_p}]")
        if self.max_iterations < 0:
            raise ValueError("max_iterations must be >= 0")
        if not 0 <= self.eta_margin <= 1:
            raise ValueError("eta_margin must be within [0, 1]")
        if not self.stale_s > 0:  # a NaN here would make nothing ever stale
            raise ValueError("stale_s must be > 0")
        for name in (
            "exclude_buffer_m",
            "max_depart_lead_min",
            "dwell_s",
            "commit_zone_m",
            "closed_memory_s",
            "min_saving_s",
        ):
            if not getattr(self, name) >= 0:  # also rejects NaN, which would disable the rule
                raise ValueError(f"{name} must be >= 0")
        if not 0 <= self.min_saving_frac <= 1:
            raise ValueError("min_saving_frac must be within [0, 1]")


DEFAULT = Config()


def _finite_nonneg(name: str, v: float) -> None:
    if not (math.isfinite(v) and v >= 0):
        raise ValueError(f"{name} must be a finite number >= 0, got {v!r}")


@dataclass(frozen=True)
class Edge:
    """One stretch of a route. segment_id None means it maps to no segment (unassessed)."""

    segment_id: int | None
    geometry: tuple[LatLon, ...]
    travel_time_s: float
    length_m: float = 0.0
    # A junction at the end of this edge where the driver could leave the route (FR-RT6).
    # Unknown is True: with no junction data, offer a reroute rather than hold.
    turn_off_after: bool = True

    def __post_init__(self) -> None:
        _finite_nonneg("travel_time_s", self.travel_time_s)
        _finite_nonneg("length_m", self.length_m)


@dataclass(frozen=True)
class Route:
    edges: tuple[Edge, ...]

    def __post_init__(self) -> None:
        if not self.edges:
            raise ValueError("a route needs at least one edge")

    @property
    def total_time_s(self) -> float:
        return sum(e.travel_time_s for e in self.edges)


@dataclass(frozen=True)
class SegmentRisk:
    """Forecast for one segment and vehicle class; horizons are minutes after issued_at.

    p and state are keyed by horizon and must cover exactly HORIZONS: a missing horizon
    could hide a flood peak, so incomplete rows raise instead of interpolating over the gap.
    """

    issued_at: datetime
    p: Mapping[int, float]
    state: Mapping[int, str]
    confidence: str = "low"
    evidence_age_s: int | None = 0  # None: the row rests on no evidence, so only its own age counts

    def __post_init__(self) -> None:
        if self.issued_at.tzinfo is None:
            raise ValueError("issued_at must be timezone-aware")
        if set(self.p) != set(HORIZONS) or set(self.state) != set(HORIZONS):
            raise ValueError(f"p and state must have exactly the horizons {HORIZONS}")
        if not all(0.0 <= p <= 1.0 for p in self.p.values()):  # also rejects NaN
            raise ValueError(f"p must be within [0, 1], got {dict(self.p)!r}")
        if not set(self.state.values()) <= set(STATES):
            raise ValueError(f"unknown state in {dict(self.state)!r}")


# ---- TRD 8.2 API models --------------------------------------------------------------

# Rough India bounding box, a cheap guard against swapped or foreign coordinates.
# The per-city polygon check (TRD 8.4) needs city data and belongs to the API layer.
IN_LAT = (6.0, 37.5)
IN_LON = (68.0, 97.6)


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=IN_LAT[0], le=IN_LAT[1])
    lon: float = Field(ge=IN_LON[0], le=IN_LON[1])


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Point
    destination: Point
    vclass: VClass
    depart_at: AwareDatetime
    # "ambulance" widens the exclusion threshold: the API layer must authorise it per tenant.
    profile: Profile = "citizen"
    lang: str = Field(default="en", pattern=r"^[a-z]{2,3}$")


class SegmentOut(BaseModel):
    segment_id: str
    assessed: bool
    state: State | None = None  # None when assessed is false
    p: float | None = None
    confidence: Confidence | None = None
    evidence_age_s: int | None = None
    over_limit: bool = False  # true when p is at or above the exclusion threshold


class RouteOut(BaseModel):
    kind: Literal["fastest", "safest", "least_risk"]
    is_default: bool  # never true for a route with an over_limit segment
    eta_min: int
    delta_min: int | None = None
    worst_state: State
    data_age_s: int | None = None
    reasons: list[str]
    segments: list[SegmentOut]
    geometry: str = Field(description="Encoded polyline, precision 6 (Valhalla's native).")


class Action(BaseModel):
    id: str
    tel: str | None = None


class Guidance(BaseModel):
    keys: list[str]  # message ids, so clients can localise
    text: list[str]
    actions: list[Action]


class RouteResponse(BaseModel):
    decision_id: str
    model_version: str
    no_safe_route: bool
    valid_until: AwareDatetime | None  # None when no route is recommended
    routes: list[RouteOut]
    guidance_when_no_route: Guidance | None
    lang: str  # language the strings are rendered in (English when the request's is missing)


# ---- Live Reroute API models (TRD 7.4, FR-RT5 to FR-RT7) -----------------------------


class TripStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_suggestion_at: AwareDatetime | None = None
    baseline_band: int = 0
    closed_at: dict[str, AwareDatetime] = Field(default_factory=dict)


class EdgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: int | None = None
    travel_time_s: float = Field(ge=0.0)
    length_m: float = Field(default=0.0, ge=0.0)
    turn_off_after: bool = True
    geometry: list[Point] = Field(default_factory=list)


class RerouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Point
    destination: Point
    vclass: VClass
    current_edges: list[EdgeIn]
    trip_state: TripStatePayload | None = None
    depart_at: AwareDatetime | None = None
    profile: Profile = "citizen"
    lang: str = Field(default="en", pattern=r"^[a-z]{2,3}$")


class RerouteResponse(BaseModel):
    decision_id: str
    action: Literal["keep", "suggest", "hold"]
    code: str
    warn: bool
    reasons: list[str]
    reason_keys: list[str]
    trip_state: TripStatePayload
    suggested_route: RouteOut | None = None
    current_worst_state: State | None = None
    current_worst_band: int = 0
    current_violations_count: int = 0
    lang: str
