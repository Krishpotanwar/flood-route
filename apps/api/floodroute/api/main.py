"""FastAPI application entrypoint for FloodRoute."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from floodroute.api.body_limit import RequestBodyLimit
from floodroute.api.routes import (
    bot,
    cities,
    feed,
    health,
    metrics,
    overrides,
    reports,
    risk,
    route,
    safety,
    snapshot,
    webhooks,
)
from floodroute.metrics.middleware import PrometheusMetricsMiddleware


def create_app() -> FastAPI:
    """Create and configure the FloodRoute FastAPI application."""
    app = FastAPI(
        title="FloodRoute API",
        version="0.0.1",
        description="Provides flood-aware road conditions and routing advisories.",
        openapi_url="/openapi.json",
        docs_url="/docs",
    )

    app.add_middleware(PrometheusMetricsMiddleware)
    app.add_middleware(RequestBodyLimit)
    # The console and PWA are served same-origin; public feeds need no
    # credentials. Origins come from the environment so control-room POSTs
    # are never exposed to an allow-all credentialed policy.
    cors_origins = [
        o.strip()
        for o in os.environ.get("FLOODROUTE_CORS_ORIGINS", "https://floodroute.in").split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "If-None-Match", "X-FloodRoute-Co-Signature"],
    )

    app.include_router(health.router)
    app.include_router(risk.router)
    app.include_router(route.router)
    app.include_router(reports.router)
    app.include_router(overrides.router)
    app.include_router(feed.router)
    app.include_router(webhooks.router)
    app.include_router(bot.router)
    app.include_router(cities.router)
    app.include_router(snapshot.router)
    app.include_router(metrics.router)
    app.include_router(safety.router)



    # Static assets and Situation Board Console
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        @app.get("/console", include_in_schema=False)
        def get_console() -> FileResponse:
            return FileResponse(static_dir / "console.html")

    # Citizen Mobile PWA
    citizen_dist = Path(__file__).resolve().parents[3] / "citizen" / "dist"
    if citizen_dist.exists() and (citizen_dist / "index.html").exists():
        app.mount("/app", StaticFiles(directory=str(citizen_dist), html=True), name="citizen_app")

    return app


app = create_app()
