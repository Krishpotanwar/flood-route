from dataclasses import replace
from itertools import pairwise

import pytest
from route_testkit import T0, ctx, edge, mins, risk, route

from floodroute.route.explain import MESSAGES
from floodroute.route.models import DEFAULT
from floodroute.route.reroute import Decision, TripState, decide, note_closed
from floodroute.route.validate import assess

FLOODED = {2: risk(0.9)}  # segment 2 is over the limit all the time
OK = {1: risk(0.01), 3: risk(0.01), 4: risk(0.01)}


def look(edges, table=None, depart=T0):
    """Assess a route the way the server does on each tick."""
    return assess(route(*edges), ctx({**OK, **FLOODED, **(table or {})}), depart)


def flooded_ahead(first_len=800.0, first_turn_off=True):
    return look([edge(1, 5, length_m=first_len, turn_off=first_turn_off), edge(2, 2, length_m=60)])


def clear_alt():
    return look([edge(1, 5, length_m=800), edge(3, 4, length_m=500, dlon=0.01)])


def test_a_segment_ahead_going_over_the_limit_triggers_a_suggestion():
    cur, alt = flooded_ahead(), clear_alt()
    assert cur.violations == (1,) and not alt.violations
    d = decide(TripState(), cur, alt, T0)
    assert (d.action, d.code, d.reasons, d.warn) == (
        "suggest",
        "suggest",
        ("reroute.road_flooded",),
        True,
    )
    assert d.route is alt.route
    assert d.state.last_suggestion_at == T0 and d.state.baseline_band == cur.worst_band
    # even a slower route is offered when the current one is blocked
    slow = look([edge(1, 5), edge(3, 60, dlon=0.01)])
    assert decide(TripState(), cur, slow, T0).action == "suggest"


@pytest.mark.parametrize(
    "current_min,saving_min,expect",
    [
        (60, 9.0, True),  # 15% of 60 = 9 min beats the 5 min floor
        (60, 8.9, False),
        (20, 5.0, True),  # 15% of 20 = 3 min, so the 5 min floor applies
        (20, 4.9, False),
    ],
)
def test_time_saving_must_reach_max_of_5_min_and_15_percent(current_min, saving_min, expect):
    cur = look([edge(None, current_min)])
    alt = look([edge(None, current_min - saving_min, dlon=0.01)])
    d = decide(TripState(), cur, alt, T0)
    assert (d.action == "suggest") is expect
    assert d.reasons == (("reroute.faster",) if expect else ())
    assert d.warn is False


def test_a_faster_route_in_a_higher_risk_band_is_not_offered():
    cur = look([edge(1, 30)])  # clear
    riskier = look([edge(5, 10, dlon=0.01)], {5: risk(0.15)})  # watch, but 20 min faster
    assert riskier.worst_band > cur.worst_band
    d = decide(TripState(), cur, riskier, T0)
    assert (d.action, d.code) == ("keep", "no_trigger")


def test_risk_rising_one_band_triggers_only_if_the_candidate_is_lower():
    watch = {5: risk(0.2)}  # below the 0.25 limit, so not flooded, but watch band
    cur = look([edge(5, 10)], watch)
    assert cur.worst_band == 1 and cur.violations == ()
    clear = look([edge(1, 10, dlon=0.01)])
    d = decide(TripState(baseline_band=0), cur, clear, T0)
    assert (d.action, d.reasons, d.warn) == ("suggest", ("reroute.risk_rising",), False)
    assert d.state.baseline_band == 1  # the user has been told: no repeat for the same level
    same_band = look([edge(5, 10, dlon=0.01)], watch)
    assert decide(TripState(baseline_band=0), cur, same_band, T0).action == "keep"
    assert decide(TripState(baseline_band=1), cur, clear, T0).action == "keep"  # not a rise


def test_the_baseline_follows_risk_down_so_a_later_rise_counts():
    cur = look([edge(1, 10)])  # now clear
    alt = look([edge(1, 10, dlon=0.01)])
    d = decide(TripState(baseline_band=2), cur, alt, T0)
    assert d.action == "keep" and d.state.baseline_band == 0
    watch = look([edge(5, 10)], {5: risk(0.2)})
    assert decide(d.state, watch, alt, T0 + mins(10)).action == "suggest"


# ---- dwell (FR-RT5) --------------------------------------------------------------------


def test_minimum_dwell_of_2_5_minutes_between_suggestions():
    cur, alt = flooded_ahead(), clear_alt()
    state = TripState(last_suggestion_at=T0)
    assert DEFAULT.dwell_s == 150
    held = decide(state, cur, alt, T0 + mins(2.49))  # 149.4 s later
    assert (held.action, held.code, held.route) == ("keep", "dwell", None)
    assert held.warn and held.reasons == ("reroute.flood_ahead",)  # warned, not silent
    ok = decide(state, cur, alt, T0 + mins(2.5))
    assert ok.action == "suggest"
    quiet = decide(state, look([edge(1, 60)]), look([edge(1, 30, dlon=0.01)]), T0 + mins(1))
    assert quiet.action == "keep" and quiet.code == "dwell" and not quiet.warn


def test_replay_of_a_live_trace_gives_at_most_one_suggestion_per_dwell_window():
    cur, alt = flooded_ahead(), clear_alt()
    state, times = TripState(), []
    for tick in range(0, 20 * 60 + 1, 15):  # a tick every 15 s for 20 min, route never accepted
        d = decide(state, cur, alt, T0 + mins(tick / 60))
        state = d.state
        if d.action == "suggest":
            times.append(tick)
    gaps = [b - a for a, b in pairwise(times)]
    assert times[0] == 0 and gaps and min(gaps) >= DEFAULT.dwell_s
    assert len(times) == 9  # 0, 150, ..., 1200


# ---- commit zone (FR-RT6) --------------------------------------------------------------


def test_commit_zone_holds_and_warns_instead_of_flipping():
    cur, alt = flooded_ahead(first_len=100, first_turn_off=False), clear_alt()
    d = decide(TripState(), cur, alt, T0)
    assert (d.action, d.code, d.route, d.warn) == ("hold", "commit_zone", None, True)
    assert d.reasons == ("reroute.commit_zone",)


def test_commit_zone_boundary_is_300_m_and_a_junction_releases_it():
    alt = clear_alt()
    at_300 = flooded_ahead(first_len=300, first_turn_off=False)
    assert decide(TripState(), at_300, alt, T0).action == "hold"
    beyond = flooded_ahead(first_len=301, first_turn_off=False)
    assert decide(TripState(), beyond, alt, T0).action == "suggest"
    with_exit = flooded_ahead(first_len=100, first_turn_off=True)  # a way off before the water
    assert decide(TripState(), with_exit, alt, T0).action == "suggest"
    exit_later = look(
        [
            edge(1, 1, length_m=100, turn_off=False),
            edge(3, 1, length_m=100, turn_off=True, dlon=0.01),
            edge(2, 1, length_m=50),
        ]
    )
    assert (
        exit_later.violations == (2,)
        and decide(TripState(), exit_later, alt, T0).action == "suggest"
    )


def test_being_inside_the_flooded_segment_is_a_hold():
    cur = look([edge(2, 1, length_m=40)])
    assert decide(TripState(), cur, clear_alt(), T0).code == "commit_zone"


def test_commit_zone_wins_over_dwell_and_does_not_apply_without_flooding():
    cur = flooded_ahead(first_len=100, first_turn_off=False)
    d = decide(TripState(last_suggestion_at=T0), cur, clear_alt(), T0 + mins(1))
    assert d.code == "commit_zone"
    no_flood = look([edge(1, 60, length_m=100, turn_off=False)])
    faster = look([edge(1, 30, dlon=0.01)])
    assert decide(TripState(), no_flood, faster, T0).action == "suggest"


# ---- never into a recently closed segment (FR-RT7) -------------------------------------


def test_never_reroute_into_a_segment_closed_in_the_last_15_minutes():
    cur, alt = flooded_ahead(), clear_alt()
    now = T0 + mins(30)
    recent = TripState(closed_at={3: now - mins(14)})
    d = decide(recent, cur, alt, now)
    assert (d.action, d.code, d.route) == ("keep", "recently_closed", None)
    assert d.warn and d.reasons == ("reroute.no_alternative",)
    old = TripState(closed_at={3: now - mins(16)})
    assert decide(old, cur, alt, now).action == "suggest"
    unrelated = TripState(closed_at={99: now - mins(1)})
    assert decide(unrelated, cur, alt, now).action == "suggest"


def test_a_segment_already_on_the_current_route_does_not_block_the_reroute():
    now = T0 + mins(30)
    cur = look([edge(3, 2, length_m=800), edge(2, 2, length_m=60)])  # 3 is ahead on both routes
    alt = look([edge(3, 2, length_m=800), edge(4, 5, dlon=0.01)])
    d = decide(TripState(closed_at={3: now - mins(5)}), cur, alt, now)
    assert d.action == "suggest"


def test_note_closed_records_the_latest_time_per_segment():
    s = note_closed(TripState(), [3, 4], T0)
    s = note_closed(s, [3], T0 + mins(5))
    assert dict(s.closed_at) == {3: T0 + mins(5), 4: T0}
    assert TripState().closed_at == {}  # the default state is not mutated


# ---- no usable alternative -------------------------------------------------------------


def test_flooded_ahead_with_no_usable_candidate_warns_and_suggests_nothing():
    cur = flooded_ahead()
    bad = look([edge(1, 5), edge(2, 2, dlon=0.01)])  # the candidate also crosses segment 2
    for candidate in (None, bad):
        d = decide(TripState(), cur, candidate, T0)
        assert (d.action, d.code, d.route) == ("keep", "no_candidate", None)
        assert d.warn and d.reasons == ("reroute.no_alternative",)
    ok = look([edge(1, 60)])
    d = decide(TripState(), ok, None, T0)
    assert (d.action, d.warn, d.reasons) == ("keep", False, ())


def test_a_route_with_a_violation_is_never_suggested():
    cur = flooded_ahead()
    for violating in (look([edge(2, 1)]), look([edge(1, 1), edge(2, 1)])):
        assert violating.violations
        assert decide(TripState(), cur, violating, T0).route is None
        assert decide(TripState(), look([edge(1, 60)]), violating, T0).route is None


def test_every_reason_id_is_a_known_message():
    cur, alt = flooded_ahead(), clear_alt()
    seen = set()
    for state, c, a in [
        (TripState(), cur, alt),
        (TripState(last_suggestion_at=T0), cur, alt),
        (TripState(), flooded_ahead(100, False), alt),
        (TripState(), cur, None),
        (TripState(baseline_band=0), look([edge(5, 10)], {5: risk(0.2)}), look([edge(1, 10)])),
        (TripState(), look([edge(1, 60)]), look([edge(1, 30, dlon=0.01)])),
    ]:
        d = decide(state, c, a, T0 + mins(1))
        assert isinstance(d, Decision)
        seen.update(d.reasons)
    assert seen <= set(MESSAGES["en"]) and len(seen) >= 5


def test_config_can_move_the_dwell_and_the_commit_zone():
    cfg = replace(DEFAULT, dwell_s=60.0, commit_zone_m=500.0)
    cur, alt = flooded_ahead(), clear_alt()
    assert decide(TripState(last_suggestion_at=T0), cur, alt, T0 + mins(1), cfg).action == "suggest"
    far = flooded_ahead(first_len=450, first_turn_off=False)
    assert decide(TripState(), far, alt, T0, cfg).action == "hold"
