"""OpenTelemetry instrumentation for Forge.

Wraps the OTel SDK with Forge-specific conventions, trace propagation,
and metric collection across agent boundaries.
"""

from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from typing import Any, Callable, Generator, TypeVar

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics._internal.aggregation import AggregationTemporality
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server

from forge.config import get_settings

F = TypeVar("F", bound=Callable[..., Any])


class ForgeTracer:
    """Forge-specific tracer wrapper with automatic context propagation."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._tracer: trace.Tracer | None = None

    def _get_tracer(self) -> trace.Tracer:
        if self._tracer is None:
            self._tracer = trace.get_tracer("forge", self._settings.app_version)
        return self._tracer

    def start_span(
        self,
        name: str,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> trace.Span:
        """Start a new span with Forge-specific attributes."""
        tracer = self._get_tracer()
        attrs = attributes or {}
        attrs.update({
            "forge.service.name": self._settings.app_name,
            "forge.service.version": self._settings.app_version,
            "forge.environment": self._settings.environment.value,
        })
        return tracer.start_span(name, kind=kind, attributes=attrs)

    def add_event(
        self,
        span: trace.Span,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Add an event to a span with timestamp."""
        span.add_event(name, attributes=attributes)

    def set_error(self, span: trace.Span, exception: Exception) -> None:
        """Record an exception on a span."""
        span.set_status(Status(StatusCode.ERROR, str(exception)))
        span.record_exception(exception)


class ForgeMeter:
    """Forge-specific metrics wrapper with Prometheus + OTel export."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._labels = {
            "service": self._settings.app_name,
            "version": self._settings.app_version,
            "environment": self._settings.environment.value,
        }

        # Prometheus metrics
        self.spec_executions = Counter(
            "forge_spec_executions_total",
            "Total spec executions",
            ["status", "spec_id", "agent_type"],
        )
        self.spec_duration = Histogram(
            "forge_spec_duration_seconds",
            "Spec execution duration in seconds",
            ["spec_id", "agent_type"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
        )
        self.governance_decisions = Counter(
            "forge_governance_decisions_total",
            "Total governance decisions",
            ["decision", "spec_id", "agent_id"],
        )
        self.memory_hits = Counter(
            "forge_memory_hits_total",
            "Total memory fabric hits",
            ["backend", "operation", "hit_type"],
        )
        self.memory_latency = Histogram(
            "forge_memory_latency_seconds",
            "Memory operation latency",
            ["backend", "operation"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )
        self.agent_executions = Counter(
            "forge_agent_executions_total",
            "Total agent executions",
            ["agent_type", "status", "spec_id"],
        )
        self.active_specs = Gauge(
            "forge_active_specs",
            "Currently active spec executions",
        )
        self.active_agents = Gauge(
            "forge_active_agents",
            "Currently active agents",
        )
        self.orchestrator_queue_depth = Gauge(
            "forge_orchestrator_queue_depth",
            "Current orchestrator queue depth",
        )
        self.info = Info("forge_build_info", "Forge build information")
        self.info.info({
            "version": self._settings.app_version,
            "python_version": f"{__import__("sys").version_info.major}.{__import__("sys").version_info.minor}",
        })

    def record_spec_execution(
        self,
        spec_id: str,
        agent_type: str,
        status: str,
        duration: float,
    ) -> None:
        """Record a completed spec execution."""
        self.spec_executions.labels(
            status=status, spec_id=spec_id, agent_type=agent_type,
        ).inc()
        self.spec_duration.labels(spec_id=spec_id, agent_type=agent_type).observe(duration)

    def record_governance_decision(
        self,
        decision: str,
        spec_id: str,
        agent_id: str,
    ) -> None:
        """Record a governance decision."""
        self.governance_decisions.labels(
            decision=decision, spec_id=spec_id, agent_id=agent_id,
        ).inc()

    def record_memory_operation(
        self,
        backend: str,
        operation: str,
        hit_type: str,
        latency: float,
    ) -> None:
        """Record a memory fabric operation."""
        self.memory_hits.labels(
            backend=backend, operation=operation, hit_type=hit_type,
        ).inc()
        self.memory_latency.labels(backend=backend, operation=operation).observe(latency)

    def record_agent_execution(
        self,
        agent_type: str,
        status: str,
        spec_id: str,
    ) -> None:
        """Record an agent execution."""
        self.agent_executions.labels(
            agent_type=agent_type, status=status, spec_id=spec_id,
        ).inc()

    def set_active_specs(self, count: int) -> None:
        """Update active specs gauge."""
        self.active_specs.set(count)

    def set_active_agents(self, count: int) -> None:
        """Update active agents gauge."""
        self.active_agents.set(count)

    def set_queue_depth(self, depth: int) -> None:
        """Update orchestrator queue depth."""
        self.orchestrator_queue_depth.set(depth)


# Global instances (lazy initialization)
_tracer_instance: ForgeTracer | None = None
_meter_instance: ForgeMeter | None = None


def get_tracer() -> ForgeTracer:
    """Get the global Forge tracer."""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = ForgeTracer()
    return _tracer_instance


def get_meter() -> ForgeMeter:
    """Get the global Forge meter."""
    global _meter_instance
    if _meter_instance is None:
        _meter_instance = ForgeMeter()
    return _meter_instance


@contextmanager
def trace_span(
    name: str,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> Generator[trace.Span, None, None]:
    """Context manager for creating a traced span.

    Usage:
        with trace_span("spec.execute", attributes={"spec_id": "SPEC-001"}) as span:
            result = execute_spec()
    """
    tracer = get_tracer()
    span = tracer.start_span(name, kind=kind, attributes=attributes)
    start_time = time.monotonic()
    try:
        yield span
        span.set_status(Status(StatusCode.OK))
    except Exception as exc:
        tracer.set_error(span, exc)
        raise
    finally:
        duration = time.monotonic() - start_time
        span.set_attribute("duration_ms", duration * 1000)
        span.end()


def record_metric(
    metric_name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Record a custom metric value."""
    meter = get_meter()
    # Dispatch to appropriate metric based on name
    if metric_name == "spec.execution":
        meter.record_spec_execution(
            labels.get("spec_id", "unknown"),
            labels.get("agent_type", "unknown"),
            labels.get("status", "unknown"),
            value,
        )
    elif metric_name == "governance.decision":
        meter.record_governance_decision(
            labels.get("decision", "unknown"),
            labels.get("spec_id", "unknown"),
            labels.get("agent_id", "unknown"),
        )
    elif metric_name == "memory.operation":
        meter.record_memory_operation(
            labels.get("backend", "unknown"),
            labels.get("operation", "unknown"),
            labels.get("hit_type", "unknown"),
            value,
        )


def init_telemetry() -> None:
    """Initialize OpenTelemetry with Forge resource attributes.

    Must be called once at application startup before any tracing/metrics.
    """
    settings = get_settings()

    # Resource attributes
    resource = Resource.create({
        SERVICE_NAME: settings.otel_service_name,
        SERVICE_NAMESPACE: settings.otel_service_namespace,
        SERVICE_VERSION: settings.app_version,
        "deployment.environment": settings.environment.value,
    })

    # Tracer provider
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=trace.sampling.TraceIdRatioBased(settings.otel_trace_sampling_rate),
    )
    otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Meter provider
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=settings.otel_exporter_endpoint),
        export_interval_millis=60000,
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )
    metrics.set_meter_provider(meter_provider)

    # Start Prometheus HTTP server
    start_http_server(settings.prometheus_port)


def shutdown_telemetry() -> None:
    """Gracefully shutdown telemetry providers."""
    trace_provider = trace.get_tracer_provider()
    if hasattr(trace_provider, "shutdown"):
        trace_provider.shutdown()
    meter_provider = metrics.get_meter_provider()
    if hasattr(meter_provider, "shutdown"):
        meter_provider.shutdown()
