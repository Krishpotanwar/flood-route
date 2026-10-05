"""python -m floodroute.ingest <adapter> [--once]. Reads DATABASE_URL. Exit code 1 if the run failed.

--once runs a single pass and exits (what cron or a Kubernetes CronJob calls). Without it the adapter
loops at its own cadence, which is a dev convenience: there is no scheduler in production (TRD section 3).
"""

import argparse
import sys
import time

import psycopg

from floodroute.db.conn import database_url
from floodroute.ingest import metno, sachet
from floodroute.ingest.common import Http, run

ADAPTERS = {"sachet": sachet, "metno": metno}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m floodroute.ingest", description=__doc__)
    ap.add_argument("adapter", choices=sorted(ADAPTERS))
    ap.add_argument("--once", action="store_true", help="run one pass and exit")
    args = ap.parse_args(argv)
    adapter = ADAPTERS[args.adapter]
    try:
        conn = psycopg.connect(database_url(), autocommit=True)
    except (RuntimeError, psycopg.Error) as e:
        print(f"ingest: {e}", file=sys.stderr)
        return 1
    http = Http(adapter.HOSTS)
    try:
        while True:
            code = run(conn, adapter.SOURCE, lambda c: adapter.ingest(c, http))
            if args.once:
                return code
            time.sleep(adapter.INTERVAL_S)
    except KeyboardInterrupt:
        return 0
    finally:
        http.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
