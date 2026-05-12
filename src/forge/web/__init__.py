"""Web API for Forge.

Provides HTTP endpoints for health checks, metrics, and
workflow management.
"""

from forge.web.health import HealthCheck

__all__ = ["HealthCheck"]
