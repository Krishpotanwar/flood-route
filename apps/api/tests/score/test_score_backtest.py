"""Tests for floodroute.score.backtest (contingency metrics, Brier score, DB backtest)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floodroute.score.backtest import (
    ContingencyTable,
    compute_brier_score,
    compute_contingency,
    compute_mae_depth,
    run_db_backtest,
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
