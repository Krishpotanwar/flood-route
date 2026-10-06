"""Arrival-time validation loop (TRD 7.3, FR-RT1 to FR-RT4). Pure: no IO, clock or randomness.

Every edge is checked against p over the time the vehicle is on it (arrival time), not at
request time. A route with any edge at or above the class threshold is never the default. If no
route passes within `max_iterations` re-queries, the answer is no_safe_route with guidance and
the least-risk route clearly marked. Unassessed edges are neutral (assessed false); unknown
assessed edges count as watch while it rains. Nothing here ever labels anything "safe".

Contract for `risk_for(segment_id, vclass)`: called once per edge, so back it with an in-process
dict or LRU of the assessed set. It returns None only for segments outside the inventory. A
malformed row must raise, never become None, or it would read as neutral.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from floodroute.route.explain import about, pick_lang, say
from floodroute.route.interp import first_crossing, knots, p_at
from floodroute.route.models import (
    DEFAULT,
    IST,
    Action,
    Config,
    Edge,
    Guidance,
    LatLon,
    Polygon,
    Route,
    RouteOut,
    RouteRequest,
    RouteResponse,
    SegmentOut,
    SegmentRisk,
)
from floodroute.route.valhalla import encode_polyline6

Router = Callable[[LatLon, LatLon, str, datetime, Sequence[Polygon]], Route | None]
RiskFor = Callable[[int, str], SegmentRisk | None]
NameOf = Callable[[int], str | None]

BAND = {"clear": 0, "watch": 1, "risky": 2, "impassable": 3}  # effective rank, used by reroute
# worst_state ranking: unknown sits above watch so it never reads as clear, below a known risky
ORDER = ("clear", "watch", "unknown", "risky", "impassable")
MAX_AVOID_LINES = 3


def state_from_p(p: float, cfg: Config = DEFAULT) -> str:
    if p >= cfg.impassable_p:
        return "impassable"
    if p >= cfg.risky_p:
        return "risky"
    if p >= cfg.watch_p:
        return "watch"
    return "clear"


@dataclass(frozen=True)
class Ctx:
    risk_for: RiskFor
    vclass: str
    now: datetime
    threshold: float
    cfg: Config = DEFAULT
    in_rain: bool = True  # unknown assessed edges count as watch only while it rains

    def __post_init__(self) -> None:
        if not 0 < self.threshold <= self.cfg.impassable_p:  # same guard as Config.thresholds
            raise ValueError(f"threshold {self.threshold!r} must be in (0, impassable_p]")


@dataclass(frozen=True)
class EdgeCheck:
    segment_id: int | None
    assessed: bool
    p: float | None = None  # highest p while on the edge
    state: str | None = None
    band: int = 0  # effective rank: unknown counts as watch in rain
    confidence: str | None = None
    evidence_age_s: int | None = None
    violation: bool = False
    # Violating edges: first time from now that p reaches the limit ("water likely in ...").
    onset: datetime | None = None
    # Other assessed edges: first limit crossing after arrival, else the end of the forecast.
    valid_to: datetime | None = None


@dataclass(frozen=True)
class Assessment:
    route: Route
    checks: tuple[EdgeCheck, ...]  # one per route.edges entry
    depart: datetime
    violations: tuple[int, ...]  # indexes of edges at or above the limit
    worst_state: str
    worst_band: int
    valid_until: datetime  # earliest forecast limit crossing on the route; ETA if nothing assessed
    data_age_s: int | None

    @property
    def total_time_s(self) -> float:
        return self.route.total_time_s


def _minutes(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 60.0


def _effective(risk: SegmentRisk, ctx: Ctx) -> tuple[dict[int, float], dict[int, str], float]:
    """Per-horizon p and state with the safety rules applied, and the row's age in seconds.

    Age is the stored evidence age plus the time since the row was issued, so a dead scoring job
    cannot leave an old "clear" looking fresh (FR-R4). Rules: a row past stale_s degrades clear to
    unknown; a stored impassable counts as at least the impassable band even if hysteresis keeps p
    lower; unknown counts as watch while it rains.
    """
    age = (risk.evidence_age_s or 0) + max(0.0, (ctx.now - risk.issued_at).total_seconds())
    stale = age > ctx.cfg.stale_s
    ps, states = {}, {}
    for h, p in risk.p.items():
        s = risk.state[h]
        if stale and s == "clear":
            s = "unknown"
        if s == "impassable":
            p = max(p, ctx.cfg.impassable_p)
        elif s == "unknown" and ctx.in_rain:
            p = max(p, ctx.cfg.watch_p)
        ps[h], states[h] = p, s
    return ps, states, age


def _check_edge(e: Edge, t_in: datetime, t_out: datetime, depart: datetime, ctx: Ctx) -> EdgeCheck:
    risk = ctx.risk_for(e.segment_id, ctx.vclass) if e.segment_id is not None else None
    if risk is None:
        return EdgeCheck(e.segment_id, assessed=False)
    pm, st, age = _effective(risk, ctx)
    margin = ctx.cfg.eta_margin
    lo = _minutes(t_in, risk.issued_at) - margin * _minutes(t_in, depart)
    hi = _minutes(t_out, risk.issued_at) + margin * _minutes(t_out, depart)
    # p is monotone between horizons, so the window maximum is at an end or a horizon inside it
    p = max(p_at(pm, m) for m in (lo, hi, *knots(pm, lo, hi)))
    floor_h = max((h for h in pm if h <= lo), default=min(pm))
    banded = state_from_p(p, ctx.cfg)
    state = "unknown" if st[floor_h] == "unknown" else banded
    violation = p >= ctx.threshold

    def at(minute: float) -> datetime:
        return risk.issued_at + timedelta(minutes=minute)

    onset = valid_to = None
    if violation:
        m = first_crossing(pm, ctx.threshold, _minutes(ctx.now, risk.issued_at))
        onset = at(m) if m is not None else None
    else:
        m = first_crossing(pm, ctx.threshold, lo)
        valid_to = at(m if m is not None else max(pm))  # no crossing: valid to the forecast end
    return EdgeCheck(
        segment_id=e.segment_id,
        assessed=True,
        p=p,
        state=state,
        band=BAND[banded],
        confidence=risk.confidence,
        evidence_age_s=int(age),
        violation=violation,
        onset=onset,
        valid_to=valid_to,
    )


def assess(route: Route, ctx: Ctx, depart: datetime) -> Assessment:
    """Check every edge at its cumulative arrival time. Also used for live reroute checks."""
    t = depart
    checks = []
    for e in route.edges:
        t_out = t + timedelta(seconds=e.travel_time_s)
        checks.append(_check_edge(e, t, t_out, depart, ctx))
        t = t_out
    seen = [c for c in checks if c.assessed]
    return Assessment(
        route=route,
        checks=tuple(checks),
        depart=depart,
        violations=tuple(i for i, c in enumerate(checks) if c.violation),
        worst_state=max((c.state for c in seen), key=ORDER.index, default="unknown"),
        worst_band=max((c.band for c in seen), default=0),
        valid_until=min((c.valid_to for c in seen if c.valid_to), default=t),
        data_age_s=max((c.evidence_age_s for c in seen), default=None),
    )


def exclusion_polygon(edge: Edge, buffer_m: float) -> Polygon | None:
    """Padded bounding box of the edge as a closed (lat, lon) ring; None without geometry.

    ponytail: a box, not a true line buffer. It also excludes roads that touch the box near the
    edge's ends and any road crossing above an underpass (Valhalla tests 2D intersection).
    Over-excluding errs towards no_safe_route, never towards a flooded road. Tune in S1.
    """
    if not edge.geometry:
        return None
    lats = [p[0] for p in edge.geometry]
    lons = [p[1] for p in edge.geometry]
    dlat = buffer_m / 110_574.0  # metres per degree of latitude at its smallest: never short
    dlon = dlat / max(math.cos(math.radians(sum(lats) / len(lats))), 0.01)
    s, n, w, e = min(lats) - dlat, max(lats) + dlat, min(lons) - dlon, max(lons) + dlon
    return ((s, w), (s, e), (n, e), (n, w), (s, w))


def _search(req: RouteRequest, router: Router, ctx: Ctx) -> tuple[list[Assessment], int]:
    """The TRD 7.3 loop. Returns every route tried and the number of router calls made."""
    origin, dest = (req.origin.lat, req.origin.lon), (req.destination.lat, req.destination.lon)
    polygons: list[Polygon] = []
    excluded: set[int | None] = set()
    found: list[Assessment] = []
    calls = 0
    for _ in range(ctx.cfg.max_iterations + 1):
        route = router(origin, dest, ctx.vclass, req.depart_at, tuple(polygons))
        calls += 1
        if route is None:
            break
        a = assess(route, ctx, req.depart_at)
        found.append(a)
        if not a.violations:
            break
        grown = False
        for i in a.violations:
            edge = route.edges[i]
            if edge.segment_id in excluded:
                continue
            excluded.add(edge.segment_id)
            poly = exclusion_polygon(edge, ctx.cfg.exclude_buffer_m)
            if poly:
                polygons.append(poly)
                grown = True
        if not grown:  # the router handed back an already excluded segment: no progress possible
            break
    return found, calls


def _exposure(a: Assessment) -> float:
    """Chance at least one assessed edge is unusable, treating edges as independent."""
    return 1.0 - math.prod(1.0 - c.p for c in a.checks if c.p is not None)


def _least_risk_key(a: Assessment) -> tuple[float, int, float]:
    return (_exposure(a), len(a.violations), a.total_time_s)


def _segments(a: Assessment) -> list[SegmentOut]:
    out = []
    for c in a.checks:
        if c.segment_id is None:
            continue
        sid = str(c.segment_id)
        if not c.assessed:
            out.append(SegmentOut(segment_id=sid, assessed=False))
        else:
            out.append(
                SegmentOut(
                    segment_id=sid,
                    assessed=True,
                    state=c.state,
                    p=round(c.p, 3),
                    confidence=c.confidence,
                    evidence_age_s=c.evidence_age_s,
                    over_limit=c.violation,
                )
            )
    return out


def _notes(a: Assessment, lang: str) -> list[str]:
    notes = []
    if any(not c.assessed for c in a.checks):
        notes.append(say("route.unassessed", lang))
    if any(c.state == "unknown" for c in a.checks):
        notes.append(say("route.unknown", lang))
    return notes


def _avoid_lines(found: list[Assessment], name_of: NameOf, now: datetime, lang: str) -> list[str]:
    worst: dict[int, EdgeCheck] = {}
    for a in found:
        for i in a.violations:
            c = a.checks[i]
            worst.setdefault(c.segment_id, c)

    def minutes(c: EdgeCheck) -> float:
        return 0.0 if c.onset is None else max(0.0, _minutes(c.onset, now))

    lines = []
    for c in sorted(worst.values(), key=minutes)[:MAX_AVOID_LINES]:
        m = minutes(c)
        name = name_of(c.segment_id)
        key = "avoid." + ("now_" if m <= 2.5 else "") + ("named" if name else "unnamed")
        lines.append(say(key, lang, place=name, minutes=about(m)))
    return lines


def _eta_min(a: Assessment) -> int:
    return math.ceil(a.total_time_s / 60)


def _out(
    kind: str, a: Assessment, first: Assessment, default: bool, lang: str, lead: list[str]
) -> RouteOut:
    if default and a.violations:  # the safety invariant, enforced where the default is built
        raise RuntimeError("refusing to mark a route with an over-limit segment as the default")
    return RouteOut(
        kind=kind,
        is_default=default,
        eta_min=_eta_min(a),
        delta_min=max(0, _eta_min(a) - _eta_min(first)),
        worst_state=a.worst_state,
        data_age_s=a.data_age_s,
        reasons=lead + _notes(a, lang),
        segments=_segments(a),
        geometry=encode_polyline6(pt for e in a.route.edges for pt in e.geometry),
    )


def _guidance(profile: str, lang: str, has_route: bool) -> Guidance:
    if profile == "ambulance":
        keys = ["guidance.escalate", "guidance.alt_modes"]
        keys += ["guidance.least_risk"] if has_route else []
        actions = [Action(id="escalate_dispatcher")]
    else:
        keys = ["guidance.stay", "guidance.no_water", "guidance.avoid_low", "guidance.call_112"]
        actions = [Action(id="call_112", tel="112"), Action(id="share_location")]
    return Guidance(keys=keys, text=[say(k, lang) for k in keys], actions=actions)


@dataclass(frozen=True)
class Plan:
    response: RouteResponse
    iterations: int  # router calls after the first (the TRD 7.3 metric)
    rejected: tuple[Assessment, ...]  # routes that failed validation, for route_decision.rejected
    accepted: Assessment | None = None


def plan(
    req: RouteRequest,
    router: Router,
    risk_for: RiskFor,
    *,
    now: datetime,
    model_version: str,
    decision_id: str,
    cfg: Config = DEFAULT,
    in_rain: bool = True,
    name_of: NameOf | None = None,
) -> Plan:
    """Route with arrival-time validation. Raises ValueError for a depart_at beyond the forecast,
    and lets router or risk_for errors propagate: failing closed beats an unchecked route."""
    if req.depart_at - now > timedelta(minutes=cfg.max_depart_lead_min):
        raise ValueError(f"depart_at is more than {cfg.max_depart_lead_min} min ahead of now")
    ctx = Ctx(risk_for, req.vclass, now, cfg.thresholds[req.profile], cfg, in_rain)
    found, calls = _search(req, router, ctx)
    lang = pick_lang(req.lang)
    name_of = name_of or (lambda _: None)
    ok = found[-1] if found and not found[-1].violations else None
    first = found[0] if found else None

    if ok is not None:
        if ok is first:
            routes = [_out("fastest", ok, first, True, lang, [])]
        else:
            delta = _eta_min(ok) - _eta_min(first)
            lead = _avoid_lines(found, name_of, now, lang)
            lead.append(
                say("delta.longer", lang, minutes=delta) if delta >= 1 else say("delta.same", lang)
            )
            routes = [
                _out("safest", ok, first, True, lang, lead),
                _out("fastest", first, first, False, lang, [say("route.over_limit", lang)]),
            ]
        valid_until: datetime | None = ok.valid_until.astimezone(IST)
        guidance = None
    else:
        best = min(found, key=_least_risk_key) if found else None
        routes = []
        if best is not None:
            lead = [say("route.least_risk", lang)]
            routes.append(_out("least_risk", best, first, False, lang, lead))
        valid_until = None
        guidance = _guidance(req.profile, lang, best is not None)

    response = RouteResponse(
        decision_id=decision_id,
        model_version=model_version,
        no_safe_route=ok is None,
        valid_until=valid_until,
        routes=routes,
        guidance_when_no_route=guidance,
        lang=lang,
    )
    rejected = tuple(a for a in found if a.violations)
    return Plan(response, max(0, calls - 1), rejected, ok)
