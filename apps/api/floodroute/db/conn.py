"""DATABASE_URL helper. No pooling, no ORM: callers use psycopg directly."""

import os


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError('DATABASE_URL is not set (dev: eval "$(infra/dev/pg.sh start)")')
    return url
