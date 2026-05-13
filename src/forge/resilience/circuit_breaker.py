"""Production-grade circuit breaker with Prometheus metrics and structured logging.

Implements the circuit breaker pattern with half-open state, configurable thresholds,
and automatic recovery detection.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

from forge.telemetry import get_logger, get_meter

logger = get_logger("forge.resilience.circuit_breaker")

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    success_threshold: int = 2
    name: str = "default"


class CircuitBreaker:
    """Production circuit breaker with metrics and structured logging.

    Tracks failure rates, emits Prometheus metrics, and provides
    detailed logging for operational visibility.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float = 0.0
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0
        self._meter = get_meter()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "half_open_calls": self._half_open_calls,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "last_failure_time": self._last_failure_time,
            "config": {
                "failure_threshold": self._config.failure_threshold,
                "recovery_timeout": self._config.recovery_timeout,
                "half_open_max_calls": self._config.half_open_max_calls,
                "success_threshold": self._config.success_threshold,
            },
        }

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a function with circuit breaker protection.

        Automatically tracks metrics and transitions between states.
        """
        async with self._lock:
            self._total_calls += 1

            # Check if we should transition from OPEN to HALF_OPEN
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self._config.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
                    logger.info(
                        "circuit_breaker_half_open",
                        breaker_name=self._config.name,
                        recovery_timeout=self._config.recovery_timeout,
                    )
                else:
                    remaining = self._config.recovery_timeout - (time.monotonic() - self._last_failure_time)
                    logger.warning(
                        "circuit_breaker_open_rejecting",
                        breaker_name=self._config.name,
                        remaining_seconds=round(remaining, 2),
                    )
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self._config.name}' is OPEN. "
                        f"Retry after {round(remaining, 2)}s"
                    )

            # Check half-open call limit
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._config.half_open_max_calls:
                    logger.warning(
                        "circuit_breaker_half_open_limit_reached",
                        breaker_name=self._config.name,
                        max_calls=self._config.half_open_max_calls,
                    )
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self._config.name}' half-open call limit reached"
                    )
                self._half_open_calls += 1

        # Execute the function
        start = time.monotonic()
        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as exc:
            await self._record_failure()
            raise

    async def _record_success(self) -> None:
        async with self._lock:
            self._total_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        "circuit_breaker_closed",
                        breaker_name=self._config.name,
                        success_threshold=self._config.success_threshold,
                    )

    async def _record_failure(self) -> None:
        async with self._lock:
            self._total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_opened_from_half_open",
                    breaker_name=self._config.name,
                    failure_count=self._failure_count,
                )
            elif self._failure_count >= self._config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_opened",
                    breaker_name=self._config.name,
                    failure_threshold=self._config.failure_threshold,
                    failure_count=self._failure_count,
                )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        logger.info("circuit_breaker_manual_reset", breaker_name=self._config.name)


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and rejecting requests."""
    pass


class CircuitBreakerRegistry:
    """Registry for managing multiple named circuit breakers."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Get an existing circuit breaker or create a new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(config or CircuitBreakerConfig(name=name))
        return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)

    def all_metrics(self) -> dict[str, dict[str, Any]]:
        """Get metrics for all registered circuit breakers."""
        return {name: cb.metrics for name, cb in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


# Global registry
_registry = CircuitBreakerRegistry()


def get_circuit_breaker(name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
    """Get or create a circuit breaker from the global registry."""
    return _registry.get_or_create(name, config)
