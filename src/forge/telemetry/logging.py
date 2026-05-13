"""Structured logging configuration with correlation IDs and trace context.

Uses structlog with JSON output for production and console output for development.
All logs include trace_id, span_id, and correlation_id for cross-service debugging.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import Processor

from forge.config import get_settings

# Context variable for correlation ID (thread-safe and async-safe)
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the current correlation ID or generate a new one."""
    cid = _correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())
        _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id.set(cid)


def _add_correlation_id(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: inject correlation_id into every log entry."""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def _add_trace_context(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: inject OpenTelemetry trace context into every log entry."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
            event_dict["trace_flags"] = format(ctx.trace_flags, "02x")
    except Exception:
        pass
    return event_dict


def _add_environment_info(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: inject environment info into every log entry."""
    settings = get_settings()
    event_dict["environment"] = settings.environment.value
    event_dict["service"] = settings.app_name
    event_dict["version"] = settings.app_version
    return event_dict


def _sanitize_secrets(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor: redact sensitive fields from log output."""
    sensitive_keys = {
        "password", "secret", "token", "key", "auth", "credential",
        "api_key", "jwt", "encryption_key", "access_key", "private_key",
    }
    for key in list(event_dict.keys()):
        if any(sk in key.lower() for sk in sensitive_keys):
            event_dict[key] = "***REDACTED***"
    return event_dict


def configure_structlog() -> None:
    """Configure structlog with production-grade processors.

    Must be called once at application startup.
    """
    settings = get_settings()

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_correlation_id,
        _add_trace_context,
        _add_environment_info,
        structlog.stdlib.ExtraAdder(),
        _sanitize_secrets,
    ]

    if settings.log_format == "json":
        shared_processors.append(structlog.processors.dict_tracebacks)
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.value)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.value),
    )
    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.value)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Usage:
        logger = get_logger("forge.orchestrator")
        logger.info("spec_started", spec_id="SPEC-001", agent_type="planner")
    """
    return structlog.get_logger(name)
