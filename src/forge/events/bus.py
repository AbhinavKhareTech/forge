"""Event bus for real-time Forge telemetry.

Enables decoupled communication between the orchestrator,
agents, and dashboard via pub/sub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable

from forge.utils.logging import get_logger

logger = get_logger("forge.events.bus")


class EventType(str, Enum):
    """Types of Forge events."""

    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_BLOCKED = "step_blocked"
    AGENT_EXECUTED = "agent_executed"
    AGENT_FAILED = "agent_failed"
    GOVERNANCE_DECISION = "governance_decision"
    MCP_TOOL_CALLED = "mcp_tool_called"
    MCP_TOOL_FAILED = "mcp_tool_failed"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_APPROVED = "checkpoint_approved"


@dataclass
class WorkflowEvent:
    """A single Forge event."""

    event_type: EventType
    workflow_id: str | None = None
    spec_id: str | None = None
    step_id: str | None = None
    agent_name: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    payload: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[WorkflowEvent], Awaitable[None]]


class EventBus:
    """In-memory pub/sub event bus for Forge.

    Subscribers register handlers for event types.
    Publishers emit events to all matching handlers.
    """

    _instance: EventBus | None = None

    def __new__(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers: dict[EventType, list[Handler]] = {}
            cls._instance._all_handlers: list[Handler] = []
        return cls._instance

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """Subscribe a handler to a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug("event_subscribed", event_type=event_type.value)

    def subscribe_all(self, handler: Handler) -> None:
        """Subscribe a handler to all events."""
        self._all_handlers.append(handler)
        logger.debug("event_subscribed_all", handler=handler.__name__)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        """Unsubscribe a handler."""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    async def publish(self, event: WorkflowEvent) -> None:
        """Publish an event to all subscribers."""
        handlers = self._handlers.get(event.event_type, [])
        all_handlers = self._all_handlers

        for handler in handlers + all_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("event_handler_failed", event=event.event_type.value, error=str(e))

    async def emit(
        self,
        event_type: EventType,
        workflow_id: str | None = None,
        spec_id: str | None = None,
        step_id: str | None = None,
        agent_name: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Convenience method to create and publish an event."""
        event = WorkflowEvent(
            event_type=event_type,
            workflow_id=workflow_id,
            spec_id=spec_id,
            step_id=step_id,
            agent_name=agent_name,
            payload=payload or {},
        )
        await self.publish(event)

    def get_subscriber_count(self, event_type: EventType) -> int:
        """Get number of subscribers for an event type."""
        return len(self._handlers.get(event_type, []))
