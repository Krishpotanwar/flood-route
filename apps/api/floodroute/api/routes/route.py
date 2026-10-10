"""Route endpoint: POST /v1/route."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from psycopg.types.json import Jsonb

from floodroute.api.auth import authorize_route_profile
from floodroute.api.deps import (
    RouterCallable,
    db_risk_for,
    get_db,
    get_route_config,
    get_router,
    get_score_config,
)
from floodroute.inventory import get_city_id_for_point
from floodroute.route.explain import pick_lang, say
from floodroute.route.models import (
    Config as RouteConfig,
)
from floodroute.route.models import (
    Edge,
    Guidance,
    RerouteRequest,
    RerouteResponse,
    Route,
    RouteRequest,
    RouteResponse,
    TripStatePayload,
)
from floodroute.route.reroute import TripState, decide, note_closed
from floodroute.route.validate import Ctx, assess, plan
from floodroute.route.watch import (
    WatchRequest,
    WatchResponse,
    cancel_route_watch,
    create_route_watch,
    get_route_watch,
)
from floodroute.safety.kill_switch import get_active_kill_switch
from floodroute.score.config import Config as ScoreConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["route"])


def _route_city_ids(req: RouteRequest | RerouteRequest) -> set[int]:
    """City ids touched by the request endpoints, for city-scoped freeze checks."""
    ids = set()
    for pt in (req.origin, req.destination):
        cid = get_city_id_for_point(pt.lat, pt.lon)
        if cid is not None:
            ids.add(cid)
    return ids


def _rejected_segment_ids(p) -> list[int]:
    """Every violating segment id across all rejected routes (audit needs all,
    not just the first edge, to replay which water blocked each option)."""
    ids: list[int] = []
    for assessment in p.rejected:
        for edge_idx in assessment.violations:
            sid = assessment.checks[edge_idx].segment_id
            if sid is not None and sid not in ids:
                ids.append(sid)
    return ids


def _record_route_decision(
    db: psycopg.Connection,
    decision_id: str,
    now: datetime,
    vclass: str,
    depart_at: datetime | None,
    model_version: str,
    chosen: Any | None,
    rejected: list[int],
    advisories: Any | None,
    no_safe_route: bool,
) -> None:
    """Best-effort audit write shared by /route and /reroute."""
    # Retain segment decisions for watches/replay, not the caller's precise
    # journey geometry. No origin/destination coordinates enter this audit.
    if isinstance(chosen, dict):
        chosen = {key: value for key, value in chosen.items() if key != "geometry"}
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
                vclass,
                depart_at,
                model_version,
                Jsonb(chosen) if chosen is not None else None,
                Jsonb(rejected),
                Jsonb(advisories) if advisories is not None else None,
                no_safe_route,
            ),
        )
    except psycopg.Error as e:
        logger.warning("Could not record route_decision %s: %s", decision_id, e)


def _frozen_route_response(
    decision_id: str, req: RouteRequest, model_version: str
) -> RouteResponse:
    """Deterministic advisory_off answer when routing is frozen: no router call."""
    lang = pick_lang(req.lang)
    return RouteResponse(
        decision_id=decision_id,
        model_version=model_version,
        no_safe_route=True,
        valid_until=None,
        routes=[],
        guidance_when_no_route=Guidance(
            keys=["advisory_off"],
            text=[say("advisory_off", lang)],
            actions=[],
        ),
        lang=lang,
    )


def _active_freeze(db: psycopg.Connection, req: RouteRequest | RerouteRequest):
    """Global freeze, else the city freeze of either endpoint city.

    Tenant identity is not available on these endpoints yet (handoff: API auth
    batch), so tenant-scoped freezes still need that plumbing to take effect.
    """
    hit = get_active_kill_switch(db)
    if hit is not None:
        return hit
    for cid in _route_city_ids(req):
        hit = get_active_kill_switch(db, city_id=cid)
        if hit is not None:
            return hit
    return None


@router.post("/route", response_model=RouteResponse)
def compute_route(
    req: RouteRequest,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    route_cfg: Annotated[RouteConfig, Depends(get_route_config)],
    score_cfg: Annotated[ScoreConfig, Depends(get_score_config)],
    router_fn: Annotated[RouterCallable, Depends(get_router)],
    authorization: Annotated[str | None, Header()] = None,
) -> RouteResponse:
    """Route calculation with arrival-time validation loop."""
    authorize_route_profile(req.profile, authorization)
    now = datetime.now(UTC)
    decision_id = uuid.uuid4().hex

    # Safety Case: freeze short-circuits before any external routing call, so
    # a frozen advisory never waits on (or 502s from) the router (TRD 16).
    if _active_freeze(db, req) is not None:
        frozen = _frozen_route_response(decision_id, req, score_cfg.model_version)
        _record_route_decision(
            db,
            decision_id,
            now,
            req.vclass,
            req.depart_at,
            score_cfg.model_version,
            None,
            [],
            frozen.guidance_when_no_route.model_dump() if frozen.guidance_when_no_route else None,
            frozen.no_safe_route,
        )
        return frozen

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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (RuntimeError, httpx.HTTPError, psycopg.Error) as e:
        logger.warning("Routing failure for decision %s: %s", decision_id, e)
        raise HTTPException(status_code=502, detail="routing temporarily unavailable") from e

    # Safety Case: a freeze engaged mid-computation still stamps the answer.
    active_kill = _active_freeze(db, req)
    if active_kill:
        frozen = _frozen_route_response(decision_id, req, score_cfg.model_version)
        _record_route_decision(
            db,
            decision_id,
            now,
            req.vclass,
            req.depart_at,
            score_cfg.model_version,
            None,
            [],
            frozen.guidance_when_no_route.model_dump(),
            True,
        )
        return frozen

    # Record decision for audit / FR-M1 privacy-safe logging
    _record_route_decision(
        db,
        decision_id,
        now,
        req.vclass,
        req.depart_at,
        score_cfg.model_version,
        p.response.routes[0].model_dump() if p.response.routes else None,
        _rejected_segment_ids(p),
        p.response.guidance_when_no_route.model_dump()
        if p.response.guidance_when_no_route
        else None,
        p.response.no_safe_route,
    )

    return p.response


def _frozen_reroute_response(
    decision_id: str,
    req: RerouteRequest,
    db: psycopg.Connection,
    now: datetime,
    model_version: str,
) -> RerouteResponse:
    _record_route_decision(
        db,
        decision_id,
        now,
        req.vclass,
        req.depart_at or now,
        model_version,
        None,
        [],
        {"keys": ["advisory_off"]},
        True,
    )
    return RerouteResponse(
        decision_id=decision_id,
        action="keep",
        code="advisory_off",
        warn=True,
        reasons=["Emergency advisory freeze active. Follow on-ground traffic directions."],
        reason_keys=["advisory_off"],
        trip_state=req.trip_state or TripStatePayload(),
        suggested_route=None,
        current_worst_state="unknown",
        lang=pick_lang(req.lang),
    )


@router.post("/route/reroute", response_model=RerouteResponse)
def compute_reroute(
    req: RerouteRequest,
    db: Annotated[psycopg.Connection, Depends(get_db)],
    route_cfg: Annotated[RouteConfig, Depends(get_route_config)],
    score_cfg: Annotated[ScoreConfig, Depends(get_score_config)],
    router_fn: Annotated[RouterCallable, Depends(get_router)],
    authorization: Annotated[str | None, Header()] = None,
) -> RerouteResponse:
    """Evaluate live position tick against route conditions and propose reroutes."""
    authorize_route_profile(req.profile, authorization)
    now = req.depart_at or datetime.now(UTC)
    decision_id = uuid.uuid4().hex

    # Safety Case: check emergency kill switch freeze (TRD 16); same scoping note as /route.
    active_kill = _active_freeze(db, req)
    if active_kill:
        return _frozen_reroute_response(
            decision_id,
            req,
            db,
            now,
            score_cfg.model_version,
        )

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
    try:
        current_assessment = assess(current_route, ctx, now)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except (RuntimeError, httpx.HTTPError, psycopg.Error) as e:
        logger.warning("Reroute assessment failure for decision %s: %s", decision_id, e)
        raise HTTPException(status_code=502, detail="routing temporarily unavailable") from None

    state_in = req.trip_state or TripStatePayload()
    try:
        closed_at = {int(k): v for k, v in state_in.closed_at.items()}
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="trip_state.closed_at keys must be integer segment ids",
        ) from None
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
    st = note_closed(st, impassable_ids, now, cfg=route_cfg)

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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (RuntimeError, httpx.HTTPError, psycopg.Error) as e:
        logger.warning("Reroute failure for decision %s: %s", decision_id, e)
        raise HTTPException(status_code=502, detail="routing temporarily unavailable") from e

    if _active_freeze(db, req) is not None:
        return _frozen_reroute_response(
            decision_id,
            req,
            db,
            now,
            score_cfg.model_version,
        )

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

    # Persist the reroute decision on the same audit path as /route: the
    # rejected list carries the currently violating segment ids.
    _record_route_decision(
        db,
        decision_id,
        now,
        req.vclass,
        req.depart_at or now,
        score_cfg.model_version,
        suggested_route.model_dump() if suggested_route else None,
        [
            c.segment_id
            for c in current_assessment.checks
            if c.violation and c.segment_id is not None
        ],
        None,
        False,
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


@router.post("/routes/{decision_id}/watch", response_model=WatchResponse)
@router.post("/route/{decision_id}/watch", response_model=WatchResponse)
def watch_route_endpoint(
    decision_id: uuid.UUID,
    req: WatchRequest,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> WatchResponse:
    """Subscribe to material risk change alerts for a planned route."""
    # A global freeze suspends new watch promises (alerts cannot be trusted
    # while advisories are off). City scoping needs segment-city mapping that
    # does not exist at this endpoint yet; parked with tenant plumbing.
    if get_active_kill_switch(db) is not None:
        raise HTTPException(
            status_code=503,
            detail="Emergency advisory freeze active. Watch subscriptions are suspended until operators lift the freeze.",
        )
    try:
        return create_route_watch(db, decision_id, req)
    except ValueError as e:
        err_msg = str(e)
        if "not found" in err_msg.lower():
            raise HTTPException(status_code=404, detail=err_msg) from e
        raise HTTPException(status_code=400, detail=err_msg) from e


@router.get("/routes/{decision_id}/watch", response_model=WatchResponse)
@router.get("/route/{decision_id}/watch", response_model=WatchResponse)
def get_route_watch_endpoint(
    decision_id: uuid.UUID,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> WatchResponse:
    """Check active watch subscription status for a route decision."""
    watch = get_route_watch(db, decision_id)
    if not watch:
        raise HTTPException(
            status_code=404, detail=f"No active watch found for route {decision_id}"
        )
    return watch


@router.delete("/routes/{decision_id}/watch")
@router.delete("/route/{decision_id}/watch")
def cancel_route_watch_endpoint(
    decision_id: uuid.UUID,
    db: Annotated[psycopg.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Unsubscribe and cancel active watch subscription for a route decision."""
    cancelled = cancel_route_watch(db, decision_id)
    if not cancelled:
        raise HTTPException(
            status_code=404, detail=f"No active watch found for route {decision_id}"
        )
    return {"decision_id": str(decision_id), "cancelled": True}
