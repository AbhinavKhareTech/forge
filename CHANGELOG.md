# Changelog

All notable changes to Forge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Production-grade security model with RBAC, JWT, and API key authentication
- OpenTelemetry instrumentation for distributed tracing
- Prometheus metrics with custom Forge metrics
- Structured logging with correlation IDs and trace context
- PostgreSQL checkpoint persistence for crash recovery
- Circuit breaker pattern with metrics
- Graceful degradation when BGI Trident is unavailable
- Rate limiting with Redis-backed slowapi
- Security headers (CSP, HSTS, X-Frame-Options)
- Audit logging with SHA-256 tamper detection
- Health checks (liveness, readiness, deep)
- Kubernetes NetworkPolicies for zero-trust networking
- Pod Disruption Budgets for HA
- ServiceMonitor for Prometheus Operator
- Helm chart with secrets management
- Docker multi-stage build with non-root user
- GitHub Actions CI with security scanning (Bandit, pip-audit, Semgrep)
- Property-based testing with Hypothesis
- Load testing framework
- Integration tests with testcontainers
- Architecture Decision Records (ADRs)
- Operational runbooks
- Contributing guidelines

### Security
- All secrets use `pydantic.SecretStr`
- Input validation with Pydantic
- Fail-closed governance when Trident is unavailable
- Secret redaction in logs
- GPG-signed releases
- SBOM generation
- Container image signing with cosign

## [0.1.0] - 2024-XX-XX

### Added
- Initial scaffold with Spec Engine, Agent Registry, and Orchestrator
- Basic governance runtime
- Redis memory fabric
- MCP mesh adapters for GitHub and Jira
- FastAPI server with WebSocket support
- Voice-driven spec generation
- BGI Trident integration framework
- Docker and Helm deployment configs
- Comprehensive test suite
