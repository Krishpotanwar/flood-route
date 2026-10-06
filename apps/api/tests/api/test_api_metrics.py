"""Tests for Prometheus metrics endpoint and middleware telemetry (TRD 13)."""

from __future__ import annotations


def test_api_metrics_endpoint_and_middleware(client):
    # Make a few API calls to trigger middleware telemetry
    r_health = client.get("/v1/health")
    assert r_health.status_code == 200

    r_cities = client.get("/v1/cities")
    assert r_cities.status_code == 200

    # Query metrics endpoint
    r_met = client.get("/metrics")
    assert r_met.status_code == 200
    assert r_met.headers["content-type"].startswith("text/plain")

    text = r_met.text
    assert "floodroute_api_requests_total" in text
    assert "floodroute_api_request_duration_seconds" in text
    assert 'endpoint="/v1/health"' in text
    assert 'endpoint="/v1/cities"' in text
