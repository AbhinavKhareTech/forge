"""Redis backend for the Memory Fabric.

Provides persistent, distributed memory with TTL support,
vector search (via Redis Stack), and pub/sub for real-time
agent coordination.
"""

from __future__ import annotations

import json
from typing import Any

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None  # type: ignore

from forge.config import get_config
from forge.protocols.memory import MemoryBackend, MemoryEntry
from forge.utils.logging import get_logger

logger = get_logger("forge.memory.redis")


class RedisBackend(MemoryBackend):
    """Production memory backend using Redis.

    Features:
    - Persistent storage across restarts
    - TTL for automatic expiration
    - Namespaced keys (forge:{namespace}:{key})
    - JSON serialization for complex values
    - Optional vector search with Redis Stack
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self.config = get_config()
        self._redis_url = redis_url or self.config.redis_url
        self._client: Any | None = None

    async def _get_client(self) -> Any:
        """Lazy initialization of Redis client."""
        if self._client is None:
            if aioredis is None:
                raise RuntimeError(
                    "redis package not installed. "
                    "Install with: pip install redis"
                )
            self._client = await aioredis.from_url(
                self._redis_url,
                decode_responses=True,
            )
            logger.info("redis_connected", url=self._redis_url)
        return self._client

    def _make_key(self, key: str, namespace: str) -> str:
        """Create a namespaced Redis key."""
        return f"forge:{namespace}:{key}"

    def _serialize(self, entry: MemoryEntry) -> str:
        """Serialize a MemoryEntry to JSON."""
        data = {
            "key": entry.key,
            "value": entry.value,
            "namespace": entry.namespace,
            "agent_id": entry.agent_id,
            "workflow_id": entry.workflow_id,
            "timestamp": entry.timestamp.isoformat(),
            "ttl_seconds": entry.ttl_seconds,
            "tags": entry.tags,
        }
        return json.dumps(data)

    def _deserialize(self, raw: str) -> MemoryEntry:
        """Deserialize JSON to MemoryEntry."""
        from datetime import datetime
        data = json.loads(raw)
        return MemoryEntry(
            key=data["key"],
            value=data["value"],
            namespace=data["namespace"],
            agent_id=data.get("agent_id"),
            workflow_id=data.get("workflow_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            ttl_seconds=data.get("ttl_seconds"),
            tags=data.get("tags", []),
        )

    async def write(self, entry: MemoryEntry) -> None:
        """Store a memory entry in Redis."""
        client = await self._get_client()
        key = self._make_key(entry.key, entry.namespace)
        value = self._serialize(entry)

        if entry.ttl_seconds:
            await client.setex(key, entry.ttl_seconds, value)
        else:
            await client.set(key, value)

        # Index tags for searchability
        for tag in entry.tags:
            tag_key = f"forge:tags:{entry.namespace}:{tag}"
            await client.sadd(tag_key, entry.key)

        logger.debug("redis_write", key=entry.key, namespace=entry.namespace)

    async def read(self, key: str, namespace: str = "default") -> MemoryEntry | None:
        """Retrieve a memory entry from Redis."""
        client = await self._get_client()
        redis_key = self._make_key(key, namespace)
        raw = await client.get(redis_key)

        if raw is None:
            return None

        return self._deserialize(raw)

    async def search(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Search memory entries by tag or key prefix.

        For full semantic search, Redis Stack with vector search is required.
        This implementation uses tag-based and substring matching.
        """
        client = await self._get_client()
        results: list[MemoryEntry] = []

        # Search by tag
        tag_key = f"forge:tags:{namespace}:{query}"
        tagged_keys = await client.smembers(tag_key)
        for key in tagged_keys:
            entry = await self.read(key, namespace)
            if entry and entry not in results:
                results.append(entry)

        # Search by key pattern
        pattern = f"forge:{namespace}:*{query}*"
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor, match=pattern, count=100)
            for redis_key in keys:
                raw = await client.get(redis_key)
                if raw:
                    entry = self._deserialize(raw)
                    if entry not in results:
                        results.append(entry)
            if cursor == 0:
                break

        return results[:limit]

    async def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete a memory entry from Redis."""
        client = await self._get_client()
        redis_key = self._make_key(key, namespace)
        result = await client.delete(redis_key)
        return result > 0

    async def list_keys(self, namespace: str = "default") -> list[str]:
        """List all keys in a namespace."""
        client = await self._get_client()
        pattern = f"forge:{namespace}:*"
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = await client.scan(cursor, match=pattern, count=100)
            for redis_key in batch:
                # Strip namespace prefix
                prefix = f"forge:{namespace}:"
                if redis_key.startswith(prefix):
                    keys.append(redis_key[len(prefix):])
            if cursor == 0:
                break
        return keys

    async def clear_namespace(self, namespace: str = "default") -> None:
        """Remove all entries in a namespace."""
        client = await self._get_client()
        pattern = f"forge:{namespace}:*"
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor, match=pattern, count=100)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
        logger.info("redis_namespace_cleared", namespace=namespace)
