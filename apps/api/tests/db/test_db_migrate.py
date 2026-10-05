"""Migration runner: ordering, idempotency, tamper detection, atomic files, CLI."""

import os
import subprocess
import sys

import psycopg
import pytest

from floodroute.db.migrate import MIGRATIONS, MigrationError, migrate


def write(directory, files: dict[str, str]):
    for name, body in files.items():
        (directory / f"{name}.sql").write_text(body)


def exists(url: str, table: str) -> bool:
    with psycopg.connect(url) as conn:
        return conn.execute("select to_regclass(%s)", (table,)).fetchone()[0] is not None


def test_real_migrations_apply_from_scratch_and_twice_is_a_noop(fresh_db, template_db):
    names = sorted(p.name for p in MIGRATIONS.iterdir())
    assert len(names) >= 3
    assert migrate(fresh_db) == names
    assert migrate(fresh_db) == []
    with psycopg.connect(fresh_db) as conn:
        rows = conn.execute("select filename from schema_migrations order by 1").fetchall()
    assert [r[0] for r in rows] == names


def test_tampered_applied_file_is_refused_before_anything_new_applies(tmp_path, fresh_db):
    write(tmp_path, {"0001_a": "create table a (x int);", "0002_b": "create table b (x int);"})
    assert migrate(fresh_db, tmp_path) == ["0001_a.sql", "0002_b.sql"]
    (tmp_path / "0001_a.sql").write_text("create table a (x int, y int);")
    write(tmp_path, {"0003_c": "create table c (x int);"})
    with pytest.raises(MigrationError, match=r"checksum mismatch.*0001_a\.sql"):
        migrate(fresh_db, tmp_path)
    assert not exists(fresh_db, "c")


def test_applied_file_that_vanished_is_refused(tmp_path, fresh_db):
    write(tmp_path, {"0001_a": "create table a (x int);"})
    migrate(fresh_db, tmp_path)
    (tmp_path / "0001_a.sql").unlink()
    with pytest.raises(MigrationError, match=r"0001_a\.sql is missing"):
        migrate(fresh_db, tmp_path)


def test_pending_file_older_than_applied_is_refused(tmp_path, fresh_db):
    write(tmp_path, {"0001_a": "create table a (x int);", "0003_c": "create table c (x int);"})
    migrate(fresh_db, tmp_path)
    write(tmp_path, {"0002_b": "create table b (x int);"})
    with pytest.raises(MigrationError, match="renumber"):
        migrate(fresh_db, tmp_path)
    assert not exists(fresh_db, "b")


def test_stray_file_is_refused(tmp_path, fresh_db):
    write(tmp_path, {"0001_a": "create table a (x int);"})
    (tmp_path / "notes.txt").write_text("hi")
    with pytest.raises(MigrationError, match="unexpected files"):
        migrate(fresh_db, tmp_path)
    assert not exists(fresh_db, "a")


def test_failed_file_rolls_back_whole_and_earlier_files_stay(tmp_path, fresh_db):
    write(tmp_path, {"0001_ok": "create table ok (x int);"})
    write(tmp_path, {"0002_bad": "create table half (x int); select 1 / 0;"})
    with pytest.raises(MigrationError, match=r"0002_bad\.sql failed"):
        migrate(fresh_db, tmp_path)
    assert exists(fresh_db, "ok") and not exists(fresh_db, "half")
    with psycopg.connect(fresh_db) as conn:
        done = conn.execute("select filename from schema_migrations").fetchall()
    assert done == [("0001_ok.sql",)]
    # A file that never applied may be fixed in place, and the next run picks it up.
    write(tmp_path, {"0002_bad": "create table fixed (x int);"})
    assert migrate(fresh_db, tmp_path) == ["0002_bad.sql"]
    assert exists(fresh_db, "fixed")


def test_file_effects_and_bookkeeping_commit_together(tmp_path, fresh_db):
    # The file records itself, so the runner's own bookkeeping insert collides with it.
    # The whole file, including its table, must then roll back.
    record = "insert into schema_migrations (filename, checksum) values ('0001_a.sql', 'x');"
    write(tmp_path, {"0001_a": f"create table a (x int); {record}"})
    with pytest.raises(MigrationError, match=r"0001_a\.sql failed"):
        migrate(fresh_db, tmp_path)
    assert not exists(fresh_db, "a")


def test_a_migration_blocked_by_a_lock_fails_fast_and_can_be_retried(
    tmp_path, fresh_db, monkeypatch
):
    monkeypatch.setattr("floodroute.db.migrate.LOCK_TIMEOUT", "200ms")
    write(tmp_path, {"0001_a": "create table a (x int);"})
    migrate(fresh_db, tmp_path)
    write(tmp_path, {"0002_b": "alter table a add column y int;"})
    with psycopg.connect(fresh_db) as holder:
        holder.execute("lock table a in access exclusive mode")  # held until the block ends
        with pytest.raises(MigrationError, match="lock timeout"):
            migrate(fresh_db, tmp_path)
    assert migrate(fresh_db, tmp_path) == ["0002_b.sql"]


def run_cli(url: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    if url is not None:
        env["DATABASE_URL"] = url
    cmd = [sys.executable, "-m", "floodroute.db.migrate"]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60, check=False)


def test_cli_applies_then_reports_up_to_date(fresh_db, template_db):
    first = run_cli(fresh_db)
    assert first.returncode == 0, first.stderr
    assert "applied 0001_init.sql" in first.stdout
    second = run_cli(fresh_db)
    assert second.returncode == 0 and second.stdout.strip() == "up to date"


def test_cli_fails_clearly_without_database_url():
    result = run_cli(None)
    assert result.returncode == 1
    assert "DATABASE_URL is not set" in result.stderr
