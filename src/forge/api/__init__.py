"""Web API for Forge.

FastAPI-based REST API and WebSocket server for workflow monitoring,
agent management, and real-time dashboard updates.
"""

from forge.api.server import create_app

__all__ = ["create_app"]
