"""FastAPI application entrypoint for FloodRoute."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from floodroute.api.routes import feed, health, overrides, reports, risk, route


def create_app() -> FastAPI:
    """Create and configure the FloodRoute FastAPI application."""
    app = FastAPI(
        title="FloodRoute API",
        version="0.0.1",
        description="Predicts unusable roads in heavy rain and safely routes vehicles.",
        openapi_url="/openapi.json",
        docs_url="/docs",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(risk.router)
    app.include_router(route.router)
    app.include_router(reports.router)
    app.include_router(overrides.router)
    app.include_router(feed.router)

    return app


app = create_app()
