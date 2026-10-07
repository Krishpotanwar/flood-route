"""FastAPI telemetry middleware recording Prometheus metrics (TRD 13)."""

from __future__ import annotations

import re
import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from floodroute.metrics.collector import METRICS


def sanitize_path(path: str) -> str:
    """Normalize dynamic URL segments into parameterized metrics labels."""
    # Replace UUIDs
    p = re.sub(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        "{id}",
        path,
    )
    # Replace numeric IDs
    p = re.sub(r"/\d+(?=/|$)", "/{id}", p)
    # Collapse open-ended string segments that would each mint a series.
    p = re.sub(r"^/v1/cities/[^/]+", "/v1/cities/{city}", p)
    p = re.sub(r"^/v1/cities/\{city\}/[^/]+", "/v1/cities/{city}/{op}", p)
    p = re.sub(r"^/v1/reports/photo/[^/]+", "/v1/reports/photo/{id}", p)
    return (p or "/")[:128]


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Measures request duration and outcome counts per endpoint."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics endpoint itself to prevent skewing
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        endpoint = sanitize_path(request.url.path)
        method = request.method
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            labels = {"endpoint": endpoint, "method": method, "status": str(status_code)}
            METRICS.requests_total.inc(labels=labels)
            METRICS.request_duration_seconds.observe(duration, labels={"endpoint": endpoint, "method": method})
