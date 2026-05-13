"""Forge telemetry module — OpenTelemetry instrumentation, metrics, and logging.

Provides unified observability across all Forge components with distributed tracing,
structured metrics, and correlated logging.
"""

from __future__ import annotations

from .instrumentation import (
    ForgeTracer,
    ForgeMeter,
    get_tracer,
    get_meter,
    trace_span,
    record_metric,
    init_telemetry,
    shutdown_telemetry,
)
from .logging import configure_structlog, get_logger
from .health import HealthChecker, HealthStatus, ComponentHealth

__all__ = [
    "ForgeTracer",
    "ForgeMeter",
    "get_tracer",
    "get_meter",
    "trace_span",
    "record_metric",
    "init_telemetry",
    "shutdown_telemetry",
    "configure_structlog",
    "get_logger",
    "HealthChecker",
    "HealthStatus",
    "ComponentHealth",
]
