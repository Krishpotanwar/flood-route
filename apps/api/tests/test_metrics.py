"""Tests for Prometheus metrics collector and middleware telemetry (TRD 13)."""

from __future__ import annotations

from floodroute.metrics.collector import Counter, Gauge, Histogram


def test_counter_monotonic_and_rendering():
    c = Counter("test_counter", "Test counter help", ("status",))
    assert c.get({"status": "ok"}) == 0.0

    c.inc(labels={"status": "ok"})
    c.inc(amount=2.5, labels={"status": "ok"})
    assert c.get({"status": "ok"}) == 3.5

    lines = c.render()
    assert "# HELP test_counter Test counter help" in lines
    assert "# TYPE test_counter counter" in lines
    assert any('test_counter{status="ok"} 3.5' in line for line in lines)


def test_gauge_operations():
    g = Gauge("test_gauge", "Test gauge help", ("city",))
    g.set(42.0, labels={"city": "mumbai"})
    assert g.get({"city": "mumbai"}) == 42.0

    g.inc(labels={"city": "mumbai"})
    assert g.get({"city": "mumbai"}) == 43.0

    g.dec(amount=10.0, labels={"city": "mumbai"})
    assert g.get({"city": "mumbai"}) == 33.0

    lines = g.render()
    assert any('test_gauge{city="mumbai"} 33.0' in line for line in lines)


def test_histogram_observations_and_buckets():
    h = Histogram("test_lat", "Latency in seconds", buckets=(0.01, 0.05, 0.1))
    h.observe(0.005)
    h.observe(0.03)
    h.observe(0.2)

    lines = "\n".join(h.render())
    assert "test_lat_bucket{le=\"0.01\"} 1" in lines
    assert "test_lat_bucket{le=\"0.05\"} 2" in lines
    assert "test_lat_bucket{le=\"0.1\"} 2" in lines
    assert "test_lat_bucket{le=\"+Inf\"} 3" in lines
    assert "test_lat_count 3" in lines


    assert "test_lat_count 3" in lines

