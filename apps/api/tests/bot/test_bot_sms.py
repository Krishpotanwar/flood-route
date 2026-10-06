"""Tests for DLT-compliant SMS templates, character budgets, and Unicode/GSM-7 limits."""

from __future__ import annotations

import pytest

from floodroute.bot.sms import DLT_TEMPLATES, is_gsm7, render_sms


def test_zero_em_dashes_in_dlt_templates():
    for key, tmpl in DLT_TEMPLATES.items():
        assert "\u2014" not in tmpl.pattern, f"Em-dash found in template pattern {key}"
        assert "\u2013" not in tmpl.pattern, f"En-dash found in template pattern {key}"



def test_is_gsm7_classification():
    assert is_gsm7("FloodRoute Alert: Silk Board closed.") is True
    assert is_gsm7("ಗಮನಿಸಿ: ರಸ್ತೆ ಮುಚ್ಚಲಾಗಿದೆ.") is False  # Kannada is Unicode
    assert is_gsm7("चेतावनी: रास्ता बंद है।") is False  # Hindi is Unicode


def test_render_sms_kannada_under_70_chars():
    res = render_sms(
        "KN_ROAD_CLOSED",
        {"landmark": "ಸಿಲ್ಕ್ ಬೋರ್ಡ್", "detour": "ಹೊಸೂರು ರಸ್ತೆ"},
    )
    assert res["lang"] == "kn"
    assert res["encoding"] == "Unicode (UCS-2)"
    assert res["character_limit"] == 70
    assert res["character_count"] <= 70
    assert res["is_single_segment"] is True
    assert "ಸಿಲ್ಕ್ ಬೋರ್ಡ್" in res["text"]
    assert "ಹೊಸೂರು ರಸ್ತೆ" in res["text"]


def test_render_sms_hindi_under_70_chars():
    res = render_sms(
        "HI_ROAD_CLOSED",
        {"landmark": "सिल्क बोर्ड", "detour": "होसुर रोड"},
    )
    assert res["lang"] == "hi"
    assert res["encoding"] == "Unicode (UCS-2)"
    assert res["character_limit"] == 70
    assert res["character_count"] <= 70
    assert res["is_single_segment"] is True
    assert "सिल्क बोर्ड" in res["text"]


def test_render_sms_english_under_160_chars():
    res = render_sms(
        "EN_ROAD_CLOSED",
        {
            "landmark": "Silk Board Underpass",
            "detour": "Outer Ring Road via Marathahalli flyover",
        },
    )
    assert res["lang"] == "en"
    assert res["encoding"] == "GSM-7"
    assert res["character_limit"] == 160
    assert res["character_count"] <= 160
    assert res["is_single_segment"] is True


def test_render_sms_auto_truncation():
    # Very long landmark name that would overflow Kannada 70-char limit
    long_landmark = "ಬೆಂಗಳೂರು ಮಹಾನಗರ ಪಾಲಿಕೆ ಮುಖ್ಯ ರಸ್ತೆ ಸಿಲ್ಕ್ ಬೋರ್ಡ್ ಜಂಕ್ಷನ್ ಹತ್ತಿರದ ಸೇತುವೆ"
    res = render_sms(
        "KN_ROAD_CLOSED",
        {"landmark": long_landmark, "detour": "ಹೊಸೂರು ರಸ್ತೆ"},
        auto_truncate=True,
    )
    assert res["character_count"] <= 70
    assert res["text"].endswith("ಹೊಸೂರು ರಸ್ತೆ")


def test_render_sms_safety_invariant_violation():
    with pytest.raises(ValueError, match="safety invariant"):
        render_sms(
            "EN_ROAD_CLOSED",
            {"landmark": "Madiwala", "detour": "Use safe route"},
        )
