"""Integration tests for Forge end-to-end workflows.

These tests exercise the full orchestrator with mock agents
to validate spec-to-completion flows.
"""

from __future__ import annotations

import pytest

from forge.agents.coder import CoderAgent
from forge.agents.planner import PlannerAgent
from forge.agents.reviewer import ReviewerAgent
from forge.config import get_config
from forge.core.agent_registry import AgentRegistry
from forge.core.orchestrator import Orchestrator, WorkflowStatus
from forge.core.spec_engine import SpecEngine
from forge.governance.runtime import GovernanceRuntime
from forge.memory.fabric import InMemoryBackend, MemoryFabric
from forge.mcp.adapters.github import GitHubMCPServer
from forge.mcp.adapters.jira import JiraMCPServer
from forge.mcp.mesh import MCPMesh
from forge.protocols.agent import AgentConfig


@pytest.fixture
def demo_spec_engine(tmp_path) -> SpecEngine:
    """Spec engine loaded with the demo spec."""
    engine = SpecEngine(spec_dir=tmp_path / "specs")

    # Write demo spec
    spec_file = tmp_path / "specs" / "demo.md"
    spec_file.parent.mkdir(parents=True)
    spec_file.write_text("""---
id: DEMO-SPEC-001
title: Spec-to-PR Demo
description: End-to-end demo
constitution_refs:
  - security
---

#### STEP: plan-api
**Type:** plan
**Agent:** planner
**Depends:** []

Design a REST API for user management.

#### STEP: code-api
**Type:** code
**Agent:** coder
**Depends:** [plan-api]

Implement the API based on the plan.

#### STEP: review-api
**Type:** review
**Agent:** reviewer
**Depends:** [code-api]

Review against security constitution.
""")
    engine.load_from_markdown(spec_file)
    return engine


@pytest.fixture
def demo_agent_registry(tmp_path) -> AgentRegistry:
    """Registry with mock agents instantiated."""
    registry = AgentRegistry(config_path=tmp_path / "agents.yaml")

    # Register agent configs
    planner_cfg = AgentConfig(
        name="planner",
        role="planner",
        tools=["github_search", "jira_read"],
        permissions=["read:repo"],
    )
    coder_cfg = AgentConfig(
        name="coder",
        role="coder",
        tools=["github_read_file", "github_write_file", "github_create_pr"],
        permissions=["read:repo", "write:file"],
    )
    reviewer_cfg = AgentConfig(
        name="reviewer",
        role="reviewer",
        tools=["github_read_file", "github_pr_review"],
        permissions=["read:repo"],
    )

    registry.register_agent("planner", PlannerAgent(planner_cfg))
    registry.register_agent("coder", CoderAgent(coder_cfg))
    registry.register_agent("reviewer", ReviewerAgent(reviewer_cfg))

    return registry


@pytest.fixture
def demo_orchestrator(demo_spec_engine, demo_agent_registry) -> Orchestrator:
    """Fully configured orchestrator with demo agents."""
    memory = MemoryFabric(backend=InMemoryBackend())
    governance = GovernanceRuntime()
    governance.load_policies([
        {
            "name": "coder_cannot_delete_db",
            "condition": {
                "forbidden_roles": ["coder"],
                "forbidden_actions": ["delete_database"],
            },
            "action": "block",
        },
    ])
    return Orchestrator(
        spec_engine=demo_spec_engine,
        agent_registry=demo_agent_registry,
        memory=memory,
        governance=governance,
    )


class TestSpecToPREndToEnd:
    """End-to-end spec-to-PR workflow tests."""

    @pytest.mark.asyncio
    async def test_workflow_starts(self, demo_orchestrator: Orchestrator) -> None:
        """Workflow starts and reaches running state."""
        workflow = await demo_orchestrator.start_workflow("DEMO-SPEC-001")

        assert workflow.workflow_id.startswith("wf-DEMO-SPEC-001-")
        assert workflow.spec_id == "DEMO-SPEC-001"
        assert workflow.status in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING)
        assert len(workflow.steps) == 3

    def test_workflow_has_all_steps(self, demo_orchestrator: Orchestrator) -> None:
        """Workflow contains all spec steps."""
        spec = demo_orchestrator.spec_engine.get_spec("DEMO-SPEC-001")
        assert spec is not None
        assert len(spec.steps) == 3
        assert spec.get_step("plan-api") is not None
        assert spec.get_step("code-api") is not None
        assert spec.get_step("review-api") is not None

    def test_execution_order(self, demo_orchestrator: Orchestrator) -> None:
        """Steps execute in correct dependency order."""
        spec = demo_orchestrator.spec_engine.get_spec("DEMO-SPEC-001")
        order = spec.execution_order()

        assert order.index("plan-api") < order.index("code-api")
        assert order.index("code-api") < order.index("review-api")

    @pytest.mark.asyncio
    async def test_governance_blocks_unauthorized_action(self, demo_orchestrator: Orchestrator) -> None:
        """Governance runtime blocks unauthorized actions."""
        governance = demo_orchestrator.governance
        assert governance is not None

        # Coder without deploy permission trying to deploy
        coder = AgentConfig(name="coder", role="coder", tools=[], permissions=[])
        decision = await governance.evaluate_action(coder, "delete_database", {})
        assert decision.value == "block"

    @pytest.mark.asyncio
    async def test_governance_allows_authorized_action(self, demo_orchestrator: Orchestrator) -> None:
        """Governance allows actions with proper permissions."""
        governance = demo_orchestrator.governance
        assert governance is not None

        # Reviewer reading files is safe
        reviewer = AgentConfig(name="reviewer", role="reviewer", tools=[], permissions=["read:repo"])
        decision = await governance.evaluate_action(reviewer, "read_file", {})
        assert decision.value == "allow"


class TestMCPMesh:
    """MCP Mesh integration tests."""

    @pytest.mark.asyncio
    async def test_github_server_connect(self) -> None:
        """GitHub MCP server connects and discovers tools."""
        server = GitHubMCPServer(
            server_id="github-test",
            endpoint="https://api.github.com",
            credentials={"owner": "test", "repo": "test-repo", "token": "fake"},
        )
        connected = await server.connect()
        assert connected is True

        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "github_search" in tool_names
        assert "github_create_pr" in tool_names
        assert "github_write_file" in tool_names

    @pytest.mark.asyncio
    async def test_github_tool_call(self) -> None:
        """GitHub tool calls return mock data."""
        server = GitHubMCPServer(
            server_id="github-test",
            credentials={"owner": "test", "repo": "test-repo"},
        )
        await server.connect()

        from forge.protocols.mcp import ToolCall
        result = await server.call_tool(ToolCall(
            tool_name="github_create_pr",
            arguments={"title": "Test PR", "head": "feature"},
        ))

        assert result.success is True
        assert result.data["number"] == 42
        assert result.data["title"] == "Test PR"

    @pytest.mark.asyncio
    async def test_jira_server_connect(self) -> None:
        """Jira MCP server connects and discovers tools."""
        server = JiraMCPServer(
            server_id="jira-test",
            credentials={"project": "TEST", "token": "fake"},
        )
        connected = await server.connect()
        assert connected is True

        tools = await server.list_tools()
        tool_names = [t.name for t in tools]
        assert "jira_read" in tool_names
        assert "jira_create" in tool_names

    @pytest.mark.asyncio
    async def test_mcp_mesh_registration(self) -> None:
        """MCP Mesh registers and routes to servers."""
        mesh = MCPMesh()
        github = GitHubMCPServer(server_id="github", credentials={})
        jira = JiraMCPServer(server_id="jira", credentials={})

        mesh.register_server(github)
        mesh.register_server(jira)

        await github.connect()
        await jira.connect()
        await mesh.discover_tools()

        assert "github_search" in mesh.list_tools()
        assert "jira_read" in mesh.list_tools()


class TestAgentExecution:
    """Agent execution tests."""

    @pytest.mark.asyncio
    async def test_planner_generates_plan(self) -> None:
        """Planner agent produces a structured plan."""
        config = AgentConfig(name="planner", role="planner", tools=[])
        agent = PlannerAgent(config)

        result = await agent.execute(
            task_input={
                "step": {"id": "plan-auth", "type": "plan", "description": "Design auth with MFA"},
                "spec_id": "TEST-001",
            },
            context={},
        )

        assert result.status.value == "completed"
        assert "plan" in result.output
        assert "subtasks" in result.output["plan"]
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_coder_generates_code(self) -> None:
        """Coder agent produces code artifacts."""
        config = AgentConfig(name="coder", role="coder", tools=[])
        agent = CoderAgent(config)

        result = await agent.execute(
            task_input={
                "step": {"id": "code-auth", "type": "code", "description": "Implement auth service"},
                "spec_id": "TEST-001",
            },
            context={
                "plan": {
                    "overview": "Auth system",
                    "subtasks": [{"id": "t1", "task": "Implement login"}],
                },
            },
        )

        assert result.status.value == "completed"
        assert "code" in result.output
        assert len(result.artifacts) > 0

    @pytest.mark.asyncio
    async def test_reviewer_approves_clean_code(self) -> None:
        """Reviewer approves code with no issues."""
        config = AgentConfig(name="reviewer", role="reviewer", tools=[])
        agent = ReviewerAgent(config)

        result = await agent.execute(
            task_input={
                "step": {"id": "review-auth", "type": "review", "description": "Review auth code"},
                "spec_id": "TEST-001",
            },
            context={
                "code": {"src/auth.py": "def login(): pass"},
                "files_generated": ["src/auth.py"],
            },
        )

        assert result.status.value == "completed"
        assert "review" in result.output
        assert result.output["review"]["summary"]["total_files"] == 1
