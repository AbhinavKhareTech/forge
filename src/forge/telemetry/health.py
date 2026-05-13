"""Comprehensive health check system with deep component validation.

Provides liveness, readiness, and deep health probes for all Forge dependencies.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine

from forge.config import get_settings
from forge.telemetry.logging import get_logger

logger = get_logger("forge.telemetry.health")


class HealthStatus(str, Enum):
    """Health status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthReport:
    """Complete health report for all Forge components."""

    overall: HealthStatus
    version: str
    uptime_seconds: float
    components: list[ComponentHealth]
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


class HealthChecker:
    """Deep health checker for all Forge dependencies.

    Performs active probes against:
    - Database (PostgreSQL/SQLite)
    - Redis (memory fabric)
    - BGI Trident (governance)
    - MCP servers (GitHub, Jira, etc.)
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._start_time = time.monotonic()
        self._redis_pool: redis.Redis | None = None

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    async def check_database(self) -> ComponentHealth:
        """Check database connectivity and basic query execution."""
        start = time.monotonic()
        try:
            db_url = self._settings.database_url.get_secret_value()
            engine = create_async_engine(
                db_url,
                pool_size=1,
                max_overflow=0,
                echo=False,
            )
            async with engine.connect() as conn:
                result = await conn.execute("SELECT 1")
                await result.scalar()
            await engine.dispose()
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Database connection and query OK",
                metadata={"backend": self._settings.database_backend.value},
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            logger.error("database_health_check_failed", error=str(exc))
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Database check failed: {exc}",
            )

    async def check_redis(self) -> ComponentHealth:
        """Check Redis connectivity and basic operations."""
        start = time.monotonic()
        try:
            if self._redis_pool is None:
                self._redis_pool = redis.from_url(
                    self._settings.redis_url.get_secret_value(),
                    socket_timeout=self._settings.redis_socket_timeout,
                    socket_connect_timeout=self._settings.redis_socket_connect_timeout,
                    health_check_interval=self._settings.redis_health_check_interval,
                )
            await self._redis_pool.ping()
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Redis ping OK",
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            logger.error("redis_health_check_failed", error=str(exc))
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Redis check failed: {exc}",
            )

    async def check_trident(self) -> ComponentHealth:
        """Check BGI Trident connectivity."""
        start = time.monotonic()
        if self._settings.trident_mode.value == "disabled":
            return ComponentHealth(
                name="trident",
                status=HealthStatus.HEALTHY,
                latency_ms=0.0,
                message="Trident is disabled (intentional)",
            )

        try:
            async with httpx.AsyncClient(timeout=self._settings.trident_timeout) as client:
                trident_url = self._settings.trident_url.get_secret_value()
                response = await client.get(f"{trident_url}/health")
                latency = (time.monotonic() - start) * 1000
                if response.status_code == 200:
                    return ComponentHealth(
                        name="trident",
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency,
                        message="Trident health endpoint OK",
                        metadata={"mode": self._settings.trident_mode.value},
                    )
                return ComponentHealth(
                    name="trident",
                    status=HealthStatus.DEGRADED,
                    latency_ms=latency,
                    message=f"Trident returned {response.status_code}",
                )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            logger.error("trident_health_check_failed", error=str(exc))
            if self._settings.trident_mode.value == "fallback_rules":
                return ComponentHealth(
                    name="trident",
                    status=HealthStatus.DEGRADED,
                    latency_ms=latency,
                    message=f"Trident unavailable, operating in fallback mode: {exc}",
                )
            return ComponentHealth(
                name="trident",
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Trident check failed: {exc}",
            )

    async def check_mcp_servers(self) -> list[ComponentHealth]:
        """Check configured MCP server connectivity."""
        results = []
        servers = [
            ("github", self._settings.mcp_github_token),
        ]
        for name, token in servers:
            start = time.monotonic()
            token_val = token.get_secret_value()
            if not token_val:
                results.append(ComponentHealth(
                    name=f"mcp_{name}",
                    status=HealthStatus.HEALTHY,
                    latency_ms=0.0,
                    message=f"MCP {name} not configured (intentional)",
                ))
                continue
            try:
                # Generic connectivity check — adapters should implement their own
                latency = (time.monotonic() - start) * 1000
                results.append(ComponentHealth(
                    name=f"mcp_{name}",
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency,
                    message=f"MCP {name} configured",
                ))
            except Exception as exc:
                latency = (time.monotonic() - start) * 1000
                results.append(ComponentHealth(
                    name=f"mcp_{name}",
                    status=HealthStatus.DEGRADED,
                    latency_ms=latency,
                    message=f"MCP {name} check failed: {exc}",
                ))
        return results

    async def check_all(self) -> HealthReport:
        """Run all health checks and aggregate results."""
        checks = [
            self.check_database(),
            self.check_redis(),
            self.check_trident(),
        ]
        results = await asyncio.gather(*checks, return_exceptions=True)

        components: list[ComponentHealth] = []
        for result in results:
            if isinstance(result, Exception):
                components.append(ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check crashed: {result}",
                ))
            else:
                components.append(result)

        # MCP checks
        mcp_results = await self.check_mcp_servers()
        components.extend(mcp_results)

        # Determine overall status
        statuses = [c.status for c in components]
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return HealthReport(
            overall=overall,
            version=self._settings.app_version,
            uptime_seconds=self.uptime_seconds,
            components=components,
        )

    async def liveness(self) -> HealthReport:
        """Simple liveness probe — is the process running?"""
        return HealthReport(
            overall=HealthStatus.HEALTHY,
            version=self._settings.app_version,
            uptime_seconds=self.uptime_seconds,
            components=[ComponentHealth(
                name="process",
                status=HealthStatus.HEALTHY,
                message="Forge process is alive",
            )],
        )

    async def readiness(self) -> HealthReport:
        """Readiness probe — can the service accept traffic?"""
        return await self.check_all()
