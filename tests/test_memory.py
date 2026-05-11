"""Tests for the Memory Fabric."""

from __future__ import annotations

import pytest

from forge.memory.fabric import InMemoryBackend, MemoryFabric
from forge.protocols.memory import MemoryEntry


class TestMemoryFabric:
    """Test suite for memory operations."""

    @pytest.fixture
    async def fabric(self):
        backend = InMemoryBackend()
        return MemoryFabric(backend=backend)

    @pytest.mark.asyncio
    async def test_write_and_read(self, fabric: MemoryFabric) -> None:
        """Basic write/read roundtrip."""
        await fabric.write("key1", "value1", namespace="test")
        result = await fabric.read("key1", namespace="test")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_read_missing(self, fabric: MemoryFabric) -> None:
        """Reading missing key returns None."""
        result = await fabric.read("missing", namespace="test")
        assert result is None

    @pytest.mark.asyncio
    async def test_search(self, fabric: MemoryFabric) -> None:
        """Search finds matching entries."""
        await fabric.write("k1", "hello world", namespace="test", tags=["greeting"])
        await fabric.write("k2", "goodbye world", namespace="test", tags=["farewell"])

        results = await fabric.search("hello", namespace="test")
        assert len(results) == 1
        assert results[0].key == "k1"

    @pytest.mark.asyncio
    async def test_workflow_step_result(self, fabric: MemoryFabric) -> None:
        """Store and retrieve step results."""
        await fabric.write_step_result("wf-1", "step-a", {"output": "done"})
        result = await fabric.get_step_result("wf-1", "step-a")
        assert result == {"output": "done"}

    @pytest.mark.asyncio
    async def test_constitution(self, fabric: MemoryFabric) -> None:
        """Store and retrieve constitution documents."""
        await fabric.write_constitution("security", "No secrets in code")
        result = await fabric.get_constitution("security")
        assert result == "No secrets in code"

    @pytest.mark.asyncio
    async def test_namespace_isolation(self, fabric: MemoryFabric) -> None:
        """Namespaces isolate keys."""
        await fabric.write("key", "ns1-value", namespace="ns1")
        await fabric.write("key", "ns2-value", namespace="ns2")

        assert await fabric.read("key", "ns1") == "ns1-value"
        assert await fabric.read("key", "ns2") == "ns2-value"
