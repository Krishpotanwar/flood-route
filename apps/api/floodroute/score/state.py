"""State mapping, hysteresis, staleness and the override overlay (TRD 6.4, FR-R2 to FR-R4).

Published state for a row is built in three steps:
  1. hysteresis    the model-only machine: closes at p >= impassable_min, reopens after p stays
                   below reopen_below for reopen_hold_s with fresh evidence, else bands from p
  2. degrade       missing or stale data can turn clear (and, in an alert with no rain source,
                   watch) into unknown, but never lowers risky or impassable (fail safe)
  3. overlay       a human override in force wins; it never touches the machine's own state, so
                   when it expires the row reverts to what the model says
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import Config
from .records import CLEAR, IMPASSABLE, RISKY, UNKNOWN, WATCH, RiskRow


def state_from_p(p: float, cfg: Config) -> str:
    s = cfg.states
    if p < s.watch_min:
        return CLEAR
    if p < s.risky_min:
        return WATCH
    if p < s.impassable_min:
        return RISKY
    return IMPASSABLE


@dataclass(frozen=True)
class Latch:
    closed_since: datetime | None
    reopen_ok_since: datetime | None


def hysteresis(
    p: float, now: datetime, fresh: bool, prev: RiskRow | None, cfg: Config
) -> tuple[str, Latch, str]:
    """One step of the close and reopen machine. Returns (state, latch, reason).

    Closing is immediate. Reopening needs p below reopen_below, continuously for
    reopen_hold_s, with fresh evidence; any sample that breaks the condition restarts the timer.
    A gap between runs longer than the hold cannot certify continuity, so it restarts the timer.
    Once reopened the state is re-banded from p. Closed with p between reopen_below and
    impassable_min stays closed.
    ponytail: only the impassable boundary has hysteresis (TRD 6.4); watch and risky follow p."""
    hold = cfg.hysteresis.reopen_hold_s
    if p >= cfg.states.impassable_min:
        return (
            IMPASSABLE,
            Latch(prev.closed_since if prev and prev.closed_since else now, None),
            "closed",
        )
    if prev is None or prev.closed_since is None:
        return state_from_p(p, cfg), Latch(None, None), "band"
    if p < cfg.hysteresis.reopen_below and fresh:
        timer = prev.reopen_ok_since
        if timer is None or (now - prev.updated_at).total_seconds() > hold:
            timer = now
        if (now - timer).total_seconds() >= hold:
            return state_from_p(p, cfg), Latch(None, None), "reopened"
        return IMPASSABLE, Latch(prev.closed_since, timer), "closed_hold"
    return IMPASSABLE, Latch(prev.closed_since, None), "closed_hold"


def degrade(
    state: str, evidence_age_s: int | None, no_rain_in_alert: bool, cfg: Config
) -> tuple[str, str | None]:
    """Turn clear or watch into unknown when the data cannot support them.

    no_rain_in_alert: an alert is active and no rain observation is newer than rain.max_age_s
    (TRD 5). evidence_age_s above staleness.max_age_s degrades clear only (FR-R4). Equality does
    not degrade ("over 15 min")."""
    if no_rain_in_alert and state in (CLEAR, WATCH):
        return UNKNOWN, "no_rain_source"
    if state == CLEAR and (evidence_age_s is None or evidence_age_s > cfg.staleness.max_age_s):
        return UNKNOWN, "stale_data"
    return state, None


def overlay(
    state: str,
    p: float,
    actions: frozenset[str],
    evidence_age_s: int | None,
    no_rain_in_alert: bool,
    cfg: Config,
) -> tuple[str, float, str | None, str | None]:
    """Apply human overrides in force. Returns (state, p, reason, applied action).

    close beats everything (p = 1). reopen only acts on an Impassable state: it caps p, so the
    state shows at most Watch, and the staleness rules still apply to the result.
    force_watch lifts clear or unknown to watch."""
    if "close" in actions:
        return IMPASSABLE, 1.0, "override_close", "close"
    reason, applied = None, None
    if "reopen" in actions and state == IMPASSABLE:
        p = min(p, cfg.overrides.reopen_cap_p)
        state, why = degrade(state_from_p(p, cfg), evidence_age_s, no_rain_in_alert, cfg)
        reason, applied = why or "override_reopen", "reopen"
    if "force_watch" in actions and state in (CLEAR, UNKNOWN):
        state, p = WATCH, max(p, cfg.states.watch_min)
        reason, applied = "override_force_watch", "force_watch"
    return state, p, reason, applied
