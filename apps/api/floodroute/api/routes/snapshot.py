"""API endpoints for offline and CDN road closure snapshots (TRD 11)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from floodroute.api.auth import require_operator
from floodroute.api.deps import get_db
from floodroute.feed.snapshot import (
    SNAPSHOT_STALE_S,
    generate_city_closure_snapshot,
    list_snapshot_status,
    load_city_closure_snapshot,
)
from floodroute.inventory import CITIES, CITY_IDS
from floodroute.safety.kill_switch import get_active_kill_switch
from floodroute.score.db import SUPPORTED_VCLASSES

router = APIRouter(prefix="/v1/feed/snapshot", tags=["snapshot"])

VALID_VCLASSES = SUPPORTED_VCLASSES
# Serve budget: max-age + stale-while-revalidate stays within the 300 s staleness bound.
CACHE_CONTROL = "public, max-age=120, stale-while-revalidate=180"

logger = logging.getLogger(__name__)


def _reject_when_frozen(db: psycopg.Connection, city_norm: str) -> None:
    """Global freeze, else the freeze of the requested city, suspends serving."""
    if get_active_kill_switch(db) is not None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Emergency advisory freeze active. Snapshots are suspended until operators lift the freeze.",
        )
    city_id = CITY_IDS.get(city_norm)
    if city_id is not None and get_active_kill_switch(db, city_id=city_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Emergency advisory freeze active for this city. Snapshots are suspended until operators lift the freeze.",
        )


def _snapshot_headers(snapshot: dict[str, Any]) -> dict[str, str]:
    headers = {
        "ETag": snapshot.get("etag", ""),
        "Cache-Control": CACHE_CONTROL,
        "X-Conditions-As-Of": snapshot.get("conditions_as_of", ""),
    }
    if snapshot.get("stale"):
        headers["X-Snapshot-Stale"] = "true"
    return headers


@router.get("/closures")
def get_closure_snapshot(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    city: str = Query("bengaluru", description="City identifier"),
    vclass: str = Query("car", description="Vehicle classification profile"),
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    """Retrieve CDN-cacheable offline road closures snapshot for a city."""
    norm = city.strip().lower()
    if norm not in CITIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"City '{city}' not supported.",
        )
    if vclass not in VALID_VCLASSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="vclass must be one of two_wheeler, car, ambulance, heavy",
        )
    _reject_when_frozen(db, norm)

    # 1. Check disk cache
    snapshot = load_city_closure_snapshot(norm, vclass=vclass)
    if not snapshot:
        # Generate on demand if cache miss
        snapshot = generate_city_closure_snapshot(db, city_name=norm, vclass=vclass)
    else:
        # Never serve an old file as fresh: past the staleness bound, try to
        # regenerate; on failure keep the file but flag it stale.
        try:
            age_s = (
                datetime.now(UTC) - datetime.fromisoformat(snapshot["generated_at"])
            ).total_seconds()
        except (KeyError, ValueError, TypeError):
            age_s = SNAPSHOT_STALE_S + 1
        if not 0 <= age_s <= SNAPSHOT_STALE_S:
            try:
                snapshot = generate_city_closure_snapshot(db, city_name=norm, vclass=vclass)
            except Exception as e:  # noqa: BLE001 - serve stale, flagged, instead of 500
                logger.warning("Snapshot regen failed for %s/%s: %s", norm, vclass, e)
                snapshot = {**snapshot, "stale": True}
                content = {k: v for k, v in snapshot.items() if k not in ("etag", "generated_at")}
                digest = hashlib.sha256(
                    json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                snapshot["etag"] = f'"{digest[:16]}"'

    etag = snapshot.get("etag", "")

    # 2. Conditional GET validation
    if if_none_match and if_none_match.strip() == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=_snapshot_headers(snapshot),
        )

    return JSONResponse(content=snapshot, headers=_snapshot_headers(snapshot))


@router.post(
    "/generate", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_operator)]
)
def trigger_snapshot_generation(
    db: Annotated[psycopg.Connection, Depends(get_db)],
    city: str = Query("bengaluru", description="City identifier"),
    vclass: str = Query("car", description="Vehicle classification profile"),
) -> dict[str, Any]:
    """Manually regenerate offline snapshot for a city and vehicle class."""
    norm = city.strip().lower()
    if norm not in CITIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"City '{city}' not supported.",
        )
    if vclass not in VALID_VCLASSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="vclass must be one of two_wheeler, car, ambulance, heavy",
        )
    _reject_when_frozen(db, norm)

    snapshot = generate_city_closure_snapshot(db, city_name=norm, vclass=vclass)
    return {
        "city": norm,
        "vclass": vclass,
        "generated": True,
        "etag": snapshot["etag"],
        "feature_count": snapshot["feature_count"],
        "generated_at": snapshot["generated_at"],
    }


@router.get("/status")
def get_snapshots_status() -> list[dict[str, Any]]:
    """Inspect age and freshness across all pre-generated offline CDN snapshots."""
    return list_snapshot_status()
