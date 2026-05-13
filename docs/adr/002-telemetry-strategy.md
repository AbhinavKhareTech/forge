# ADR-002: Telemetry and Observability Strategy

## Status
Accepted

## Context
Forge operates a distributed multi-agent system where failures can cascade across agent boundaries. We need comprehensive observability to:
1. Debug cross-agent failures
2. Monitor governance decision accuracy
3. Track system performance under load
4. Meet compliance requirements for audit trails

## Decision

### 1. OpenTelemetry for Distributed Tracing
We instrument all core components with **OpenTelemetry**:
- Every spec execution is a root trace
- Each agent step is a child span
- Governance decisions are annotated spans
- Trace context propagates across agent boundaries

**Export**: OTLP to Jaeger/Tempo for visualization.

### 2. Prometheus for Metrics
Custom metrics for operational visibility:
- `forge_spec_executions_total` (status, spec_id, agent_type)
- `forge_spec_duration_seconds` (histogram)
- `forge_governance_decisions_total` (decision, spec_id, agent_id)
- `forge_memory_hits_total` (backend, operation, hit_type)
- `forge_active_specs`, `forge_active_agents`, `forge_orchestrator_queue_depth`

### 3. Structured Logging with structlog
All logs are structured JSON with:
- `correlation_id` for request tracing
- `trace_id`/`span_id` for OpenTelemetry correlation
- `environment`, `service`, `version` for filtering
- Automatic secret redaction

### 4. Sentry for Error Tracking
Exception tracking with context enrichment:
- Agent ID, spec ID, trace ID attached to every error
- Release tracking for regression detection
- Breadcrumbs for debugging

## Consequences

### Positive
- Full request tracing across agent boundaries
- Proactive alerting on governance anomalies
- Immutable audit trail for compliance
- Fast incident response with correlated logs

### Negative
- ~5-10% performance overhead from tracing
- Additional infrastructure (Jaeger, Prometheus, Grafana)
- Log volume increases significantly

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|----------------|
| Custom tracing | Reinventing the wheel, poor ecosystem |
| StatsD | Less flexible than Prometheus, no histograms |
| Plain text logs | Impossible to query at scale |
| CloudWatch-only | Vendor lock-in, expensive at scale |
