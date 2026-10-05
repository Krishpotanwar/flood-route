"""Config loading is strict: unknown or missing keys, bad types and inconsistent values fail."""

from __future__ import annotations

import copy
import json
from dataclasses import fields

import pytest
from score_helpers import CFG

from floodroute.score.config import DEFAULT_PATH, Config, ConfigError, Group, parse_config

RAW = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))


def mutated(fn) -> str:
    data = copy.deepcopy(RAW)
    fn(data)
    return json.dumps(data)


def test_default_config_loads_with_prd_horizons():
    assert CFG.horizons_min == (0, 30, 60, 120)  # FR-R1
    assert CFG.model_version


def test_every_group_is_flagged_provisional_with_a_note():
    groups = [getattr(CFG, f.name) for f in fields(Config)]
    groups += list(CFG.structures.values()) + list(CFG.vehicle_profiles.values())
    groups = [g for g in groups if isinstance(g, Group)]
    assert len(groups) >= 15
    for g in groups:
        assert g.provisional is True, type(g).__name__
        assert g.note.strip(), type(g).__name__


def test_vehicle_profiles_follow_prd_11_2():
    want = {  # caution, unusable (ranges take the lower, cautious end)
        "pedestrian": (10, 15),
        "two_wheeler": (10, 15),
        "auto_rickshaw": (10, 20),
        "car": (15, 30),
        "suv": (25, 40),
        "ambulance": (15, 20),
        "heavy": (30, 50),
    }
    assert {k: (v.caution_cm, v.unusable_cm) for k, v in CFG.vehicle_profiles.items()} == want
    assert all(v.basis.strip() and v.provisional for v in CFG.vehicle_profiles.values())


def test_unknown_key_is_rejected_at_every_level():
    with pytest.raises(ConfigError, match="unknown keys.*bogus"):
        parse_config(mutated(lambda d: d.update(bogus=1)))
    with pytest.raises(ConfigError, match="states.*bogus"):
        parse_config(mutated(lambda d: d["states"].update(bogus=1)))
    with pytest.raises(ConfigError, match="structures.underpass.*bogus"):
        parse_config(mutated(lambda d: d["structures"]["underpass"].update(bogus=1)))


def test_missing_key_is_rejected_at_every_level():
    with pytest.raises(ConfigError, match="missing keys.*staleness"):
        parse_config(mutated(lambda d: d.pop("staleness")))
    with pytest.raises(ConfigError, match="missing keys.*reopen_hold_s"):
        parse_config(mutated(lambda d: d["hysteresis"].pop("reopen_hold_s")))
    with pytest.raises(ConfigError, match="missing keys.*basis"):
        parse_config(mutated(lambda d: d["vehicle_profiles"]["car"].pop("basis")))
    with pytest.raises(ConfigError, match="missing keys.*provisional"):
        parse_config(mutated(lambda d: d["rain"].pop("provisional")))


def test_provisional_group_needs_a_note():
    with pytest.raises(ConfigError, match="non-empty note"):
        parse_config(mutated(lambda d: d["logit"].update(note="  ")))


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d["hysteresis"].update(reopen_hold_s=600.5),  # float for an int field
        lambda d: d["hysteresis"].update(reopen_hold_s=True),  # bool is not a number
        lambda d: d["states"].update(watch_min="0.1"),  # string for a number
        lambda d: d["rain"].update(source_priority="gauge"),  # not a list
        lambda d: d["states"].update(provisional="yes"),
    ],
)
def test_wrong_types_are_rejected(edit):
    with pytest.raises(ConfigError, match="expected"):
        parse_config(mutated(edit))


def test_duplicate_keys_and_nan_are_rejected():
    text = json.dumps(RAW).replace('"watch_min": 0.1', '"watch_min": 0.1, "watch_min": 0.2')
    with pytest.raises(ConfigError, match="duplicate"):
        parse_config(text)
    with pytest.raises(ConfigError, match="NaN"):
        parse_config(json.dumps(RAW).replace('"k_trigger": 5.0', '"k_trigger": NaN'))
    with pytest.raises(ConfigError, match="not valid JSON"):
        parse_config("{")


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        (lambda d: d["states"].update(watch_min=0.4), "watch_min < risky_min"),
        (lambda d: d["states"].update(impassable_min=1.0), "impassable_min < 1"),
        (lambda d: d["hysteresis"].update(reopen_below=0.6), "below states.impassable_min"),
        (lambda d: d["hysteresis"].update(reopen_hold_s=0), "reopen_hold_s"),
        (lambda d: d["evidence"].update(corroboration_min_sources=1), r"FR-R8"),
        (lambda d: d["evidence"].update(probe_min_contributors=4), "k-anonymity"),
        (lambda d: d["evidence"].update(tau_min=0), "tau_min"),
        (lambda d: d["evidence"].update(depth_clear_cap_p=0.95), "cap must be below"),
        (lambda d: d["structures"]["dip"].update(r_low=60.0), "r_low < r_high"),
        (lambda d: d["vehicle_profiles"]["car"].update(caution_cm=30.0), "caution_cm"),
        (lambda d: d.update(horizons_min=[0, 60, 30]), "strictly increasing"),
        (lambda d: d.update(horizons_min=[]), "strictly increasing"),
        (lambda d: d["logit"].update(delta_reference_class="tank"), "delta_reference_class"),
        (lambda d: d["rain"].update(source_priority=["gauge", "gauge"]), "duplicates"),
        (lambda d: d["logit"].update(delta_per_ln_depth=-1.0), "delta_per_ln_depth"),
    ],
)
def test_inconsistent_values_are_rejected(edit, match):
    with pytest.raises(ConfigError, match=match):
        parse_config(mutated(edit))
