"""Retry policies with exponential backoff."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from forge.utils.logging import get_logger

logger = get_logger("forge.resilience.retry")

T = TypeVar("T")


def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """Calculate delay for exponential backoff.

    Args:
        attempt: Zero-based attempt number.
        base_delay: Base delay in seconds.
        max_delay: Maximum delay cap.
        jitter: Add random jitter to prevent thundering herd.

    Returns:
        Delay in seconds before next retry.
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random() * 0.5)
    return delay


@dataclass
class RetryPolicy:
    """Configurable retry policy."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    on_retry: Callable[[Exception, int, float], None] | None = None

    async def execute(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute fn with retry logic.

        Args:
            fn: Async function to call.
            *args, **kwargs: Arguments for fn.

        Returns:
            Result from fn on success.

        Raises:
            Exception: Last exception after all retries exhausted.
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_attempts):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if not isinstance(e, self.retryable_exceptions):
                    raise

                if attempt < self.max_attempts - 1:
                    delay = exponential_backoff(
                        attempt,
                        self.base_delay,
                        self.max_delay,
                    )

                    if self.on_retry:
                        self.on_retry(e, attempt + 1, delay)

                    logger.warning(
                        "retry_attempt",
                        attempt=attempt + 1,
                        max_attempts=self.max_attempts,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "retry_exhausted",
                        attempts=self.max_attempts,
                        error=str(e),
                    )

        if last_exception:
            raise last_exception

        raise RuntimeError("Retry logic reached unreachable state")
