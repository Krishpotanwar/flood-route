"""Shared fixtures. Database fixtures need PostgreSQL 16 with PostGIS: `infra/dev/pg.sh start`.

DATABASE_URL_ADMIN points at a superuser on the server (default: the pg.sh cluster). Without a
reachable server the database tests skip with the reason. CI sets FLOODROUTE_REQUIRE_DB=1 so that a
missing database fails the run instead of skipping it.
"""

import contextlib
import os
import uuid

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from floodroute.db.migrate import migrate

os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "test-only-verify-token-not-a-secret")
os.environ.setdefault("WHATSAPP_APP_SECRET", "test-only-app-secret-not-a-secret")

ADMIN_URL = os.environ.get("DATABASE_URL_ADMIN", "postgresql://postgres@127.0.0.1:54329/postgres")


def unavailable(reason: str):
    if os.environ.get("FLOODROUTE_REQUIRE_DB"):
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def conninfo(dbname: str, **kw: str) -> str:
    return make_conninfo(ADMIN_URL, dbname=dbname, **kw)


@pytest.fixture(scope="session")
def pg_admin():
    """Superuser autocommit connection to the server (postgres database)."""
    try:
        conn = psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as e:
        why = " ".join(str(e).split())  # libpq errors span several lines
        unavailable(f"no PostgreSQL at DATABASE_URL_ADMIN ({why}); run infra/dev/pg.sh start")
    with conn:
        yield conn


@contextlib.contextmanager
def _database(pg_admin, template: str | None = None):
    name = f"fr_test_{uuid.uuid4().hex[:12]}"
    pg_admin.execute(f'create database "{name}"' + (f' template "{template}"' if template else ""))
    try:
        yield name
    finally:
        pg_admin.execute(f'drop database "{name}" with (force)')


@pytest.fixture
def fresh_db(pg_admin):
    """Conninfo of an empty throwaway database, dropped afterwards."""
    with _database(pg_admin) as name:
        yield conninfo(name)


@pytest.fixture(scope="session")
def template_db(pg_admin):
    """Name of a database with every migration applied. `db_url` clones it."""
    if not pg_admin.execute(
        "select 1 from pg_available_extensions where name = 'postgis'"
    ).fetchone():
        unavailable(
            "PostGIS is not installed on the test server: apt-get install postgresql-16-postgis-3"
        )
    with _database(pg_admin) as name:
        migrate(conninfo(name))
        yield name


@pytest.fixture
def db_url(pg_admin, template_db):
    """Conninfo of a throwaway database cloned from the fully migrated template."""
    with _database(pg_admin, template_db) as name:
        yield conninfo(name)


@pytest.fixture
def db(db_url):
    """Superuser autocommit connection to a fully migrated throwaway database."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        yield conn


@pytest.fixture
def app_db(db_url):
    """Connection to the same database acting as floodroute_app (DML only)."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute("set role floodroute_app")
        yield conn
