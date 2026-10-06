"""API endpoints for offline and CDN road closure snapshots (TRD 11)."""

from __future__ import annotations

from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from floodroute.api.deps import get_db
from floodroute.feed.snapshot import (
    generate_city_closure_snapshot,
    list_snapshot_status,
    load_city_closure_snapshot,
)
from floodroute.inventory import CITIES

router = APIRouter(prefix="/v1/feed/snapshot", tags=["snapshot"])


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

    # 1. Check disk cache
    snapshot = load_city_closure_snapshot(norm, vclass=vclass)
    if not snapshot:
        # Generate on demand if cache miss
        snapshot = generate_city_closure_snapshot(db, city_name=norm, vclass=vclass)

    etag = snapshot.get("etag", "")

    # 2. Conditional GET validation
    if if_none_match and if_none_match.strip() == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={
                "ETag": etag,
                "Cache-Control": "public, max-age=120, stale-while-revalidate=300",
            },
        )

    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=120, stale-while-revalidate=300",
        "X-Conditions-As-Of": snapshot.get("conditions_as_of", ""),
    }
    return JSONResponse(content=snapshot, headers=headers)


@router.post("/generate", status_code=status.HTTP_201_CREATED)
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
