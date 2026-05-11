"""Memory backend protocol.

Forge agents share memory through a unified fabric, enabling cross-session
context and episodic recall.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MemoryEntry:
    """A single entry in the shared memory fabric."""

    key: str
    value: Any
    namespace: str = "default"
    agent_id: str | None = None
    workflow_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int | None = None  # None = immortal
    tags: list[str] = field(default_factory=list)


class MemoryBackend(ABC):
    """Abstract memory backend — implementations: Redis, in-memory, vector DB."""

    @abstractmethod
    async def write(self, entry: MemoryEntry) -> None:
        """Store a memory entry."""
        ...

    @abstractmethod
    async def read(self, key: str, namespace: str = "default") -> MemoryEntry | None:
        """Retrieve a memory entry by key."""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Semantic search over memory entries (if backend supports vectors)."""
        ...

    @abstractmethod
    async def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete a memory entry. Returns True if existed."""
        ...

    @abstractmethod
    async def list_keys(self, namespace: str = "default") -> list[str]:
        """List all keys in a namespace."""
        ...

    @abstractmethod
    async def clear_namespace(self, namespace: str = "default") -> None:
        """Remove all entries in a namespace."""
        ...
