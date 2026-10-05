"""Builders shared by the scoring tests."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from floodroute.score import (
    RainFcst,
    RainObs,
    RunInput,
    SegmentInput,
    ZoneInput,
    load_config,
    score_run,
)

CFG = load_config()
T0 = datetime(2027, 5, 18, 11, 0, tzinfo=timezone.utc)
ZONE = 10


def at(minutes: float = 0, seconds: float = 0) -> datetime:
    return T0 + timedelta(minutes=minutes, seconds=seconds)


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def seg(segment_id: int = 1, p: float | None = None, structure: str = "underpass", **kw):
    """An assessed segment. With p, base_logit is set so that a car at horizon 0 with no rain
    and no antecedent wetness scores exactly p (delta for car is 0)."""
    if p is not None:
        kw["base_logit"] = logit(p)
    return SegmentInput(
        segment_id, kw.pop("zone_id", ZONE), kw.pop("assessed", True), structure, **kw
    )


def step(
    now: datetime,
    segments,
    prev=None,
    rate: float = 0.0,
    *,
    mm_24h: float | None = 0.0,
    obs_age_s: int = 0,
    obs=None,
    fcst=(),
    alert: bool = False,
    cfg=CFG,
):
    """One scoring run for a single zone. Returns (RunResult, rows by key).
    obs=() means a zone with no rain observation at all."""
    if obs is None:
        obs = (RainObs("gauge", now - timedelta(seconds=obs_age_s), rate, mm_24h),)
    zone = ZoneInput(ZONE, obs=tuple(obs), fcst=tuple(fcst), alert_active=alert)
    res = score_run(RunInput(now, (zone,), tuple(segments)), prev or {}, cfg)
    return res, {r.key: r for r in res.rows}


def fcst(valid: datetime, rate: float, source: str = "imd_nowcast", spread=None) -> RainFcst:
    return RainFcst(source, valid, rate, spread)


def row(rows, segment_id: int = 1, vclass: str = "car", h: int = 0):
    return rows[(segment_id, vclass, h)]
