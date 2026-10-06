"""Tests for Citizen PWA serving and static bundle integration."""

from __future__ import annotations

from fastapi.testclient import TestClient

from floodroute.api.main import create_app


def test_citizen_app_serving():
    """Verify that Citizen PWA index HTML and assets are mounted and served correctly."""
    app = create_app()
    client = TestClient(app)

    redirect = client.get("/app?live=1", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"].endswith("/app/?live=1")

    res_app = client.get("/app")
    assert res_app.status_code == 200
    assert "<title>FloodRoute | Flood-aware route planning</title>" in res_app.text
    assert '<div id="root"></div>' in res_app.text
    assert "assets/index-" in res_app.text

    res_app_slash = client.get("/app/")
    assert res_app_slash.status_code == 200
    assert "<title>FloodRoute | Flood-aware route planning</title>" in res_app_slash.text


def test_citizen_app_assets_served():
    """Verify that citizen asset bundles are reachable via HTTP."""
    app = create_app()
    client = TestClient(app)

    res_app = client.get("/app")
    assert res_app.status_code == 200

    import re

    css_match = re.search(r'href="(\./assets/[^"]+\.css)"', res_app.text)
    if css_match:
        css_path = css_match.group(1).replace("./", "/app/")
        res_css = client.get(css_path)
        assert res_css.status_code == 200
        assert len(res_css.content) > 0

    js_match = re.search(r'src="(\./assets/[^"]+\.js)"', res_app.text)
    if js_match:
        js_path = js_match.group(1).replace("./", "/app/")
        res_js = client.get(js_path)
        assert res_js.status_code == 200
        assert len(res_js.content) > 0


def test_control_room_console_unaffected():
    """Ensure control room situation board is still served at / and /console."""
    app = create_app()
    client = TestClient(app)

    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "FloodRoute Control Room Console" in res_root.text

    res_console = client.get("/console")
    assert res_console.status_code == 200
    assert "FloodRoute Control Room Console" in res_console.text
