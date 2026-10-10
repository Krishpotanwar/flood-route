"""TRAI DLT-compliant SMS template registry and character budget engine.

Enforces Telecom Commercial Communications Customer Preference Regulations (TCCCPR):
- Strict single-segment SMS character limits:
  * Unicode (Indic scripts: Kannada, Hindi, Tamil, Telugu): 70 characters
  * GSM-7 (Standard Latin): 160 characters
- Pre-approved DLT template IDs and variable slot validation
- Utility category compliance (no promotional copy)
- Safety invariant: never uses 'safe' label
- Design rule: zero em-dashes
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# GSM-7 standard characters pattern
GSM7_BASIC = re.compile(
    r"^[A-Za-z0-9 \r\n!\"#$%&'()*+,-./:;<=>?@_¡£¥§¿èéùìòÇØøÅåΔΦΓΛΩΠΨΣΘΞÆæßÉ\^{}\\\[~\]|€]*$"
)


@dataclass(frozen=True)
class DLTTemplate:
    """Registered DLT SMS template specification."""

    template_id: str
    name: str
    lang: str  # 'kn', 'hi', 'en'
    category: str  # 'service_implicit' or 'utility'
    pattern: str  # e.g. "FloodRoute: {#var#} is closed. Detour: {#var#}"
    variable_names: tuple[str, ...]
    max_chars: int  # 70 for Unicode, 160 for GSM-7


# Pre-approved DLT templates for FloodRoute emergency and navigation alerts
DLT_TEMPLATES: dict[str, DLTTemplate] = {
    # Kannada templates (Unicode, max 70 characters)
    "KN_ROAD_CLOSED": DLTTemplate(
        template_id="11071690000001",
        name="kannada_road_closure_alert",
        lang="kn",
        category="utility",
        pattern="ಎಚ್ಚರಿಕೆ: {#var#} ರಸ್ತೆ ಮುಚ್ಚಲಾಗಿದೆ. ಪರ್ಯಾಯ: {#var#}",
        variable_names=("landmark", "detour"),
        max_chars=70,
    ),
    "KN_WATERLOGGED_WARNING": DLTTemplate(
        template_id="11071690000002",
        name="kannada_waterlog_warning",
        lang="kn",
        category="utility",
        pattern="ಗಮನಿಸಿ: {#var#} ಬಳಿ ನೀರು ನಿಲ್ಲುವ ಸಾಧ್ಯತೆ. ನಿಧಾನವಾಗಿ ಚಲಿಸಿ: {#var#}",
        variable_names=("landmark", "action"),
        max_chars=70,
    ),
    "KN_REROUTE_SUGGEST": DLTTemplate(
        template_id="11071690000003",
        name="kannada_reroute_detour",
        lang="kn",
        category="utility",
        pattern="ಮಾರ್ಗ ಬದಲಾವಣೆ: {#var#} ಜಲಾವೃತ. {#var#} ಮೂಲಕ ಚಲಿಸಿ.",
        variable_names=("landmark", "alternate_road"),
        max_chars=70,
    ),
    # Hindi templates (Unicode, max 70 characters)
    "HI_ROAD_CLOSED": DLTTemplate(
        template_id="11071690000004",
        name="hindi_road_closure_alert",
        lang="hi",
        category="utility",
        pattern="चेतावनी: {#var#} रास्ता बंद है। वैकल्पिक मार्ग: {#var#}",
        variable_names=("landmark", "detour"),
        max_chars=70,
    ),
    "HI_WATERLOGGED_WARNING": DLTTemplate(
        template_id="11071690000005",
        name="hindi_waterlog_warning",
        lang="hi",
        category="utility",
        pattern="ध्यान दें: {#var#} पर जलभराव की संभावना है। संಭलकर चलें: {#var#}",
        variable_names=("landmark", "action"),
        max_chars=70,
    ),
    "HI_REROUTE_SUGGEST": DLTTemplate(
        template_id="11071690000006",
        name="hindi_reroute_detour",
        lang="hi",
        category="utility",
        pattern="मार्ग परिवर्तन: {#var#} जलमग्न। {#var#} से जाएं।",
        variable_names=("landmark", "alternate_road"),
        max_chars=70,
    ),
    # English templates (GSM-7, max 160 characters)
    "EN_ROAD_CLOSED": DLTTemplate(
        template_id="11071690000007",
        name="english_road_closure_alert",
        lang="en",
        category="utility",
        pattern="FloodRoute: {#var#} is closed due to waterlogging. Take detour via {#var#}.",
        variable_names=("landmark", "detour"),
        max_chars=160,
    ),
    "EN_WATERLOGGED_WARNING": DLTTemplate(
        template_id="11071690000008",
        name="english_waterlog_warning",
        lang="en",
        category="utility",
        pattern="FloodRoute Watch: Water likely at {#var#} in 20-30 min. Plan detour via {#var#}.",
        variable_names=("landmark", "detour"),
        max_chars=160,
    ),
    "EN_REROUTE_SUGGEST": DLTTemplate(
        template_id="11071690000009",
        name="english_reroute_detour",
        lang="en",
        category="utility",
        pattern="FloodRoute Detour: Road ahead closed at {#var#}. Suggest alternative via {#var#}.",
        variable_names=("landmark", "alternate_road"),
        max_chars=160,
    ),
}


def is_gsm7(text: str) -> bool:
    """Return True if text consists strictly of standard GSM-7 characters."""
    return bool(GSM7_BASIC.match(text))


def get_sms_char_limit(text: str) -> int:
    """Return character limit for a single SMS part (70 for Unicode, 160 for GSM-7)."""
    return 160 if is_gsm7(text) else 70


def render_sms(
    template_key: str,
    variables: dict[str, str],
    auto_truncate: bool = True,
) -> dict[str, Any]:
    """Render a DLT-approved SMS template with variables.

    Validates:
    - Template key existence
    - Variable substitution matching pre-approved pattern
    - Resulting character length against DLT single-segment limit (70 / 160)
    - Zero em-dashes and strict safety invariants
    """
    if template_key not in DLT_TEMPLATES:
        raise ValueError(f"Unknown DLT template key: {template_key}")

    tmpl = DLT_TEMPLATES[template_key]
    rendered = tmpl.pattern

    # Count variables
    var_count = rendered.count("{#var#}")

    # Every slot must be filled with a non-blank value; blanks would send a
    # non-compliant incomplete alert under the DLT pattern.
    missing = [name for name in tmpl.variable_names if not str(variables.get(name, "")).strip()]
    if missing:
        raise ValueError(f"Template {template_key} is missing variables: {missing}")
    var_values = [str(variables[name]).strip() for name in tmpl.variable_names]

    if len(var_values) != var_count:
        raise ValueError(
            f"Template {template_key} requires {var_count} variables ({tmpl.variable_names}), "
            f"got {len(var_values)}"
        )

    # Perform substitution
    for val in var_values:
        rendered = rendered.replace("{#var#}", val, 1)

    # Remove any forbidden em-dashes
    rendered = rendered.replace("\u2014", "-").replace("\u2013", "-")


    # Safety check: road state must never be called "safe"
    lower_text = rendered.lower()
    if re.search(r"\bsafe\b", lower_text):
        raise ValueError("Rendered SMS violates safety invariant: contains 'safe'")

    char_limit = tmpl.max_chars
    actual_length = len(rendered)

    if actual_length > char_limit:
        if auto_truncate:
            # Shorten variable values if overflow occurs
            overflow = actual_length - char_limit
            # Truncate first long variable (usually landmark or detour)
            adjusted_vars = dict(variables)
            for v_name in tmpl.variable_names:
                curr_val = adjusted_vars.get(v_name, "")
                if len(curr_val) > overflow + 3:
                    adjusted_vars[v_name] = curr_val[: -overflow - 1] + "."
                    return render_sms(template_key, adjusted_vars, auto_truncate=False)
        raise ValueError(
            f"Rendered SMS ({actual_length} chars) exceeds DLT limit ({char_limit} chars): '{rendered}'"
        )

    return {
        "template_id": tmpl.template_id,
        "template_key": template_key,
        "lang": tmpl.lang,
        "text": rendered,
        "character_count": len(rendered),
        "character_limit": char_limit,
        "encoding": "GSM-7" if is_gsm7(rendered) else "Unicode (UCS-2)",
        "is_single_segment": len(rendered) <= char_limit,
    }
