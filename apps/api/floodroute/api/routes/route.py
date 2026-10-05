"""Route endpoint: POST /v1/route."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

import httpx
import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb

from floodroute.api.deps import (
    RouterCallable,
    db_risk_for,
    get_db,
    get_route_config,
    get_router,
    get_score_config,
)
from floodroute.route.models import (
    Config as RouteConfig,
)
from floodroute.route.models import (
    RouteRequest,
    RouteResponse,
)
from floodroute.route.validate import plan
from floodroute.score.config import Config as ScoreConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["route"])


@router.post("/route", response_model=RouteResponse)
def compute_route(
    req: RouteRequest,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    route_cfg: Annotated[RouteConfig, Depends(get_route_config)],
    score_cfg: Annotated[ScoreConfig, Depends(get_score_config)],
    router_fn: Annotated[RouterCallable, Depends(get_router)],
) -> RouteResponse:
    """Route calculation with arrival-time validation loop."""
    now = datetime.now(UTC)
    decision_id = uuid.uuid4().hex

    def risk_for(segment_id: int, vclass: str):
        return db_risk_for(db, segment_id, vclass)

    try:
        p = plan(
            req=req,
            router=router_fn,
            risk_for=risk_for,
            now=now,
            model_version=score_cfg.model_version,
            decision_id=decision_id,
            cfg=route_cfg,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (RuntimeError, httpx.HTTPError, psycopg.Error) as e:
        raise HTTPException(status_code=502, detail=f"routing error: {e}")

    # Record decision for audit / FR-M1 privacy-safe logging
    try:
        db.execute(
            """
            insert into route_decision (
                decision_id, ts, vclass, depart_at, model_version,
                chosen, rejected, advisories, no_safe_route
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                decision_id,
                now,
                req.vclass,
                req.depart_at,
                score_cfg.model_version,
                Jsonb(p.response.routes[0].model_dump()) if p.response.routes else None,
                Jsonb([r.route.edges[0].segment_id for r in p.rejected if r.route.edges]),
                Jsonb(p.response.guidance_when_no_route.model_dump()) if p.response.guidance_when_no_route else None,
                p.response.no_safe_route,
            ),
        )
    except psycopg.Error as e:
        logger.warning("Could not record route_decision %s: %s", decision_id, e)

    return p.response
