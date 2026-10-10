import re
import string
from pathlib import Path

import pytest

from floodroute.route import explain
from floodroute.route.explain import MESSAGES, about, pick_lang, say

EN = MESSAGES["en"]
DASHES = (chr(0x2014), chr(0x2013))  # em and en dash, spelled out so this file has none
SOURCES = Path(explain.__file__).parent


def placeholders(template):
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def sentences(text):
    return [s for s in re.split(r"(?<=[.?!])\s+", text) if s]


@pytest.mark.parametrize("lang", sorted(MESSAGES))
def test_no_string_says_safe_or_uses_banned_words(lang):
    for mid, text in MESSAGES[lang].items():
        assert not re.search(r"\bsafe", text, re.IGNORECASE), mid
        assert not re.search(r"\b(eta|inundation|oops)\b", text, re.IGNORECASE), mid


@pytest.mark.parametrize("lang", sorted(MESSAGES))
def test_style_rules_no_dashes_plain_text_short_sentences(lang):
    for mid, text in MESSAGES[lang].items():
        assert not any(d in text for d in DASHES), mid  # no em or en dash
        assert text.isascii() or lang != "en", mid  # English is plain ASCII, no emoji
        assert all(len(s.split()) <= 14 for s in sentences(text)), mid  # about 12 words
        assert text.endswith((".", "?")), mid


def test_every_template_renders_with_exactly_its_placeholders():
    for mid, text in EN.items():
        params = dict.fromkeys(placeholders(text), "7")
        out = say(mid, "en", **params)
        assert "{" not in out and "}" not in out, mid


def test_every_language_has_the_english_ids_and_placeholders():
    for lang, table in MESSAGES.items():
        assert set(table) == set(EN), lang
        for mid, text in table.items():
            assert placeholders(text) == placeholders(EN[mid]), (lang, mid)


def test_a_missing_language_falls_back_to_english_and_says_so():
    assert pick_lang("kn") == "en" and pick_lang("en") == "en"
    assert say("delta.longer", "kn", minutes=6) == "6 min longer."


def test_about_rounds_to_five_minutes_and_never_says_zero():
    assert [about(m) for m in (0, 2.4, 3, 7.4, 7.5, 23.2, 41)] == [5, 5, 5, 5, 10, 25, 40]


def test_times_in_strings_are_hedged_with_about():
    assert "about" in EN["avoid.named"] and "about" in EN["avoid.unnamed"]
    assert say("avoid.named", place="Madiwala underpass", minutes=about(23)) == (
        "Avoiding Madiwala underpass (water likely in about 25 min)."
    )


def test_every_message_id_the_code_uses_exists():
    used = set()
    for name in ("validate.py", "reroute.py"):
        used |= set(
            re.findall(
                r'"((?:avoid|delta|route|guidance|reroute)\.[a-z_0-9]+)"',
                (SOURCES / name).read_text(),
            )
        )
    # avoid.* keys are built from parts in validate._avoid_lines
    used |= {f"avoid.{now}{named}" for now in ("", "now_") for named in ("named", "unnamed")}
    # advisory_off is set as a guidance key by the kill-switch path in api/routes/route.py
    api_route = SOURCES.parent / "api" / "routes" / "route.py"
    if '"advisory_off"' in api_route.read_text():
        used.add("advisory_off")
    assert used and used <= set(EN), used - set(EN)
    assert set(EN) <= used, set(EN) - used  # no orphan strings either
