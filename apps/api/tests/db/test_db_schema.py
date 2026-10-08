"""Schema behaviour: CHECK constraints, upserts, history partitions."""

import uuid

import psycopg
import pytest
from psycopg import errors

NOW = "2026-10-05 12:00:00+05:30"
LATER = "2026-10-05 14:00:00+05:30"
LINE = "SRID=4326;LINESTRING(77.60 12.90, 77.61 12.91)"
POINT = "SRID=4326;POINT(77.605 12.905)"
AREA = "SRID=4326;MULTIPOLYGON(((77.5 12.8, 77.7 12.8, 77.7 13.0, 77.5 13.0, 77.5 12.8)))"
NAN, INF = float("nan"), float("inf")


def row(**cols):
    return cols


RISK = row(
    segment_id=10,
    vclass="car",
    horizon_min=60,
    p_unusable=0.3,
    depth_p50_cm=5,
    depth_p90_cm=12,
    state="risky",
    confidence="medium",
    evidence_age_s=120,
    model_version="v0",
    updated_at=NOW,
)

# One valid row per table. Zone 1, segments 10 and 11, tenant 1 and run 1 come from seeded().
GOOD = {
    "zone": row(zone_id=2, city_id=1, geom=AREA, params="{}"),
    "segment": row(segment_id=12, osm_way_id=1, geom=LINE, road_class="primary", city_id=1),
    "segment_static": row(segment_id=11, zone_id=1, base_logit=-2.0, structure="dip"),
    "rain_obs": row(source="gauge", zone_id=1, ts=NOW, mm_5m=1.5, mm_60m=10, mm_24h=40),
    "rain_fcst": row(
        source="gfs", zone_id=1, issued=NOW, valid=LATER, mm_per_h=2, ensemble_spread=1
    ),
    "evidence": row(
        segment_id=10,
        kind="report",
        ts=NOW,
        expires=LATER,
        depth_cm=12,
        speed_ratio=0.5,
        trust=0.8,
        source_id="r1",
    ),
    "segment_risk": RISK,
    "segment_risk_history": {**RISK, "run_id": 1},
    "tenant": row(tenant_id=2, name="Acme", kind="fleet", rate_limit_rpm=60),
    "override": row(
        tenant_id=1,
        segment_id=10,
        action="close",
        reason="police closure",
        operator_id="op1",
        second_operator_id="op2",
        starts_at=NOW,
        expires_at=LATER,
    ),
    "route_decision": row(decision_id=uuid.uuid4(), ts=NOW, vclass="car", model_version="v0"),
    "report": row(report_id=uuid.uuid4(), segment_id=10, ts=NOW, depth_class="ankle", trust=0.5),
    "shadow_run": row(model_version="v0", config_hash="abc"),
    "observed_event": row(
        city_id=1,
        observed_at=NOW,
        segment_id=10,
        location=POINT,
        kind="flooded",
        depth_class="knee",
        source_kind="traffic_police",
        label_tier="high",
    ),
    "audit_log": row(actor="op1", action="override.create"),
}


def insert(conn, table, suffix="", **cols):
    marks = ", ".join(["%s"] * len(cols))
    sql = f"insert into {table} ({', '.join(cols)}) values ({marks}) {suffix}"
    return conn.execute(sql, list(cols.values()))


@pytest.fixture
def seeded(db):
    insert(db, "zone", zone_id=1, city_id=1, geom=AREA, params="{}")
    insert(db, "segment", segment_id=10, osm_way_id=1, geom=LINE, road_class="primary", city_id=1)
    insert(db, "segment", segment_id=11, osm_way_id=2, geom=LINE, road_class="primary", city_id=1)
    insert(db, "tenant", tenant_id=1, name="Control room", kind="control_room")
    insert(db, "shadow_run", model_version="v0", config_hash="abc")
    return db


def bad(table, constraint, **cols):
    return pytest.param(table, cols, constraint, id=f"{constraint}-{next(iter(cols.values()))}")


CASES = [
    bad("segment_static", "segment_static_structure_check", structure="tunnel"),
    bad("segment_static", "segment_static_lowest_elev_m_check", lowest_elev_m=NAN),
    bad("segment_static", "segment_static_depression_m_check", depression_m=-1),
    bad("segment_static", "segment_static_drain_dist_m_check", drain_dist_m=INF),
    bad("segment_static", "segment_static_hotspot_count_check", hotspot_count=-1),
    bad("segment_static", "segment_static_base_logit_check", base_logit=NAN),
    bad("rain_obs", "rain_obs_mm_5m_check", mm_5m=-0.1),
    bad("rain_obs", "rain_obs_mm_5m_check", mm_5m=NAN),
    bad("rain_obs", "rain_obs_mm_60m_check", mm_60m=INF),
    bad("rain_obs", "rain_obs_mm_24h_check", mm_24h=-5),
    bad("rain_fcst", "rain_fcst_mm_per_h_check", mm_per_h=-1),
    bad("rain_fcst", "rain_fcst_ensemble_spread_check", ensemble_spread=NAN),
    bad("evidence", "evidence_kind_check", kind="rumour"),
    bad("evidence", "evidence_depth_cm_check", depth_cm=-1),
    bad("evidence", "evidence_speed_ratio_check", speed_ratio=NAN),
    bad("evidence", "evidence_trust_check", trust=1.5),
    bad("evidence", "evidence_trust_check", trust=NAN),
    bad("evidence", "evidence_expires_after_ts", expires=NOW),
    bad("evidence", "evidence_contributors_check", contributors=-1),
    bad("segment_risk", "segment_risk_vclass_check", vclass="bus"),
    bad("segment_risk", "segment_risk_horizon_min_check", horizon_min=45),
    bad("segment_risk", "segment_risk_p_unusable_check", p_unusable=1.01),
    bad("segment_risk", "segment_risk_p_unusable_check", p_unusable=-0.01),
    bad("segment_risk", "segment_risk_p_unusable_check", p_unusable=NAN),
    bad("segment_risk", "segment_risk_depth_p50_cm_check", depth_p50_cm=-1),
    bad("segment_risk", "segment_risk_depth_order", depth_p50_cm=30, depth_p90_cm=12),
    bad("segment_risk", "segment_risk_state_check", state="safe"),
    bad("segment_risk", "segment_risk_confidence_check", confidence="certain"),
    bad("segment_risk", "segment_risk_evidence_age_s_check", evidence_age_s=-1),
    bad("segment_risk_history", "segment_risk_state_check", state="safe"),
    bad("segment_risk_history", "segment_risk_p_unusable_check", p_unusable=2),
    bad("tenant", "tenant_kind_check", kind="partner"),
    bad("tenant", "tenant_rate_limit_rpm_check", rate_limit_rpm=0),
    bad("override", "override_action_check", action="delete"),
    bad("override", "override_reason_check", reason="   "),
    bad("override", "override_expires_after_start", expires_at=NOW),
    bad("override", "override_two_people", second_operator_id="op1"),
    bad("route_decision", "route_decision_vclass_check", vclass="tractor"),
    bad("report", "report_depth_class_check", depth_class="ankle-deep"),
    bad("report", "report_trust_check", trust=-0.5),
    bad("report", "report_status_check", status="done"),
    bad("observed_event", "observed_event_kind_check", kind="wet"),
    bad("observed_event", "observed_event_depth_class_check", depth_class="chest"),
    bad("observed_event", "observed_event_source_kind_check", source_kind="rumour"),
    bad("observed_event", "observed_event_label_tier_check", label_tier="certain"),
    bad(
        "observed_event",
        "observed_event_noisy_source_is_low",
        source_kind="news",
        label_tier="high",
    ),
    bad(
        "observed_event",
        "observed_event_noisy_source_is_low",
        source_kind="social",
        label_tier="medium",
    ),
]


@pytest.mark.parametrize("table", sorted(GOOD))
def test_the_valid_baseline_row_is_accepted(seeded, table):
    insert(seeded, table, **GOOD[table])


@pytest.mark.parametrize(("table", "override", "constraint"), CASES)
def test_check_constraint_rejects_bad_value(seeded, table, override, constraint):
    with pytest.raises(errors.CheckViolation) as err:
        insert(seeded, table, **{**GOOD[table], **override})
    assert err.value.diag.constraint_name == constraint


def test_optional_columns_and_valid_alternatives_are_accepted(seeded):
    # Not every constraint is a rejection: nulls and boundary values must pass.
    insert(seeded, "observed_event", **{**GOOD["observed_event"], "location": None, "segment_id": None,
                                        "depth_class": None, "source_kind": "news", "label_tier": "low"})  # fmt: skip
    insert(
        seeded,
        "observed_event",
        **{**GOOD["observed_event"], "source_kind": "crowd", "label_tier": "low"},
    )
    insert(
        seeded,
        "segment_risk",
        **{**RISK, "horizon_min": 0, "p_unusable": 0.0, "depth_p50_cm": None},
    )
    insert(seeded, "segment_risk", **{**RISK, "horizon_min": 30, "p_unusable": 1.0})
    insert(seeded, "override", **{**GOOD["override"], "second_operator_id": None})
    insert(
        seeded,
        "segment_risk",
        **{**RISK, "vclass": "ambulance", "horizon_min": 0, "evidence_age_s": None},
    )  # unknown age is NULL, never 0


def test_evidence_carries_verification_and_report_link(seeded):
    report_id = uuid.uuid4()
    insert(seeded, "report", **{**GOOD["report"], "report_id": report_id})
    insert(
        seeded,
        "evidence",
        **{
            **GOOD["evidence"],
            "verified": True,
            "contributors": 9,
            "report_id": report_id,
        },
    )
    got = seeded.execute(
        "select verified, contributors, report_id from evidence where source_id = 'r1'"
    ).fetchone()
    assert (got[0], got[1], str(got[2])) == (True, 9, str(report_id))
    with pytest.raises(errors.ForeignKeyViolation):
        insert(
            seeded,
            "evidence",
            **{**GOOD["evidence"], "source_id": "r2", "report_id": uuid.uuid4()},
        )


def test_kill_switch_scope_must_match_its_id_columns(seeded):
    good_global = {
        "switch_id": uuid.uuid4(),
        "scope": "global",
        "reason": "storm drill freeze",
        "operator_id": "op1",
    }
    insert(seeded, "kill_switch", **good_global)
    insert(
        seeded,
        "kill_switch",
        **{**good_global, "switch_id": uuid.uuid4(), "scope": "tenant", "tenant_id": 1},
    )
    insert(
        seeded,
        "kill_switch",
        **{**good_global, "switch_id": uuid.uuid4(), "scope": "city", "city_id": 1},
    )
    for bad_ids in ({"tenant_id": 1}, {"city_id": 1}, {"tenant_id": 1, "city_id": 1}):
        with pytest.raises(errors.CheckViolation) as err:
            insert(
                seeded,
                "kill_switch",
                **{**good_global, "switch_id": uuid.uuid4(), **bad_ids},
            )
        assert err.value.diag.constraint_name == "kill_switch_scope_ids_check"
    with pytest.raises(errors.CheckViolation):
        insert(
            seeded,
            "kill_switch",
            **{**good_global, "switch_id": uuid.uuid4(), "scope": "tenant"},
        )
    with pytest.raises(errors.CheckViolation):
        insert(
            seeded,
            "kill_switch",
            **{**good_global, "switch_id": uuid.uuid4(), "scope": "city"},
        )


def test_every_trd_table_exists(db):
    rows = db.execute(
        "select relname from pg_class where relnamespace = 'public'::regnamespace"
        " and relkind in ('r', 'p') and not relispartition"
    ).fetchall()
    trd = {  # docs/TRD.md section 4
        "segment", "segment_static", "zone", "rain_obs", "rain_fcst", "official_alert", "evidence",
        "segment_risk", "segment_risk_history", "override", "audit_log", "route_decision", "report",
        "source_health", "tenant",
    }  # fmt: skip
    assert trd | {"shadow_run", "observed_event", "schema_migrations"} <= {r[0] for r in rows}


def test_assessed_graph_edge_lookup_has_a_partial_way_index(db):
    row = db.execute(
        "select pg_get_indexdef(i.indexrelid), pg_get_expr(i.indpred, i.indrelid)"
        " from pg_index i join pg_class c on c.oid = i.indexrelid"
        " where c.relname = 'segment_assessed_osm_way_idx'"
    ).fetchone()
    assert row is not None and "USING btree (osm_way_id)" in row[0]
    assert row[1] == "assessed"


# ------------------------------------------------------------------ segment_risk upsert and history

UPSERT = """
insert into segment_risk (segment_id, vclass, horizon_min, p_unusable, state, confidence,
                          evidence_age_s, model_version, updated_at, closed_since)
values (%(segment_id)s, %(vclass)s, %(horizon_min)s, %(p)s, %(state)s, 'medium', 60, 'v0', %(at)s, %(closed)s)
on conflict (segment_id, vclass, horizon_min) do update set
  p_unusable = excluded.p_unusable, state = excluded.state,
  updated_at = excluded.updated_at, closed_since = excluded.closed_since
"""


def upsert(conn, p, state, at, closed=None, horizon_min=60):
    args = row(segment_id=10, vclass="car", horizon_min=horizon_min, p=p, state=state)
    conn.execute(UPSERT, {**args, "at": at, "closed": closed})


def test_segment_risk_upsert_by_primary_key_as_the_app_role(seeded, app_db):
    upsert(app_db, 0.2, "watch", NOW)
    upsert(app_db, 0.9, "impassable", LATER, closed=LATER)
    upsert(app_db, 0.0, "clear", LATER, horizon_min=0)  # another horizon is a different row
    rows = app_db.execute(
        "select horizon_min, p_unusable, state, closed_since is not null from segment_risk order by 1"
    ).fetchall()
    assert rows == [(0, 0.0, "clear", False), (60, pytest.approx(0.9), "impassable", True)]
    with pytest.raises(errors.CheckViolation):  # the conflict path is still validated
        upsert(app_db, 1.5, "impassable", LATER)


def test_history_insert_is_idempotent_and_needs_a_known_run(seeded, app_db):
    row = GOOD["segment_risk_history"]
    assert insert(app_db, "segment_risk_history", **row).rowcount == 1
    assert (
        insert(app_db, "segment_risk_history", suffix="on conflict do nothing", **row).rowcount == 0
    )
    with pytest.raises(errors.ForeignKeyViolation):
        insert(app_db, "segment_risk_history", **{**row, "run_id": 999, "updated_at": LATER})


# ------------------------------------------------------------------ partitions


def part_of(conn, ts, **extra):
    """Insert a history row dated ts and return the partition it landed in."""
    row = {**GOOD["segment_risk_history"], "updated_at": ts, **extra}
    cur = insert(conn, "segment_risk_history", suffix="returning tableoid::regclass::text", **row)
    return cur.fetchone()[0]


def month_name(conn, now, months):
    """Expected partition name for the IST month `months` after now's month."""
    return conn.execute(
        "select 'segment_risk_history_' || to_char((%s::timestamptz at time zone 'Asia/Kolkata')"
        " + make_interval(months => %s), 'YYYY_MM')",
        (now, months),
    ).fetchone()[0]


def partitions(conn):
    rows = conn.execute(
        "select relid::text from pg_partition_tree('segment_risk_history') where isleaf"
    ).fetchall()
    return {r[0] for r in rows}


def test_migration_creates_current_and_next_three_months_plus_default(seeded):
    now = seeded.execute("select now()").fetchone()[0]
    expected = {month_name(seeded, now, m) for m in range(4)} | {"segment_risk_history_default"}
    assert partitions(seeded) == expected


def test_rows_route_to_their_month_and_strays_to_default(seeded):
    now = seeded.execute("select now()").fetchone()[0]
    assert part_of(seeded, now) == month_name(seeded, now, 0)
    assert part_of(seeded, now, vclass="ambulance") == month_name(seeded, now, 0)
    later = seeded.execute("select %s::timestamptz + interval '70 days'", (now,)).fetchone()[0]
    assert part_of(seeded, later) == month_name(seeded, later, 0)
    far = seeded.execute("select %s::timestamptz + interval '3 years'", (now,)).fetchone()[0]
    assert part_of(seeded, far) == "segment_risk_history_default"
    past = seeded.execute("select %s::timestamptz - interval '3 years'", (now,)).fetchone()[0]
    assert part_of(seeded, past) == "segment_risk_history_default"


def test_partition_boundaries_are_india_midnight(seeded):
    # The last microsecond of an IST month and the first instant of the next month.
    edge = seeded.execute(
        "select (date_trunc('month', now() at time zone 'Asia/Kolkata') + interval '1 month')"
        " at time zone 'Asia/Kolkata'"
    ).fetchone()[0]
    before = seeded.execute(
        "select %s::timestamptz - interval '1 microsecond'", (edge,)
    ).fetchone()[0]
    now = seeded.execute("select now()").fetchone()[0]
    assert part_of(seeded, before) == month_name(seeded, now, 0)
    assert part_of(seeded, edge) == month_name(seeded, now, 1)


def test_partitions_created_later_still_enforce_the_run_foreign_key(seeded):
    seeded.execute("select ensure_risk_history_partitions(6)")
    now = seeded.execute("select now()").fetchone()[0]
    ts = seeded.execute("select %s::timestamptz + interval '6 months'", (now,)).fetchone()[0]
    assert part_of(seeded, ts) == month_name(seeded, ts, 0)
    with pytest.raises(errors.ForeignKeyViolation):
        part_of(seeded, ts, run_id=999, vclass="heavy")


def test_ensure_is_idempotent_and_creates_only_what_is_missing(seeded):
    ensure = "select ensure_risk_history_partitions(%s)"
    assert seeded.execute(ensure, (3,)).fetchone()[0] == 0
    assert seeded.execute(ensure, (0,)).fetchone()[0] == 0
    assert seeded.execute(ensure, (6,)).fetchone()[0] == 3
    assert seeded.execute(ensure, (6,)).fetchone()[0] == 0
    assert len(partitions(seeded)) == 8  # current + 6 months + default


@pytest.mark.parametrize("months", [-1, 25, None])
def test_ensure_rejects_out_of_range_horizon(seeded, months):
    with pytest.raises(psycopg.errors.RaiseException, match="between 0 and 24"):
        seeded.execute("select ensure_risk_history_partitions(%s)", (months,))


def test_rows_that_strayed_into_default_move_when_their_partition_appears(seeded):
    now = seeded.execute("select now()").fetchone()[0]
    ts = seeded.execute("select %s::timestamptz + interval '5 months'", (now,)).fetchone()[0]
    assert part_of(seeded, ts) == "segment_risk_history_default"
    assert seeded.execute("select ensure_risk_history_partitions(6)").fetchone()[0] == 3
    landed = seeded.execute(
        "select tableoid::regclass::text from segment_risk_history where updated_at = %s", (ts,)
    ).fetchone()[0]
    assert landed == month_name(seeded, ts, 0)
    assert seeded.execute("select count(*) from segment_risk_history_default").fetchone()[0] == 0


def test_app_role_can_extend_partitions_without_ddl_rights(seeded, app_db):
    assert app_db.execute("select ensure_risk_history_partitions(5)").fetchone()[0] == 2
    owners = seeded.execute(
        "select distinct pg_get_userbyid(c.relowner) from pg_partition_tree('segment_risk_history') t"
        " join pg_class c on c.oid = t.relid"
    ).fetchall()
    assert owners == [("floodroute_migrator",)]
    with pytest.raises(errors.InsufficientPrivilege):
        app_db.execute("create table sneaky (x int)")
