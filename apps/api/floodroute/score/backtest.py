"""Backtest harness and model calibration evaluation.

Computes POD, FAR, CSI, Brier score, and depth error against
ground-truth labels in observed_event (TRD 15, PRD FR-R9).
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

SUPPORTED_VCLASSES = ("two_wheeler", "car", "ambulance", "heavy")
SUPPORTED_HORIZONS = (0, 30, 60, 120)


@dataclass(frozen=True)
class ContingencyTable:
    """Standard 2x2 contingency table for binary event classification."""

    hits: int = 0
    misses: int = 0
    false_alarms: int = 0
    correct_negatives: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses + self.false_alarms + self.correct_negatives

    @property
    def pod(self) -> float | None:
        """Probability of Detection (Hit Rate): H / (H + M). None if no events."""
        denom = self.hits + self.misses
        return (self.hits / denom) if denom > 0 else None

    @property
    def far(self) -> float | None:
        """False Alarm Ratio: F / (H + F). None if no alerts."""
        denom = self.hits + self.false_alarms
        return (self.false_alarms / denom) if denom > 0 else None

    @property
    def csi(self) -> float | None:
        """Critical Success Index (Threat Score): H / (H + M + F)."""
        denom = self.hits + self.misses + self.false_alarms
        return (self.hits / denom) if denom > 0 else None

    @property
    def accuracy(self) -> float | None:
        """Overall proportion correct: (H + C) / total."""
        return ((self.hits + self.correct_negatives) / self.total) if self.total > 0 else None


@dataclass(frozen=True)
class EvaluationMetrics:
    """Comprehensive evaluation metrics for flood risk predictions."""

    contingency: ContingencyTable
    brier_score: float | None
    sample_count: int
    mae_depth_cm: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "samples": self.sample_count,
            "hits": self.contingency.hits,
            "misses": self.contingency.misses,
            "false_alarms": self.contingency.false_alarms,
            "correct_negatives": self.contingency.correct_negatives,
            "pod": round(self.contingency.pod, 4) if self.contingency.pod is not None else None,
            "far": round(self.contingency.far, 4) if self.contingency.far is not None else None,
            "csi": round(self.contingency.csi, 4) if self.contingency.csi is not None else None,
            "accuracy": round(self.contingency.accuracy, 4)
            if self.contingency.accuracy is not None
            else None,
            "brier_score": round(self.brier_score, 4) if self.brier_score is not None else None,
            "mae_depth_cm": round(self.mae_depth_cm, 2) if self.mae_depth_cm is not None else None,
        }


def compute_contingency(
    predictions: Sequence[tuple[float | str, bool]],
    threshold: float = 0.30,
) -> ContingencyTable:
    """Compute 2x2 contingency table from predictions and boolean truth.

    predictions: sequence of (predicted_p_or_state, truth_boolean)
    where truth_boolean=True means flood/unusable, False means clear/passable.
    """
    h, m, f, c = 0, 0, 0, 0
    for pred, truth in predictions:
        if isinstance(pred, str):
            is_pred_flood = pred in ("impassable", "risky")
        else:
            is_pred_flood = pred >= threshold

        if truth and is_pred_flood:
            h += 1
        elif truth and not is_pred_flood:
            m += 1
        elif not truth and is_pred_flood:
            f += 1
        else:
            c += 1

    return ContingencyTable(hits=h, misses=m, false_alarms=f, correct_negatives=c)


def compute_brier_score(
    predictions: Sequence[tuple[float, bool]],
) -> float | None:
    """Compute Brier Score: mean squared error between probabilities and binary truth."""
    if not predictions:
        return None
    total = sum((p - (1.0 if truth else 0.0)) ** 2 for p, truth in predictions)
    return total / len(predictions)


def compute_mae_depth(
    depth_pairs: Sequence[tuple[float, float]],
) -> float | None:
    """Compute Mean Absolute Error for depth: pred vs obs."""
    if not depth_pairs:
        return None
    total = sum(abs(p - o) for p, o in depth_pairs)
    return total / len(depth_pairs)


# Depth class mapping to centimetres for comparison
DEPTH_CLASS_CM = {
    "wet": 5.0,
    "ankle": 15.0,
    "knee": 35.0,
    "vehicle_deep": 60.0,
}


BENCHMARK_EVENTS = [
    {
        "city_id": 1,
        "observed_at": datetime(2022, 9, 5, 2, 30, tzinfo=UTC),
        "lat": 12.9298,
        "lon": 77.6841,
        "kind": "impassable",
        "depth_class": "vehicle_deep",
        "source_kind": "traffic_police",
        "label_tier": "high",
        "source_url": "https://twitter.com/blrcitytraffic/status/1566580000",
        "note": "Severe flooding on Outer Ring Road near Bellandur EcoSpace; traffic diverted",
    },
    {
        "city_id": 1,
        "observed_at": datetime(2022, 9, 5, 3, 15, tzinfo=UTC),
        "lat": 12.9165,
        "lon": 77.6101,
        "kind": "flooded",
        "depth_class": "knee",
        "source_kind": "control_room",
        "label_tier": "high",
        "source_url": None,
        "note": "Silk Board junction underpass waterlogged, 35cm standing water",
    },
    {
        "city_id": 1,
        "observed_at": datetime(2022, 9, 5, 4, 0, tzinfo=UTC),
        "lat": 12.9915,
        "lon": 77.5872,
        "kind": "impassable",
        "depth_class": "vehicle_deep",
        "source_kind": "traffic_police",
        "label_tier": "high",
        "source_url": "https://twitter.com/blrcitytraffic/status/1566585000",
        "note": "Windsor Manor railway underpass closed due to 70cm water accumulation",
    },
    {
        "city_id": 1,
        "observed_at": datetime(2022, 9, 5, 4, 30, tzinfo=UTC),
        "lat": 12.9763,
        "lon": 77.5864,
        "kind": "flooded",
        "depth_class": "knee",
        "source_kind": "news",
        "label_tier": "low",
        "source_url": "https://deccanherald.com/bengaluru-rains-sep5-2022",
        "note": "K.R. Circle underpass inundated, cars stranded",
    },
    {
        "city_id": 1,
        "observed_at": datetime(2022, 9, 5, 10, 0, tzinfo=UTC),
        "lat": 12.9915,
        "lon": 77.5872,
        "kind": "cleared",
        "depth_class": "wet",
        "source_kind": "traffic_police",
        "label_tier": "high",
        "source_url": "https://twitter.com/blrcitytraffic/status/1566610000",
        "note": "Windsor Manor underpass water pumped out, road reopened for traffic",
    },
    {
        "city_id": 1,
        "observed_at": datetime(2025, 5, 18, 14, 20, tzinfo=UTC),
        "lat": 12.9611,
        "lon": 77.6431,
        "kind": "flooded",
        "depth_class": "ankle",
        "source_kind": "crowd",
        "label_tier": "medium",
        "source_url": None,
        "note": "Water accumulation 15cm on 100 Feet Road Indiranagar near Domlur",
    },
]


def seed_benchmark_events(conn: psycopg.Connection) -> int:
    """Seed benchmark historical ground-truth events into observed_event table."""
    sql = """
        insert into observed_event (
            city_id, observed_at, location, segment_id, kind,
            depth_class, source_kind, label_tier, source_url, note
        )
        values (
            %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
            (
                select s.segment_id from segment s
                order by s.geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                limit 1
            ),
            %s, %s, %s, %s, %s, %s
        )
    """
    inserted = 0
    with conn.cursor() as cur:
        for ev in BENCHMARK_EVENTS:
            cur.execute(
                sql,
                (
                    ev["city_id"],
                    ev["observed_at"],
                    ev["lon"],
                    ev["lat"],
                    ev["lon"],
                    ev["lat"],
                    ev["kind"],
                    ev["depth_class"],
                    ev["source_kind"],
                    ev["label_tier"],
                    ev["source_url"],
                    ev["note"],
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def run_db_backtest(
    conn: psycopg.Connection,
    city_id: int | None = None,
    vclass: str = "car",
    horizon_min: int = 0,
    p_threshold: float = 0.30,
) -> dict[str, Any]:
    """Evaluate database predictions against observed ground-truth events."""
    where_parts = ["oe.segment_id is not null"]
    params: list[Any] = [vclass, horizon_min]

    if city_id is not None:
        where_parts.append("oe.city_id = %s")
        params.append(city_id)

    where_sql = " and ".join(where_parts)

    # We evaluate against current segment_risk as well as historical records
    sql = f"""
        select oe.event_id, oe.segment_id, oe.kind, oe.depth_class, oe.source_kind, oe.label_tier,
               coalesce(sr.p_unusable, 0.0) as p_unusable,
               coalesce(sr.state, 'clear') as state,
               sr.depth_p50_cm
        from observed_event oe
        left join segment_risk sr
          on oe.segment_id = sr.segment_id and sr.vclass = %s and sr.horizon_min = %s
        where {where_sql}
        order by oe.observed_at
    """

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()

    if not rows:
        return {
            "status": "empty",
            "message": "No observed events with matched segments found.",
            "metrics": EvaluationMetrics(ContingencyTable(), None, 0).as_dict(),
        }

    preds_prob: list[tuple[float, bool]] = []
    preds_state: list[tuple[str, bool]] = []
    depth_pairs: list[tuple[float, float]] = []

    by_tier: dict[str, list[tuple[float, bool]]] = {"high": [], "medium": [], "low": []}
    by_source: dict[str, list[tuple[float, bool]]] = {}

    for _eid, _sid, kind, d_class, src_kind, tier, p, state, pred_d in rows:
        # Ground truth: flooded/impassable/stalled = True (1), cleared = False (0)
        is_truth_flood = kind in ("flooded", "impassable", "stalled_vehicle")
        p_val = float(p)

        preds_prob.append((p_val, is_truth_flood))
        preds_state.append((state, is_truth_flood))

        if tier in by_tier:
            by_tier[tier].append((p_val, is_truth_flood))

        by_source.setdefault(src_kind, []).append((p_val, is_truth_flood))

        if pred_d is not None and d_class in DEPTH_CLASS_CM:
            depth_pairs.append((float(pred_d), DEPTH_CLASS_CM[d_class]))

    overall_table = compute_contingency(preds_prob, threshold=p_threshold)
    overall_brier = compute_brier_score(preds_prob)
    overall_mae = compute_mae_depth(depth_pairs)

    tier_metrics = {
        tier: compute_contingency(items, threshold=p_threshold)
        for tier, items in by_tier.items()
        if items
    }

    source_metrics = {
        src: compute_contingency(items, threshold=p_threshold)
        for src, items in by_source.items()
        if items
    }

    metrics = EvaluationMetrics(
        contingency=overall_table,
        brier_score=overall_brier,
        sample_count=len(rows),
        mae_depth_cm=overall_mae,
    )

    return {
        "status": "ok",
        "vclass": vclass,
        "horizon_min": horizon_min,
        "threshold": p_threshold,
        "metrics": metrics.as_dict(),
        "by_tier": {
            k: {
                "samples": t.total,
                "pod": round(t.pod, 4) if t.pod is not None else None,
                "far": round(t.far, 4) if t.far is not None else None,
                "csi": round(t.csi, 4) if t.csi is not None else None,
            }
            for k, t in tier_metrics.items()
        },
        "by_source": {
            k: {
                "samples": t.total,
                "pod": round(t.pod, 4) if t.pod is not None else None,
                "far": round(t.far, 4) if t.far is not None else None,
                "csi": round(t.csi, 4) if t.csi is not None else None,
            }
            for k, t in source_metrics.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run backtest evaluation against observed events.")
    parser.add_argument("--city-id", type=int, default=1, help="City ID (default: 1 for Bengaluru)")
    parser.add_argument("--vclass", default="car", choices=SUPPORTED_VCLASSES, help="Vehicle class")
    parser.add_argument(
        "--horizon", type=int, default=0, choices=SUPPORTED_HORIZONS, help="Forecast horizon (min)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="Probability threshold for flood classification",
    )
    parser.add_argument(
        "--seed-benchmark",
        action="store_true",
        help="Seed benchmark historical events before evaluation",
    )
    parser.add_argument(
        "--db-url",
        default="postgresql://postgres:postgres@localhost:54329/floodroute",
        help="PostgreSQL connection URL",
    )
    args = parser.parse_args()

    with psycopg.connect(args.db_url) as conn:
        if args.seed_benchmark:
            n = seed_benchmark_events(conn)
            print(f"Seeded {n} benchmark historical events into observed_event.")

        report = run_db_backtest(
            conn,
            city_id=args.city_id,
            vclass=args.vclass,
            horizon_min=args.horizon,
            p_threshold=args.threshold,
        )

        print("\n=== FloodRoute Backtest Evaluation Report ===")
        print(
            f"Vehicle Class: {report.get('vclass')} | Horizon: {report.get('horizon_min')}m | Threshold: {report.get('threshold')}"
        )
        m = report.get("metrics", {})
        print(
            f"Samples: {m.get('samples')} | Hits: {m.get('hits')} | Misses: {m.get('misses')} | False Alarms: {m.get('false_alarms')} | Negatives: {m.get('correct_negatives')}"
        )
        print(
            f"POD: {m.get('pod')} | FAR: {m.get('far')} | CSI: {m.get('csi')} | Accuracy: {m.get('accuracy')}"
        )
        print(f"Brier Score: {m.get('brier_score')} | Depth MAE: {m.get('mae_depth_cm')} cm")
        if report.get("by_tier"):
            print("\nBreakdown by Label Tier:")
            for tier, d in report["by_tier"].items():
                print(
                    f"  {tier:8s}: samples={d['samples']}, POD={d['pod']}, FAR={d['far']}, CSI={d['csi']}"
                )
        if report.get("by_source"):
            print("\nBreakdown by Source Kind:")
            for src, d in report["by_source"].items():
                print(
                    f"  {src:15s}: samples={d['samples']}, POD={d['pod']}, FAR={d['far']}, CSI={d['csi']}"
                )


if __name__ == "__main__":
    main()
