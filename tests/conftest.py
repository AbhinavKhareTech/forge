"""Pytest fixtures and configuration for Forge tests."""

from __future__ import annotations

import pytest

from forge.config import ForgeConfig, reset_config
from forge.core.agent_registry import AgentRegistry
from forge.core.orchestrator import Orchestrator
from forge.core.spec_engine import SpecEngine
from forge.governance.runtime import GovernanceRuntime
from forge.memory.fabric import InMemoryBackend, MemoryFabric
from forge.mcp.mesh import MCPMesh


@pytest.fixture(autouse=True)
def reset_forge_config():
    """Reset global config before each test."""
    reset_config()
    yield
    reset_config()


@pytest.fixture
def forge_config() -> ForgeConfig:
    """Default test configuration."""
    return ForgeConfig(
        env="development",
        log_level="debug",
        governance_enabled=True,
        trident_enabled=False,
        max_concurrent_agents=5,
        human_checkpoint_threshold=0.7,
    )


@pytest.fixture
def memory_fabric() -> MemoryFabric:
    """In-memory memory fabric for testing."""
    return MemoryFabric(backend=InMemoryBackend())


@pytest.fixture
def spec_engine(tmp_path) -> SpecEngine:
    """Spec engine with temp directory."""
    return SpecEngine(spec_dir=tmp_path / "specs")


@pytest.fixture
def agent_registry(tmp_path) -> AgentRegistry:
    """Agent registry with temp config path."""
    return AgentRegistry(config_path=tmp_path / "agents.yaml")


@pytest.fixture
def governance_runtime() -> GovernanceRuntime:
    """Governance runtime with default policies."""
    gov = GovernanceRuntime()
    gov.load_policies([
        {
            "name": "no_prod_deploy_without_approval",
            "condition": {"forbidden_actions": ["deploy_prod"]},
            "action": "block",
            "description": "Production deployment requires explicit approval",
        },
        {
            "name": "coder_cannot_delete_db",
            "condition": {
                "forbidden_roles": ["coder"],
                "forbidden_actions": ["delete_database"],
            },
            "action": "block",
            "description": "Coders cannot delete databases",
        },
    ])
    return gov


@pytest.fixture
def mcp_mesh() -> MCPMesh:
    """MCP mesh instance."""
    return MCPMesh()


@pytest.fixture
def orchestrator(spec_engine, agent_registry, memory_fabric, governance_runtime) -> Orchestrator:
    """Fully configured orchestrator for integration tests."""
    return Orchestrator(
        spec_engine=spec_engine,
        agent_registry=agent_registry,
        memory=memory_fabric,
        governance=governance_runtime,
    )
