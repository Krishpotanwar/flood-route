"""Plain dataclasses for scoring inputs and outputs. Every datetime must be timezone-aware."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

CLEAR, WATCH, RISKY, IMPASSABLE, UNKNOWN = "clear", "watch", "risky", "impassable", "unknown"
STATES = (CLEAR, WATCH, RISKY, IMPASSABLE, UNKNOWN)
EVIDENCE_KINDS = ("report", "probe", "sensor", "camera", "official")
OVERRIDE_ACTIONS = ("close", "reopen", "force_watch")


def aware(dt: object, name: str) -> datetime:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime, got {dt!r}")
    return dt


def _num(v: object, name: str, lo: float | None = None, hi: float | None = None) -> None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{name} must be a finite number, got {v!r}")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ValueError(f"{name} out of range [{lo}, {hi}]: {v}")


def _flag(v: object, name: str) -> None:
    """A real bool only: the string "false" is truthy, and a wrong flag can hide a segment."""
    if not isinstance(v, bool):
        raise TypeError(f"{name} must be a boolean, got {v!r}")


def _id(v: object, name: str) -> None:
    if isinstance(v, bool) or not isinstance(v, int):
        raise TypeError(f"{name} must be an integer, got {v!r}")


def age_s(now: datetime, ts: datetime, max_skew_s: int, what: str) -> int:
    """Whole seconds from ts to now. A timestamp beyond the skew tolerance in the future is
    rejected: a feed with a wrong clock must not look fresh forever."""
    d = (now - ts).total_seconds()
    if d < -max_skew_s:
        raise ValueError(f"{what} is dated {-d:.0f}s in the future")
    return max(0, int(d))


@dataclass(frozen=True)
class RainObs:
    """Observed rain for a zone. mm_60m is mm over the last 60 min (equal to mm/h)."""

    source: str
    ts: datetime
    mm_60m: float
    mm_24h: float | None = None

    def __post_init__(self) -> None:
        aware(self.ts, "RainObs.ts")
        _num(self.mm_60m, "RainObs.mm_60m", lo=0)
        if self.mm_24h is not None:
            _num(self.mm_24h, "RainObs.mm_24h", lo=0)


@dataclass(frozen=True)
class RainFcst:
    """Forecast rain rate (mm/h) valid at a time. spread is the ensemble spread in mm/h."""

    source: str
    valid: datetime
    mm_per_h: float
    spread: float | None = None

    def __post_init__(self) -> None:
        aware(self.valid, "RainFcst.valid")
        _num(self.mm_per_h, "RainFcst.mm_per_h", lo=0)
        if self.spread is not None:
            _num(self.spread, "RainFcst.spread", lo=0)


@dataclass(frozen=True)
class ZoneInput:
    zone_id: int
    obs: tuple[RainObs, ...] = ()
    fcst: tuple[RainFcst, ...] = ()
    alert_active: bool = False  # an official alert (for example SACHET) is active for the zone

    def __post_init__(self) -> None:
        _id(self.zone_id, "ZoneInput.zone_id")
        _flag(self.alert_active, "ZoneInput.alert_active")


@dataclass(frozen=True)
class Evidence:
    """One evidence item on a segment (TRD 4 evidence table). source_id identifies the
    contributor for independence checks. kind 'official' is an official closure."""

    kind: str
    ts: datetime
    expires: datetime
    source_id: str
    trust: float = 1.0
    depth_cm: float | None = None
    speed_ratio: float | None = None
    contributors: int | None = None
    verified: bool = False

    def __post_init__(self) -> None:
        if self.kind not in EVIDENCE_KINDS:
            raise ValueError(f"Evidence.kind must be one of {EVIDENCE_KINDS}, got {self.kind!r}")
        if not self.source_id:
            raise ValueError("Evidence.source_id is required")
        aware(self.ts, "Evidence.ts")
        aware(self.expires, "Evidence.expires")
        if self.expires <= self.ts:
            raise ValueError("Evidence.expires must be after Evidence.ts")
        _flag(self.verified, "Evidence.verified")
        _num(self.trust, "Evidence.trust", lo=0, hi=1)
        for name in ("depth_cm", "speed_ratio"):
            if getattr(self, name) is not None:
                _num(getattr(self, name), f"Evidence.{name}", lo=0)
        if self.contributors is not None:
            _id(self.contributors, "Evidence.contributors")
            if self.contributors < 0:
                raise ValueError(
                    f"Evidence.contributors out of range [0, None]: {self.contributors}"
                )


@dataclass(frozen=True)
class Override:
    """A human decision (TRD 4 override table) valid from starts_at until expires_at."""

    action: str
    starts_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.action not in OVERRIDE_ACTIONS:
            raise ValueError(
                f"Override.action must be one of {OVERRIDE_ACTIONS}, got {self.action!r}"
            )
        aware(self.starts_at, "Override.starts_at")
        aware(self.expires_at, "Override.expires_at")
        if self.expires_at <= self.starts_at:
            raise ValueError("Override.expires_at must be after Override.starts_at")


@dataclass(frozen=True)
class SegmentInput:
    segment_id: int
    zone_id: int
    assessed: bool
    structure: str = "none"
    base_logit: float | None = None  # None: use the structure default from the config
    covered: bool = True  # inside the DEM and drain-mapped area (confidence input)
    evidence: tuple[Evidence, ...] = ()
    overrides: tuple[Override, ...] = ()

    def __post_init__(self) -> None:
        _id(self.segment_id, "SegmentInput.segment_id")
        _id(self.zone_id, "SegmentInput.zone_id")
        _flag(self.assessed, "SegmentInput.assessed")
        _flag(self.covered, "SegmentInput.covered")
        if self.base_logit is not None:
            _num(self.base_logit, "SegmentInput.base_logit")


@dataclass(frozen=True)
class RunInput:
    now: datetime
    zones: tuple[ZoneInput, ...]
    segments: tuple[SegmentInput, ...]

    def __post_init__(self) -> None:
        aware(self.now, "RunInput.now")


@dataclass(frozen=True)
class RiskRow:
    """One segment_risk row: a segment, a vehicle class and a horizon.

    assessed=False means no state, no p and no confidence (FR-R5). closed_since and
    reopen_ok_since are the model's own hysteresis state; an active override is only an overlay
    and shows in `override` (so closed_since can be None on an override-closed row).
    evidence_age_s is None when the row rests on no evidence at all."""

    segment_id: int
    vclass: str
    horizon_min: int
    assessed: bool
    p: float | None
    state: str | None
    confidence: str | None
    evidence_age_s: int | None
    model_version: str
    updated_at: datetime
    closed_since: datetime | None = None
    reopen_ok_since: datetime | None = None
    override: str | None = None
    reason: str = ""
    evidence_rules: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        aware(self.updated_at, "RiskRow.updated_at")
        for name in ("closed_since", "reopen_ok_since"):
            if getattr(self, name) is not None:
                aware(getattr(self, name), f"RiskRow.{name}")

    @property
    def key(self) -> tuple[int, str, int]:
        return (self.segment_id, self.vclass, self.horizon_min)


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat()


def snapshot(row: RiskRow) -> dict:
    """The state fields of a row as JSON-safe values (used as before and after in a Change)."""
    return {
        "state": row.state,
        "p": row.p,
        "confidence": row.confidence,
        "evidence_age_s": row.evidence_age_s,
        "override": row.override,
        "closed_since": _iso(row.closed_since),
        "reopen_ok_since": _iso(row.reopen_ok_since),
        "evidence_rules": list(row.evidence_rules),
    }


def row_dict(row: RiskRow) -> dict:
    return {
        "segment_id": row.segment_id,
        "vclass": row.vclass,
        "horizon_min": row.horizon_min,
        "assessed": row.assessed,
        "model_version": row.model_version,
        "updated_at": _iso(row.updated_at),
        "reason": row.reason,
        **snapshot(row),
    }


@dataclass(frozen=True)
class Change:
    """A published-state change, ready to write to history and audit_log (TRD 6.4).
    before is None the first time a row is seen. reason is a short code."""

    ts: datetime
    segment_id: int
    vclass: str
    horizon_min: int
    before: dict | None
    after: dict
    reason: str


@dataclass(frozen=True)
class RunResult:
    rows: tuple[RiskRow, ...]
    changes: tuple[Change, ...]
