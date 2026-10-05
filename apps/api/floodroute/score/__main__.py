"""CLI: python -m floodroute.score {replay,backtest} ..."""

from __future__ import annotations

import argparse
import sys

from .backtest import run_db_backtest, seed_benchmark_events
from .config import DEFAULT_PATH, load_config
from .replay import dumps, replay


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m floodroute.score")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("replay", help="replay a JSONL event log, one JSON line per tick")
    r.add_argument("file", help="JSONL event log (see floodroute/score/replay.py)")
    r.add_argument("--config", default=str(DEFAULT_PATH), help="scoring config JSON")

    b = sub.add_parser("backtest", help="run backtest against observed ground-truth events")
    b.add_argument("--city-id", type=int, default=1, help="City ID (default: 1)")
    b.add_argument("--vclass", default="car", help="Vehicle class (default: car)")
    b.add_argument("--horizon", type=int, default=0, help="Forecast horizon (min, default: 0)")
    b.add_argument("--threshold", type=float, default=0.30, help="Probability threshold (default: 0.30)")
    b.add_argument("--seed-benchmark", action="store_true", help="Seed benchmark historical events")
    b.add_argument(
        "--db-url",
        default="postgresql://postgres:postgres@localhost:54329/floodroute",
        help="PostgreSQL connection URL",
    )

    args = ap.parse_args(argv)
    if args.cmd == "replay":
        try:
            cfg = load_config(args.config)
            with open(args.file, encoding="utf-8") as f:
                for tick in replay(f, cfg):
                    print(dumps(tick))
        except (ValueError, OSError) as e:
            sys.exit(f"error: {e}")
    elif args.cmd == "backtest":
        import psycopg

        with psycopg.connect(args.db_url) as conn:
            if args.seed_benchmark:
                n = seed_benchmark_events(conn)
                print(f"Seeded {n} benchmark events.")
            rep = run_db_backtest(
                conn,
                city_id=args.city_id,
                vclass=args.vclass,
                horizon_min=args.horizon,
                p_threshold=args.threshold,
            )
            print("Backtest results:")
            print(rep["metrics"])


if __name__ == "__main__":
    main()
