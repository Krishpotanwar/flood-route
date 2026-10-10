"""Live reroute rules (TRD 7.4, FR-RT5 to FR-RT7). Pure functions over TripState.

decide() runs on each position tick with two validate.assess results: the remaining current route
and the best candidate from the validation loop (None if the loop found no route). It never
suggests a route that has an over-limit segment, and it warns rather than staying silent when the
current route is flooded ahead. Reasons are explain.py message ids.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal

from floodroute.route.models import DEFAULT, Config, Route
from floodroute.route.validate import Assessment


@dataclass(frozen=True)
class TripState:
    """Per-trip memory kept by the server between ticks (TRD 7.4)."""

    last_suggestion_at: datetime | None = None
    baseline_band: int = 0  # worst band the user already knows about; a rise above it is news
    closed_at: Mapping[int, datetime] = field(default_factory=dict)  # last time seen impassable


@dataclass(frozen=True)
class Decision:
    action: Literal["keep", "suggest", "hold"]
    state: TripState  # store this for the next tick
    code: str  # machine-readable why, for logs and tests
    reasons: tuple[str, ...] = ()  # user-facing message ids for explain.say
    route: Route | None = None  # the new route when action is "suggest"
    warn: bool = False  # tell the user about flooding ahead on the current route


def note_closed(
    state: TripState,
    segment_ids: Iterable[int],
    now: datetime,
    cfg: Config = DEFAULT,
    max_entries: int = 256,
) -> TripState:
    """Record segments seen impassable now (FR-RT7 memory). Call every tick while they stay shut.

    Entries older than `closed_memory_s` are evicted and the map is capped at
    `max_entries` (newest win), so long trips cannot grow the payload without bound.
    """
    merged = {**state.closed_at, **dict.fromkeys(segment_ids, now)}
    limit = timedelta(seconds=cfg.closed_memory_s)
    fresh = {s: t for s, t in merged.items() if now - t < limit}
    if len(fresh) > max_entries:
        fresh = dict(sorted(fresh.items(), key=lambda kv: kv[1])[-max_entries:])
    return replace(state, closed_at=fresh)


def _in_commit_zone(current: Assessment, cfg: Config) -> bool:
    """FR-RT6: a flooded edge starts within commit_zone_m and no junction offers a way off first."""
    dist = 0.0
    for edge, check in zip(current.route.edges, current.checks, strict=True):
        if check.violation:
            return dist <= cfg.commit_zone_m
        if edge.turn_off_after:
            return False
        dist += edge.length_m
        if dist > cfg.commit_zone_m:
            return False
    return False


def _recently_closed(
    current: Assessment, candidate: Assessment, state: TripState, now: datetime, cfg: Config
) -> bool:
    """FR-RT7: does the candidate enter a segment, new to the trip, closed in the last 15 min?

    The boundary is exclusive: exactly `closed_memory_s` old counts as expired.
    """
    ahead = {e.segment_id for e in current.route.edges}
    new = {e.segment_id for e in candidate.route.edges} - ahead - {None}
    limit = timedelta(seconds=cfg.closed_memory_s)
    return any(now - state.closed_at[s] < limit for s in new if s in state.closed_at)


def decide(
    state: TripState,
    current: Assessment,
    candidate: Assessment | None,
    now: datetime,
    cfg: Config = DEFAULT,
) -> Decision:
    flooded = bool(current.violations)  # a segment ahead fails validation: the FR-RT5 trigger
    # Follow the band down so a later rise from the lower level counts as news again.
    quiet = replace(state, baseline_band=min(state.baseline_band, current.worst_band))

    if flooded and _in_commit_zone(current, cfg):
        return Decision("hold", quiet, "commit_zone", ("reroute.commit_zone",), warn=True)

    if (
        state.last_suggestion_at is not None
        and (now - state.last_suggestion_at).total_seconds() < cfg.dwell_s
    ):
        reasons = ("reroute.flood_ahead",) if flooded else ()
        return Decision("keep", quiet, "dwell", reasons, warn=flooded)

    no_alt = ("reroute.no_alternative",) if flooded else ()
    if candidate is None or candidate.violations:
        return Decision("keep", quiet, "no_candidate", no_alt, warn=flooded)
    if _recently_closed(current, candidate, state, now, cfg):
        return Decision("keep", quiet, "recently_closed", no_alt, warn=flooded)

    # One reason, most urgent first. A faster route must not sit in a higher band than this one:
    # never trade risk for time.
    saving = current.total_time_s - candidate.total_time_s
    rising = current.worst_band > state.baseline_band and candidate.worst_band < current.worst_band
    faster = saving >= max(cfg.min_saving_s, cfg.min_saving_frac * current.total_time_s)
    faster = faster and candidate.worst_band <= current.worst_band
    if flooded:
        reason = "reroute.road_flooded"
    elif rising:
        reason = "reroute.risk_rising"
    elif faster:
        reason = "reroute.faster"
    else:
        return Decision("keep", quiet, "no_trigger")

    nxt = replace(state, last_suggestion_at=now, baseline_band=current.worst_band)
    return Decision("suggest", nxt, "suggest", (reason,), candidate.route, warn=flooded)
