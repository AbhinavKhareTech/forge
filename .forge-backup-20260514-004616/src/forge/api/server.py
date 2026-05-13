"""FastAPI server for Forge dashboard and API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from forge.api.routes import router
from forge.api.websocket import ws_router
from forge.api.sse import sse_router
from forge.auth.middleware import APIKeyAuth
from forge.utils.logging import get_logger

logger = get_logger("forge.api")


def create_app() -> Any:
    """Create and configure the FastAPI application."""
    try:
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        logger.error("fastapi_not_installed")
        raise RuntimeError("FastAPI not installed. Run: pip install fastapi[standard]")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("api_server_starting")
        yield
        logger.info("api_server_shutting_down")

    app = FastAPI(
        title="Forge API",
        description="Agent-Native SDLC Control Plane",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/ws")
    app.include_router(sse_router, prefix="/sse")

    # Auth middleware
    auth = APIKeyAuth()
    if auth.is_enabled():
        logger.info("api_auth_enabled")
    else:
        logger.warning("api_auth_disabled")

    # Static files for dashboard
    try:
        app.mount("/static", StaticFiles(directory="src/forge/api/static"), name="static")
    except Exception:
        logger.warning("static_files_not_mounted")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"message": "Forge API", "version": "0.1.0", "docs": "/docs"}

    @app.get("/health")
    async def health() -> dict[str, Any]:
        from forge.web.health import HealthCheck
        check = HealthCheck()
        return check.to_dict(check.deep())

    @app.get("/ready")
    async def ready() -> dict[str, Any]:
        from forge.web.health import HealthCheck
        check = HealthCheck()
        return check.to_dict(check.readiness())

    return app
