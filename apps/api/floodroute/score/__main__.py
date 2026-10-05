"""CLI: python -m floodroute.score replay FILE [--config PATH]"""

from __future__ import annotations

import argparse
import sys

from .config import DEFAULT_PATH, load_config
from .replay import dumps, replay


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m floodroute.score")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="replay a JSONL event log, one JSON line per tick")
    r.add_argument("file", help="JSONL event log (see floodroute/score/replay.py)")
    r.add_argument("--config", default=str(DEFAULT_PATH), help="scoring config JSON")
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
        with open(args.file, encoding="utf-8") as f:
            for tick in replay(f, cfg):
                print(dumps(tick))
    except (ValueError, OSError) as e:  # ConfigError is a ValueError
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
