"""Tests for console UI serving and static assets."""

from __future__ import annotations

from fastapi.testclient import TestClient

from floodroute.api.main import create_app


def test_console_and_static_serving():
    app = create_app()
    client = TestClient(app)

    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "FloodRoute Control Room Console" in res_root.text

    res_console = client.get("/console")
    assert res_console.status_code == 200
    assert "FloodRoute Control Room Console" in res_console.text

    res_css = client.get("/static/tokens.css")
    assert res_css.status_code == 200
    assert "--fr-accent" in res_css.text
