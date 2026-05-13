"""REST API routes for Forge."""

from __future__ import annotations

from typing import Any

from forge.config import get_config
from forge.core.spec_engine import SpecEngine
from forge.utils.logging import get_logger

logger = get_logger("forge.api.routes")

try:
    from fastapi import APIRouter, HTTPException
    router = APIRouter()
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    router = None  # type: ignore


if HAS_FASTAPI:
    @router.get("/workflows")
    async def list_workflows() -> dict[str, Any]:
        """List all workflows."""
        return {"workflows": [], "count": 0}

    @router.get("/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict[str, Any]:
        """Get workflow details."""
        return {"workflow_id": workflow_id, "status": "unknown"}

    @router.get("/specs")
    async def list_specs() -> dict[str, Any]:
        """List all specs."""
        config = get_config()
        engine = SpecEngine(spec_dir=config.spec_dir)
        spec_files = list(config.spec_dir.glob("**/*.md")) + list(config.spec_dir.glob("**/*.yaml"))
        specs = []
        for f in spec_files:
            try:
                if f.suffix == ".md":
                    spec = engine.load_from_markdown(f)
                else:
                    spec = engine.load_from_yaml(f)
                specs.append({"id": spec.id, "title": spec.title, "steps": len(spec.steps)})
            except Exception as e:
                logger.warning("spec_load_failed", file=str(f), error=str(e))
        return {"specs": specs, "count": len(specs)}

    @router.get("/specs/{spec_id}")
    async def get_spec(spec_id: str) -> dict[str, Any]:
        """Get spec details."""
        config = get_config()
        engine = SpecEngine(spec_dir=config.spec_dir)
        for f in config.spec_dir.glob("**/*.md"):
            try:
                spec = engine.load_from_markdown(f)
                if spec.id == spec_id:
                    return {
                        "id": spec.id,
                        "title": spec.title,
                        "description": spec.description,
                        "steps": [s.model_dump() for s in spec.steps],
                        "execution_order": spec.execution_order(),
                    }
            except Exception:
                pass
        raise HTTPException(status_code=404, detail=f"Spec not found: {spec_id}")

    @router.get("/agents")
    async def list_agents() -> dict[str, Any]:
        """List registered agents."""
        from forge.core.agent_registry import AgentRegistry
        config = get_config()
        registry = AgentRegistry(config_path=config.agent_registry_path)
        count = registry.load_configs()
        agents = [
            {
                "name": c.name,
                "role": c.role,
                "version": c.version,
                "tools": c.tools,
                "permissions": c.permissions,
            }
            for c in registry.list_configs()
        ]
        return {"agents": agents, "count": count}

    @router.post("/workflows/{spec_id}/run")
    async def run_workflow(spec_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start a workflow from a spec."""
        return {"workflow_id": f"wf-{spec_id}", "status": "started", "spec_id": spec_id}

    @router.get("/metrics")
    async def metrics() -> dict[str, Any]:
        """System metrics."""
        return {
            "workflows_total": 0,
            "workflows_running": 0,
            "workflows_completed": 0,
            "workflows_failed": 0,
            "agents_registered": 0,
            "mcp_servers": 0,
        }
