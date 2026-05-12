"""Tests for Forge Web API."""

from __future__ import annotations

import pytest


class TestAPIServer:
    """Test suite for FastAPI server."""

    def test_create_app(self) -> None:
        """FastAPI app can be created."""
        try:
            from forge.api.server import create_app
            app = create_app()
            assert app is not None
            assert app.title == "Forge API"
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_health_endpoint(self) -> None:
        """Health endpoint returns status."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "checks" in data
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_ready_endpoint(self) -> None:
        """Ready endpoint returns status."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/ready")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_root_endpoint(self) -> None:
        """Root endpoint returns API info."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert data["version"] == "0.1.0"
            assert "docs" in data
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_list_specs_endpoint(self) -> None:
        """Specs endpoint returns list."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/api/v1/specs")
            assert response.status_code == 200
            data = response.json()
            assert "specs" in data
            assert "count" in data
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_list_agents_endpoint(self) -> None:
        """Agents endpoint returns list."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/api/v1/agents")
            assert response.status_code == 200
            data = response.json()
            assert "agents" in data
            assert "count" in data
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_metrics_endpoint(self) -> None:
        """Metrics endpoint returns counts."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/api/v1/metrics")
            assert response.status_code == 200
            data = response.json()
            assert "workflows_total" in data
            assert "agents_registered" in data
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_run_workflow_endpoint(self) -> None:
        """Run workflow endpoint starts workflow."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.post("/api/v1/workflows/SPEC-001/run")
            assert response.status_code == 200
            data = response.json()
            assert data["spec_id"] == "SPEC-001"
            assert "workflow_id" in data
        except ImportError:
            pytest.skip("FastAPI not installed")

    def test_get_spec_not_found(self) -> None:
        """Get spec returns 404 for unknown spec."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/api/v1/specs/NONEXISTENT")
            assert response.status_code == 404
        except ImportError:
            pytest.skip("FastAPI not installed")


class TestWebSocket:
    """Test suite for WebSocket endpoints."""

    def test_websocket_connection(self) -> None:
        """WebSocket accepts connections."""
        try:
            from forge.api.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            with client.websocket_connect("/ws/events") as websocket:
                websocket.send_text("hello")
                data = websocket.receive_json()
                assert data["type"] == "echo"
        except ImportError:
            pytest.skip("FastAPI not installed")
