"""Memory Fabric — unified memory layer for agent teams.

Agents read from and write to the Memory Fabric instead of maintaining
local state. This enables:
- Cross-session context persistence
- Episodic recall ("what did the coder agent do last Tuesday?")
- Semantic search over past agent outputs
- Workflow traceability and audit

Backends: Redis (production), in-memory (testing/development).
"""

from __future__ import annotations

import json
from typing import Any

from forge.config import get_config
from forge.protocols.memory import MemoryBackend, MemoryEntry
from forge.utils.logging import get_logger

logger = get_logger("forge.memory")


class InMemoryBackend(MemoryBackend):
    """In-memory memory backend for development and testing."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, MemoryEntry]] = {}

    async def write(self, entry: MemoryEntry) -> None:
        if entry.namespace not in self._store:
            self._store[entry.namespace] = {}
        self._store[entry.namespace][entry.key] = entry

    async def read(self, key: str, namespace: str = "default") -> MemoryEntry | None:
        return self._store.get(namespace, {}).get(key)

    async def search(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 10,
    ) -> list[MemoryEntry]:
        # Simple substring search for in-memory backend
        entries = self._store.get(namespace, {}).values()
        results = [
            e for e in entries
            if query.lower() in str(e.value).lower() or query.lower() in " ".join(e.tags).lower()
        ]
        return results[:limit]

    async def delete(self, key: str, namespace: str = "default") -> bool:
        ns = self._store.get(namespace, {})
        if key in ns:
            del ns[key]
            return True
        return False

    async def list_keys(self, namespace: str = "default") -> list[str]:
        return list(self._store.get(namespace, {}).keys())

    async def clear_namespace(self, namespace: str = "default") -> None:
        if namespace in self._store:
            self._store[namespace] = {}


class MemoryFabric:
    """High-level memory interface for Forge workflows and agents.

    Provides structured namespaces for different memory types:
    - workflow:{id}: Step results and context for a specific workflow
    - agent:{name}: Agent-specific learning and preferences
    - org: Organization-wide constitutions and standards
    - episodic: Time-indexed event log
    """

    def __init__(self, backend: MemoryBackend | None = None) -> None:
        self.config = get_config()
        self._backend = backend or InMemoryBackend()

    async def write(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        agent_id: str | None = None,
        workflow_id: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Write a value to the memory fabric."""
        entry = MemoryEntry(
            key=key,
            value=value,
            namespace=namespace,
            agent_id=agent_id,
            workflow_id=workflow_id,
            tags=tags or [],
        )
        await self._backend.write(entry)
        logger.debug("memory_write", key=key, namespace=namespace, agent=agent_id)

    async def read(self, key: str, namespace: str = "default") -> Any | None:
        """Read a value from the memory fabric."""
        entry = await self._backend.read(key, namespace)
        return entry.value if entry else None

    async def search(
        self,
        query: str,
        namespace: str = "default",
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Semantic search over memory entries."""
        return await self._backend.search(query, namespace, limit)

    async def write_step_result(
        self,
        workflow_id: str,
        step_id: str,
        result: Any,
    ) -> None:
        """Store an agent step result in the workflow namespace."""
        namespace = f"workflow:{workflow_id}"
        key = f"step:{step_id}"
        await self.write(
            key=key,
            value=result,
            namespace=namespace,
            workflow_id=workflow_id,
            tags=["step_result", step_id],
        )

    async def get_step_result(
        self,
        workflow_id: str,
        step_id: str,
    ) -> Any | None:
        """Retrieve a step result from a workflow."""
        namespace = f"workflow:{workflow_id}"
        key = f"step:{step_id}"
        return await self.read(key, namespace)

    async def write_constitution(self, name: str, content: str) -> None:
        """Store an organizational constitution document."""
        await self.write(
            key=f"constitution:{name}",
            value=content,
            namespace="org",
            tags=["constitution", "policy"],
        )

    async def get_constitution(self, name: str) -> str | None:
        """Retrieve a constitution document."""
        result = await self.read(f"constitution:{name}", namespace="org")
        return result if isinstance(result, str) else None

    async def log_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
        workflow_id: str | None = None,
    ) -> None:
        """Write an episodic event to the audit log."""
        import time
        key = f"event:{time.time():.6f}"
        await self.write(
            key=key,
            value={"type": event_type, "payload": payload, "timestamp": key},
            namespace="episodic",
            agent_id=agent_id,
            workflow_id=workflow_id,
            tags=["event", event_type],
        )

    async def get_workflow_history(self, workflow_id: str) -> list[MemoryEntry]:
        """Get all memory entries for a workflow."""
        namespace = f"workflow:{workflow_id}"
        keys = await self._backend.list_keys(namespace)
        entries: list[MemoryEntry] = []
        for key in keys:
            entry = await self._backend.read(key, namespace)
            if entry:
                entries.append(entry)
        return entries
