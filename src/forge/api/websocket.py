"""WebSocket endpoint for real-time Forge updates."""

from __future__ import annotations

from typing import Any

from forge.utils.logging import get_logger

logger = get_logger("forge.api.websocket")

try:
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
    ws_router = APIRouter()
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    ws_router = None  # type: ignore


if HAS_FASTAPI:
    class ConnectionManager:
        """Manage WebSocket connections."""

        def __init__(self) -> None:
            self.active_connections: list[WebSocket] = []

        async def connect(self, websocket: WebSocket) -> None:
            await websocket.accept()
            self.active_connections.append(websocket)
            logger.info("websocket_connected", connections=len(self.active_connections))

        def disconnect(self, websocket: WebSocket) -> None:
            self.active_connections.remove(websocket)
            logger.info("websocket_disconnected", connections=len(self.active_connections))

        async def broadcast(self, message: dict[str, Any]) -> None:
            for connection in self.active_connections:
                await connection.send_json(message)

    manager = ConnectionManager()

    @ws_router.websocket("/events")
    async def websocket_events(websocket: WebSocket) -> None:
        """WebSocket for real-time workflow events."""
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                await websocket.send_json({"type": "echo", "data": data})
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @ws_router.websocket("/workflows/{workflow_id}")
    async def websocket_workflow(websocket: WebSocket, workflow_id: str) -> None:
        """WebSocket for specific workflow updates."""
        await manager.connect(websocket)
        await websocket.send_json({"type": "subscribed", "workflow_id": workflow_id})
        try:
            while True:
                data = await websocket.receive_text()
                await websocket.send_json({"type": "workflow_update", "workflow_id": workflow_id, "data": data})
        except WebSocketDisconnect:
            manager.disconnect(websocket)
