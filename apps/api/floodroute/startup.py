"""Automated startup orchestrator for container boot (migrations, inventory seeding, snapshot priming).

Executes before the ASGI server starts (e.g. on Render):
1. Applies pending forward-only SQL migrations (floodroute.db.migrate).
2. Seeds road network inventory for Bengaluru if empty (floodroute.inventory.seed).
3. Primes initial offline/CDN closure snapshots for supported cities (floodroute.feed.snapshot).
4. Checks operator token configuration diagnostics and logs readiness.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

import psycopg

from floodroute.db.conn import database_url
from floodroute.db.migrate import migrate
from floodroute.feed.snapshot import generate_city_closure_snapshot
from floodroute.inventory import CITIES
from floodroute.inventory.seed import seed_inventory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("floodroute.startup")


def run_startup(db_url: str | None = None) -> dict[str, Any]:
    """Run all pre-server initialization steps idempotently."""
    url = (db_url or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        url = database_url()

    # Step 1: Apply forward-only SQL migrations
    logger.info("Checking database migrations...")
    applied = migrate(url)
    if applied:
        logger.info("Applied %d migration(s): %s", len(applied), ", ".join(applied))
    else:
        logger.info("Database schema is up to date.")

    # Step 2: Seed road inventory if empty
    logger.info("Checking road network inventory...")
    with psycopg.connect(url) as conn:
        seed_stats = seed_inventory(conn, city="bengaluru", if_empty=True)
        inserted = getattr(seed_stats, "inserted_segments", 0)
        total = getattr(seed_stats, "total_candidates", 0)
        if isinstance(inserted, int) and inserted > 0:
            logger.info(
                "Seeded Bengaluru inventory: %d segments, %d static records, %d matched hotspots.",
                seed_stats.inserted_segments,
                getattr(seed_stats, "inserted_static", 0),
                getattr(seed_stats, "matched_hotspots", 0),
            )
        else:
            logger.info(
                "Bengaluru inventory already populated (%d segments present); skipping.",
                total if isinstance(total, int) else 0,
            )

        # Step 3: Prime offline closure snapshots
        logger.info("Priming offline closure snapshots...")
        snapshot_errors = 0
        for city in CITIES:
            try:
                generate_city_closure_snapshot(conn, city_name=city, vclass="car")
                logger.info("Primed closure snapshot for %s (vclass=car).", city)
            except (psycopg.Error, OSError, RuntimeError, ValueError, KeyError) as e:
                snapshot_errors += 1
                logger.warning("Failed to prime snapshot for %s: %s", city, e)

    # Step 4: Operator token diagnostic check
    tokens_raw = os.environ.get("FLOODROUTE_OPERATOR_TOKENS", "").strip()
    tokens_configured = False
    token_count = 0
    if tokens_raw:
        try:
            tokens = json.loads(tokens_raw)
            if isinstance(tokens, dict) and tokens:
                tokens_configured = True
                token_count = len(tokens)
                logger.info("Operator tokens configured: %d active operator(s).", token_count)
            else:
                logger.warning("FLOODROUTE_OPERATOR_TOKENS is set but not a non-empty JSON map.")
        except json.JSONDecodeError as e:
            logger.warning("FLOODROUTE_OPERATOR_TOKENS contains invalid JSON: %s", e)
    else:
        logger.info(
            "FLOODROUTE_OPERATOR_TOKENS not set. Operator console disabled (503); citizen endpoints active."
        )

    return {
        "migrations_applied": applied,
        "seed_stats": seed_stats,
        "snapshot_errors": snapshot_errors,
        "operator_tokens_configured": tokens_configured,
        "operator_token_count": token_count,
    }


def main() -> None:
    """CLI entrypoint for container startup."""
    try:
        run_startup()
    except Exception:
        logger.exception("Startup orchestration failed")
        sys.exit(1)
    logger.info("Startup orchestration complete; launching API server.")


if __name__ == "__main__":
    main()
