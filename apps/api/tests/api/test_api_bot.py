"""Tests for bot API endpoints: /v1/whatsapp/webhook and /v1/sms/render."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

VERIFY_TOKEN = os.environ["WHATSAPP_VERIFY_TOKEN"]
APP_SECRET = os.environ["WHATSAPP_APP_SECRET"]


def test_inbound_worker_serializes_shared_sessions(monkeypatch):
    from floodroute.api.routes import bot

    barrier = Barrier(4)
    counter_lock = Lock()
    active = maximum = 0

    def handle(db, parsed):
        nonlocal active, maximum
        with counter_lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.01)  # overlapping DB work must preserve serial session access
        with counter_lock:
            active -= 1
        return parsed

    def invoke(sender):
        barrier.wait(timeout=5)
        return bot._handle_message(None, {"sender": sender})

    monkeypatch.setattr(bot, "handle_incoming_message", handle)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(invoke, range(4)))
    assert results == [{"sender": sender} for sender in range(4)]
    assert maximum == 1


def _signed_post(client, payload):
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(APP_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/v1/whatsapp/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig}",
        },
    )


def test_whatsapp_webhook_verification(client):
    r_ok = client.get(
        "/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "challenge_code_999",
        },
    )
    assert r_ok.status_code == 200
    assert r_ok.text == "challenge_code_999"

    r_fail = client.get(
        "/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "challenge_code_999",
        },
    )
    assert r_fail.status_code == 403


def test_whatsapp_inbound_webhook(client, app_db):
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919988776655",
                                    "id": "wamid.inbound_1",
                                    "type": "text",
                                    "text": {"body": "status"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    r = _signed_post(client, payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "processed"
    assert "outbound" in data
    assert data["outbound"]["type"] == "text"


def test_sms_templates_and_render_endpoints(client):
    # 1. List templates
    r_list = client.get("/v1/sms/templates")
    assert r_list.status_code == 200
    templates = r_list.json()
    assert len(templates) >= 6
    template_keys = {t["template_key"] for t in templates}
    assert "KN_ROAD_CLOSED" in template_keys
    assert "EN_ROAD_CLOSED" in template_keys

    # 2. Render template
    render_req = {
        "template_key": "KN_ROAD_CLOSED",
        "variables": {
            "landmark": "ಸಿಲ್ಕ್ ಬೋರ್ಡ್",
            "detour": "ಹೊಸೂರು ರಸ್ತೆ",
        },
    }
    r_render = client.post("/v1/sms/render", json=render_req)
    assert r_render.status_code == 200
    res = r_render.json()
    assert res["lang"] == "kn"
    assert res["character_count"] <= 70
    assert res["is_single_segment"] is True

    # 3. Invalid template key
    r_bad = client.post(
        "/v1/sms/render",
        json={"template_key": "NON_EXISTENT_TEMPLATE", "variables": {}},
    )
    assert r_bad.status_code == 400
