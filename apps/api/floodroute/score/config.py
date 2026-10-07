"""Strict loader for data/config/scoring.v0.json.

Unknown keys, missing keys, wrong types, duplicate keys, NaN and inconsistent values all raise
ConfigError. Every group carries `provisional` and `note`; a provisional group needs a note.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, fields, is_dataclass
from itertools import pairwise
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

# apps/api/floodroute/score/config.py -> repo root is four levels above the package
DEFAULT_PATH = Path(__file__).resolve().parents[4] / "data" / "config" / "scoring.v0.json"


class ConfigError(ValueError):
    pass


def _check(ok: bool, msg: str) -> None:
    if not ok:
        raise ConfigError(msg)


@dataclass(frozen=True)
class Group:
    provisional: bool
    note: str

    def __post_init__(self) -> None:
        _check(isinstance(self.note, str), "note must be a string")
        _check(
            not self.provisional or self.note.strip() != "",
            f"{type(self).__name__}: a provisional group needs a non-empty note",
        )
        self.check()

    def check(self) -> None:  # overridden by groups with value constraints
        pass


@dataclass(frozen=True)
class States(Group):
    watch_min: float
    risky_min: float
    impassable_min: float

    def check(self) -> None:
        _check(
            0 < self.watch_min < self.risky_min < self.impassable_min < 1,
            "states: need 0 < watch_min < risky_min < impassable_min < 1",
        )


@dataclass(frozen=True)
class Hysteresis(Group):
    reopen_below: float
    reopen_hold_s: int

    def check(self) -> None:
        _check(0 < self.reopen_below < 1, "hysteresis.reopen_below must be in (0, 1)")
        _check(self.reopen_hold_s > 0, "hysteresis.reopen_hold_s must be > 0")


@dataclass(frozen=True)
class Staleness(Group):
    max_age_s: int
    max_future_skew_s: int

    def check(self) -> None:
        _check(self.max_age_s > 0, "staleness.max_age_s must be > 0")
        _check(self.max_future_skew_s >= 0, "staleness.max_future_skew_s must be >= 0")


@dataclass(frozen=True)
class Rain(Group):
    source_priority: tuple[str, ...]
    max_age_s: int
    blend_window_min: float
    forecast_match_tol_s: int

    def check(self) -> None:
        _check(len(self.source_priority) > 0, "rain.source_priority must not be empty")
        _check(
            len(set(self.source_priority)) == len(self.source_priority),
            "rain.source_priority has duplicates",
        )
        _check(
            self.max_age_s > 0 and self.blend_window_min > 0,
            "rain.max_age_s and blend_window_min must be > 0",
        )
        _check(self.forecast_match_tol_s >= 0, "rain.forecast_match_tol_s must be >= 0")


@dataclass(frozen=True)
class Logit(Group):
    k_trigger: float
    k_antecedent: float
    antecedent_ref_mm: float
    antecedent_max_age_s: int
    delta_reference_class: str
    delta_per_ln_depth: float

    def check(self) -> None:
        _check(
            self.k_trigger >= 0 and self.k_antecedent >= 0,
            "logit.k_trigger and k_antecedent must be >= 0",
        )
        _check(
            self.antecedent_ref_mm > 0 and self.antecedent_max_age_s > 0,
            "logit.antecedent_ref_mm and antecedent_max_age_s must be > 0",
        )
        _check(
            self.delta_per_ln_depth >= 0,
            "logit.delta_per_ln_depth must be >= 0 (a lower unusable depth must not lower risk)",
        )


@dataclass(frozen=True)
class Structure(Group):
    base_logit: float
    r_low: float
    r_high: float

    def check(self) -> None:
        _check(0 <= self.r_low < self.r_high, "structure: need 0 <= r_low < r_high")


@dataclass(frozen=True)
class Profile(Group):
    caution_cm: float
    unusable_cm: float
    basis: str

    def check(self) -> None:
        _check(
            0 < self.caution_cm < self.unusable_cm,
            "vehicle profile: need 0 < caution_cm < unusable_cm",
        )
        _check(self.basis.strip() != "", "vehicle profile: basis must not be empty")


@dataclass(frozen=True)
class EvidenceRules(Group):
    tau_min: float
    horizon_tau_min: float
    report_min_trust: float
    corroboration_window_s: int
    corroboration_min_sources: int
    report_floor_p: float
    depth_unusable_floor_p: float
    depth_clear_cap_p: float
    probe_speed_ratio_below: float
    probe_min_contributors: int
    probe_logit: float

    def check(self) -> None:
        _check(
            self.tau_min > 0 and self.horizon_tau_min > 0,
            "evidence: tau_min and horizon_tau_min must be > 0",
        )
        _check(0 <= self.report_min_trust <= 1, "evidence.report_min_trust must be in [0, 1]")
        _check(self.corroboration_window_s > 0, "evidence.corroboration_window_s must be > 0")
        # FR-R8: a single report must never close a segment
        _check(
            self.corroboration_min_sources >= 2,
            "evidence.corroboration_min_sources must be >= 2 (FR-R8)",
        )
        for name in ("report_floor_p", "depth_unusable_floor_p", "depth_clear_cap_p"):
            _check(0 < getattr(self, name) < 1, f"evidence.{name} must be in (0, 1)")
        _check(
            self.depth_clear_cap_p < self.depth_unusable_floor_p,
            "evidence: cap must be below the depth floor",
        )
        _check(self.probe_speed_ratio_below > 0, "evidence.probe_speed_ratio_below must be > 0")
        # TRD 12: k-anonymity floor of 5 contributors
        _check(
            self.probe_min_contributors >= 5,
            "evidence.probe_min_contributors must be >= 5 (k-anonymity floor)",
        )
        _check(self.probe_logit >= 0, "evidence.probe_logit must be >= 0")


@dataclass(frozen=True)
class Overrides(Group):
    reopen_cap_p: float

    def check(self) -> None:
        _check(0 < self.reopen_cap_p < 1, "overrides.reopen_cap_p must be in (0, 1)")


@dataclass(frozen=True)
class ConfidenceParams(Group):
    high_max_age_s: int
    high_min_sources: int
    spread_penalty_mm_h: float

    def check(self) -> None:
        _check(
            self.high_max_age_s > 0 and self.high_min_sources >= 1,
            "confidence: high_max_age_s > 0 and high_min_sources >= 1",
        )
        _check(self.spread_penalty_mm_h > 0, "confidence.spread_penalty_mm_h must be > 0")


@dataclass(frozen=True)
class Config:
    model_version: str
    horizons_min: tuple[int, ...]
    states: States
    hysteresis: Hysteresis
    staleness: Staleness
    rain: Rain
    logit: Logit
    structures: dict[str, Structure]
    vehicle_profiles: dict[str, Profile]
    evidence: EvidenceRules
    overrides: Overrides
    confidence: ConfidenceParams

    def __post_init__(self) -> None:
        _check(self.model_version.strip() != "", "model_version must not be empty")
        h = self.horizons_min
        _check(
            len(h) > 0 and h[0] >= 0 and all(a < b for a, b in pairwise(h)),
            "horizons_min must be non-empty, non-negative and strictly increasing",
        )
        _check(
            len(self.structures) > 0 and len(self.vehicle_profiles) > 0,
            "structures and vehicle_profiles must not be empty",
        )
        _check(
            self.logit.delta_reference_class in self.vehicle_profiles,
            "logit.delta_reference_class is not a vehicle profile",
        )
        _check(
            self.hysteresis.reopen_below < self.states.impassable_min,
            "hysteresis.reopen_below must be below states.impassable_min",
        )

    @property
    def vclasses(self) -> tuple[str, ...]:
        return tuple(self.vehicle_profiles)

    def delta(self, vclass: str) -> float:
        """Logit shift for a class, derived from its profile: a lower unusable depth means
        a higher shift. Zero for the reference class."""
        ref = self.vehicle_profiles[self.logit.delta_reference_class].unusable_cm
        return self.logit.delta_per_ln_depth * math.log(
            ref / self.vehicle_profiles[vclass].unusable_cm
        )


def _coerce(tp: object, v: object, path: str) -> object:
    origin = get_origin(tp)
    if is_dataclass(tp):
        return _build(tp, v, path)  # type: ignore[arg-type]
    if origin is tuple:
        item = next(a for a in get_args(tp) if a is not Ellipsis)
        _check(isinstance(v, list), f"{path}: expected a list")
        return tuple(_coerce(item, x, f"{path}[{i}]") for i, x in enumerate(v))  # type: ignore[arg-type]
    if origin is dict:
        _check(isinstance(v, dict), f"{path}: expected an object")
        vt = get_args(tp)[1]
        return {k: _coerce(vt, x, f"{path}.{k}") for k, x in v.items()}  # type: ignore[union-attr]
    if tp is bool:
        ok = isinstance(v, bool)
    elif tp is int:
        ok = isinstance(v, int) and not isinstance(v, bool)
    elif tp is float:
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)  # type: ignore[arg-type]
        v = float(v) if ok else v  # type: ignore[arg-type]
    else:
        ok = tp is str and isinstance(v, str)
    _check(ok, f"{path}: expected {getattr(tp, '__name__', tp)}, got {v!r}")
    return v


def _build(cls: type, data: object, path: str) -> object:
    _check(isinstance(data, dict), f"{path or '<root>'}: expected an object")
    names = {f.name for f in fields(cls)}
    extra, missing = sorted(set(data) - names), sorted(names - set(data))  # type: ignore[arg-type]
    _check(
        not extra and not missing,
        f"{path or '<root>'}: unknown keys {extra}, missing keys {missing}",
    )
    hints = get_type_hints(cls)
    return cls(**{n: _coerce(hints[n], data[n], f"{path}.{n}" if path else n) for n in names})  # type: ignore[index]


def _no_dupes(pairs: list[tuple[str, object]]) -> dict:
    d = dict(pairs)
    _check(len(d) == len(pairs), "duplicate keys in config JSON")
    return d


def _bad_constant(name: str) -> object:
    raise ConfigError(f"{name} is not allowed in config JSON")


def parse_config(text: str) -> Config:
    try:
        data = json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_bad_constant)
    except json.JSONDecodeError as e:
        raise ConfigError(f"config is not valid JSON: {e}") from e
    return _build(Config, data, "")  # type: ignore[return-value]


def load_config(path: str | Path | None = None) -> Config:
    """Load the scoring config. An explicit path wins, then FLOODROUTE_SCORING_CONFIG,
    then the repo default. A missing or unreadable file is a ConfigError, never an OSError."""
    if path is None:
        env = os.environ.get("FLOODROUTE_SCORING_CONFIG")
        path = Path(env) if env else DEFAULT_PATH
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read scoring config {path}: {e}") from e
    return parse_config(text)
