"""Tests for deployment and health checks."""

from __future__ import annotations

import pytest

from forge.web.health import HealthCheck, HealthStatus


class TestHealthCheck:
    """Test suite for health check endpoints."""

    @pytest.fixture
    def health(self):
        return HealthCheck()

    def test_liveness(self, health: HealthCheck) -> None:
        """Liveness probe returns healthy."""
        result = health.liveness()
        assert isinstance(result, HealthStatus)
        assert result.status == "healthy"
        assert result.uptime_seconds >= 0
        assert result.version == "0.1.0"

    def test_readiness(self, health: HealthCheck) -> None:
        """Readiness probe checks dependencies."""
        result = health.readiness()
        assert result.status in ("healthy", "degraded")
        assert "config" in result.checks
        assert "memory" in result.checks

    def test_deep_health(self, health: HealthCheck) -> None:
        """Deep health checks all components."""
        result = health.deep()
        assert result.status in ("healthy", "degraded")
        assert "config" in result.checks
        assert "memory" in result.checks
        assert "trident" in result.checks
        assert "mcp_mesh" in result.checks

    def test_to_dict(self, health: HealthCheck) -> None:
        """Convert HealthStatus to dict."""
        status = health.liveness()
        data = health.to_dict(status)
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "uptime_seconds" in data
        assert "checks" in data

    def test_uptime_increases(self, health: HealthCheck) -> None:
        """Uptime increases over time."""
        import time
        result1 = health.liveness()
        time.sleep(0.1)
        result2 = health.liveness()
        assert result2.uptime_seconds > result1.uptime_seconds


class TestVersion:
    """Test suite for version information."""

    def test_version_string(self) -> None:
        """Version is a valid string."""
        from forge.__version__ import __version__, get_version
        assert isinstance(__version__, str)
        assert len(__version__) > 0
        assert get_version() == __version__

    def test_version_format(self) -> None:
        """Version follows semantic versioning."""
        from forge.__version__ import __version__
        parts = __version__.split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() for p in parts[:2])
