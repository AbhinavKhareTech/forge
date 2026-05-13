"""Server-Sent Events (SSE) for real-time Forge updates."""

from __future__ import annotations

import asyncio
from typing import Any

from forge.events.bus import EventBus, EventType, WorkflowEvent
from forge.utils.logging import get_logger

logger = get_logger("forge.api.sse")

try:
    from fastapi import APIRouter, Request
    from fastapi.responses import StreamingResponse
    sse_router = APIRouter()
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    sse_router = None  # type: ignore


if HAS_FASTAPI:
    async def event_generator(request: Request, workflow_id: str | None = None) -> Any:
        """Generate SSE events for a client connection."""
        bus = EventBus()
        queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()

        async def handler(event: WorkflowEvent) -> None:
            if workflow_id is None or event.workflow_id == workflow_id:
                await queue.put(event)

        # Subscribe to all workflow events
        for event_type in [
            EventType.WORKFLOW_STARTED,
            EventType.WORKFLOW_COMPLETED,
            EventType.WORKFLOW_FAILED,
            EventType.STEP_STARTED,
            EventType.STEP_COMPLETED,
            EventType.STEP_FAILED,
            EventType.GOVERNANCE_DECISION,
        ]:
            bus.subscribe(event_type, handler)

        logger.info("sse_client_connected", workflow_id=workflow_id)

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    data = {
                        "event": event.event_type.value,
                        "workflow_id": event.workflow_id,
                        "spec_id": event.spec_id,
                        "step_id": event.step_id,
                        "agent_name": event.agent_name,
                        "timestamp": event.timestamp,
                        "payload": event.payload,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ":keepalive\n\n"
        finally:
            logger.info("sse_client_disconnected", workflow_id=workflow_id)

    @sse_router.get("/events")
    async def sse_events(request: Request) -> StreamingResponse:
        """SSE endpoint for all workflow events."""
        import json
        return StreamingResponse(
            event_generator(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @sse_router.get("/workflows/{workflow_id}/events")
    async def sse_workflow_events(request: Request, workflow_id: str) -> StreamingResponse:
        """SSE endpoint for specific workflow events."""
        import json
        return StreamingResponse(
            event_generator(request, workflow_id=workflow_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
