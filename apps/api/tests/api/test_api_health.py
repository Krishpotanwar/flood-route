"""Tests for GET /v1/health."""

from __future__ import annotations

from datetime import UTC, datetime


def test_health_empty_sources(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["model_version"] != ""
    assert isinstance(data["sources"], dict)


def test_health_with_sources(client, app_db):
    now = datetime.now(UTC)
    app_db.execute(
        """
        insert into source_health (source, last_ok, last_error, lag_s)
        values ('sachet', %s, null, 15), ('metno', %s, null, 45)
        """,
        (now, now),
    )
    r = client.get("/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "sachet" in data["sources"]
    assert data["sources"]["sachet"]["lag_s"] == 15
    assert "metno" in data["sources"]
    assert data["sources"]["metno"]["lag_s"] == 45
