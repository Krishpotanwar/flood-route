"""WhatsApp Business Cloud API bot handler and interactive conversation engine.

Implements PRD FR-P1 and TRD 9:
- Multi-lingual support: Kannada (kn), Hindi (hi), and English (en)
- Meta Cloud API webhook verification and inbound message parser
- Location sharing intent: checks nearby road segment passability
- Vehicle profile switching: two_wheeler, car, ambulance
- City-wide flood status queries
- Safety invariant: never uses 'safe' label
- Design rule: zero em-dashes
"""

from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psycopg

from floodroute.score.db import SUPPORTED_VCLASSES

SUPPORTED_LANGUAGES = {"kn": "ಕನ್ನಡ", "hi": "हिन्दी", "en": "English"}
DEFAULT_VEHICLE_CLASS = "car"

# Inbound abuse controls (single-process; a multi-replica deployment needs a
# shared store to enforce these globally).
SESSION_TTL_S = 24 * 3600.0
SESSION_CAP = 10000
RATE_LIMIT_N = 30
RATE_LIMIT_WINDOW_S = 60.0


@dataclass
class UserSession:
    """Session state for WhatsApp citizen user."""

    phone_number: str
    lang: str = "kn"
    vclass: str = "car"
    last_lat: float | None = None
    last_lon: float | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# In-memory session store (can be backed by Postgres or Redis as needed).
# Bounded by SESSION_CAP with TTL eviction so spoofed senders cannot grow it
# without limit (see get_user_session).
_SESSIONS: dict[str, UserSession] = {}

# Sender -> (window_start_epoch_s, count). Best effort per process.
_RATE: dict[str, tuple[float, int]] = {}


def _prune_sessions(now_ts: float) -> None:
    """Drop sessions past the TTL."""
    expired = [k for k, s in _SESSIONS.items() if now_ts - s.updated_at.timestamp() > SESSION_TTL_S]
    for k in expired:
        del _SESSIONS[k]


def get_user_session(phone_number: str) -> UserSession:
    """Retrieve or create user session (bounded: oldest-first past the cap)."""
    now_ts = datetime.now(UTC).timestamp()
    _prune_sessions(now_ts)
    if phone_number not in _SESSIONS:
        if len(_SESSIONS) >= SESSION_CAP:
            oldest = min(_SESSIONS, key=lambda k: _SESSIONS[k].updated_at)
            del _SESSIONS[oldest]
        _SESSIONS[phone_number] = UserSession(phone_number=phone_number)
    return _SESSIONS[phone_number]


def _prune_rate_windows(now: float) -> None:
    """Drop sender windows that already expired."""
    expired = [k for k, (start, _) in _RATE.items() if now - start >= RATE_LIMIT_WINDOW_S]
    for k in expired:
        del _RATE[k]


def sender_allowed(sender: str, now_ts: float | None = None) -> bool:
    """Fixed-window per-sender rate limit for inbound webhook traffic."""
    now = now_ts if now_ts is not None else datetime.now(UTC).timestamp()
    if len(_RATE) > SESSION_CAP:
        _prune_rate_windows(now)
    start, count = _RATE.get(sender, (now, 0))
    if now - start >= RATE_LIMIT_WINDOW_S:
        _RATE[sender] = (now, 1)
        return True
    if count >= RATE_LIMIT_N:
        return False
    _RATE[sender] = (start, count + 1)
    return True


def is_valid_inbound(parsed: dict[str, Any] | None) -> bool:
    """Strict shape check: only well-formed sender message events are handled."""
    if not parsed:
        return False
    sender = parsed.get("sender")
    if not isinstance(sender, str) or not sender.strip():
        return False
    if not parsed.get("message_id"):
        return False
    return parsed.get("type") in ("text", "location", "interactive")


def _parse_coord(value: Any, lo: float, hi: float) -> float | None:
    """Numeric, finite, in-range coordinate, else None (fail closed to welcome)."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or not lo <= num <= hi:
        return None
    return num


def verify_meta_webhook(
    mode: str | None,
    token: str | None,
    challenge: str | None,
    expected_token: str,
) -> str | None:
    """Verify Meta Webhook setup handshake (hub.mode, hub.verify_token)."""
    if mode != "subscribe" or not challenge or not token or not expected_token:
        return None
    try:
        ok = hmac.compare_digest(token.encode("utf-8"), expected_token.encode("utf-8"))
    except (TypeError, ValueError):
        return None
    return challenge if ok else None


def verify_whatsapp_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    """Validate a WhatsApp Cloud API webhook POST against the App Secret.

    Meta signs every webhook POST with HMAC-SHA256 over the raw body keyed
    by the App Secret and sends the hex digest in X-Hub-Signature-256; see
    https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint/
    Validation recomputes the digest over the exact request bytes and
    compares in constant time. Returns False on a missing or malformed
    header or an empty secret.
    """
    if not app_secret or not signature_header or raw_body is None:
        return False
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    candidate = signature_header[len(prefix):].strip()
    if not candidate:
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, candidate)
    except (TypeError, ValueError):
        return False


def parse_meta_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract message details from Meta Cloud API webhook payload."""
    try:
        entries = payload.get("entry", [])
        if not entries:
            return None
        changes = entries[0].get("changes", [])
        if not changes:
            return None
        value = changes[0].get("value", [])
        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        sender = msg.get("from")
        msg_id = msg.get("id")
        msg_type = msg.get("type")

        result: dict[str, Any] = {
            "sender": sender,
            "message_id": msg_id,
            "type": msg_type,
            "text": None,
            "location": None,
            "button_id": None,
        }

        if msg_type == "text":
            result["text"] = msg.get("text", {}).get("body", "").strip()
        elif msg_type == "location":
            loc = msg.get("location", {})
            result["location"] = {
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "name": loc.get("name"),
                "address": loc.get("address"),
            }
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            itype = interactive.get("type")
            if itype == "button_reply":
                result["button_id"] = interactive.get("button_reply", {}).get("id")
            elif itype == "list_reply":
                result["button_id"] = interactive.get("list_reply", {}).get("id")

        return result
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None



def handle_incoming_message(
    db: psycopg.Connection,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """Process parsed WhatsApp user message and return outbound response payload."""
    sender = parsed["sender"]
    session = get_user_session(sender)

    # 1. Location intent
    if parsed["type"] == "location" and parsed["location"]:
        lat = _parse_coord(parsed["location"].get("latitude"), -90.0, 90.0)
        lon = _parse_coord(parsed["location"].get("longitude"), -180.0, 180.0)
        if lat is None or lon is None:
            return _handle_welcome(session)
        session.last_lat = lat
        session.last_lon = lon
        session.updated_at = datetime.now(UTC)
        return _handle_location_check(db, session, lat, lon)

    # 2. Interactive button responses
    btn = parsed.get("button_id")
    if btn:
        if btn.startswith("LANG_"):
            new_lang = btn.replace("LANG_", "").lower()
            if new_lang in SUPPORTED_LANGUAGES:
                session.lang = new_lang
                return _response_text(
                    sender,
                    _text(
                        session.lang,
                        kn="ಭಾಷೆಯನ್ನು ಕನ್ನಡಕ್ಕೆ ಬದಲಾಯಿಸಲಾಗಿದೆ. ನಿಮ್ಮ ಸ್ಥಳವನ್ನು ಹಂಚಿಕೊಳ್ಳಿ ಅಥವಾ 'status' ಎಂದು ಕಳುಹಿಸಿ.",
                        hi="भाषा बदलकर हिन्दी कर दी गई है। अपनी लोकेशन भेजें या 'status' लिखें।",
                        en="Language set to English. Share your location or type 'status' to check nearby roads.",
                    ),
                )
        elif btn.startswith("VEHICLE_"):
            new_vclass = btn.replace("VEHICLE_", "").lower()
            if new_vclass not in SUPPORTED_VCLASSES:
                return _response_text(
                    sender,
                    _text(
                        session.lang,
                        kn="ವಾಹನ ವರ್ಗ ಗುರುತಿಸಲಾಗಲಿಲ್ಲ. ದ್ವಿಚಕ್ರ, ಕಾರು, ಆಂಬ್ಯುಲೆನ್ಸ್ ಅಥವಾ ಹೆವಿ ಆಯ್ಕೆಮಾಡಿ.",
                        hi="वाहन प्रकार पहचाना नहीं गया। दोपहिया, कार, एम्बुलेंस या हैवी चुनें।",
                        en=f"Vehicle class '{new_vclass}' is not recognized. Choose two_wheeler, car, ambulance or heavy.",
                    ),
                )
            session.vclass = new_vclass
            return _response_text(
                sender,
                _text(
                    session.lang,
                    kn=f"ವಾಹನ ವರ್ಗವನ್ನು '{new_vclass}' ಗೆ ನವೀಕರಿಸಲಾಗಿದೆ.",
                    hi=f"वाहन प्रकार '{new_vclass}' पर सेट किया गया।",
                    en=f"Vehicle class updated to '{new_vclass}'. Passability thresholds adjusted.",
                ),
            )
        elif btn == "CHECK_STATUS":
            return _handle_city_status(db, session)

    # 3. Text command matching
    text = (parsed.get("text") or "").strip().lower()

    if any(k in text for k in ("hi", "hello", "namaskara", "namaste", "help", "start", "menu")):
        return _handle_welcome(session)

    if text in ("status", "rain", "flood", "పరిస్థಿತಿ", "ಸ್ಥಿತಿ", "स्थिति"):
        return _handle_city_status(db, session)

    if any(k in text for k in ("kannada", "ಕನ್ನಡ", "kn")):
        session.lang = "kn"
        return _response_text(sender, "ಭಾಷೆಯನ್ನು ಕನ್ನಡಕ್ಕೆ ಬದಲಾಯಿಸಲಾಗಿದೆ.")

    if any(k in text for k in ("hindi", "हिन्दी", "hi")):
        session.lang = "hi"
        return _response_text(sender, "भाषा बदलकर हिन्दी कर दी गई है।")

    if any(k in text for k in ("english", "en")):
        session.lang = "en"
        return _response_text(sender, "Language set to English.")

    if "bike" in text or "two_wheeler" in text:
        session.vclass = "two_wheeler"
        return _response_text(
            sender,
            _text(
                session.lang,
                kn="ವಾಹನ: ದ್ವಿಚಕ್ರ ವಾಹನ (ಮಿತಿ: 10 ಸೆಂ.ಮೀ)",
                hi="वाहन: दोपहिया (सीमा: 10 सेमी)",
                en="Vehicle set to Two-Wheeler (Clearance limit: 10cm).",
            ),
        )

    if "car" in text:
        session.vclass = "car"
        return _response_text(
            sender,
            _text(
                session.lang,
                kn="ವಾಹನ: ಕಾರು (ಮಿತಿ: 20 ಸೆಂ.ಮೀ)",
                hi="वाहन: कार (सीमा: 20 सेमी)",
                en="Vehicle set to Car (Clearance limit: 20cm).",
            ),
        )

    # Fallback response
    return _handle_welcome(session)


def _handle_welcome(session: UserSession) -> dict[str, Any]:
    """Build welcome message with interactive quick action buttons."""
    body = _text(
        session.lang,
        kn=(
            "ನಮಸ್ಕಾರ! ಫ್ಲಡ್‌ರೂಟ್ ಬೆಂಗಳೂರು ರಸ್ತೆ ಜಲಾವೃತ ಮಾಹಿತಿ ವ್ಯವಸ್ಥೆ.\n\n"
            "ನಿಮ್ಮ ಹತ್ತಿರದ ರಸ್ತೆ ಮತ್ತು ಅಂಡರ್‌ಪಾಸ್ ಸ್ಥಿತಿ ತಿಳಿಯಲು ವಾಟ್ಸಾಪ್ ಸ್ಥಳ (Location) ಹಂಚಿಕೊಳ್ಳಿ."
        ),
        hi=(
            "नमस्ते! फ्लडरूट बेंगलुरु जलभराव चेतावनी प्रणाली।\n\n"
            "अपने आसपास की सड़क और अंडरपास की स्थिति जानने के लिए लोकेशन शेयर करें।"
        ),
        en=(
            "Hello! FloodRoute monitors waterlogged roads and underpasses in Bengaluru.\n\n"
            "Share your live location to check nearby road conditions, or tap a button below."
        ),
    )

    buttons = [
        {"id": "CHECK_STATUS", "title": "Flood Status"},
        {"id": "LANG_KN", "title": "ಕನ್ನಡ"},
        {"id": "LANG_EN", "title": "English"},
    ]
    return _response_buttons(session.phone_number, body, buttons)


def _handle_location_check(
    db: psycopg.Connection, session: UserSession, lat: float, lon: float
) -> dict[str, Any]:
    """Find nearby road segments within 1.5km and report flood status."""
    point_wkt = f"SRID=4326;POINT({lon} {lat})"
    sql = """
    select s.segment_id, s.road_class, sr.state, sr.p_unusable,
           sr.depth_p50_cm, ST_Distance(s.geom::geography, ST_GeomFromEWKT(%s)::geography) as dist_m
    from segment s
    join segment_risk sr on s.segment_id = sr.segment_id
    where sr.vclass = %s
      and sr.horizon_min = 0
      and ST_DWithin(s.geom::geography, ST_GeomFromEWKT(%s)::geography, 1500)
    order by sr.p_unusable desc, dist_m asc
    limit 5
    """
    rows = db.execute(sql, (point_wkt, session.vclass, point_wkt)).fetchall()

    if not rows:
        msg = _text(
            session.lang,
            kn="ನಿಮ್ಮ 1.5 ಕಿ.ಮೀ ವ್ಯಾಪ್ತಿಯಲ್ಲಿ ಯಾವುದೇ ಜಲಾವೃತ ರಸ್ತೆಗಳು ಕಂಡುಬಂದಿಲ್ಲ. ಎಚ್ಚರಿಕೆಯಿಂದ ಚಲಿಸಿ.",
            hi="आपके 1.5 किमी दायरे में कोई जलभराव वाली सड़क नहीं है। संभलकर चलें।",
            en="No waterlogged roads reported within 1.5 km of your location. Drive carefully.",
        )
        return _response_text(session.phone_number, msg)

    impassable_count = sum(1 for r in rows if r[2] == "impassable")
    risky_count = sum(1 for r in rows if r[2] == "risky")

    lines = []
    if impassable_count > 0:
        lines.append(
            _text(
                session.lang,
                kn=f"ಎಚ್ಚರಿಕೆ: {impassable_count} ರಸ್ತೆ(ಗಳು) ಸಂಪೂರ್ಣವಾಗಿ ಮುಚ್ಚಲಾಗಿದೆ!",
                hi=f"चेतावनी: {impassable_count} सड़क(ें) पूरी तरह से बंद हैं!",
                en=f"Warning: {impassable_count} road(s) nearby are IMPASSABLE!",
            )
        )
    elif risky_count > 0:
        lines.append(
            _text(
                session.lang,
                kn="ಗಮನಿಸಿ: ಹತ್ತಿರದ ರಸ್ತೆಗಳಲ್ಲಿ ನೀರು ನಿಲ್ಲುವ ಸಾಧ್ಯತೆ ಇದೆ.",
                hi="ध्यान दें: नजदीकी सड़कों पर जलभराव का जोखिम है।",
                en="Notice: High water risk detected on nearby roads.",
            )
        )
    else:
        lines.append(
            _text(
                session.lang,
                kn="ಸ್ಥಿತಿ: ಹತ್ತಿರದ ಮಾನಿಟರ್ ಮಾಡಿದ ರಸ್ತೆಗಳು ಸದ್ಯಕ್ಕೆ ಸ್ಪಷ್ಟವಾಗಿವೆ (Clear).",
                hi="स्थिति: नजदीकी सड़कें अभी खुली हैं (Clear)।",
                en="Status: Monitored roads near you are currently Clear.",
            )
        )

    for sid, rclass, state, _p, d50, dist_m in rows[:3]:
        dist_str = f"{int(dist_m)}m"
        depth_str = f"~{int(d50)}cm" if d50 else ""
        lines.append(f"- Road {sid} ({rclass}, {dist_str}): {state.upper()} {depth_str}".strip())

    lines.append("\n" + _text(
        session.lang,
        kn="ಪರ್ಯಾಯ ಮಾರ್ಗಗಳಿಗಾಗಿ ಫ್ಲಡ್‌ರೂಟ್ ಬಳಸಿ.",
        hi="वैकल्पिक मार्ग के लिए फ्लडरूट का उपयोग करें।",
        en="Use FloodRoute for alternate detour routing.",
    ))

    return _response_text(session.phone_number, "\n".join(lines))


def _handle_city_status(db: psycopg.Connection, session: UserSession) -> dict[str, Any]:
    """Summarize city-wide road closures and risk state."""
    sql = """
    select state, count(*)
    from segment_risk
    where vclass = %s and horizon_min = 0
    group by state
    """
    counts = dict(db.execute(sql, (session.vclass,)).fetchall())
    impassable = counts.get("impassable", 0)
    risky = counts.get("risky", 0)
    watch = counts.get("watch", 0)
    clear = counts.get("clear", 0)

    msg = _text(
        session.lang,
        kn=(
            f"ಬೆಂಗಳೂರು ರಸ್ತೆ ಜಲಾವೃತ ಸಾರಾಂಶ ({session.vclass}):\n"
            f"- ಮುಚ್ಚಿದ ರಸ್ತೆಗಳು (Impassable): {impassable}\n"
            f"- ಅಪಾಯಕಾರಿ (Risky): {risky}\n"
            f"- ನಿಗಾ ವಹಿಸಿ (Watch): {watch}\n"
            f"- ಸ್ಪಷ್ಟ (Clear): {clear}\n\n"
            "ನಿಮ್ಮ ಸ್ಥಳವನ್ನು ಹಂಚಿಕೊಳ್ಳುವ ಮೂಲಕ ಸ್ಥಳೀಯ ಮಾಹಿತಿ ಪಡೆಯಿರಿ."
        ),
        hi=(
            f"बेंगलुरु जलभराव स्थिति ({session.vclass}):\n"
            f"- बंद सड़कें (Impassable): {impassable}\n"
            f"- जोखिम (Risky): {risky}\n"
            f"- निगरानी (Watch): {watch}\n"
            f"- सामान्य (Clear): {clear}\n\n"
            "सटीक जानकारी के लिए अपनी लोकेशन शेयर करें।"
        ),
        en=(
            f"Bengaluru Flood Condition Summary ({session.vclass}):\n"
            f"- Closed roads (Impassable): {impassable}\n"
            f"- Risky roads: {risky}\n"
            f"- Watch status: {watch}\n"
            f"- Clear segments: {clear}\n\n"
            "Share your location to check roads near you."
        ),
    )
    return _response_text(session.phone_number, msg)


def _text(lang: str, kn: str, hi: str, en: str) -> str:
    if lang == "kn":
        return kn
    if lang == "hi":
        return hi
    return en


def _response_text(recipient: str, body: str) -> dict[str, Any]:
    # Clean any em-dashes
    clean_body = body.replace("\u2014", "-").replace("\u2013", "-")
    return {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": clean_body},
    }


def _response_buttons(recipient: str, body: str, buttons: list[dict[str, str]]) -> dict[str, Any]:
    clean_body = body.replace("\u2014", "-").replace("\u2013", "-")

    action_buttons = [
        {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
        for b in buttons[:3]
    ]
    return {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": clean_body},
            "action": {"buttons": action_buttons},
        },
    }
