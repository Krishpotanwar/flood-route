"""Evidence rules (TRD 6.3, FR-R8) and the human override overlay (PRD principle 4, FR-C3).

Rules act on the model probability in three ways:
  floors  p moves toward a higher target by weight w (reports, verified deep water)
  caps    p moves toward a lower target by weight w (verified shallow water, dry sky)
  logit   an additive logit term scaled by w (weak probe signal)
with w = exp(-age / tau) * exp(-horizon / horizon_tau): evidence fades with age, and fades
further at later horizons. At age 0 and horizon 0 a floor or cap sets p to its target exactly.
Exception: corroborated reports hold at full strength for their whole corroboration window, which
is their age limit (TRD 6.3). Fading them inside the window would end the closure after about
4 min, so a run a few minutes late could miss it. Only the horizon fade applies to them.
Caps are applied before floors, so conflicting evidence never hides a hazard signal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import Config
from .records import Evidence, SegmentInput, age_s


@dataclass(frozen=True)
class Live:
    e: Evidence
    age_s: int


@dataclass(frozen=True)
class Effect:
    logit_add: float = 0.0
    caps: tuple[tuple[float, float], ...] = ()  # (target p, weight)
    floors: tuple[tuple[float, float], ...] = ()  # (target p, weight)
    rules: tuple[str, ...] = ()
    age_s: int | None = None  # age of the newest evidence that fired
    sources: frozenset[str] = frozenset()  # source_ids of the evidence that fired


def live_evidence(evidence: tuple[Evidence, ...], now: datetime, cfg: Config) -> tuple[Live, ...]:
    """Unexpired items, newest per (kind, source_id), in a fixed order.

    One source counts once however often it reports: a later reading from the same source
    replaces its earlier one. Official closures are handled by `active_actions`."""
    skew = cfg.staleness.max_future_skew_s
    best: dict[tuple[str, str], Live] = {}
    for e in evidence:
        if e.kind == "official" or e.expires <= now:
            continue
        live = Live(e, age_s(now, e.ts, skew, f"evidence {e.kind} from {e.source_id}"))
        cur = best.get((e.kind, e.source_id))
        if cur is None or (e.ts, e.expires) > (cur.e.ts, cur.e.expires):
            best[(e.kind, e.source_id)] = live
    return tuple(best[k] for k in sorted(best))


def fade(h: int, cfg: Config) -> float:
    """How much of evidence observed now still counts at horizon h."""
    return math.exp(-h / cfg.evidence.horizon_tau_min)


def weight(age: int, h: int, cfg: Config) -> float:
    return math.exp(-age / (cfg.evidence.tau_min * 60.0)) * fade(h, cfg)


def evidence_effect(
    live: tuple[Live, ...],
    vclass: str,
    h: int,
    raining_now: bool,
    below_trigger: bool,
    cfg: Config,
) -> Effect:
    """Apply the TRD 6.3 rules for one vehicle class and horizon.

    raining_now: a fresh observation shows rain. below_trigger: rain at this horizon is known
    and below the structure trigger r_low."""
    ev, prof = cfg.evidence, cfg.vehicle_profiles[vclass]
    caps: list[tuple[float, float]] = []
    floors: list[tuple[float, float]] = []
    rules: list[str] = []
    fired: list[Live] = []
    logit_add = 0.0

    # FR-R8: two independent trusted reports inside the window. Independent means distinct
    # source_id, so the same source twice counts once (live_evidence keeps one per source).
    reports = [
        x
        for x in live
        if x.e.kind == "report"
        and x.e.trust >= ev.report_min_trust
        and x.age_s <= ev.corroboration_window_s
    ]
    if len({x.e.source_id for x in reports}) >= ev.corroboration_min_sources:
        floors.append((ev.report_floor_p, fade(h, cfg)))
        rules.append("reports_corroborated")
        fired += reports

    # Verified photo or sensor depth at or above this class's unusable depth
    deep = [
        x
        for x in live
        if x.e.kind in ("report", "sensor", "camera")
        and x.e.verified
        and x.e.depth_cm is not None
        and x.e.depth_cm >= prof.unusable_cm
    ]
    if deep:
        top = min(deep, key=lambda x: x.age_s)
        floors.append((ev.depth_unusable_floor_p, weight(top.age_s, h, cfg)))
        rules.append("depth_unusable")
        fired.append(top)

    # Verified sensor or camera depth below the caution depth while rain is below trigger
    shallow = [
        x
        for x in live
        if x.e.kind in ("sensor", "camera")
        and x.e.verified
        and x.e.depth_cm is not None
        and x.e.depth_cm < prof.caution_cm
    ]
    if shallow and below_trigger:
        top = min(shallow, key=lambda x: x.age_s)
        caps.append((ev.depth_clear_cap_p, weight(top.age_s, h, cfg)))
        rules.append("depth_below_caution")
        fired.append(top)

    # Weak signal: probe speeds well under expected during rain, from enough contributors
    slow = [
        x
        for x in live
        if x.e.kind == "probe"
        and x.e.speed_ratio is not None
        and x.e.speed_ratio < ev.probe_speed_ratio_below
        and x.e.contributors is not None
        and x.e.contributors >= ev.probe_min_contributors
    ]
    if slow and raining_now:
        top = min(slow, key=lambda x: x.age_s)
        logit_add = ev.probe_logit * weight(top.age_s, h, cfg)
        rules.append("probe_slow")
        fired.append(top)

    return Effect(
        logit_add=logit_add,
        caps=tuple(caps),
        floors=tuple(floors),
        rules=tuple(rules),
        age_s=min((x.age_s for x in fired), default=None),
        sources=frozenset(x.e.source_id for x in fired),
    )


def apply_effect(p: float, eff: Effect) -> float:
    """Pull p toward cap and floor targets. The most extreme candidate of each kind wins, and
    floors act on the capped value so that a hazard signal is never hidden by a cap."""
    p = min([p] + [p + w * (t - p) for t, w in eff.caps if t < p])
    return max([p] + [p + w * (t - p) for t, w in eff.floors if t > p])


def active_actions(seg: SegmentInput, now: datetime, h: int, cfg: Config) -> frozenset[str]:
    """Override actions in force at the valid time now + h. An official closure in the evidence
    list is a close action from its ts to its expiry. Overrides are decisions with their own
    validity window, so unlike observations they are tested at the valid time."""
    vt = now + timedelta(minutes=h)
    skew = cfg.staleness.max_future_skew_s
    windows = [(o.action, o.starts_at, o.expires_at) for o in seg.overrides]
    for e in seg.evidence:
        if e.kind == "official":
            age_s(now, e.ts, skew, f"official closure from {e.source_id}")
            windows.append(("close", e.ts, e.expires))
    return frozenset(a for a, start, end in windows if start <= vt < end)
