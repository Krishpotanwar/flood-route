#!/usr/bin/env bash
# Local PostgreSQL 16 + PostGIS for development and tests: initdb cluster, loopback TCP only.
#   infra/dev/pg.sh start|stop|status|reset|url
# DEV ONLY: trust auth and fsync=off. Never reuse these settings where real data lives.
# Needs PG16 server binaries and PostGIS (Debian/Ubuntu: apt-get install postgresql-16-postgis-3).
# Env: FLOODROUTE_PG_DIR (default /tmp/floodroute-pg), FLOODROUTE_PG_PORT (54329),
#      FLOODROUTE_PG_DB (floodroute), FLOODROUTE_PG_BIN (dir with initdb, pg_ctl, psql).
set -euo pipefail

dir=${FLOODROUTE_PG_DIR:-/tmp/floodroute-pg}
port=${FLOODROUTE_PG_PORT:-54329}
db=${FLOODROUTE_PG_DB:-floodroute}
bin=${FLOODROUTE_PG_BIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}
[ -x "$bin/pg_ctl" ] || { echo "no PostgreSQL server binaries; set FLOODROUTE_PG_BIN" >&2; exit 2; }

# Postgres refuses to run as root; in a root container run it as the postgres OS user.
if [ "$(id -u)" = 0 ]; then
  as() { runuser -u postgres -- "$@"; }
  install -d -o postgres -g postgres -m 700 "$dir"
else
  as() { "$@"; }
  install -d -m 700 "$dir"
fi

host=127.0.0.1
admin_url="postgresql://postgres@$host:$port/postgres"
db_url="postgresql://postgres@$host:$port/$db"
sql() { as "$bin/psql" -X -h "$host" -p "$port" -U postgres -d "${2:-postgres}" -Atqc "$1"; }
running() { as "$bin/pg_ctl" -D "$dir/data" status >/dev/null 2>&1; }

urls() {
  echo "export DATABASE_URL=$db_url"
  echo "export DATABASE_URL_ADMIN=$admin_url"
}

start() {
  [ -f "$dir/data/PG_VERSION" ] || as "$bin/initdb" -D "$dir/data" -U postgres -A trust -E UTF8 --no-locale >/dev/null
  running || as "$bin/pg_ctl" -D "$dir/data" -l "$dir/pg.log" -w \
    -o "-p $port -c listen_addresses=$host -c unix_socket_directories= -c fsync=off" start >/dev/null
  [ "$(sql "select 1 from pg_database where datname = '$db'")" = 1 ] || sql "create database \"$db\""
  [ "$(sql "select count(*) from pg_available_extensions where name = 'postgis'")" = 1 ] \
    || echo "WARNING: PostGIS is not installed on this server; migrations will fail" >&2
  urls
}

case "${1:-}" in
  start) start ;;
  stop) ! running || as "$bin/pg_ctl" -D "$dir/data" -m fast -w stop >/dev/null ;;
  status) running && { echo "running on $host:$port"; urls; } || { echo "not running"; exit 3; } ;;
  # reset drops only the dev database, so throwaway test databases on the same server survive.
  reset) start >/dev/null; sql "drop database if exists \"$db\" with (force)"; sql "create database \"$db\""; urls ;;
  url) urls ;;
  *) echo "usage: $0 start|stop|status|reset|url" >&2; exit 2 ;;
esac
