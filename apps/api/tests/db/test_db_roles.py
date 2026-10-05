"""Roles, ownership, grants and the append-only audit_log."""

import shutil

import psycopg
import pytest
from psycopg import errors
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from floodroute.db.migrate import MIGRATIONS, migrate

# Everything FloodRoute created in schema public (extension members such as PostGIS are skipped).
OWNERS = """
select c.relname, pg_get_userbyid(c.relowner) from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
  and not exists (select 1 from pg_depend d where d.objid = c.oid and d.deptype = 'e')
union all
select p.proname, pg_get_userbyid(p.proowner) from pg_proc p
where p.pronamespace = 'public'::regnamespace
  and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
"""
TABLES = """
select c.relname from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relkind in ('r', 'p') and not c.relispartition
  and not exists (select 1 from pg_depend d where d.objid = c.oid and d.deptype = 'e')
"""
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
DML = {"SELECT", "INSERT", "UPDATE", "DELETE"}


def owners(conn):
    return dict(conn.execute(OWNERS).fetchall())


def test_migrator_owns_every_object(db):
    found = owners(db)
    assert {"segment", "audit_log", "segment_risk_history_default", "observed_event"} <= set(found)
    assert {"ensure_risk_history_partitions", "audit_log_append_only"} <= set(found)
    assert "audit_log_audit_id_seq" in found  # identity sequences follow their table
    assert set(found.values()) == {"floodroute_migrator"}


def test_app_role_has_dml_only_and_audit_log_is_insert_select(db):
    expected = {"audit_log": {"SELECT", "INSERT"}, "schema_migrations": set()}
    tables = [r[0] for r in db.execute(TABLES).fetchall()]
    assert len(tables) >= 18
    for table in tables:
        got = {
            p
            for p in PRIVILEGES
            if db.execute(
                "select has_table_privilege('floodroute_app', %s, %s)", (table, p)
            ).fetchone()[0]
        }
        assert got == expected.get(table, DML), table


def test_neither_role_holds_server_wide_privileges(db):
    rows = db.execute(
        "select rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls from pg_roles"
        " where rolname like 'floodroute_%'"
    ).fetchall()
    assert sorted(rows) == [
        ("floodroute_app", False, False, False, False),
        ("floodroute_migrator", False, False, False, False),
    ]


@pytest.mark.parametrize(
    "sql",
    [
        "create table sneaky (x int)",
        "alter table segment add column x int",
        "drop table segment",
        "truncate segment",
        "update schema_migrations set checksum = 'x'",
    ],
)
def test_app_role_cannot_run_ddl_truncate_or_touch_migration_history(app_db, sql):
    with pytest.raises(errors.InsufficientPrivilege):
        app_db.execute(sql)


def test_app_role_writes_identity_tables_without_sequence_grants(app_db):
    app_db.execute("insert into shadow_run (model_version, config_hash) values ('v0', 'abc')")
    app_db.execute(
        "insert into observed_event (city_id, observed_at, kind, source_kind, label_tier)"
        " values (1, now(), 'flooded', 'control_room', 'high')"
    )
    assert app_db.execute("select count(*) from observed_event").fetchone()[0] == 1


def test_a_later_migration_that_sets_the_role_is_owned_and_granted_correctly(db, db_url, tmp_path):
    shutil.copytree(MIGRATIONS, tmp_path, dirs_exist_ok=True)
    (tmp_path / "0004_later.sql").write_text(
        "set local role floodroute_migrator;\ncreate table later (x int);\n"
    )
    assert migrate(db_url, tmp_path) == ["0004_later.sql"]
    assert owners(db)["later"] == "floodroute_migrator"
    can_insert = db.execute("select has_table_privilege('floodroute_app', 'later', 'INSERT')")
    assert can_insert.fetchone() == (True,)


# ------------------------------------------------------------------ audit_log

WRITES = [
    "update audit_log set reason = 'x'",
    "delete from audit_log",
    "delete from audit_log where false",  # zero rows still refused: the trigger is statement level
    "truncate audit_log",
]


def test_audit_log_grants_allow_only_insert_and_select(app_db):
    app_db.execute("insert into audit_log (actor, action) values ('op1', 'override.create')")
    assert app_db.execute("select count(*) from audit_log").fetchone()[0] == 1
    for sql in WRITES:
        with pytest.raises(errors.InsufficientPrivilege, match="permission denied"):
            app_db.execute(sql)
    assert app_db.execute("select count(*) from audit_log").fetchone()[0] == 1


@pytest.mark.parametrize("sql", WRITES)
def test_audit_log_trigger_refuses_even_when_grants_are_wrong(db, app_db, sql):
    db.execute("insert into audit_log (actor, action) values ('op1', 'override.create')")
    db.execute("grant update, delete, truncate on audit_log to floodroute_app")  # the mistake
    for conn in (app_db, db):  # the app role, then the superuser
        with pytest.raises(errors.InsufficientPrivilege, match="append-only"):
            conn.execute(sql)
    db.execute("set session_replication_role = replica")  # skips ordinary triggers, not this one
    with pytest.raises(errors.InsufficientPrivilege, match="append-only"):
        db.execute(sql)
    assert db.execute("select count(*) from audit_log").fetchone()[0] == 1


# ------------------------------------------------------------------ non-superuser migrator


def test_migrations_apply_as_a_non_superuser_migrator_on_a_provisioned_database(
    pg_admin, fresh_db, template_db
):
    """How a managed Postgres runs them: roles, owned empty database and postgis come from infra.

    template_db is requested only so the test skips when PostGIS is missing and so the roles exist.
    """
    dbname = conninfo_to_dict(fresh_db)["dbname"]
    pg_admin.execute("alter role floodroute_migrator login")
    try:
        pg_admin.execute(f'alter database "{dbname}" owner to floodroute_migrator')
        with psycopg.connect(fresh_db, autocommit=True) as superuser:
            superuser.execute("create extension postgis")
        as_migrator = make_conninfo(fresh_db, user="floodroute_migrator")
        assert migrate(as_migrator) == sorted(p.name for p in MIGRATIONS.iterdir())
        with psycopg.connect(as_migrator, autocommit=True) as conn:
            assert set(owners(conn).values()) == {"floodroute_migrator"}
            assert conn.execute("select ensure_risk_history_partitions(5)").fetchone()[0] == 2
            me = conn.execute(
                "select current_user, usesuper from pg_user where usename = current_user"
            )
            assert me.fetchone() == ("floodroute_migrator", False)
    finally:
        pg_admin.execute("alter role floodroute_migrator nologin")
