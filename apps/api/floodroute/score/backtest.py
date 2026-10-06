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
    roc_auc: float | None = None
    brier_decomp: dict[str, float] | None = None
    optimal_threshold_csi: float | None = None

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
            "roc_auc": round(self.roc_auc, 4) if self.roc_auc is not None else None,
            "brier_decomp": self.brier_decomp,
            "optimal_threshold_csi": self.optimal_threshold_csi,
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


def compute_roc_auc(predictions: Sequence[tuple[float, bool]]) -> float | None:
    """Compute Area Under the Receiver Operating Characteristic curve (ROC-AUC).

    Uses trapezoidal integration over discrete threshold cutoffs.
    Returns None if dataset lacks both positive and negative classes.
    """
    if not predictions:
        return None
    positives = sum(1 for _, truth in predictions if truth)
    negatives = len(predictions) - positives
    if positives == 0 or negatives == 0:
        return None

    # Sort descending by predicted probability
    sorted_pairs = sorted(predictions, key=lambda x: x[0], reverse=True)

    tpr_prev = 0.0
    fpr_prev = 0.0
    cum_tp = 0
    cum_fp = 0
    auc = 0.0

    i = 0
    n = len(sorted_pairs)
    while i < n:
        cur_p = sorted_pairs[i][0]
        while i < n and sorted_pairs[i][0] == cur_p:
            if sorted_pairs[i][1]:
                cum_tp += 1
            else:
                cum_fp += 1
            i += 1
        tpr = cum_tp / positives
        fpr = cum_fp / negatives
        auc += (tpr + tpr_prev) * (fpr - fpr_prev) / 2.0
        tpr_prev = tpr
        fpr_prev = fpr

    return max(0.0, min(1.0, auc))


def decompose_brier_score(
    predictions: Sequence[tuple[float, bool]],
    n_bins: int = 5,
) -> dict[str, float] | None:
    """Decompose Brier score into reliability, resolution, and uncertainty (TRD 15).

    Brier = Reliability - Resolution + Uncertainty
    where:
      Uncertainty = base_rate * (1 - base_rate)
      Reliability = sum(N_k / N * (f_k - o_k)^2)
      Resolution  = sum(N_k / N * (o_k - base_rate)^2)
    """
    if not predictions:
        return None
    n = len(predictions)
    base_rate = sum(1 for _, truth in predictions if truth) / n
    uncertainty = base_rate * (1.0 - base_rate)

    bin_width = 1.0 / n_bins
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]

    for p, truth in predictions:
        idx = min(int(p / bin_width), n_bins - 1)
        bins[idx].append((p, truth))

    reliability = 0.0
    resolution = 0.0

    for b in bins:
        if not b:
            continue
        n_k = len(b)
        f_k = sum(p for p, _ in b) / n_k
        o_k = sum(1 for _, truth in b if truth) / n_k
        weight = n_k / n
        reliability += weight * ((f_k - o_k) ** 2)
        resolution += weight * ((o_k - base_rate) ** 2)

    brier = sum((p - (1.0 if truth else 0.0)) ** 2 for p, truth in predictions) / n

    return {
        "brier_score": round(brier, 4),
        "reliability": round(reliability, 4),
        "resolution": round(resolution, 4),
        "uncertainty": round(uncertainty, 4),
        "base_rate": round(base_rate, 4),
    }


def compute_reliability_diagram(
    predictions: Sequence[tuple[float, bool]],
    n_bins: int = 5,
) -> list[dict[str, Any]]:
    """Compute reliability diagram bins (mean forecast vs observed event frequency)."""
    if not predictions:
        return []
    bin_width = 1.0 / n_bins
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]

    for p, truth in predictions:
        idx = min(int(p / bin_width), n_bins - 1)
        bins[idx].append((p, truth))

    diagram: list[dict[str, Any]] = []
    for i, b in enumerate(bins):
        low = round(i * bin_width, 2)
        high = round((i + 1) * bin_width, 2)
        center = round((low + high) / 2.0, 2)
        count = len(b)
        mean_p = round(sum(p for p, _ in b) / count, 4) if count > 0 else center
        obs_freq = round(sum(1 for _, truth in b if truth) / count, 4) if count > 0 else 0.0

        diagram.append(
            {
                "bin_lower": low,
                "bin_upper": high,
                "bin_center": center,
                "count": count,
                "mean_pred_p": mean_p,
                "observed_frequency": obs_freq,
            }
        )

    return diagram


DEFAULT_SWEEP_THRESHOLDS = (
    0.05,
    0.10,
    0.15,
    0.20,
    0.25,
    0.30,
    0.35,
    0.40,
    0.45,
    0.50,
    0.60,
    0.70,
    0.80,
)


def compute_threshold_sweep(
    predictions: Sequence[tuple[float, bool]],
    thresholds: Sequence[float] = DEFAULT_SWEEP_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Evaluate contingency table metrics across multiple probability cutoffs."""
    if not predictions:
        return []

    points = []
    for thr in thresholds:
        ct = compute_contingency(predictions, threshold=thr)
        precision = (
            (ct.hits / (ct.hits + ct.false_alarms))
            if (ct.hits + ct.false_alarms) > 0
            else None
        )
        recall = ct.pod
        f1 = (
            (2 * precision * recall / (precision + recall))
            if precision is not None and recall is not None and (precision + recall) > 0
            else None
        )
        points.append(
            {
                "threshold": round(thr, 2),
                "pod": round(ct.pod, 4) if ct.pod is not None else None,
                "far": round(ct.far, 4) if ct.far is not None else None,
                "csi": round(ct.csi, 4) if ct.csi is not None else None,
                "accuracy": round(ct.accuracy, 4) if ct.accuracy is not None else None,
                "f1_score": round(f1, 4) if f1 is not None else None,
                "hits": ct.hits,
                "misses": ct.misses,
                "false_alarms": ct.false_alarms,
                "correct_negatives": ct.correct_negatives,
            }
        )
    return points


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
    """Seed benchmark historical ground-truth events into observed_event table.

    Idempotent: an event already present (same city, time and note) is skipped,
    so re-running the seeder adds zero rows.
    """
    sql = """
        insert into observed_event (
            city_id, observed_at, location, segment_id, kind,
            depth_class, source_kind, label_tier, source_url, note
        )
        select
            %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
            (
                select s.segment_id from segment s
                order by s.geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                limit 1
            ),
            %s, %s, %s, %s, %s, %s
        where not exists (
            select 1 from observed_event oe
            where oe.city_id = %s and oe.observed_at = %s and oe.note = %s
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
                    ev["city_id"],
                    ev["observed_at"],
                    ev["note"],
                ),
            )
            inserted += cur.rowcount
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
            "threshold_sweep": [],
            "reliability_diagram": [],
            "by_tier": {},
            "by_source": {},
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
    overall_auc = compute_roc_auc(preds_prob)
    overall_decomp = decompose_brier_score(preds_prob)
    sweep_points = compute_threshold_sweep(preds_prob)
    reliability_diagram = compute_reliability_diagram(preds_prob)

    opt_thr = None
    best_csi = -1.0
    for pt in sweep_points:
        if pt["csi"] is not None and pt["csi"] > best_csi:
            best_csi = pt["csi"]
            opt_thr = pt["threshold"]

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
        roc_auc=overall_auc,
        brier_decomp=overall_decomp,
        optimal_threshold_csi=opt_thr,
    )

    return {
        "status": "ok",
        "vclass": vclass,
        "horizon_min": horizon_min,
        "threshold": p_threshold,
        "metrics": metrics.as_dict(),
        "threshold_sweep": sweep_points,
        "reliability_diagram": reliability_diagram,
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


def run_full_calibration_audit(
    conn: psycopg.Connection,
    city_id: int | None = None,
    p_threshold: float = 0.30,
) -> dict[str, Any]:
    """Execute complete calibration evaluation across all vehicle classes and horizons."""
    matrix: dict[str, dict[str, Any]] = {}
    for vc in SUPPORTED_VCLASSES:
        matrix[vc] = {}
        for hz in SUPPORTED_HORIZONS:
            rep = run_db_backtest(
                conn,
                city_id=city_id,
                vclass=vc,
                horizon_min=hz,
                p_threshold=p_threshold,
            )
            matrix[vc][f"{hz}m"] = rep.get("metrics", {})
    return {
        "status": "ok",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "threshold": p_threshold,
        "matrix": matrix,
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
        "--audit-matrix",
        action="store_true",
        help="Run comprehensive calibration audit across all vehicle classes and horizons",
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

        if args.audit_matrix:
            audit = run_full_calibration_audit(conn, city_id=args.city_id, p_threshold=args.threshold)
            print("\n=== FloodRoute Full Calibration Matrix (TRD 15) ===")
            for vc, horizons in audit["matrix"].items():
                print(f"\nVehicle Class: {vc}")
                for hz, m in horizons.items():
                    print(
                        f"  {hz:5s}: samples={m.get('samples', 0)} | CSI={m.get('csi')} | "
                        f"POD={m.get('pod')} | FAR={m.get('far')} | "
                        f"ROC-AUC={m.get('roc_auc')} | Brier={m.get('brier_score')}"
                    )
            return

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
        print(
            f"Brier Score: {m.get('brier_score')} | ROC-AUC: {m.get('roc_auc')} | Depth MAE: {m.get('mae_depth_cm')} cm"
        )
        if m.get("brier_decomp"):
            bd = m["brier_decomp"]
            print(
                f"Brier Decomposition: Reliability={bd.get('reliability')}, Resolution={bd.get('resolution')}, Uncertainty={bd.get('uncertainty')}"
            )
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
