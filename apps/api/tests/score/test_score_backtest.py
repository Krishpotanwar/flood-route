"""Tests for floodroute.score.backtest (contingency metrics, Brier score, DB backtest)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floodroute.score.backtest import (
    ContingencyTable,
    compute_brier_score,
    compute_contingency,
    compute_mae_depth,
    compute_reliability_diagram,
    compute_roc_auc,
    compute_threshold_sweep,
    decompose_brier_score,
    run_db_backtest,
    run_full_calibration_audit,
    seed_benchmark_events,
)


def test_contingency_table_metrics():
    # H=8, M=2, F=1, C=9 -> total=20
    ct = ContingencyTable(hits=8, misses=2, false_alarms=1, correct_negatives=9)
    assert ct.total == 20
    assert ct.pod == pytest.approx(0.8)
    assert ct.far == pytest.approx(1 / 9)
    assert ct.csi == pytest.approx(8 / 11)
    assert ct.accuracy == pytest.approx(17 / 20)


def test_contingency_table_zero_division():
    empty = ContingencyTable()
    assert empty.total == 0
    assert empty.pod is None
    assert empty.far is None
    assert empty.csi is None
    assert empty.accuracy is None

    # No events observed (H=0, M=0)
    no_events = ContingencyTable(hits=0, misses=0, false_alarms=2, correct_negatives=5)
    assert no_events.pod is None
    assert no_events.far == 1.0

    # No alerts issued (H=0, F=0)
    no_alerts = ContingencyTable(hits=0, misses=3, false_alarms=0, correct_negatives=5)
    assert no_alerts.pod == 0.0
    assert no_alerts.far is None


def test_compute_contingency_probabilities():
    # threshold = 0.30
    pairs = [
        (0.8, True),  # Hit
        (0.4, True),  # Hit
        (0.2, True),  # Miss
        (0.5, False),  # False alarm
        (0.1, False),  # Correct negative
    ]
    ct = compute_contingency(pairs, threshold=0.30)
    assert ct.hits == 2
    assert ct.misses == 1
    assert ct.false_alarms == 1
    assert ct.correct_negatives == 1
    assert ct.pod == pytest.approx(2 / 3)
    assert ct.far == pytest.approx(1 / 3)
    assert ct.csi == pytest.approx(2 / 4)


def test_compute_contingency_states():
    pairs = [
        ("impassable", True),  # Hit
        ("risky", True),  # Hit
        ("watch", True),  # Miss
        ("clear", True),  # Miss
        ("impassable", False),  # False alarm
        ("clear", False),  # Correct negative
    ]
    ct = compute_contingency(pairs)
    assert ct.hits == 2
    assert ct.misses == 2
    assert ct.false_alarms == 1
    assert ct.correct_negatives == 1


def test_brier_score_and_mae():
    assert compute_brier_score([]) is None
    assert compute_mae_depth([]) is None

    # Perfect forecast
    perfect = [(1.0, True), (0.0, False)]
    assert compute_brier_score(perfect) == 0.0

    # Intermediate forecast
    # (0.8 - 1)^2 = 0.04
    # (0.2 - 0)^2 = 0.04
    # Mean = 0.04
    sample = [(0.8, True), (0.2, False)]
    assert compute_brier_score(sample) == pytest.approx(0.04)

    # MAE depth: |30 - 35| + |10 - 15| = 5 + 5 = 10 / 2 = 5.0
    depth_pairs = [(30.0, 35.0), (10.0, 15.0)]
    assert compute_mae_depth(depth_pairs) == pytest.approx(5.0)


def test_db_backtest_with_benchmark_events(db):
    # 1. Create zone and segments
    db.execute(
        "insert into zone (zone_id, city_id, geom, params) "
        "values (1, 1, 'SRID=4326;MULTIPOLYGON(((77.4 12.8, 77.85 12.8, 77.85 13.2, 77.4 13.2, 77.4 12.8)))', '{}')"
    )
    db.execute(
        "insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed) "
        "values (1001, 1, 'SRID=4326;LINESTRING(77.6841 12.9298, 77.6842 12.9299)', 'primary', 1, true), "
        "       (1002, 2, 'SRID=4326;LINESTRING(77.6101 12.9165, 77.6102 12.9166)', 'primary', 1, true)"
    )

    # 2. Add risk predictions
    now = datetime.now(UTC)
    db.execute(
        "insert into segment_risk (segment_id, vclass, horizon_min, p_unusable, state, confidence, evidence_age_s, model_version, updated_at, depth_p50_cm, depth_p90_cm) "
        "values (1001, 'car', 0, 0.75, 'impassable', 'high', 0, 'v0.0.1', %s, 50.0, 70.0), "
        "       (1002, 'car', 0, 0.10, 'watch', 'low', 0, 'v0.0.1', %s, 10.0, 20.0)",
        (now, now),
    )

    # 3. Seed benchmark events
    count = seed_benchmark_events(db)
    assert count == 6

    # 4. Run backtest
    report = run_db_backtest(db, city_id=1, vclass="car", horizon_min=0, p_threshold=0.30)
    assert report["status"] == "ok"
    assert report["vclass"] == "car"
    assert report["horizon_min"] == 0

    m = report["metrics"]
    assert m["samples"] > 0
    assert m["brier_score"] is not None
    assert "hits" in m
    assert "misses" in m
    assert "false_alarms" in m
    assert "correct_negatives" in m

    # Breakdowns
    assert "high" in report["by_tier"]
    assert "traffic_police" in report["by_source"]


def test_compute_roc_auc():
    # Empty
    assert compute_roc_auc([]) is None

    # Single-class datasets (AUC undefined)
    assert compute_roc_auc([(0.8, True), (0.4, True)]) is None
    assert compute_roc_auc([(0.8, False), (0.4, False)]) is None

    # Perfect discrimination
    perfect = [(0.9, True), (0.8, True), (0.3, False), (0.1, False)]
    assert compute_roc_auc(perfect) == pytest.approx(1.0)

    # Completely inverted
    inverted = [(0.1, True), (0.2, True), (0.8, False), (0.9, False)]
    assert compute_roc_auc(inverted) == pytest.approx(0.0)

    # Intermediate discrimination
    inter = [(0.9, True), (0.7, False), (0.6, True), (0.2, False)]
    assert compute_roc_auc(inter) == pytest.approx(0.75)


def test_decompose_brier_score_and_diagram():
    assert decompose_brier_score([]) is None
    assert compute_reliability_diagram([]) == []

    dataset = [
        (0.9, True),
        (0.8, True),
        (0.4, True),
        (0.2, False),
        (0.1, False),
    ]

    decomp = decompose_brier_score(dataset, n_bins=5)
    assert decomp is not None
    assert "reliability" in decomp
    assert "resolution" in decomp
    assert "uncertainty" in decomp
    assert "brier_score" in decomp
    assert "base_rate" in decomp
    assert decomp["base_rate"] == pytest.approx(3 / 5)

    diagram = compute_reliability_diagram(dataset, n_bins=5)
    assert len(diagram) == 5
    assert sum(b["count"] for b in diagram) == len(dataset)
    for b in diagram:
        assert "bin_lower" in b
        assert "bin_upper" in b
        assert "bin_center" in b
        assert "mean_pred_p" in b
        assert "observed_frequency" in b


def test_compute_threshold_sweep():
    assert compute_threshold_sweep([]) == []

    dataset = [
        (0.8, True),
        (0.4, True),
        (0.2, True),
        (0.5, False),
        (0.1, False),
    ]

    sweep = compute_threshold_sweep(dataset, thresholds=[0.10, 0.30, 0.50])
    assert len(sweep) == 3
    assert sweep[0]["threshold"] == 0.10
    assert sweep[1]["threshold"] == 0.30
    assert sweep[2]["threshold"] == 0.50

    pt50 = sweep[2]
    assert pt50["hits"] == 1
    assert pt50["false_alarms"] == 1
    assert pt50["misses"] == 2
    assert pt50["correct_negatives"] == 1
    assert pt50["pod"] == pytest.approx(1 / 3, abs=1e-4)
    assert pt50["far"] == pytest.approx(1 / 2, abs=1e-4)
    assert pt50["csi"] == pytest.approx(1 / 4, abs=1e-4)


def test_db_backtest_calibration_and_audit(db):
    db.execute(
        "insert into zone (zone_id, city_id, geom, params) "
        "values (1, 1, 'SRID=4326;MULTIPOLYGON(((77.4 12.8, 77.85 12.8, 77.85 13.2, 77.4 13.2, 77.4 12.8)))', '{}')"
    )
    db.execute(
        "insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed) "
        "values (1001, 1, 'SRID=4326;LINESTRING(77.6841 12.9298, 77.6842 12.9299)', 'primary', 1, true), "
        "       (1002, 2, 'SRID=4326;LINESTRING(77.6101 12.9165, 77.6102 12.9166)', 'primary', 1, true)"
    )
    now = datetime.now(UTC)
    for vc in ("two_wheeler", "car", "ambulance", "heavy"):
        for hz in (0, 30, 60, 120):
            db.execute(
                "insert into segment_risk (segment_id, vclass, horizon_min, p_unusable, state, confidence, evidence_age_s, model_version, updated_at, depth_p50_cm, depth_p90_cm) "
                "values (1001, %s, %s, 0.75, 'impassable', 'high', 0, 'v0.0.1', %s, 50.0, 70.0), "
                "       (1002, %s, %s, 0.10, 'watch', 'low', 0, 'v0.0.1', %s, 10.0, 20.0)",
                (vc, hz, now, vc, hz, now),
            )
    seed_benchmark_events(db)

    report = run_db_backtest(db, city_id=1, vclass="car", horizon_min=0, p_threshold=0.30)
    assert "threshold_sweep" in report
    assert "reliability_diagram" in report
    assert len(report["threshold_sweep"]) > 0
    assert len(report["reliability_diagram"]) > 0

    m = report["metrics"]
    assert "roc_auc" in m
    assert "brier_decomp" in m
    assert "optimal_threshold_csi" in m

    audit = run_full_calibration_audit(db, city_id=1, p_threshold=0.30)
    assert audit["status"] == "ok"
    assert "two_wheeler" in audit["matrix"]
    assert "car" in audit["matrix"]
    assert "ambulance" in audit["matrix"]
    assert "heavy" in audit["matrix"]
    for hz in ("0m", "30m", "60m", "120m"):
        assert hz in audit["matrix"]["car"]


