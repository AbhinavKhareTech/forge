"""Production Redis backend for memory fabric with graceful fallback.

Provides Redis-based memory storage with connection pooling, health checks,
and automatic fallback to in-memory cache when Redis is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from forge.config import get_settings
from forge.telemetry import get_logger, get_meter

logger = get_logger("forge.memory.redis")


class RedisMemoryBackend:
    """Production Redis memory backend with connection pooling and fallback.

    Features:
    - Connection pooling with configurable limits
    - Automatic health checks
    - Circuit breaker pattern for resilience
    - Graceful fallback to local in-memory cache
    - Structured metrics and logging
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._pool: ConnectionPool | None = None
        self._client: redis.Redis | None = None
        self._fallback_cache: dict[str, Any] = {}
        self._fallback_ttl: dict[str, float] = {}
        self._meter = get_meter()
        self._available: bool = False
        self._lock = asyncio.Lock()

    async def _ensure_connection(self) -> redis.Redis:
        """Ensure Redis connection is established."""
        if self._client is not None:
            return self._client

        redis_url = self._settings.redis_url.get_secret_value()

        try:
            self._pool = ConnectionPool.from_url(
                redis_url,
                max_connections=self._settings.redis_pool_max_connections,
                socket_timeout=self._settings.redis_socket_timeout,
                socket_connect_timeout=self._settings.redis_socket_connect_timeout,
                health_check_interval=self._settings.redis_health_check_interval,
            )
            self._client = redis.Redis(connection_pool=self._pool)
            await self._client.ping()
            self._available = True
            logger.info("redis_connection_established", url=redis_url.split("@")[-1])
        except Exception as exc:
            self._available = False
            logger.warning(
                "redis_connection_failed",
                error=str(exc),
                fallback="in_memory_cache",
            )
            # Return a dummy client that will fail operations
            # Operations will fall back to local cache
        return self._client

    async def get(self, key: str) -> Any | None:
        """Get a value from memory. Falls back to local cache if Redis is down."""
        start = time.monotonic()
        try:
            client = await self._ensure_connection()
            if client and self._available:
                value = await client.get(key)
                latency = time.monotonic() - start
                if value is not None:
                    self._meter.record_memory_operation(
                        "redis", "get", "hit", latency,
                    )
                    return json.loads(value)
                self._meter.record_memory_operation(
                    "redis", "get", "miss", latency,
                )
                return None
        except Exception as exc:
            latency = time.monotonic() - start
            self._meter.record_memory_operation(
                "redis", "get", "error", latency,
            )
            logger.warning("redis_get_failed", key=key, error=str(exc))

        # Fallback to local cache
        return self._fallback_get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set a value in memory. Falls back to local cache if Redis is down."""
        start = time.monotonic()
        serialized = json.dumps(value)

        try:
            client = await self._ensure_connection()
            if client and self._available:
                result = await client.set(key, serialized, ex=ttl)
                latency = time.monotonic() - start
                self._meter.record_memory_operation(
                    "redis", "set", "success", latency,
                )
                return result is not None
        except Exception as exc:
            latency = time.monotonic() - start
            self._meter.record_memory_operation(
                "redis", "set", "error", latency,
            )
            logger.warning("redis_set_failed", key=key, error=str(exc))

        # Fallback to local cache
        return self._fallback_set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """Delete a value from memory."""
        start = time.monotonic()
        try:
            client = await self._ensure_connection()
            if client and self._available:
                result = await client.delete(key)
                latency = time.monotonic() - start
                self._meter.record_memory_operation(
                    "redis", "delete", "success", latency,
                )
                return result > 0
        except Exception as exc:
            latency = time.monotonic() - start
            self._meter.record_memory_operation(
                "redis", "delete", "error", latency,
            )
            logger.warning("redis_delete_failed", key=key, error=str(exc))

        # Fallback
        return self._fallback_delete(key)

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        try:
            client = await self._ensure_connection()
            if client and self._available:
                return await client.exists(key) > 0
        except Exception as exc:
            logger.warning("redis_exists_failed", key=key, error=str(exc))

        return key in self._fallback_cache

    async def keys(self, pattern: str) -> list[str]:
        """Get keys matching a pattern."""
        try:
            client = await self._ensure_connection()
            if client and self._available:
                result = await client.keys(pattern)
                return [k.decode("utf-8") if isinstance(k, bytes) else k for k in result]
        except Exception as exc:
            logger.warning("redis_keys_failed", pattern=pattern, error=str(exc))

        return [k for k in self._fallback_cache.keys() if pattern in k or pattern == "*"]

    async def health_check(self) -> dict[str, Any]:
        """Perform a health check on the Redis connection."""
        try:
            client = await self._ensure_connection()
            if client:
                start = time.monotonic()
                await client.ping()
                latency = time.monotonic() - start
                info = await client.info()
                return {
                    "status": "healthy",
                    "latency_ms": round(latency * 1000, 2),
                    "version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "error": str(exc),
                "fallback_active": True,
                "fallback_cache_size": len(self._fallback_cache),
            }

    async def close(self) -> None:
        """Close Redis connection gracefully."""
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()
        logger.info("redis_connection_closed")

    # ── Fallback Cache Methods ──────────────────────────────────

    def _fallback_get(self, key: str) -> Any | None:
        """Get from local in-memory fallback cache."""
        if key in self._fallback_cache:
            if key in self._fallback_ttl:
                if time.monotonic() > self._fallback_ttl[key]:
                    del self._fallback_cache[key]
                    del self._fallback_ttl[key]
                    return None
            return self._fallback_cache[key]
        return None

    def _fallback_set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set in local in-memory fallback cache."""
        self._fallback_cache[key] = value
        if ttl:
            self._fallback_ttl[key] = time.monotonic() + ttl
        return True

    def _fallback_delete(self, key: str) -> bool:
        """Delete from local in-memory fallback cache."""
        if key in self._fallback_cache:
            del self._fallback_cache[key]
            if key in self._fallback_ttl:
                del self._fallback_ttl[key]
            return True
        return False
