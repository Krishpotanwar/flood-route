"""Tests for performance benchmark suite and SLO verification."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.benchmark import (
    ScenarioResult,
    compute_percentiles,
    execute_full_suite,
    run_benchmark_scenario,
)


def test_compute_percentiles():
    """Verify statistical percentile calculations."""
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p = compute_percentiles(latencies)
    assert p["min"] == 10.0
    assert p["max"] == 100.0
    assert 50.0 <= p["p50"] <= 60.0
    assert 90.0 <= p["p95"] <= 100.0


def test_scenario_result_dataclass():
    """Verify ScenarioResult dataclass fields and SLO status check."""
    res = ScenarioResult(
        scenario="GET /v1/test",
        total_requests=100,
        success_count=100,
        failure_count=0,
        duration_s=1.0,
        rps=100.0,
        min_ms=5.0,
        p50_ms=8.0,
        p90_ms=12.0,
        p95_ms=14.0,
        p99_ms=18.0,
        max_ms=20.0,
        target_p95_ms=50.0,
        meets_slo=True,
    )
    assert res.meets_slo is True
    assert res.rps == 100.0


@pytest.mark.anyio
async def test_benchmark_full_suite_in_process(monkeypatch, db_url):
    """Run lightweight in-process benchmark execution verifying all endpoints respond."""
    monkeypatch.setenv("DATABASE_URL", db_url)
    token = "benchmark-test-only-token-000000000000"
    monkeypatch.setenv("FLOODROUTE_OPERATOR_TOKENS", '{"benchmark": "' + token + '"}')

    import httpx

    from floodroute.api.deps import close_pool, get_router
    from floodroute.api.main import create_app
    from floodroute.route.models import Edge, Route

    def mock_router(*args, **kwargs):
        return Route(
            (
                Edge(
                    segment_id=2201617750100158755,
                    geometry=((12.9719, 77.6412), (12.9700, 77.6400)),
                    travel_time_s=60.0,
                ),
            )
        )

    close_pool()
    try:
        app = create_app()
        app.dependency_overrides[get_router] = lambda: mock_router
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            results = await execute_full_suite(
                client=client, concurrency=2, requests_per_scenario=4, stub_router=True,
            )
        assert len(results) == 7
        for r in results:
            assert r.total_requests == 4
            assert r.failure_count == 0
        # Hardware timing belongs to the benchmark CLI, not a functional CI test.
        assert sum("[stub router]" in r.scenario for r in results) == 3
    finally:
        close_pool()


@pytest.mark.anyio
async def test_benchmark_counts_transport_failures_but_exposes_programming_errors():
    import httpx

    async def transport_failure():
        raise httpx.ReadTimeout("test transport failure")

    result = await run_benchmark_scenario("transport", transport_failure, 1, 2, 100)
    assert result.failure_count == 2 and not result.meets_slo

    async def programming_error():
        raise ValueError("test programming error")

    with pytest.raises(ValueError, match="programming error"):
        await run_benchmark_scenario("programming", programming_error, 1, 1, 100)
    with pytest.raises(ValueError, match="must be positive"):
        await run_benchmark_scenario("invalid", transport_failure, 0, 1, 100)
