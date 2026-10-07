"""Tests for WhatsApp Cloud API message handling, location parsing, and language switching."""

from __future__ import annotations

from datetime import UTC, datetime

from floodroute.bot.whatsapp import (
    _RATE,
    RATE_LIMIT_N,
    RATE_LIMIT_WINDOW_S,
    SESSION_CAP,
    handle_incoming_message,
    parse_meta_payload,
    sender_allowed,
    verify_meta_webhook,
)

ZONE_GEOM = "SRID=4326;MULTIPOLYGON(((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9)))"
SEG_LINE_1 = "SRID=4326;LINESTRING(77.6101 12.9165, 77.6102 12.9166)"


def test_verify_meta_webhook():
    assert verify_meta_webhook("subscribe", "secret123", "challenge_abc", "secret123") == "challenge_abc"
    assert verify_meta_webhook("subscribe", "wrong_token", "challenge_abc", "secret123") is None
    assert verify_meta_webhook("invalid_mode", "secret123", "challenge_abc", "secret123") is None


def test_parse_meta_payload_text_and_location():
    # 1. Text payload
    text_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.123",
                                    "type": "text",
                                    "text": {"body": "help"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    p_text = parse_meta_payload(text_payload)
    assert p_text is not None
    assert p_text["sender"] == "919876543210"
    assert p_text["type"] == "text"
    assert p_text["text"] == "help"

    # 2. Location payload
    loc_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.124",
                                    "type": "location",
                                    "location": {
                                        "latitude": 12.9165,
                                        "longitude": 77.6101,
                                        "name": "Silk Board",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    p_loc = parse_meta_payload(loc_payload)
    assert p_loc is not None
    assert p_loc["type"] == "location"
    assert p_loc["location"]["latitude"] == 12.9165
    assert p_loc["location"]["longitude"] == 77.6101


def test_handle_welcome_and_buttons(app_db):
    parsed = {
        "sender": "919876543211",
        "type": "text",
        "text": "namaskara",
        "location": None,
        "button_id": None,
    }
    resp = handle_incoming_message(app_db, parsed)
    assert resp["type"] == "interactive"
    body_text = resp["interactive"]["body"]["text"]
    assert "ಫ್ಲಡ್‌ರೂಟ್" in body_text or "FloodRoute" in body_text
    assert "\u2014" not in body_text



def test_handle_location_flood_warning(app_db):
    now = datetime.now(UTC)
    app_db.execute(
        "insert into zone (zone_id, city_id, geom, params) values (1, 1, %s, '{}')",
        (ZONE_GEOM,),
    )
    app_db.execute(
        """
        insert into segment (segment_id, osm_way_id, geom, road_class, city_id, assessed)
        values (4001, 14001, %s, 'primary', 1, true)
        """,
        (SEG_LINE_1,),
    )
    app_db.execute(
        """
        insert into segment_risk (
            segment_id, vclass, horizon_min, p_unusable,
            depth_p50_cm, depth_p90_cm, state, confidence,
            evidence_age_s, model_version, updated_at
        )
        values
            (4001, 'car', 0, 0.90, 45.0, 60.0, 'impassable', 'high', 30, 'v0.0.1', %s)
        """,
        (now,),
    )

    parsed = {
        "sender": "919876543212",
        "type": "location",
        "text": None,
        "location": {"latitude": 12.9165, "longitude": 77.6101},
        "button_id": None,
    }
    resp = handle_incoming_message(app_db, parsed)
    assert resp["type"] == "text"
    text_out = resp["text"]["body"]
    assert "4001" in text_out
    assert "IMPASSABLE" in text_out
    assert "\u2014" not in text_out



def test_handle_language_and_vehicle_switching(app_db):
    # Switch language to English
    p_lang = {
        "sender": "919876543213",
        "type": "interactive",
        "text": None,
        "location": None,
        "button_id": "LANG_EN",
    }
    resp_lang = handle_incoming_message(app_db, p_lang)
    assert "English" in resp_lang["text"]["body"]

    # Switch vehicle to two-wheeler
    p_veh = {
        "sender": "919876543213",
        "type": "interactive",
        "text": None,
        "location": None,
        "button_id": "VEHICLE_TWO_WHEELER",
    }
    resp_veh = handle_incoming_message(app_db, p_veh)
    assert "two_wheeler" in resp_veh["text"]["body"].lower()


def test_sender_allowed_prunes_expired_windows_past_cap():
    _RATE.clear()
    try:
        now = datetime.now(UTC).timestamp()
        stale_start = now - RATE_LIMIT_WINDOW_S - 1.0
        for i in range(SESSION_CAP + 1):
            _RATE[f"stale-{i}"] = (stale_start, RATE_LIMIT_N)
        _RATE["live-sender"] = (now, 1)
        assert sender_allowed("fresh-sender", now_ts=now) is True
        assert "live-sender" in _RATE
        assert "fresh-sender" in _RATE
        assert not any(k.startswith("stale-") for k in _RATE)
    finally:
        _RATE.clear()


def test_sender_allowed_keeps_stale_windows_below_cap():
    _RATE.clear()
    try:
        now = datetime.now(UTC).timestamp()
        _RATE["quiet-sender"] = (now - RATE_LIMIT_WINDOW_S - 1.0, RATE_LIMIT_N)
        assert sender_allowed("other-sender", now_ts=now) is True
        # Opportunistic only: below the cap nothing is pruned.
        assert "quiet-sender" in _RATE
    finally:
        _RATE.clear()
