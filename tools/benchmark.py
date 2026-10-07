"""End-to-End Performance and Load Benchmark Harness for FloodRoute API.

Measures latency profiles (p50, p90, p95, p99) and throughput (RPS) against
live PostGIS database and FastAPI endpoints in accordance with TRD SLO specifications:
- Risk bbox query p95 < 100 ms (TRD Section 3 / 13)
- Route calculation p95 < 500 ms (TRD Section 13)
- Ambulance route calculation p95 < 300 ms (TRD Section 13)
- Health check p95 < 50 ms

Honesty note: in-process mode overrides get_router with benchmark_router, a
fixed two-edge stub. Route and reroute scenarios therefore measure API
and database processing, not the road router; they are labelled [stub router]
in that mode. Remote mode uses the server's configured router.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import sys
import time
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

# Ensure project imports resolve
sys.path.insert(0, os.path.abspath("apps/api"))

from floodroute.api.deps import close_pool, get_router
from floodroute.api.main import create_app
from floodroute.db.conn import database_url
from floodroute.route.models import Edge, LatLon, Polygon, Route

logger = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    scenario: str
    total_requests: int
    success_count: int
    failure_count: int
    duration_s: float
    rps: float
    min_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    target_p95_ms: float
    meets_slo: bool


def compute_percentiles(latencies_ms: list[float]) -> dict[str, float]:
    if not latencies_ms:
        return {"min": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    sorted_lats = sorted(latencies_ms)
    n = len(sorted_lats)

    def pct(p: float) -> float:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_lats[int(k)]
        d0 = sorted_lats[int(f)] * (c - k)
        d1 = sorted_lats[int(c)] * (k - f)
        return d0 + d1

    return {
        "min": sorted_lats[0],
        "p50": pct(0.50),
        "p90": pct(0.90),
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": sorted_lats[-1],
    }


async def run_benchmark_scenario(
    name: str,
    fn: Callable[[], Coroutine[Any, Any, tuple[bool, float]]],
    concurrency: int,
    total_requests: int,
    target_p95_ms: float,
) -> ScenarioResult:
    if concurrency < 1 or total_requests < 1:
        raise ValueError("concurrency and total_requests must be positive")
    latencies: list[float] = []
    success = 0
    failure = 0

    sem = asyncio.Semaphore(concurrency)

    async def worker() -> None:
        nonlocal success, failure
        async with sem:
            t0 = time.perf_counter()
            try:
                ok, elapsed_ms = await fn()
            except httpx.RequestError as exc:
                logger.warning("%s request failed: %s", name, type(exc).__name__)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                ok = False
            latencies.append(elapsed_ms)
            if ok:
                success += 1
            else:
                failure += 1

    start_time = time.perf_counter()
    tasks = [asyncio.create_task(worker()) for _ in range(total_requests)]
    await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start_time

    rps = total_requests / total_time if total_time > 0 else 0.0
    stats = compute_percentiles(latencies)
    meets_slo = stats["p95"] <= target_p95_ms and failure == 0

    return ScenarioResult(
        scenario=name,
        total_requests=total_requests,
        success_count=success,
        failure_count=failure,
        duration_s=round(total_time, 3),
        rps=round(rps, 1),
        min_ms=round(stats["min"], 2),
        p50_ms=round(stats["p50"], 2),
        p90_ms=round(stats["p90"], 2),
        p95_ms=round(stats["p95"], 2),
        p99_ms=round(stats["p99"], 2),
        max_ms=round(stats["max"], 2),
        target_p95_ms=target_p95_ms,
        meets_slo=meets_slo,
    )


async def execute_full_suite(
    client: httpx.AsyncClient,
    concurrency: int = 10,
    requests_per_scenario: int = 100,
    stub_router: bool = False,
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    router_label = " [stub router]" if stub_router else ""

    # Warm up pool connections
    print("[*] Warming up connection pool...")
    for _ in range(10):
        await client.get("/v1/health")

    # 1. Health Endpoint
    async def bench_health() -> tuple[bool, float]:
        t0 = time.perf_counter()
        resp = await client.get("/v1/health")
        dt = (time.perf_counter() - t0) * 1000.0
        return resp.status_code == 200, dt

    print(f"[*] Running Scenario: Health Endpoint ({requests_per_scenario} reqs, c={concurrency})...")
    res_health = await run_benchmark_scenario(
        name="GET /v1/health",
        fn=bench_health,
        concurrency=concurrency,
        total_requests=requests_per_scenario,
        target_p95_ms=50.0,
    )
    results.append(res_health)

    # 2. Risk BBox Query (Central Bengaluru)
    async def bench_risk_central() -> tuple[bool, float]:
        t0 = time.perf_counter()
        resp = await client.get(
            "/v1/risk",
            params={
                "bbox": "77.55,12.90,77.65,13.00",
                "vclass": "car",
                "h": 30,
            },
        )
        dt = (time.perf_counter() - t0) * 1000.0
        return resp.status_code == 200, dt

    print(f"[*] Running Scenario: Risk BBox Central ({requests_per_scenario} reqs, c={concurrency})...")
    res_risk_central = await run_benchmark_scenario(
        name="GET /v1/risk (Central BBox)",
        fn=bench_risk_central,
        concurrency=concurrency,
        total_requests=requests_per_scenario,
        target_p95_ms=100.0,
    )
    results.append(res_risk_central)

    # 3. Risk BBox Query (High-Density Hotspot: Silk Board to Bellandur)
    async def bench_risk_hotspot() -> tuple[bool, float]:
        t0 = time.perf_counter()
        resp = await client.get(
            "/v1/risk",
            params={
                "bbox": "77.62,12.91,77.69,12.96",
                "vclass": "two_wheeler",
                "h": 0,
            },
        )
        dt = (time.perf_counter() - t0) * 1000.0
        return resp.status_code == 200, dt

    print(f"[*] Running Scenario: Risk BBox Hotspots ({requests_per_scenario} reqs, c={concurrency})...")
    res_risk_hotspot = await run_benchmark_scenario(
        name="GET /v1/risk (Silk Board Corridor)",
        fn=bench_risk_hotspot,
        concurrency=concurrency,
        total_requests=requests_per_scenario,
        target_p95_ms=100.0,
    )
    results.append(res_risk_hotspot)

    # 4. Route Planning (Indiranagar to Silk Board)
    route_payload = {
        "origin": {"lat": 12.9719, "lon": 77.6412},
        "destination": {"lat": 12.9172, "lon": 77.6228},
        "vclass": "car",
        "profile": "citizen",
        "lang": "en",
    }

    async def bench_route() -> tuple[bool, float]:
        t0 = time.perf_counter()
        payload = {**route_payload, "depart_at": datetime.now(UTC).isoformat()}
        resp = await client.post("/v1/route", json=payload)
        dt = (time.perf_counter() - t0) * 1000.0
        return resp.status_code == 200, dt

    print(f"[*] Running Scenario: Route Planning ({requests_per_scenario} reqs, c={concurrency})...")
    res_route = await run_benchmark_scenario(
        name=f"POST /v1/route (Standard Car){router_label}",
        fn=bench_route,
        concurrency=concurrency,
        total_requests=requests_per_scenario,
        target_p95_ms=500.0,
    )
    results.append(res_route)

    # 5. Ambulance Route Planning (Target p95 < 300 ms)
    amb_payload = {
        "origin": {"lat": 12.9719, "lon": 77.6412},
        "destination": {"lat": 12.9172, "lon": 77.6228},
        "vclass": "ambulance",
        "profile": "ambulance",
        "lang": "en",
    }

    async def bench_route_amb() -> tuple[bool, float]:
        t0 = time.perf_counter()
        payload = {**amb_payload, "depart_at": datetime.now(UTC).isoformat()}
        resp = await client.post("/v1/route", json=payload)
        dt = (time.perf_counter() - t0) * 1000.0
        return resp.status_code == 200, dt

    print(f"[*] Running Scenario: Ambulance Route ({requests_per_scenario} reqs, c={concurrency})...")
    res_route_amb = await run_benchmark_scenario(
        name=f"POST /v1/route (Ambulance){router_label}",
        fn=bench_route_amb,
        concurrency=concurrency,
        total_requests=requests_per_scenario,
        target_p95_ms=300.0,
    )
    results.append(res_route_amb)

    # 6. Live Rerouting Navigation Tick (POST /v1/route/reroute)
    reroute_payload = {
        "origin": {"lat": 12.9719, "lon": 77.6412},
        "destination": {"lat": 12.9172, "lon": 77.6228},
        "vclass": "two_wheeler",
        "profile": "citizen",
        "trip_state": {"baseline_band": 0, "closed_at": {}},
        "current_edges": [
            {
                "segment_id": 2201617750100158755,
                "travel_time_s": 120,
                "length_m": 400,
                "turn_off_after": True,
                "geometry": [
                    {"lat": 12.9719, "lon": 77.6412},
                    {"lat": 12.9700, "lon": 77.6400},
                ],
            }
        ],
        "lang": "en",
    }

    async def bench_reroute() -> tuple[bool, float]:
        t0 = time.perf_counter()
        payload = {**reroute_payload, "depart_at": datetime.now(UTC).isoformat()}
        resp = await client.post("/v1/route/reroute", json=payload)
        dt = (time.perf_counter() - t0) * 1000.0
        return resp.status_code == 200, dt

    print(f"[*] Running Scenario: Reroute Navigation Tick ({requests_per_scenario} reqs, c={concurrency})...")
    res_reroute = await run_benchmark_scenario(
        name=f"POST /v1/route/reroute (Tick){router_label}",
        fn=bench_reroute,
        concurrency=concurrency,
        total_requests=requests_per_scenario,
        target_p95_ms=200.0,
    )
    results.append(res_reroute)

    # 7. GeoJSON Closure Feed (GET /v1/feed/closures.geojson)
    async def bench_feed() -> tuple[bool, float]:
        t0 = time.perf_counter()
        resp = await client.get("/v1/feed/closures.geojson")
        dt = (time.perf_counter() - t0) * 1000.0
        return resp.status_code == 200, dt

    print(f"[*] Running Scenario: Closures GeoJSON Feed ({requests_per_scenario} reqs, c={concurrency})...")
    res_feed = await run_benchmark_scenario(
        name="GET /v1/feed/closures.geojson",
        fn=bench_feed,
        concurrency=concurrency,
        total_requests=requests_per_scenario,
        target_p95_ms=150.0,
    )
    results.append(res_feed)

    return results


def print_results_table(results: list[ScenarioResult]) -> None:
    sep = "+" + "+".join(["-" * 32, "-" * 8, "-" * 9, "-" * 9, "-" * 9, "-" * 9, "-" * 11, "-" * 10]) + "+"
    header = (
        f"| {'Scenario':<30} "
        f"| {'RPS':<6} "
        f"| {'p50(ms)':<7} "
        f"| {'p90(ms)':<7} "
        f"| {'p95(ms)':<7} "
        f"| {'p99(ms)':<7} "
        f"| {'Target p95':<9} "
        f"| {'SLO Status':<8} |"
    )

    print("\n" + sep)
    print(header)
    print(sep)

    all_passed = True
    for r in results:
        status = "PASS" if r.meets_slo else "FAIL"
        if not r.meets_slo:
            all_passed = False
        print(
            f"| {r.scenario:<30} "
            f"| {r.rps:<6.1f} "
            f"| {r.p50_ms:<7.2f} "
            f"| {r.p90_ms:<7.2f} "
            f"| {r.p95_ms:<7.2f} "
            f"| {r.p99_ms:<7.2f} "
            f"| {f'<{r.target_p95_ms}ms':<9} "
            f"| {status:<8} |"
        )

    print(sep)
    if all_passed:
        print("\n[+] SUCCESS: All scenarios met TRD latency SLO targets!")
    else:
        print("\n[-] WARNING: One or more scenarios exceeded latency SLO thresholds.")


def benchmark_router(
    origin: LatLon,
    dest: LatLon,
    vclass: str,
    depart: datetime,
    exclude_polygons: Sequence[Polygon] = (),
) -> Route | None:
    return Route((
        Edge(segment_id=2201617750100158755, geometry=((12.9719, 77.6412), (12.9700, 77.6400)), travel_time_s=60.0),
        Edge(segment_id=9001, geometry=((12.9700, 77.6400), (12.9172, 77.6228)), travel_time_s=180.0),
    ))


async def async_main(args: argparse.Namespace) -> list[ScenarioResult]:
    if args.base_url:
        print(f"[*] Benchmarking remote server at: {args.base_url}")
        client = httpx.AsyncClient(base_url=args.base_url, timeout=30.0)
    else:
        database_url()  # Require an actual configured database, not an invented default.
        close_pool()
        print("[*] Benchmarking in-process FastAPI (stub road router, real database processing)...")
        app = create_app()
        app.dependency_overrides[get_router] = lambda: benchmark_router
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=30.0)

    operator_token = os.environ.get("FLOODROUTE_BENCHMARK_OPERATOR_TOKEN", "")
    if operator_token:
        client.headers["Authorization"] = f"Bearer {operator_token}"

    try:
        results = await execute_full_suite(
            client=client,
            concurrency=args.concurrency,
            requests_per_scenario=args.requests,
            stub_router=not args.base_url,
        )
        return results
    finally:
        await client.aclose()
        if not args.base_url:
            close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description="FloodRoute API Performance Benchmark")
    parser.add_argument("--concurrency", "-c", type=int, default=10, help="Number of concurrent client workers")
    parser.add_argument("--requests", "-n", type=int, default=50, help="Number of requests per scenario")
    parser.add_argument("--base-url", type=str, default="", help="Base URL of live server (empty for in-process)")
    parser.add_argument("--out", type=str, default="tools/benchmark_results.json", help="Path to save JSON results")
    args = parser.parse_args()

    results = asyncio.run(async_main(args))
    print_results_table(results)

    # Export JSON
    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "concurrency": args.concurrency,
        "requests_per_scenario": args.requests,
        "results": [asdict(r) for r in results],
    }
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2)
    print(f"[*] Benchmark results written to {out_path}")

    failed_count = sum(1 for r in results if not r.meets_slo)
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
