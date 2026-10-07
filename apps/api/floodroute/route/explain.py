"""Plain-language reason strings keyed by message id.

English only. Indic strings need native review and are never machine-translated: add a language
by adding a dict under MESSAGES with exactly the same ids and {placeholders} as "en" (a test
enforces that). Style: grade 6 to 8, verb first, about 12 words a sentence, "about" for times,
no jargon, and never the word "safe" (research 06 section C.12).
"""

from __future__ import annotations

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # Why the route avoids a road. minutes is passed through about().
        "avoid.named": "Avoiding {place} (water likely in about {minutes} min).",
        "avoid.unnamed": "Avoiding a road where water is likely in about {minutes} min.",
        "avoid.now_named": "Avoiding {place} (water likely now).",
        "avoid.now_unnamed": "Avoiding a road where water is likely now.",
        "delta.longer": "{minutes} min longer.",
        "delta.same": "About the same time.",
        # Honest coverage and data notes: not assessed or stale never reads as clear.
        "route.unassessed": "Some roads on this route have no flood data.",
        "route.unknown": "Take care. Flood data is out of date on part of this route.",
        "route.over_limit": "Avoid this route if you can. Water is likely on part of it.",
        "route.least_risk": "Use this route only if you must. Water is still likely on part of it.",
        # Shown when no route stays under the limit (FR-RT3, TRD 7.5).
        "guidance.stay": "Wait on higher ground or in a sturdy building if you can.",
        "guidance.no_water": "Do not drive or walk through moving water.",
        "guidance.avoid_low": "Keep away from underpasses and low parking areas.",
        "guidance.call_112": "Call 112 if you are in danger.",
        "guidance.escalate": "Tell your dispatcher now. No route avoids flooding.",
        "guidance.alt_modes": "Ask about a boat, a high-clearance vehicle or a foot relay.",
        "guidance.least_risk": (
            "Read the marked risk on the route shown. It has the lowest chance of flooding."
        ),
        # Live reroute decisions (reroute.py).
        "reroute.road_flooded": "A road ahead may be flooded. Switch to the new route?",
        "reroute.risk_rising": "Flood risk is rising on your route. Switch to a lower-risk route?",
        "reroute.faster": "A faster route is open. Switch to it?",
        "reroute.flood_ahead": "A road ahead may be flooded. Slow down and stay alert.",
        "reroute.commit_zone": (
            "Water is just ahead and there is no turn-off. Slow down and be ready to stop."
        ),
        "reroute.no_alternative": (
            "A road ahead may be flooded and no other route is open. Slow down and stay alert."
        ),
        # Freeze key set by the kill-switch path in api/routes/route.py (not localisable flood keys).
        "advisory_off": (
            "Flood advisories are suspended. Follow on-ground traffic police directions."
        ),
    },
}


def pick_lang(lang: str) -> str:
    """The language strings will really be rendered in: lang if we have it, else English."""
    return lang if lang in MESSAGES else "en"


def say(message_id: str, lang: str = "en", **params: object) -> str:
    return MESSAGES[pick_lang(lang)][message_id].format(**params)


def about(minutes: float) -> int:
    """Round to the nearest 5 min (at least 5) for "in about N min" wording."""
    return max(5, 5 * int(minutes / 5 + 0.5))
