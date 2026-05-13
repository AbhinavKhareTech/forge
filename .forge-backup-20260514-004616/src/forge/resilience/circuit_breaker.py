"""Circuit Breaker pattern for fault-tolerant agent execution.

Prevents cascading failures by stopping calls to failing agents/MCP
servers after a threshold of failures is reached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

from forge.utils.logging import get_logger

logger = get_logger("forge.resilience.circuit_breaker")

T = TypeVar("T")


class CircuitState(str, Enum):
    """States of a circuit breaker."""

    CLOSED = "closed"       # Normal operation, requests pass through
    OPEN = "open"           # Failing fast, requests rejected
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5          # Failures before opening
    recovery_timeout: float = 30.0      # Seconds before half-open
    half_open_max_calls: int = 3        # Test calls in half-open
    success_threshold: int = 2          # Successes to close


class CircuitBreaker:
    """Circuit breaker for agent and MCP server calls.

    Tracks failures per target (agent name, MCP server, etc.) and
    opens the circuit when failure threshold is exceeded.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._states: dict[str, CircuitState] = {}
        self._failure_counts: dict[str, int] = {}
        self._success_counts: dict[str, int] = {}
        self._last_failure_time: dict[str, datetime] = {}
        self._half_open_calls: dict[str, int] = {}

    def get_state(self, target: str) -> CircuitState:
        """Get current state for a target."""
        state = self._states.get(target, CircuitState.CLOSED)

        # Check if open circuit should transition to half-open
        if state == CircuitState.OPEN:
            last_fail = self._last_failure_time.get(target)
            if last_fail:
                elapsed = (datetime.utcnow() - last_fail).total_seconds()
                if elapsed >= self.config.recovery_timeout:
                    self._states[target] = CircuitState.HALF_OPEN
                    self._half_open_calls[target] = 0
                    logger.info("circuit_half_open", target=target)
                    return CircuitState.HALF_OPEN

        return state

    async def call(
        self,
        target: str,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute a call through the circuit breaker.

        Args:
            target: Identifier for the target (agent name, server ID).
            fn: Async function to call.
            *args, **kwargs: Arguments for fn.

        Returns:
            Result from fn.

        Raises:
            CircuitBreakerOpen: If circuit is open.
            Exception: Re-raises any exception from fn.
        """
        state = self.get_state(target)

        if state == CircuitState.OPEN:
            logger.warning("circuit_breaker_open", target=target)
            raise CircuitBreakerOpen(f"Circuit breaker open for: {target}")

        if state == CircuitState.HALF_OPEN:
            calls = self._half_open_calls.get(target, 0)
            if calls >= self.config.half_open_max_calls:
                logger.warning("circuit_half_open_limit", target=target)
                raise CircuitBreakerOpen(f"Circuit half-open limit reached for: {target}")
            self._half_open_calls[target] = calls + 1

        try:
            result = await fn(*args, **kwargs)
            self._on_success(target)
            return result
        except Exception as e:
            self._on_failure(target)
            raise

    def _on_success(self, target: str) -> None:
        """Record a successful call."""
        state = self._states.get(target, CircuitState.CLOSED)

        if state == CircuitState.HALF_OPEN:
            self._success_counts[target] = self._success_counts.get(target, 0) + 1
            if self._success_counts[target] >= self.config.success_threshold:
                self._close_circuit(target)
        else:
            # Reset failure count on success in closed state
            self._failure_counts[target] = 0

    def _on_failure(self, target: str) -> None:
        """Record a failed call."""
        self._failure_counts[target] = self._failure_counts.get(target, 0) + 1
        self._last_failure_time[target] = datetime.utcnow()

        if self._failure_counts[target] >= self.config.failure_threshold:
            self._open_circuit(target)

    def _open_circuit(self, target: str) -> None:
        """Open the circuit for a target."""
        self._states[target] = CircuitState.OPEN
        logger.error("circuit_breaker_opened", target=target, failures=self._failure_counts[target])

    def _close_circuit(self, target: str) -> None:
        """Close the circuit for a target."""
        self._states[target] = CircuitState.CLOSED
        self._failure_counts[target] = 0
        self._success_counts[target] = 0
        self._half_open_calls[target] = 0
        logger.info("circuit_breaker_closed", target=target)

    def reset(self, target: str) -> None:
        """Manually reset circuit for a target."""
        self._states.pop(target, None)
        self._failure_counts.pop(target, None)
        self._success_counts.pop(target, None)
        self._last_failure_time.pop(target, None)
        self._half_open_calls.pop(target, None)
        logger.info("circuit_breaker_reset", target=target)

    def get_stats(self, target: str) -> dict[str, Any]:
        """Get circuit breaker statistics for a target."""
        return {
            "target": target,
            "state": self.get_state(target).value,
            "failure_count": self._failure_counts.get(target, 0),
            "success_count": self._success_counts.get(target, 0),
            "last_failure": self._last_failure_time.get(target),
        }


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass
