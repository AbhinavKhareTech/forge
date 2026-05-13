"""Tests for event system."""

from __future__ import annotations

import pytest

from forge.events.bus import EventBus, EventType, WorkflowEvent


class TestEventBus:
    """Test suite for event bus."""

    @pytest.fixture(autouse=True)
    def reset_bus(self):
        """Reset singleton between tests."""
        EventBus._instance = None
        yield
        EventBus._instance = None

    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.mark.asyncio
    async def test_publish_single_subscriber(self, bus: EventBus) -> None:
        """Event reaches single subscriber."""
        received: list[WorkflowEvent] = []

        async def handler(event: WorkflowEvent) -> None:
            received.append(event)

        bus.subscribe(EventType.WORKFLOW_STARTED, handler)
        await bus.emit(EventType.WORKFLOW_STARTED, workflow_id="wf-1")

        assert len(received) == 1
        assert received[0].event_type == EventType.WORKFLOW_STARTED
        assert received[0].workflow_id == "wf-1"

    @pytest.mark.asyncio
    async def test_publish_multiple_subscribers(self, bus: EventBus) -> None:
        """Event reaches multiple subscribers."""
        count = 0

        async def handler1(event: WorkflowEvent) -> None:
            nonlocal count
            count += 1

        async def handler2(event: WorkflowEvent) -> None:
            nonlocal count
            count += 1

        bus.subscribe(EventType.WORKFLOW_STARTED, handler1)
        bus.subscribe(EventType.WORKFLOW_STARTED, handler2)
        await bus.emit(EventType.WORKFLOW_STARTED)

        assert count == 2

    @pytest.mark.asyncio
    async def test_subscribe_all(self, bus: EventBus) -> None:
        """Subscribe_all receives all event types."""
        received: list[str] = []

        async def handler(event: WorkflowEvent) -> None:
            received.append(event.event_type.value)

        bus.subscribe_all(handler)
        await bus.emit(EventType.WORKFLOW_STARTED)
        await bus.emit(EventType.STEP_COMPLETED)

        assert len(received) == 2
        assert "workflow_started" in received
        assert "step_completed" in received

    @pytest.mark.asyncio
    async def test_no_subscribers(self, bus: EventBus) -> None:
        """Publishing with no subscribers is safe."""
        await bus.emit(EventType.WORKFLOW_STARTED)
        assert bus.get_subscriber_count(EventType.WORKFLOW_STARTED) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus: EventBus) -> None:
        """Unsubscribe removes handler."""
        received: list[WorkflowEvent] = []

        async def handler(event: WorkflowEvent) -> None:
            received.append(event)

        bus.subscribe(EventType.WORKFLOW_STARTED, handler)
        bus.unsubscribe(EventType.WORKFLOW_STARTED, handler)
        await bus.emit(EventType.WORKFLOW_STARTED)

        assert len(received) == 0

    def test_event_creation(self) -> None:
        """WorkflowEvent stores all fields."""
        event = WorkflowEvent(
            event_type=EventType.STEP_FAILED,
            workflow_id="wf-1",
            spec_id="SPEC-1",
            step_id="step-1",
            agent_name="coder",
            payload={"error": "timeout"},
        )
        assert event.event_type == EventType.STEP_FAILED
        assert event.workflow_id == "wf-1"
        assert event.payload["error"] == "timeout"


class TestAuth:
    """Test suite for API key auth."""

    def test_disabled_when_no_key(self) -> None:
        """Auth disabled when FORGE_API_KEY not set."""
        import os
        old_key = os.environ.pop("FORGE_API_KEY", None)
        try:
            from forge.auth.middleware import APIKeyAuth
            auth = APIKeyAuth()
            assert auth.is_enabled() is False
            assert auth.validate(None) is True
            assert auth.validate("anything") is True
        finally:
            if old_key:
                os.environ["FORGE_API_KEY"] = old_key

    def test_enabled_with_key(self) -> None:
        """Auth enabled when FORGE_API_KEY set."""
        import os
        old_key = os.environ.get("FORGE_API_KEY")
        os.environ["FORGE_API_KEY"] = "secret123"
        try:
            from forge.auth.middleware import APIKeyAuth
            auth = APIKeyAuth()
            assert auth.is_enabled() is True
            assert auth.validate("secret123") is True
            assert auth.validate("wrong") is False
            assert auth.validate(None) is False
        finally:
            if old_key:
                os.environ["FORGE_API_KEY"] = old_key
            else:
                os.environ.pop("FORGE_API_KEY", None)
