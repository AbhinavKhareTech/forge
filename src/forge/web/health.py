"""Health check endpoint for Forge.

Provides liveness, readiness, and deep health probes for
Kubernetes and monitoring systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from forge.config import get_config
from forge.utils.logging import get_logger

logger = get_logger("forge.web.health")


@dataclass
class HealthStatus:
    """Health check result."""

    status: str  # healthy | degraded | unhealthy
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    version: str = "0.1.0"
    uptime_seconds: float = 0.0


class HealthCheck:
    """Health check provider for Forge.

    Supports three probe types:
    - Liveness: Is the process running?
    - Readiness: Is it ready to serve traffic?
    - Deep: Are all dependencies healthy?
    """

    def __init__(self) -> None:
        self.config = get_config()
        self._start_time = datetime.utcnow()

    def liveness(self) -> HealthStatus:
        """Liveness probe -- is the process alive?"""
        return HealthStatus(
            status="healthy",
            checks={"process": {"status": "up", "pid": None}},
            uptime_seconds=self._uptime(),
        )

    def readiness(self) -> HealthStatus:
        """Readiness probe -- is it ready to serve?"""
        checks: dict[str, dict[str, Any]] = {}
        status = "healthy"

        # Check configuration loaded
        try:
            _ = self.config.env
            checks["config"] = {"status": "up"}
        except Exception as e:
            checks["config"] = {"status": "down", "error": str(e)}
            status = "unhealthy"

        # Check memory backend
        try:
            from forge.memory.fabric import MemoryFabric
            memory = MemoryFabric()
            checks["memory"] = {"status": "up", "backend": self.config.memory_backend}
        except Exception as e:
            checks["memory"] = {"status": "down", "error": str(e)}
            status = "degraded" if status == "healthy" else status

        return HealthStatus(
            status=status,
            checks=checks,
            uptime_seconds=self._uptime(),
        )

    def deep(self) -> HealthStatus:
        """Deep health check -- all dependencies."""
        checks: dict[str, dict[str, Any]] = {}
        status = "healthy"

        # Config
        try:
            _ = self.config.env
            checks["config"] = {"status": "up"}
        except Exception as e:
            checks["config"] = {"status": "down", "error": str(e)}
            status = "unhealthy"

        # Memory
        try:
            from forge.memory.fabric import MemoryFabric
            memory = MemoryFabric()
            checks["memory"] = {"status": "up", "backend": self.config.memory_backend}
        except Exception as e:
            checks["memory"] = {"status": "down", "error": str(e)}
            status = "degraded"

        # Trident (if enabled)
        if self.config.trident_enabled:
            try:
                from forge.trident.ensemble import TridentEnsemble
                from forge.trident.config import TridentConfig
                trident = TridentEnsemble(config=TridentConfig())
                checks["trident"] = {
                    "status": "up",
                    "prong1": trident._prong1_available,
                    "prong2": trident._prong2_available,
                    "prong3": trident._prong3_available,
                }
            except Exception as e:
                checks["trident"] = {"status": "down", "error": str(e)}
                status = "degraded"
        else:
            checks["trident"] = {"status": "disabled"}

        # MCP Mesh
        try:
            from forge.mcp.mesh import MCPMesh
            mesh = MCPMesh()
            checks["mcp_mesh"] = {"status": "up", "servers": len(mesh.list_servers())}
        except Exception as e:
            checks["mcp_mesh"] = {"status": "down", "error": str(e)}
            status = "degraded"

        return HealthStatus(
            status=status,
            checks=checks,
            uptime_seconds=self._uptime(),
        )

    def _uptime(self) -> float:
        """Calculate uptime in seconds."""
        return (datetime.utcnow() - self._start_time).total_seconds()

    def to_dict(self, status: HealthStatus) -> dict[str, Any]:
        """Convert HealthStatus to dict for JSON response."""
        return {
            "status": status.status,
            "version": status.version,
            "timestamp": status.timestamp,
            "uptime_seconds": status.uptime_seconds,
            "checks": status.checks,
        }
