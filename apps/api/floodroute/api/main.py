"""FastAPI application entrypoint for FloodRoute."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from floodroute.api.routes import (
    bot,
    cities,
    feed,
    health,
    overrides,
    reports,
    risk,
    route,
    webhooks,
)


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
    app.include_router(webhooks.router)
    app.include_router(bot.router)
    app.include_router(cities.router)



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

        @app.get("/app", include_in_schema=False)
        def get_citizen_app() -> FileResponse:
            return FileResponse(citizen_dist / "index.html")

    return app


app = create_app()
