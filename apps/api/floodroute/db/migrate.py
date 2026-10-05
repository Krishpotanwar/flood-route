"""Forward-only SQL migrations: `python -m floodroute.db.migrate` (reads DATABASE_URL).

Files in ./migrations named NNNN_name.sql apply in order, one transaction per file, and are recorded in
schema_migrations with a sha256. An applied file that changed or vanished stops the run: fix forward
with a new file, never edit an old one. The first apply needs a superuser (see 0002_roles_and_audit.sql).
"""

import hashlib
import re
import sys
from pathlib import Path

import psycopg

from floodroute.db.conn import database_url

MIGRATIONS = Path(__file__).parent / "migrations"
NAME = re.compile(r"\d{4}_[a-z0-9_]+\.sql")
LOCK_ID = 7302026  # arbitrary advisory-lock key: one runner at a time
# DDL that cannot get its locks fails fast instead of queueing behind live traffic.
LOCK_TIMEOUT = "10s"


class MigrationError(RuntimeError):
    pass


def migrate(url: str, directory: Path = MIGRATIONS) -> list[str]:
    """Apply pending files in order and return their names. Altered history raises before any apply."""
    files = sorted(directory.iterdir())
    stray = [f.name for f in files if not NAME.fullmatch(f.name)]
    if stray:
        raise MigrationError(f"unexpected files in {directory}: {stray}")
    sql = {f.name: f.read_bytes() for f in files}
    digest = {name: hashlib.sha256(body).hexdigest() for name, body in sql.items()}
    applied = []
    with psycopg.connect(url, autocommit=True) as conn:
        # Waiting for another runner is fine. Waiting for table locks is not.
        conn.execute("select pg_advisory_lock(%s)", (LOCK_ID,))
        conn.execute(f"set lock_timeout = '{LOCK_TIMEOUT}'")
        conn.execute(
            "create table if not exists schema_migrations ("
            " filename text primary key, checksum text not null,"
            " applied_at timestamptz not null default now())"
        )
        done = dict(conn.execute("select filename, checksum from schema_migrations").fetchall())
        for name, checksum in sorted(done.items()):
            if name not in digest:
                raise MigrationError(f"applied migration {name} is missing from {directory}")
            if digest[name] != checksum:
                raise MigrationError(
                    f"checksum mismatch for applied migration {name}: file was edited"
                )
        pending = [name for name in sorted(sql) if name not in done]
        if pending and done and pending[0] < max(done):
            raise MigrationError(
                f"pending {pending[0]} sorts before applied {max(done)}: renumber it"
            )
        # ponytail: one transaction per file, so no CREATE INDEX CONCURRENTLY or VACUUM in a file;
        # run those by hand and record them in a later migration. No down-migrations: fix forward.
        for name in pending:
            try:
                with conn.transaction():
                    conn.execute(sql[name].decode())
                    conn.execute(
                        "insert into schema_migrations (filename, checksum) values (%s, %s)",
                        (name, digest[name]),
                    )
            except psycopg.Error as e:
                raise MigrationError(f"{name} failed and was rolled back: {e}") from e
            applied.append(name)
    return applied


def main() -> None:
    try:
        applied = migrate(database_url())
    except (RuntimeError, psycopg.Error) as e:  # MigrationError is a RuntimeError
        sys.exit(f"migrate: {e}")
    print("\n".join(f"applied {name}" for name in applied) or "up to date")


if __name__ == "__main__":
    main()
