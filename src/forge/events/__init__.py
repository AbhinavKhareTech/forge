"""Event system for Forge.

Provides real-time event streaming for workflow monitoring,
agent telemetry, and dashboard updates via SSE.
"""

from forge.events.bus import EventBus, WorkflowEvent, EventType

__all__ = ["EventBus", "WorkflowEvent", "EventType"]
