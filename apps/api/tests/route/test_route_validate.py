import json
import math
import random
import re
from dataclasses import replace
from datetime import UTC, timedelta

import pytest
from route_testkit import (
    CLOSES_AT_40,
    T0,
    FakeRouter,
    ctx,
    edge,
    mins,
    request,
    risk,
    risk_for,
    route,
)

from floodroute.route.interp import p_at
from floodroute.route.models import DEFAULT, HORIZONS, Action
from floodroute.route.validate import Ctx, _out, assess, exclusion_polygon, plan, state_from_p


def run(fn, table, req=None, **kw):
    router = FakeRouter(fn)
    out = plan(
        req or request(),
        router,
        risk_for(table),
        now=T0,
        model_version="v0.3.1",
        decision_id="c1f2",
        **kw,
    )
    return out, router


def near(a, b, secs=1e-3):
    return abs((a - b).total_seconds()) < secs


# ---- FR-RT2: arrival time, not request time -------------------------------------------


def test_fr_rt2_reaching_the_segment_at_45_is_rejected_and_at_25_is_accepted():
    table = {2: risk(CLOSES_AT_40)}  # forecast to cross the 0.25 limit at t+40
    late = route(edge(1, 45), edge(2, 1))  # reaches segment 2 at t+45
    early = route(edge(1, 25), edge(2, 1))  # reaches segment 2 at t+25
    assert p_at(CLOSES_AT_40, 0) < 0.25  # a request-time check would wave both through

    c = ctx(table)
    assert assess(late, c, T0).violations == (1,)
    ok = assess(early, c, T0)
    assert ok.violations == ()
    assert near(ok.valid_until, T0 + mins(40))  # the closure it was racing

    out, _ = run(lambda n, polys: late, table)
    assert out.response.no_safe_route and not any(r.is_default for r in out.response.routes)
    out, _ = run(lambda n, polys: early, table)
    assert not out.response.no_safe_route and out.response.routes[0].is_default


def test_eta_margin_widens_the_window_and_defaults_to_the_routers_eta():
    table = {2: risk(CLOSES_AT_40)}
    at_35 = route(edge(1, 35), edge(2, 1))  # exact ETA says it passes before the close at t+40
    at_25 = route(edge(1, 25), edge(2, 1))
    assert DEFAULT.eta_margin == 0.0
    assert assess(at_35, ctx(table), T0).violations == ()
    cautious = Ctx(risk_for(table), "car", T0, 0.25, replace(DEFAULT, eta_margin=0.25))
    assert assess(at_35, cautious, T0).violations == (1,)  # 36 min plus 25% reaches past t+40
    assert assess(at_25, cautious, T0).violations == ()  # still clear of it
    # early side: a closure that is lifting may not have lifted yet if the vehicle is early
    lifting = {2: risk({0: 0.9, 30: 0.9, 60: 0.05, 120: 0.05})}
    after = route(edge(1, 55), edge(2, 1))  # reopened by t+55 on the router's ETA
    assert assess(after, ctx(lifting), T0).violations == ()
    assert assess(after, Ctx(risk_for(lifting), "car", T0, 0.25, cautious.cfg), T0).violations == (
        1,
    )
    for bad in (-0.1, 1.5):
        with pytest.raises(ValueError):
            replace(DEFAULT, eta_margin=bad)


def test_departing_later_shifts_every_arrival_time():
    table = {2: risk(CLOSES_AT_40)}
    r = route(edge(1, 20), edge(2, 1))  # reaches segment 2 at depart + 20
    assert assess(r, ctx(table), T0).violations == ()  # t+20: fine
    assert assess(r, ctx(table), T0 + mins(25)).violations == (1,)  # t+45: closed


def test_forecast_horizons_count_from_when_the_forecast_was_issued():
    stale = risk(CLOSES_AT_40, issued=T0 - mins(10))  # issued 10 min before the request
    r = route(edge(1, 25), edge(2, 1))  # reaches it 35 min after issue: past the crossing at 40?
    assert assess(r, ctx({2: stale}), T0).violations == ()  # 35 < 40
    r = route(edge(1, 31), edge(2, 1))  # 41 min after issue
    assert assess(r, ctx({2: stale}), T0).violations == (1,)


def test_the_limit_is_inclusive_p_equal_to_it_is_a_violation():
    r = route(edge(2, 1))
    assert assess(r, ctx({2: risk(0.25)}), T0).violations == (0,)
    assert assess(r, ctx({2: risk(0.2499)}), T0).violations == ()


def test_a_peak_inside_the_traversal_window_is_not_missed():
    peak = {0: 0.05, 30: 0.40, 60: 0.05, 120: 0.05}  # low when entering and leaving
    table = {2: risk(peak)}
    assert assess(route(edge(1, 2), edge(2, 56)), ctx(table), T0).violations == (1,)
    assert assess(route(edge(1, 2), edge(2, 1)), ctx(table), T0).violations == ()


# ---- thresholds: class, tenant, hysteresis --------------------------------------------


def test_ambulance_threshold_differs_from_citizen():
    assert DEFAULT.thresholds == {"citizen": 0.25, "ambulance": 0.45}
    r = route(edge(1, 5), edge(2, 1))
    cit, _ = run(lambda n, p: r, {2: risk(0.35)}, request("car", "citizen"))
    amb, _ = run(lambda n, p: r, {2: risk(0.35)}, request("ambulance", "ambulance"))
    assert cit.response.no_safe_route
    assert not amb.response.no_safe_route
    assert amb.response.routes[0].worst_state == "risky"  # allowed, but still labelled risky
    over, _ = run(lambda n, p: r, {2: risk(0.46)}, request("ambulance", "ambulance"))
    assert over.response.no_safe_route


def test_tenant_override_moves_the_limit_but_never_past_impassable():
    r = route(edge(2, 1))
    cfg = replace(DEFAULT, thresholds={**DEFAULT.thresholds, "citizen": 0.4})
    out, _ = run(lambda n, p: r, {2: risk(0.35)}, cfg=cfg)
    assert not out.response.no_safe_route
    for bad in (0.51, 1.0, 0.0, -0.1, float("nan")):
        with pytest.raises(ValueError):
            replace(DEFAULT, thresholds={"citizen": bad})
    assert replace(DEFAULT, thresholds={"citizen": 0.5})  # up to the Impassable band is allowed


def test_assess_refuses_a_limit_above_the_impassable_band():
    for bad in (0.0, 0.51, 1.0, float("nan")):
        with pytest.raises(ValueError):
            ctx({}, threshold=bad)
    assert ctx({}, threshold=0.5)


def test_a_closure_held_by_hysteresis_is_excluded_even_when_p_has_dropped():
    states = {0: "impassable", 30: "clear", 60: "clear", 120: "clear"}
    held = risk({0: 0.30, 30: 0.05, 60: 0.05, 120: 0.05}, states=states)
    amb = ctx({2: held}, threshold=0.45)
    assert assess(route(edge(2, 1)), amb, T0).violations == (0,)  # closed now
    assert assess(route(edge(1, 31), edge(2, 1)), amb, T0).violations == ()  # forecast open
    plain = risk({0: 0.30, 30: 0.05, 60: 0.05, 120: 0.05})  # same p, but not a held closure
    assert assess(route(edge(2, 1)), ctx({2: plain}, threshold=0.45), T0).violations == ()


# ---- coverage honesty ------------------------------------------------------------------


def test_unassessed_edges_are_neutral_and_marked_assessed_false():
    r = route(edge(1, 5), edge(None, 3), edge(2, 4))
    out, _ = run(lambda n, p: r, {})
    resp = out.response
    rt = resp.routes[0]
    assert not resp.no_safe_route and rt.is_default
    assert [(s.segment_id, s.assessed, s.state, s.p) for s in rt.segments] == [
        ("1", False, None, None),
        ("2", False, None, None),
    ]
    assert rt.worst_state == "unknown"  # nothing was assessed: must not read as clear
    assert "Some roads on this route have no flood data." in rt.reasons
    assert near(resp.valid_until, T0 + mins(12))  # nothing forecast: valid for the trip


def test_clear_assessed_edges_do_not_make_unassessed_ones_look_clear():
    r = route(edge(1, 5), edge(2, 4))
    out, _ = run(lambda n, p: r, {2: risk(0.01)})
    rt = out.response.routes[0]
    assert rt.worst_state == "clear" and [s.assessed for s in rt.segments] == [False, True]
    assert "Some roads on this route have no flood data." in rt.reasons


def test_unknown_counts_as_watch_in_rain_but_is_reported_as_unknown():
    table = {2: risk(0.0, states="unknown")}  # stale data: the stored p means nothing
    r = route(edge(1, 5), edge(2, 1))
    rain = assess(r, ctx(table, in_rain=True), T0)
    c = rain.checks[1]
    assert (c.state, c.band, c.p) == ("unknown", 1, pytest.approx(0.10))
    assert rain.worst_state == "unknown" and rain.violations == ()
    dry = assess(r, ctx(table, in_rain=False), T0)
    c = dry.checks[1]
    assert (c.state, c.band, c.p) == ("unknown", 0, 0.0)
    strict = ctx(table, threshold=0.05)  # a limit below the watch band excludes it in rain only
    assert assess(r, strict, T0).violations == (1,)
    assert assess(r, replace(strict, in_rain=False), T0).violations == ()


def test_an_old_row_cannot_vouch_for_clear_even_if_its_stored_age_is_small():
    r = route(edge(2, 1))
    old = risk(0.02, issued=T0 - mins(20), age=30)  # the scoring job died 20 min ago
    c = assess(r, ctx({2: old}), T0).checks[0]
    assert (c.state, c.band, c.evidence_age_s) == ("unknown", 1, 30 + 20 * 60)  # watch in rain
    dry = assess(r, ctx({2: old}, in_rain=False), T0).checks[0]
    assert (dry.state, dry.band, dry.p) == ("unknown", 0, pytest.approx(0.02))
    fresh = risk(0.02, issued=T0 - mins(5), age=30)
    c = assess(r, ctx({2: fresh}), T0).checks[0]
    assert (c.state, c.evidence_age_s) == ("clear", 330)
    # only clear degrades (FR-R4): a stale watch or risky row stays as stored
    for p, want in ((0.2, "watch"), (0.4, "risky")):
        c = assess(r, ctx({2: risk(p, issued=T0 - mins(20))}, threshold=0.5), T0).checks[0]
        assert c.state == want and c.p == pytest.approx(p)


def test_a_row_with_no_evidence_is_aged_by_the_run_alone():
    r = route(edge(2, 1))
    c = assess(r, ctx({2: risk(0.02, issued=T0 - mins(5), age=None)}), T0).checks[0]
    assert (c.state, c.evidence_age_s) == ("clear", 300)
    c = assess(r, ctx({2: risk(0.02, issued=T0 - mins(20), age=None)}), T0).checks[0]
    assert c.state == "unknown"


def test_the_stale_limit_is_inclusive_of_exactly_15_minutes():
    r = route(edge(2, 1))
    edge_of_stale = risk(0.02, issued=T0 - timedelta(seconds=870), age=30)  # exactly 900 s
    assert assess(r, ctx({2: edge_of_stale}), T0).checks[0].state == "clear"
    just_over = risk(0.02, issued=T0 - timedelta(seconds=870), age=31)
    assert assess(r, ctx({2: just_over}), T0).checks[0].state == "unknown"
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            replace(DEFAULT, stale_s=bad)


def test_the_response_reports_the_true_age_of_the_data():
    old = risk(0.02, issued=T0 - mins(20), age=30)
    out, _ = run(lambda n, p: route(edge(2, 1)), {2: old})
    rt = out.response.routes[0]
    assert rt.data_age_s == 1230 and rt.segments[0].evidence_age_s == 1230
    assert rt.worst_state == "unknown"  # a stale "clear" must not read as clear
    assert "Take care. Flood data is out of date on part of this route." in rt.reasons


def test_unknown_is_called_out_in_the_reasons():
    out, _ = run(lambda n, p: route(edge(2, 1)), {2: risk(0.0, states="unknown")})
    reasons = out.response.routes[0].reasons
    assert "Take care. Flood data is out of date on part of this route." in reasons


# ---- the loop --------------------------------------------------------------------------


def test_iteration_cap_yields_no_safe_route():
    flooded = {10 + n: risk(0.9) for n in range(1, 8)}
    out, router = run(lambda n, polys: route(edge(10 + n, 2, dlon=n * 0.01)), flooded)
    assert router.calls == 4 and out.iterations == 3  # first route plus 3 re-queries
    assert [len(p) for p in router.polygons] == [0, 1, 2, 3]  # each pass excludes one more
    r = out.response
    assert r.no_safe_route and r.valid_until is None
    assert [x.kind for x in r.routes] == ["least_risk"] and not r.routes[0].is_default
    assert len(out.rejected) == 4
    capped = replace(DEFAULT, max_iterations=1)
    _, router = run(lambda n, polys: route(edge(10 + n, 2, dlon=n * 0.01)), flooded, cfg=capped)
    assert router.calls == 2
    once = replace(DEFAULT, max_iterations=0)
    _, router = run(lambda n, polys: route(edge(10 + n, 2, dlon=n * 0.01)), flooded, cfg=once)
    assert router.calls == 1


def test_a_router_that_ignores_exclusions_stops_instead_of_looping():
    out, router = run(lambda n, polys: route(edge(11, 2)), {11: risk(0.9)})
    assert router.calls == 2 and out.iterations == 1 and out.response.no_safe_route


def test_no_route_at_all_is_no_safe_route_without_a_route():
    out, router = run(lambda n, polys: None, {})
    assert router.calls == 1
    r = out.response
    assert r.no_safe_route and r.routes == [] and r.valid_until is None
    assert r.guidance_when_no_route is not None and out.iterations == 0 and out.rejected == ()


def test_no_route_after_exclusions_keeps_the_least_risk_route_found():
    table = {2: risk(0.9)}
    out, router = run(lambda n, polys: route(edge(2, 2)) if n == 1 else None, table)
    r = out.response
    assert r.no_safe_route and [x.kind for x in r.routes] == ["least_risk"]
    assert r.routes[0].segments[0].over_limit
    assert router.polygons[1] != ()  # the second query did carry an exclusion


def test_safest_and_fastest_side_by_side_fr_rt4():
    table = {2: risk(CLOSES_AT_40), 3: risk(0.02)}
    fast = route(edge(1, 45), edge(2, 1))  # 46 min, reaches segment 2 after it has closed
    alt = route(edge(1, 45), edge(3, 7, dlon=0.01))  # 52 min
    names = {2: "Madiwala underpass"}
    out, router = run(lambda n, polys: fast if n == 1 else alt, table, name_of=names.get)
    resp = out.response
    safest, fastest = resp.routes
    assert (safest.kind, safest.is_default, safest.delta_min) == ("safest", True, 6)
    assert (fastest.kind, fastest.is_default, fastest.delta_min) == ("fastest", False, 0)
    assert safest.eta_min == 52 and fastest.eta_min == 46
    assert safest.reasons[:2] == [
        "Avoiding Madiwala underpass (water likely in about 40 min).",
        "6 min longer.",
    ]
    assert "Avoid this route if you can. Water is likely on part of it." in fastest.reasons
    assert [s.over_limit for s in fastest.segments] == [False, True]
    assert not any(s.over_limit for s in safest.segments)
    assert resp.no_safe_route is False and resp.guidance_when_no_route is None
    assert near(resp.valid_until, T0 + mins(120))  # nothing on the safest route crosses

    # the exclusion handed to the router covers the violating edge
    (poly,) = router.polygons[1]
    lats, lons = [p[0] for p in poly], [p[1] for p in poly]
    for lat, lon in fast.edges[1].geometry:
        assert min(lats) < lat < max(lats) and min(lons) < lon < max(lons)


def test_unnamed_and_immediate_avoid_lines():
    table = {2: risk(0.9), 3: risk(0.01)}
    out, _ = run(lambda n, p: route(edge(2, 2)) if n == 1 else route(edge(3, 2)), table)
    assert out.response.routes[0].reasons[0] == "Avoiding a road where water is likely now."
    out, _ = run(
        lambda n, p: route(edge(2, 2)) if n == 1 else route(edge(3, 2)),
        table,
        name_of={2: "Silk Board underpass"}.get,
    )
    assert out.response.routes[0].reasons[0] == "Avoiding Silk Board underpass (water likely now)."


def test_least_risk_route_is_marked_and_chosen_by_exposure():
    # A has one segment at 0.9 (exposure 0.9). B has three at 0.3 (exposure 1 - 0.7**3 = 0.657).
    table = {20: risk(0.9), 21: risk(0.3), 22: risk(0.3), 23: risk(0.3)}
    a = route(edge(20, 2))
    b = route(edge(21, 1), edge(22, 1, dlon=0.01), edge(23, 1, dlon=0.02))
    out, _ = run(lambda n, p: a if n == 1 else b, table, cfg=replace(DEFAULT, max_iterations=1))
    (least,) = out.response.routes
    assert least.kind == "least_risk" and not least.is_default
    assert least.eta_min == 3
    assert "Use this route only if you must. Water is still likely on part of it." in least.reasons
    assert any(s.over_limit for s in least.segments)


def test_guidance_when_no_route_by_profile():
    r = route(edge(2, 1))
    table = {2: risk(0.9)}
    cit, _ = run(lambda n, p: r, table)
    g = cit.response.guidance_when_no_route
    assert g.keys == [
        "guidance.stay",
        "guidance.no_water",
        "guidance.avoid_low",
        "guidance.call_112",
    ]
    assert Action(id="call_112", tel="112") in g.actions and len(g.text) == len(g.keys)
    amb, _ = run(lambda n, p: r, table, request("ambulance", "ambulance"))
    g = amb.response.guidance_when_no_route
    assert g.keys == ["guidance.escalate", "guidance.alt_modes", "guidance.least_risk"]
    assert [a.id for a in g.actions] == ["escalate_dispatcher"]
    none, _ = run(lambda n, p: None, table, request("ambulance", "ambulance"))
    assert "guidance.least_risk" not in none.response.guidance_when_no_route.keys


def test_the_default_marker_refuses_a_route_with_a_violation():
    a = assess(route(edge(2, 1)), ctx({2: risk(0.9)}), T0)
    assert a.violations
    with pytest.raises(RuntimeError):
        _out("fastest", a, a, True, "en", [])
    assert _out("least_risk", a, a, False, "en", []).is_default is False


def _router_through_all_segments(durations):
    """Visits every segment whose start point is not inside an exclusion box; None if none left."""

    def fn(n, polys):
        def blocked(seg):
            lat, lon = edge(seg, dlon=seg * 0.01).geometry[0]
            return any(
                min(q[0] for q in p) <= lat <= max(q[0] for q in p)
                and min(q[1] for q in p) <= lon <= max(q[1] for q in p)
                for p in polys
            )

        keep = [s for s in sorted(durations) if not blocked(s)]
        return route(*(edge(s, durations[s], dlon=s * 0.01) for s in keep)) if keep else None

    return fn


def test_default_route_never_has_a_sampled_p_at_or_above_the_limit():
    rng = random.Random(2027)
    defaults = rerouted = 0
    for _ in range(150):
        table = {s: risk({h: rng.random() ** 3 for h in HORIZONS}) for s in range(1, 7)}
        dur = {s: rng.uniform(0.5, 30) for s in table}
        thr = rng.choice([0.25, 0.45])
        cfg = replace(DEFAULT, thresholds={"citizen": thr, "ambulance": thr})
        out, _ = run(_router_through_all_segments(dur), table, cfg=cfg)
        rerouted += out.iterations > 0
        for rt in out.response.routes:
            if not rt.is_default:
                continue
            defaults += 1
            assert not any(s.over_limit for s in rt.segments)
            t = 0.0
            for s in rt.segments:  # re-check by sampling, independent of the window logic
                start = t
                t += dur[int(s.segment_id)]
                for i in range(int((t - start) * 10) + 1):
                    assert p_at(table[int(s.segment_id)].p, start + i / 10) < thr
                assert p_at(table[int(s.segment_id)].p, t) < thr
    assert defaults > 30 and rerouted > 30  # the property was actually exercised


# ---- valid_until -----------------------------------------------------------------------


def _cross(pa, pb, thr, a, b):  # independent maths: where logit-linear p from pa to pb hits thr
    lg = lambda p: math.log(p / (1 - p))
    return a + (lg(thr) - lg(pa)) / (lg(pb) - lg(pa)) * (b - a)


def test_valid_until_is_the_earliest_crossing_along_the_route():
    slow = {0: 0.02, 30: 0.02, 60: 0.02, 120: 0.9}  # crosses 0.25 at about t+87.5
    table = {2: risk(CLOSES_AT_40), 3: risk(slow)}
    r = route(edge(1, 25), edge(2, 1), edge(4, 4), edge(3, 1))  # reaches 2 at +25, 3 at +30
    a = assess(r, ctx(table), T0)
    assert a.violations == () and near(a.valid_until, T0 + mins(40))
    only3 = assess(route(edge(1, 30), edge(3, 1)), ctx({3: risk(slow)}), T0)
    assert near(only3.valid_until, T0 + mins(_cross(0.02, 0.9, 0.25, 60, 120)), 1e-2)


def test_valid_until_without_a_crossing_is_the_end_of_the_forecast():
    a = (assess(route(edge(2, 5)), ctx({2: risk(0.02)}), T0 - mins(0)),)
    a = a[0]
    assert near(a.valid_until, T0 + mins(120))
    old = assess(route(edge(2, 5)), ctx({2: risk(0.02, issued=T0 - mins(30))}), T0)
    assert near(old.valid_until, T0 + mins(90))  # horizons count from the issue time


def test_a_crossing_that_is_over_before_arrival_does_not_set_valid_until():
    blip = {0: 0.02, 30: 0.9, 60: 0.02, 120: 0.02}  # closes around +30 and has reopened by +90
    a = assess(route(edge(1, 90), edge(2, 1)), ctx({2: risk(blip)}), T0)
    assert a.violations == () and near(a.valid_until, T0 + mins(120))


def test_response_valid_until_is_in_india_time():
    table = {2: risk(CLOSES_AT_40)}
    r = route(edge(1, 25), edge(2, 1))
    out, _ = run(lambda n, p: r, table, request(depart=T0.astimezone(UTC)))
    dumped = out.response.model_dump(mode="json")
    assert dumped["valid_until"].endswith("+05:30")
    assert dumped["valid_until"] == "2027-05-18T18:20:00+05:30"


# ---- never a "safe" label ----------------------------------------------------------------


def _walk(obj, key=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield "key", k, None
            yield from _walk(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, key)
    elif isinstance(obj, str):
        yield "value", obj, key


def test_no_safe_label_anywhere_in_any_response():
    scenarios = []
    table = {2: risk(CLOSES_AT_40), 3: risk(0.02), 4: risk(0.0, states="unknown"), 5: risk(0.9)}
    fast = route(edge(1, 45), edge(2, 1))
    alt = route(edge(1, 45), edge(3, 7, dlon=0.01), edge(4, 2, dlon=0.02))
    scenarios.append(
        run(lambda n, p: fast if n == 1 else alt, table, name_of=lambda s: "Silk Board")[0]
    )
    scenarios.append(run(lambda n, p: alt, table)[0])  # accepted, mixed states
    scenarios.append(run(lambda n, p: route(edge(5, 2)), table)[0])  # no_safe_route, citizen
    scenarios.append(
        run(lambda n, p: route(edge(5, 2)), table, request("ambulance", "ambulance"))[0]
    )
    scenarios.append(run(lambda n, p: None, table)[0])  # no route at all
    scenarios.append(run(lambda n, p: route(edge(7, 3)), {})[0])  # nothing assessed
    for out in scenarios:
        dumped = json.loads(out.response.model_dump_json())
        for what, text, key in _walk(dumped):
            if what == "key":
                assert text == "no_safe_route" or "safe" not in text.lower(), text
            elif key == "kind":
                assert text in {"fastest", "safest", "least_risk"}  # TRD 8.2 route kinds
            else:
                assert not re.search(r"\bsafe", text, re.IGNORECASE), (key, text)
            if key == "state":
                assert text in {"clear", "watch", "risky", "impassable", "unknown"}
        for rt in dumped["routes"]:
            assert rt["worst_state"] in {"clear", "watch", "risky", "impassable", "unknown"}


def test_state_bands_follow_the_trd_and_are_configurable():
    cases = [
        (0.0, "clear"), (0.0999, "clear"), (0.10, "watch"), (0.2999, "watch"),
        (0.30, "risky"), (0.4999, "risky"), (0.50, "impassable"), (1.0, "impassable"),
    ]  # fmt: skip
    for p, want in cases:
        assert state_from_p(p) == want
    thresholds = {"citizen": 0.2, "ambulance": 0.35}
    tight = replace(DEFAULT, watch_p=0.05, risky_p=0.2, impassable_p=0.4, thresholds=thresholds)
    assert state_from_p(0.1, tight) == "watch" and state_from_p(0.45, tight) == "impassable"
    with pytest.raises(ValueError):  # the default limits sit above a lowered Impassable band
        replace(DEFAULT, impassable_p=0.4)


# ---- determinism and fail-closed ---------------------------------------------------------


def test_plan_is_deterministic_and_ignores_dict_order():
    def one(reverse):
        forecast = dict(sorted(CLOSES_AT_40.items(), reverse=reverse))
        table = {2: risk(forecast), 3: risk(0.02)}
        fast = route(edge(1, 45), edge(2, 1))
        alt = route(edge(1, 45), edge(3, 7, dlon=0.01))
        out, _ = run(lambda n, p: fast if n == 1 else alt, table, name_of={2: "Underpass"}.get)
        return out.response.model_dump_json()

    assert one(False) == one(False) == one(True)


def test_errors_from_the_router_or_the_risk_source_propagate():
    def boom(n, polys):
        raise RuntimeError("valhalla down")

    with pytest.raises(RuntimeError):
        run(boom, {})

    def bad_risk(seg, vclass):
        raise ConnectionError("db down")

    with pytest.raises(ConnectionError):
        plan(request(), FakeRouter(lambda n, p: route(edge(2, 1))), bad_risk,
             now=T0, model_version="v", decision_id="d")  # fmt: skip


def test_depart_beyond_the_forecast_is_rejected():
    r = route(edge(2, 1))
    run(lambda n, p: r, {}, request(depart=T0 + mins(120)))  # exactly at the last horizon
    with pytest.raises(ValueError):
        run(lambda n, p: r, {}, request(depart=T0 + mins(121)))
    run(lambda n, p: r, {}, request(depart=T0 - mins(30)))  # already left: current conditions


# ---- exclusion polygon -------------------------------------------------------------------


def test_exclusion_polygon_is_a_closed_box_with_at_least_the_buffer_on_every_side():
    e = edge(2, 1)
    poly = exclusion_polygon(e, 20.0)
    assert poly[0] == poly[-1] and len(poly) == 5
    s, n = min(p[0] for p in poly), max(p[0] for p in poly)
    w, ea = min(p[1] for p in poly), max(p[1] for p in poly)
    for lat, lon in e.geometry:
        assert (lat - s) * 110_574 >= 20 - 1e-6 and (n - lat) * 110_574 >= 20 - 1e-6
        mlon = 111_320 * math.cos(math.radians(lat))
        assert (lon - w) * mlon >= 20 - 1e-6 and (ea - lon) * mlon >= 20 - 1e-6
    assert exclusion_polygon(replace(e, geometry=()), 20.0) is None
