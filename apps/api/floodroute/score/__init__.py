"""Scoring model v0: pure, deterministic, replayable (TRD 6, PRD FR-R1 to FR-R8).

score_run(inputs, prev_state, cfg) -> RunResult(rows, changes). Config: data/config/scoring.v0.json.
Replay: python -m floodroute.score replay FILE
"""

from .config import Config, ConfigError, load_config
from .records import (
    Change,
    Evidence,
    Override,
    RainFcst,
    RainObs,
    RiskRow,
    RunInput,
    RunResult,
    SegmentInput,
    ZoneInput,
)
from .run import score_run, score_segment

__all__ = [
    "Change",
    "Config",
    "ConfigError",
    "Evidence",
    "Override",
    "RainFcst",
    "RainObs",
    "RiskRow",
    "RunInput",
    "RunResult",
    "SegmentInput",
    "ZoneInput",
    "load_config",
    "score_run",
    "score_segment",
]
