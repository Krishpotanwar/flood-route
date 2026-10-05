"""Replay a JSONL event log through the scorer: events in, states out.

One JSON object per line, in time order. Every event has "type" and "ts" (ISO 8601 with a UTC
offset). Unknown types, unknown keys, missing keys, naive times and out-of-order events raise
ValueError naming the line.

  segment   segment_id, zone_id, assessed, [structure, base_logit, covered]
  rain_obs  zone_id, source, mm_60m, [mm_24h]           observed at ts
  rain_fcst zone_id, source, valid, mm_per_h, [spread]  known from ts
  alert     zone_id, active
  evidence  segment_id, kind, expires, source_id, [trust, depth_cm, speed_ratio,
            contributors, verified]                      observed at ts
  override  segment_id, action, starts_at, expires_at
  tick      (no fields) run the scorer at ts

Each tick yields {"ts", "rows", "changes"}. The state of the previous tick is the next tick's
previous state, so hysteresis carries through the log.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any

from .config import Config
from .records import (
    Change,
    Evidence,
    Override,
    RainFcst,
    RainObs,
    RunInput,
    SegmentInput,
    ZoneInput,
    aware,
    row_dict,
)
from .run import score_run


def _dt(v: Any, name: str) -> datetime:
    if not isinstance(v, str):
        raise TypeError(f"{name} must be an ISO 8601 string")
    return aware(datetime.fromisoformat(v), name)


def _change_dict(c: Change) -> dict:
    return {
        "ts": c.ts.isoformat(),
        "segment_id": c.segment_id,
        "vclass": c.vclass,
        "horizon_min": c.horizon_min,
        "before": c.before,
        "after": c.after,
        "reason": c.reason,
    }


def replay(lines: Iterable[str], cfg: Config) -> Iterator[dict]:
    segs: dict[int, dict] = {}
    obs: dict[tuple[int, str], RainObs] = {}
    fcst: dict[tuple[int, str, datetime], RainFcst] = {}
    alerts: dict[int, bool] = {}
    evidence: dict[int, list[Evidence]] = {}
    overrides: dict[int, list[Override]] = {}
    prev: dict = {}
    last: datetime | None = None

    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            if not isinstance(e, dict):
                raise TypeError("an event must be a JSON object")
            kind, ts = e.pop("type"), _dt(e.pop("ts"), "ts")
            if last is not None and ts < last:
                raise ValueError(f"event at {ts.isoformat()} is out of time order")
            last = ts
            if kind == "segment":
                segs[e.pop("segment_id")] = e
            elif kind == "rain_obs":
                zid = e.pop("zone_id")
                obs[(zid, e["source"])] = RainObs(ts=ts, **e)
            elif kind == "rain_fcst":
                zid, valid = e.pop("zone_id"), _dt(e.pop("valid"), "valid")
                fcst[(zid, e["source"], valid)] = RainFcst(valid=valid, **e)
            elif kind == "alert":
                if not isinstance(e["active"], bool) or set(e) != {"zone_id", "active"}:
                    raise ValueError("alert needs zone_id and a boolean active, nothing else")
                alerts[e["zone_id"]] = e["active"]
            elif kind == "evidence":
                sid = e.pop("segment_id")
                e["expires"] = _dt(e["expires"], "expires")
                evidence.setdefault(sid, []).append(Evidence(ts=ts, **e))
            elif kind == "override":
                sid = e.pop("segment_id")
                ov = Override(
                    action=e.pop("action"),
                    starts_at=_dt(e.pop("starts_at"), "starts_at"),
                    expires_at=_dt(e.pop("expires_at"), "expires_at"),
                )
                if e:
                    raise ValueError(f"unknown override keys {sorted(e)}")
                overrides.setdefault(sid, []).append(ov)
            elif kind == "tick":
                if e:
                    raise ValueError(f"unknown tick keys {sorted(e)}")
                result = score_run(
                    _run_input(ts, segs, obs, fcst, alerts, evidence, overrides), prev, cfg
                )
                prev = {r.key: r for r in result.rows}
                yield {
                    "ts": ts.isoformat(),
                    "rows": [row_dict(r) for r in result.rows],
                    "changes": [_change_dict(c) for c in result.changes],
                }
            else:
                raise ValueError(f"unknown event type {kind!r}")
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(f"line {n}: {type(err).__name__}: {err}") from err


def _run_input(ts, segs, obs, fcst, alerts, evidence, overrides) -> RunInput:
    zone_ids = (
        {s["zone_id"] for s in segs.values()}
        | {z for z, _ in obs}
        | {z for z, _, _ in fcst}
        | set(alerts)
    )
    zones = tuple(
        ZoneInput(
            zone_id=z,
            obs=tuple(o for (zz, _), o in sorted(obs.items()) if zz == z),
            fcst=tuple(f for (zz, _, _), f in sorted(fcst.items()) if zz == z),
            alert_active=alerts.get(z, False),
        )
        for z in sorted(zone_ids)
    )
    segments = tuple(
        SegmentInput(
            segment_id=sid,
            evidence=tuple(evidence.get(sid, ())),
            overrides=tuple(overrides.get(sid, ())),
            **kw,
        )
        for sid, kw in sorted(segs.items())
    )
    return RunInput(ts, zones, segments)


def _round(x: Any) -> Any:
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    return x


def dumps(tick: dict) -> str:
    """One output line: sorted keys, compact, floats rounded to 6 places for stable text."""
    return json.dumps(_round(tick), sort_keys=True, separators=(",", ":"))
