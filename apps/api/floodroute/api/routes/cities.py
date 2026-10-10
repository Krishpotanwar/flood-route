"""API endpoints for multi-city deployment catalog and municipal hotspots."""

from __future__ import annotations

from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from floodroute.api.auth import require_operator
from floodroute.api.deps import get_db
from floodroute.inventory.multicity import (
    get_city_metadata,
    list_supported_cities,
    load_city_hotspots,
    seed_city_hotspots_into_db,
)

router = APIRouter(prefix="/v1/cities", tags=["cities"])


@router.get("")
def list_cities() -> list[dict[str, Any]]:
    """List all deployed and supported municipal jurisdictions."""
    return [c.to_dict() for c in list_supported_cities()]


@router.get("/{city}")
def get_city_details(city: str) -> dict[str, Any]:
    """Retrieve municipal metadata and operational parameters for a specific city."""
    try:
        c = get_city_metadata(city)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"City '{city}' is not supported.",
        ) from None

    return c.to_dict()


@router.get("/{city}/hotspots")
def get_city_hotspots(
    city: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Query verified municipal waterlogging hotspots for a given city."""
    try:
        meta = get_city_metadata(city)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"City '{city}' is not supported.",
        ) from None

    all_spots = load_city_hotspots(city)
    paged = all_spots[offset : offset + limit]

    return {
        "city": meta.name,
        "city_id": meta.city_id,
        "total_hotspots": len(all_spots),
        "offset": offset,
        "limit": limit,
        "hotspots": paged,
    }


@router.post(
    "/{city}/seed",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
def seed_city(
    city: str,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Seed municipal zone and road network segments for a given city into PostGIS."""
    try:
        get_city_metadata(city)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"City '{city}' is not supported.",
        ) from None

    stats = seed_city_hotspots_into_db(db, city)
    return {
        "city": city,
        "seeded": True,
        **stats,
    }
