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
from floodroute.route.explain import pick_lang, say
from floodroute.route.models import (
    Config as RouteConfig,
)
from floodroute.route.models import (
    Edge,
    RerouteRequest,
    RerouteResponse,
    Route,
    RouteRequest,
    RouteResponse,
    TripStatePayload,
)
from floodroute.route.reroute import TripState, decide, note_closed
from floodroute.route.validate import Ctx, assess, plan
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


@router.post("/route/reroute", response_model=RerouteResponse)
def compute_reroute(
    req: RerouteRequest,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    route_cfg: Annotated[RouteConfig, Depends(get_route_config)],
    score_cfg: Annotated[ScoreConfig, Depends(get_score_config)],
    router_fn: Annotated[RouterCallable, Depends(get_router)],
) -> RerouteResponse:
    """Evaluate live position tick against route conditions and propose reroutes."""
    now = req.depart_at or datetime.now(UTC)
    decision_id = uuid.uuid4().hex

    if not req.current_edges:
        raise HTTPException(
            status_code=400,
            detail="current_edges must contain at least one remaining edge",
        )

    edges = []
    for e in req.current_edges:
        geom = tuple((pt.lat, pt.lon) for pt in e.geometry) if e.geometry else ()
        edges.append(
            Edge(
                segment_id=e.segment_id,
                geometry=geom,
                travel_time_s=e.travel_time_s,
                length_m=e.length_m,
                turn_off_after=e.turn_off_after,
            )
        )
    current_route = Route(tuple(edges))

    def risk_for(segment_id: int, vclass: str):
        return db_risk_for(db, segment_id, vclass)

    ctx = Ctx(
        risk_for=risk_for,
        vclass=req.vclass,
        now=now,
        threshold=route_cfg.thresholds[req.profile],
        cfg=route_cfg,
        in_rain=True,
    )
    current_assessment = assess(current_route, ctx, now)

    state_in = req.trip_state or TripStatePayload()
    closed_at = {
        int(k): v
        for k, v in state_in.closed_at.items()
        if k.isdigit() or (k.startswith("-") and k[1:].isdigit())
    }
    st = TripState(
        last_suggestion_at=state_in.last_suggestion_at,
        baseline_band=state_in.baseline_band,
        closed_at=closed_at,
    )

    impassable_ids = [
        c.segment_id
        for c in current_assessment.checks
        if c.segment_id is not None and c.state == "impassable"
    ]
    st = note_closed(st, impassable_ids, now)

    candidate_request = RouteRequest(
        origin=req.origin,
        destination=req.destination,
        vclass=req.vclass,
        depart_at=now,
        profile=req.profile,
        lang=req.lang,
    )
    try:
        p = plan(
            req=candidate_request,
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

    decision = decide(st, current_assessment, p.accepted, now, cfg=route_cfg)

    lang = pick_lang(req.lang)
    rendered_reasons = [say(r, lang) for r in decision.reasons]

    suggested_route = None
    if decision.action == "suggest" and p.response.routes:
        suggested_route = p.response.routes[0]

    updated_closed_at = {str(k): v for k, v in decision.state.closed_at.items()}
    updated_state = TripStatePayload(
        last_suggestion_at=decision.state.last_suggestion_at,
        baseline_band=decision.state.baseline_band,
        closed_at=updated_closed_at,
    )

    return RerouteResponse(
        decision_id=decision_id,
        action=decision.action,
        code=decision.code,
        warn=decision.warn,
        reasons=rendered_reasons,
        reason_keys=list(decision.reasons),
        trip_state=updated_state,
        suggested_route=suggested_route,
        current_worst_state=current_assessment.worst_state,
        current_worst_band=current_assessment.worst_band,
        current_violations_count=len(current_assessment.violations),
        lang=lang,
    )
