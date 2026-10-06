"""Prometheus exposition format metrics route (TRD 13)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from floodroute.metrics.collector import METRICS

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=Response)
def get_metrics() -> Response:
    """Expose application metrics in standard Prometheus exposition text format."""
    text = METRICS.render()
    return Response(
        content=text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
