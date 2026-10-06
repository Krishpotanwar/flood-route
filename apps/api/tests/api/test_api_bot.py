"""Tests for bot API endpoints: /v1/whatsapp/webhook and /v1/sms/render."""

from __future__ import annotations


def test_whatsapp_webhook_verification(client):
    r_ok = client.get(
        "/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "floodroute_wa_token_2026",
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
    r = client.post("/v1/whatsapp/webhook", json=payload)
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
