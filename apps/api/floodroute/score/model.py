"""Rain input selection, effective rainfall, g(R), logit assembly and sigmoid (TRD 5 and 6.2)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import Config, Structure
from .records import RainFcst, ZoneInput, age_s


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def g(rain: float, r_low: float, r_high: float) -> float:
    """Rain trigger: 0 at or below r_low, 1 at or above r_high, linear in between."""
    return min(1.0, max(0.0, (rain - r_low) / (r_high - r_low)))


@dataclass(frozen=True)
class ZoneRain:
    """What a run knows about rain in one zone at `now`."""

    now: datetime
    obs_rate: float  # mm/h taken as the observed rate (a forecast fallback or 0 if no observation)
    obs_source: str | None  # None when no observation is newer than rain.max_age_s
    obs_age_s: int | None  # age of that observation
    mm_24h: float | None  # antecedent accumulation, None when no usable source
    alert_active: bool
    fcst: tuple[RainFcst, ...]

    @property
    def has_obs(self) -> bool:
        return self.obs_source is not None


@dataclass(frozen=True)
class Rain:
    """Effective rainfall R(z, h) for one horizon."""

    value: float  # mm/h
    spread: float | None  # forecast ensemble spread, None when no forecast is used
    fcst_missing: bool  # h > 0 and no forecast matched, so the value is persistence


def pick_fcst(fcst: tuple[RainFcst, ...], target: datetime, cfg: Config) -> RainFcst | None:
    """Best-ranked source whose valid time is within tolerance of target, then nearest in time."""
    rank = cfg.rain.source_priority.index
    tol = cfg.rain.forecast_match_tol_s
    near = [f for f in fcst if abs((f.valid - target).total_seconds()) <= tol]
    return min(
        near,
        key=lambda f: (rank(f.source), abs((f.valid - target).total_seconds()), f.valid),
        default=None,
    )


def zone_rain(zone: ZoneInput, now: datetime, cfg: Config) -> ZoneRain:
    """Pick the rain input for a zone by the TRD 5 source hierarchy.

    The observed rate comes from the best-ranked observation newer than rain.max_age_s. With
    none, it falls back to the best forecast valid now, else 0, and has_obs is False.
    Antecedent wetness comes from the best-ranked observation that carries a 24 h total."""
    rank = cfg.rain.source_priority
    skew = cfg.staleness.max_future_skew_s
    for item in (*zone.obs, *zone.fcst):
        if item.source not in rank:
            raise ValueError(f"zone {zone.zone_id}: unknown rain source {item.source!r}")
    # (source rank, age in s, observation); the sort keys are rank then age, ties keep input order
    aged = [
        (
            rank.index(o.source),
            age_s(now, o.ts, skew, f"rain obs {o.source} zone {zone.zone_id}"),
            o,
        )
        for o in zone.obs
    ]
    aged.sort(key=lambda t: (t[0], t[1]))
    fresh = [t for t in aged if t[1] < cfg.rain.max_age_s]
    wet = [t for t in aged if t[2].mm_24h is not None and t[1] <= cfg.logit.antecedent_max_age_s]
    if fresh:
        _, obs_age, o = fresh[0]
        rate, source = o.mm_60m, o.source
    else:
        f0 = pick_fcst(zone.fcst, now, cfg)
        rate, source, obs_age = (f0.mm_per_h if f0 else 0.0), None, None
    return ZoneRain(
        now=now,
        obs_rate=rate,
        obs_source=source,
        obs_age_s=obs_age,
        mm_24h=wet[0][2].mm_24h if wet else None,
        alert_active=zone.alert_active,
        fcst=zone.fcst,
    )


def effective_rain(zr: ZoneRain, h: int, cfg: Config) -> Rain:
    """R(z, h): the trailing blend_window_min of rain ending at now + h.

    The part of the window already observed uses the observed rate, the part ahead of now uses
    the forecast valid at now + h. At h = 0 it is the observed rate; from blend_window_min on it
    is the forecast alone. With no matching forecast it falls back to the observed rate and
    fcst_missing is True."""
    a = min(1.0, h / cfg.rain.blend_window_min)
    if a == 0.0:
        return Rain(zr.obs_rate, None, False)
    f = pick_fcst(zr.fcst, zr.now + timedelta(minutes=h), cfg)
    # ponytail: one forecast value stands in for the mean over the window; persistence if none
    if f is None:
        return Rain(zr.obs_rate, None, True)
    return Rain((1.0 - a) * zr.obs_rate + a * f.mm_per_h, f.spread, False)


def antecedent(mm_24h: float | None, cfg: Config) -> float:
    """A(z) in [0, 1] from the 24 h total. Unknown wetness counts as dry (ponytail)."""
    return 0.0 if mm_24h is None else min(1.0, mm_24h / cfg.logit.antecedent_ref_mm)


def logit_x(
    base_logit: float,
    st: Structure,
    rain: Rain,
    a: float,
    vclass: str,
    cfg: Config,
) -> float:
    """x = base_logit + k_trigger * g(R) + k_antecedent * A + delta[c]  (TRD 6.2, no evidence)."""
    return (
        base_logit
        + cfg.logit.k_trigger * g(rain.value, st.r_low, st.r_high)
        + cfg.logit.k_antecedent * a
        + cfg.delta(vclass)
    )
