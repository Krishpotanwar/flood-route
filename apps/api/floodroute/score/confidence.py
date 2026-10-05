"""Confidence (FR-R6), separate from probability. Drivers per TRD 6.2: evidence freshness and
source count set the start level; nowcast spread, no zone source newer than the staleness limit,
and being outside the DEM and drain-mapped area each lower it by one."""

from __future__ import annotations

from .config import Config

LEVELS = ("low", "medium", "high")


def confidence(
    evidence_age_s: int | None,
    n_sources: int,
    spread_mm_h: float | None,
    forecast_missing: bool,
    rain_age_s: int | None,
    covered: bool,
    cfg: Config,
) -> str:
    """n_sources counts independent inputs: the rain source plus distinct evidence sources that
    fired. rain_age_s is None when no rain observation is fresh."""
    c, limit = cfg.confidence, cfg.staleness.max_age_s
    if evidence_age_s is None or evidence_age_s > limit:
        level = 0
    elif evidence_age_s <= c.high_max_age_s and n_sources >= c.high_min_sources:
        level = 2
    else:
        level = 1
    if forecast_missing or (spread_mm_h is not None and spread_mm_h > c.spread_penalty_mm_h):
        level -= 1
    if rain_age_s is None or rain_age_s > limit:
        level -= 1
    if not covered:
        level -= 1
    return LEVELS[max(0, level)]
