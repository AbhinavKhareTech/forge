"""Forge configuration with production-grade secrets management and validation.

All sensitive values use pydantic.SecretStr to prevent accidental logging.
Configuration is validated at startup with fail-fast behavior.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):
    """Structured log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Environment(str, Enum):
    """Deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class DatabaseBackend(str, Enum):
    """Supported database backends for persistence."""

    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


class MemoryBackend(str, Enum):
    """Supported memory backends."""

    REDIS = "redis"
    IN_MEMORY = "in_memory"


class TridentMode(str, Enum):
    """BGI Trident operational modes."""

    ENABLED = "enabled"
    FALLBACK_RULES = "fallback_rules"
    DISABLED = "disabled"


class ForgeSettings(BaseSettings):
    """Production-hardened Forge configuration.

    All secrets use SecretStr to prevent accidental exposure in logs,
    stack traces, or debugging output.
    """

    model_config = SettingsConfigDict(
        env_prefix="FORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        validate_assignment=True,
    )

    # ── Core Application ──────────────────────────────────────────
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment",
    )
    app_name: str = Field(default="forge", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Enable debug mode")

    # ── API Server ────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", description="API server bind host")
    api_port: int = Field(default=8000, ge=1, le=65535, description="API server port")
    api_workers: int = Field(default=1, ge=1, le=64, description="Number of API workers")
    api_timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="API request timeout (seconds)")

    # ── Secrets (NEVER logged) ────────────────────────────────────
    jwt_secret: SecretStr = Field(
        default=SecretStr("change-me-in-production"),
        description="JWT signing secret — MUST be rotated in production",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiration_minutes: int = Field(default=60, ge=5, le=10080, description="JWT expiration in minutes")

    api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Master API key for service-to-service auth",
    )
    encryption_key: SecretStr = Field(
        default=SecretStr(""),
        description="Fernet encryption key for sensitive data at rest",
    )

    # ── Rate Limiting ───────────────────────────────────────────────
    rate_limit_requests: int = Field(default=100, ge=1, description="Requests per window")
    rate_limit_window: int = Field(default=60, ge=1, description="Rate limit window in seconds")
    rate_limit_burst: int = Field(default=10, ge=1, description="Burst allowance")

    # ── Database / Persistence ────────────────────────────────────
    database_backend: DatabaseBackend = Field(
        default=DatabaseBackend.SQLITE,
        description="Primary persistence backend",
    )
    database_url: SecretStr = Field(
        default=SecretStr("sqlite+aiosqlite:///./forge.db"),
        description="Database connection string",
    )
    database_pool_size: int = Field(default=10, ge=1, le=100, description="Connection pool size")
    database_max_overflow: int = Field(default=20, ge=0, le=100, description="Connection pool overflow")
    database_echo: bool = Field(default=False, description="Echo SQL statements")

    # ── Memory Fabric ─────────────────────────────────────────────
    memory_backend: MemoryBackend = Field(default=MemoryBackend.REDIS, description="Memory backend")
    redis_url: SecretStr = Field(
        default=SecretStr("redis://localhost:6379/0"),
        description="Redis connection URL",
    )
    redis_pool_max_connections: int = Field(default=50, ge=1, description="Redis pool max connections")
    redis_socket_timeout: float = Field(default=5.0, ge=1.0, description="Redis socket timeout")
    redis_socket_connect_timeout: float = Field(default=5.0, ge=1.0, description="Redis connect timeout")
    redis_health_check_interval: int = Field(default=30, ge=1, description="Redis health check interval")

    # ── BGI Trident ───────────────────────────────────────────────
    trident_mode: TridentMode = Field(
        default=TridentMode.FALLBACK_RULES,
        description="Trident operational mode",
    )
    trident_url: SecretStr = Field(
        default=SecretStr("http://localhost:8080"),
        description="Trident service URL",
    )
    trident_timeout: float = Field(default=10.0, ge=1.0, description="Trident request timeout")
    trident_max_retries: int = Field(default=3, ge=0, description="Trident max retries")
    trident_retry_backoff: float = Field(default=1.0, ge=0.1, description="Trident retry backoff (seconds)")

    # ── MCP Mesh ──────────────────────────────────────────────────
    mcp_github_token: SecretStr = Field(
        default=SecretStr(""),
        description="GitHub personal access token",
    )
    mcp_jira_token: SecretStr = Field(
        default=SecretStr(""),
        description="Jira API token",
    )
    mcp_jira_email: SecretStr = Field(
        default=SecretStr(""),
        description="Jira user email",
    )
    mcp_aws_access_key_id: SecretStr = Field(
        default=SecretStr(""),
        description="AWS access key ID",
    )
    mcp_aws_secret_access_key: SecretStr = Field(
        default=SecretStr(""),
        description="AWS secret access key",
    )
    mcp_datadog_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Datadog API key",
    )

    # ── Observability ─────────────────────────────────────────────
    otel_exporter_endpoint: str = Field(
        default="http://localhost:4317",
        description="OpenTelemetry OTLP exporter endpoint",
    )
    otel_service_name: str = Field(default="forge", description="OTel service name")
    otel_service_namespace: str = Field(default="sdlc", description="OTel service namespace")
    otel_trace_sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Trace sampling rate")

    sentry_dsn: SecretStr = Field(
        default=SecretStr(""),
        description="Sentry DSN for error tracking",
    )
    sentry_environment: str = Field(default="development", description="Sentry environment tag")
    sentry_traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0, description="Sentry traces sample rate")

    prometheus_port: int = Field(default=9090, ge=1, le=65535, description="Prometheus metrics port")
    prometheus_path: str = Field(default="/metrics", description="Prometheus metrics endpoint path")

    log_level: LogLevel = Field(default=LogLevel.INFO, description="Application log level")
    log_format: str = Field(default="json", description="Log format: json or console")
    log_correlation_id_header: str = Field(default="x-request-id", description="Correlation ID header name")

    # ── Governance ────────────────────────────────────────────────
    governance_audit_log_path: str = Field(
        default="/var/log/forge/audit.log",
        description="Path to immutable audit log",
    )
    governance_max_spec_depth: int = Field(default=50, ge=1, le=500, description="Max spec dependency depth")
    governance_max_agents_per_spec: int = Field(default=100, ge=1, le=1000, description="Max agents per spec")
    governance_auto_approve_threshold: float = Field(
        default=0.95, ge=0.0, le=1.0, description="Auto-approve confidence threshold",
    )

    # ── Orchestrator ────────────────────────────────────────────
    orchestrator_checkpoint_interval: int = Field(
        default=30, ge=5, description="Checkpoint interval in seconds",
    )
    orchestrator_max_concurrent_specs: int = Field(
        default=10, ge=1, le=1000, description="Max concurrent spec executions",
    )
    orchestrator_default_agent_timeout: float = Field(
        default=300.0, ge=10.0, description="Default agent execution timeout (seconds)",
    )
    orchestrator_retry_max_attempts: int = Field(default=3, ge=0, description="Max retry attempts per step")
    orchestrator_retry_base_delay: float = Field(default=1.0, ge=0.1, description="Retry base delay (seconds)")
    orchestrator_retry_max_delay: float = Field(default=60.0, ge=1.0, description="Retry max delay (seconds)")
    orchestrator_retry_exponential_base: float = Field(default=2.0, ge=1.0, description="Exponential backoff base")

    # ── Validation ────────────────────────────────────────────────
    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _validate_jwt_secret(cls, v: Any) -> Any:
        """Ensure JWT secret is strong in production."""
        if isinstance(v, SecretStr):
            v = v.get_secret_value()
        env = os.getenv("FORGE_ENVIRONMENT", "development").lower()
        if env == "production" and len(str(v)) < 32:
            raise ValueError("FORGE_JWT_SECRET must be at least 32 characters in production")
        return v

    @field_validator("encryption_key", mode="before")
    @classmethod
    def _validate_encryption_key(cls, v: Any) -> Any:
        """Ensure encryption key is set in production."""
        if isinstance(v, SecretStr):
            v = v.get_secret_value()
        env = os.getenv("FORGE_ENVIRONMENT", "development").lower()
        if env == "production" and not str(v):
            raise ValueError("FORGE_ENCRYPTION_KEY is required in production")
        return v

    @model_validator(mode="after")
    def _validate_production_settings(self) -> "ForgeSettings":
        """Cross-field validation for production deployments."""
        if self.environment == Environment.PRODUCTION:
            if self.debug:
                raise ValueError("FORGE_DEBUG must be False in production")
            if self.database_backend == DatabaseBackend.SQLITE:
                raise ValueError("SQLite is not allowed in production — use PostgreSQL")
            if self.memory_backend == MemoryBackend.IN_MEMORY:
                raise ValueError("In-memory backend is not allowed in production — use Redis")
            if not self.sentry_dsn.get_secret_value():
                raise ValueError("FORGE_SENTRY_DSN is required in production")
            if self.rate_limit_requests > 10000:
                raise ValueError("Rate limit too high for production safety")
        return self

    @model_validator(mode="after")
    def _validate_timeouts(self) -> "ForgeSettings":
        """Ensure timeout relationships are sane."""
        if self.api_timeout <= self.trident_timeout:
            raise ValueError("API timeout must be greater than Trident timeout")
        if self.orchestrator_default_agent_timeout <= self.api_timeout:
            raise ValueError("Agent timeout must be greater than API timeout")
        return self


@lru_cache(maxsize=1)
def get_settings() -> ForgeSettings:
    """Return cached Forge settings instance.

    Settings are validated once at first access and cached for the process lifetime.
    This ensures consistent configuration and avoids repeated env parsing.
    """
    return ForgeSettings()


def reload_settings() -> ForgeSettings:
    """Force reload of settings (useful for testing and hot-reload scenarios)."""
    get_settings.cache_clear()
    return get_settings()
