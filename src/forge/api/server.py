"""Production-hardened FastAPI server with rate limiting, security headers,
CORS, and comprehensive health endpoints.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from forge.config import get_settings
from forge.telemetry import (
    init_telemetry,
    shutdown_telemetry,
    configure_structlog,
    get_logger,
    get_correlation_id,
    set_correlation_id,
)
from forge.telemetry.health import HealthChecker, HealthStatus
from forge.api.routes import router as api_router

logger = get_logger("forge.api.server")


def _security_headers_middleware() -> Any:
    """Factory for security headers middleware."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.types import ASGIApp, Receive, Scope, Send

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        """Add security headers to all responses."""

        async def dispatch(self, request: Request, call_next: Any) -> Any:
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self' ws: wss:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = (
                "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
                "magnetometer=(), microphone=(), payment=(), usb=()"
            )
            response.headers["X-Request-ID"] = get_correlation_id()
            return response

    return SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown."""
    # Startup
    configure_structlog()
    init_telemetry()
    app.state.health_checker = HealthChecker()
    logger.info("forge_server_startup_complete")
    yield
    # Shutdown
    shutdown_telemetry()
    logger.info("forge_server_shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the production FastAPI application."""
    settings = get_settings()

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[
            f"{settings.rate_limit_requests}/{settings.rate_limit_window}second",
        ],
        storage_uri=settings.redis_url.get_secret_value(),
    )

    app = FastAPI(
        title="Forge — Agent-Native SDLC Control Plane",
        description="Production-grade API for multi-agent SDLC orchestration with governance",
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Security headers
    app.add_middleware(_security_headers_middleware())

    # CORS (restrictive in production)
    if settings.environment.value == "production":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[],  # No CORS in production — use API gateway
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Trusted hosts
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"] if settings.debug else ["*.ahinsa.ai", "localhost"],
    )

    # Correlation ID middleware
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next: Any) -> Any:
        """Extract or generate correlation ID for request tracing."""
        cid = request.headers.get(settings.log_correlation_id_header)
        if not cid:
            cid = get_correlation_id()
        set_correlation_id(cid)
        response = await call_next(request)
        response.headers[settings.log_correlation_id_header] = cid
        return response

    # Request logging middleware
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next: Any) -> Any:
        """Log all requests with timing and status."""
        start = __import__("time").monotonic()
        try:
            response = await call_next(request)
            duration = __import__("time").monotonic() - start
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                correlation_id=get_correlation_id(),
            )
            return response
        except Exception as exc:
            duration = __import__("time").monotonic() - start
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                error_type=type(exc).__name__,
                duration_ms=round(duration * 1000, 2),
                correlation_id=get_correlation_id(),
            )
            raise

    # Health endpoints
    @app.get("/health/live", tags=["health"])
    @limiter.limit("100/minute")
    async def liveness(request: Request) -> dict[str, Any]:
        """Liveness probe — is the process running?"""
        checker: HealthChecker = request.app.state.health_checker
        report = await checker.liveness()
        status_code = (
            status.HTTP_200_OK
            if report.overall == HealthStatus.HEALTHY
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(
            content={
                "status": report.overall.value,
                "version": report.version,
                "uptime_seconds": report.uptime_seconds,
            },
            status_code=status_code,
        )

    @app.get("/health/ready", tags=["health"])
    @limiter.limit("100/minute")
    async def readiness(request: Request) -> dict[str, Any]:
        """Readiness probe — can the service accept traffic?"""
        checker: HealthChecker = request.app.state.health_checker
        report = await checker.readiness()
        status_code = (
            status.HTTP_200_OK
            if report.overall == HealthStatus.HEALTHY
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(
            content={
                "status": report.overall.value,
                "version": report.version,
                "uptime_seconds": report.uptime_seconds,
                "components": [
                    {
                        "name": c.name,
                        "status": c.status.value,
                        "latency_ms": round(c.latency_ms, 2),
                        "message": c.message,
                    }
                    for c in report.components
                ],
            },
            status_code=status_code,
        )

    @app.get("/health/deep", tags=["health"])
    @limiter.limit("10/minute")
    async def deep_health(request: Request) -> dict[str, Any]:
        """Deep health check — comprehensive dependency validation."""
        checker: HealthChecker = request.app.state.health_checker
        report = await checker.check_all()
        status_code = (
            status.HTTP_200_OK
            if report.overall == HealthStatus.HEALTHY
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(
            content={
                "status": report.overall.value,
                "version": report.version,
                "timestamp": report.timestamp,
                "uptime_seconds": report.uptime_seconds,
                "components": [
                    {
                        "name": c.name,
                        "status": c.status.value,
                        "latency_ms": round(c.latency_ms, 2),
                        "message": c.message,
                        "metadata": c.metadata,
                    }
                    for c in report.components
                ],
            },
            status_code=status_code,
        )

    # Metrics endpoint (Prometheus)
    @app.get(settings.prometheus_path, tags=["metrics"])
    async def metrics() -> Any:
        """Prometheus metrics endpoint."""
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        return JSONResponse(
            content=generate_latest().decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST,
        )

    # Include API routes
    app.include_router(api_router, prefix="/api/v1")

    # OpenTelemetry instrumentation
    FastAPIInstrumentor.instrument_app(app)

    return app


app = create_app()
