"""score_segment and score_run: pure and deterministic. No clock, no randomness, no I/O.

The same inputs, previous state and config always give the same rows and changes, so any run
can be replayed from stored inputs to explain a state (audit, FR-R1).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from .confidence import confidence
from .config import Config
from .evidence import Live, active_actions, apply_effect, evidence_effect, live_evidence
from .model import ZoneRain, antecedent, effective_rain, logit_x, sigmoid, zone_rain
from .records import Change, RiskRow, RunInput, RunResult, SegmentInput, snapshot
from .state import degrade, hysteresis, overlay

Prev = Mapping[tuple[int, str, int], RiskRow]


def _row(
    seg: SegmentInput,
    zr: ZoneRain,
    live: tuple[Live, ...],
    vclass: str,
    h: int,
    now: datetime,
    old: RiskRow | None,
    cfg: Config,
) -> RiskRow:
    st = cfg.structures[seg.structure]
    base = st.base_logit if seg.base_logit is None else seg.base_logit
    rain = effective_rain(zr, h, cfg)
    rain_known = zr.has_obs and not rain.fcst_missing
    eff = evidence_effect(
        live,
        vclass,
        h,
        raining_now=zr.has_obs and zr.obs_rate > 0,
        below_trigger=rain_known and rain.value < st.r_low,
        cfg=cfg,
    )
    x = logit_x(base, st, rain, antecedent(zr.mm_24h, cfg), vclass, cfg) + eff.logit_add
    p = apply_effect(sigmoid(x), eff)

    # newest evidence the row rests on: the rain observation used and any evidence that fired
    ages = [a for a in (zr.obs_age_s, eff.age_s) if a is not None]
    age = min(ages) if ages else None
    fresh = age is not None and age < cfg.staleness.max_age_s
    no_rain = zr.alert_active and not zr.has_obs

    state, latch, reason = hysteresis(p, now, fresh, old, cfg)
    state, why = degrade(state, age, no_rain, cfg)
    reason = why or reason
    state, p, why, applied = overlay(state, p, active_actions(seg, now, h, cfg), age, no_rain, cfg)
    return RiskRow(
        segment_id=seg.segment_id,
        vclass=vclass,
        horizon_min=h,
        assessed=True,
        p=p,
        state=state,
        confidence=confidence(
            age,
            int(zr.has_obs) + len(eff.sources),
            rain.spread,
            rain.fcst_missing,
            zr.obs_age_s,
            seg.covered,
            cfg,
            wetness_unknown=zr.mm_24h is None,
        ),
        evidence_age_s=age,
        model_version=cfg.model_version,
        updated_at=now,
        closed_since=latch.closed_since,
        reopen_ok_since=latch.reopen_ok_since,
        override=applied,
        reason=why or reason,
        evidence_rules=eff.rules,
    )


def _change(old: RiskRow | None, new: RiskRow, now: datetime) -> Change | None:
    if (old.state if old else None) == new.state:
        return None
    reason = "override_expired" if old and old.override and not new.override else new.reason
    return Change(
        ts=now,
        segment_id=new.segment_id,
        vclass=new.vclass,
        horizon_min=new.horizon_min,
        before=None if old is None else snapshot(old),
        after=snapshot(new),
        reason=reason,
    )


def score_segment(
    seg: SegmentInput,
    zr: ZoneRain | None,
    now: datetime,
    cfg: Config,
    prev: Prev | None = None,
) -> tuple[list[RiskRow], list[Change]]:
    """Rows and changes for one segment: every vehicle class at every horizon.

    A segment with assessed=False gets rows with no state, p or confidence (FR-R5) and needs no
    zone. prev maps (segment_id, vclass, horizon_min) to the previous run's rows."""
    prev = {} if prev is None else prev
    live: tuple[Live, ...] = ()
    if seg.assessed:
        if zr is None:
            raise ValueError(f"segment {seg.segment_id}: assessed but its zone has no rain data")
        if seg.structure not in cfg.structures:
            raise ValueError(f"segment {seg.segment_id}: unknown structure {seg.structure!r}")
        live = live_evidence(seg.evidence, now, cfg)
    rows: list[RiskRow] = []
    changes: list[Change] = []
    for vclass in cfg.vclasses:
        for h in cfg.horizons_min:
            old = prev.get((seg.segment_id, vclass, h))
            if zr is not None and seg.assessed:
                row = _row(seg, zr, live, vclass, h, now, old, cfg)
            else:
                row = RiskRow(
                    segment_id=seg.segment_id,
                    vclass=vclass,
                    horizon_min=h,
                    assessed=False,
                    p=None,
                    state=None,
                    confidence=None,
                    evidence_age_s=None,
                    model_version=cfg.model_version,
                    updated_at=now,
                    reason="not_assessed",
                )
            rows.append(row)
            change = _change(old, row, now)
            if change:
                changes.append(change)
    return rows, changes


def score_run(inputs: RunInput, prev_state: Prev, cfg: Config) -> RunResult:
    """Score every segment. Returns the new rows (sorted by segment, class order, horizon) and
    the list of state changes, each with before, after and a reason code for the audit log."""
    now = inputs.now
    for row in prev_state.values():
        if row.updated_at > now:
            raise ValueError(f"previous state for {row.key} is newer than the run time {now}")
    zones: dict[int, ZoneRain] = {}
    for z in inputs.zones:
        if z.zone_id in zones:
            raise ValueError(f"duplicate zone {z.zone_id}")
        zones[z.zone_id] = zone_rain(z, now, cfg)
    rows: list[RiskRow] = []
    changes: list[Change] = []
    seen: set[int] = set()
    for seg in sorted(inputs.segments, key=lambda s: s.segment_id):
        if seg.segment_id in seen:
            raise ValueError(f"duplicate segment {seg.segment_id}")
        seen.add(seg.segment_id)
        r, c = score_segment(seg, zones.get(seg.zone_id), now, cfg, prev_state)
        rows += r
        changes += c
    return RunResult(tuple(rows), tuple(changes))
