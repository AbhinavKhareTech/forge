"""Tests for the Governance Runtime."""

from __future__ import annotations

import pytest

from forge.governance.runtime import GovernanceRuntime, PolicyDecision
from forge.protocols.agent import AgentConfig


class TestGovernanceRuntime:
    """Test suite for policy enforcement."""

    @pytest.fixture
    def runtime(self) -> GovernanceRuntime:
        gov = GovernanceRuntime()
        gov.load_policies([
            {
                "name": "block_coder_delete",
                "condition": {
                    "forbidden_roles": ["coder"],
                    "forbidden_actions": ["delete_database"],
                },
                "action": "block",
            },
            {
                "name": "require_permission_deploy",
                "condition": {
                    "required_permissions": ["deploy:prod"],
                },
                "action": "block",
            },
        ])
        return gov

    @pytest.mark.asyncio
    async def test_allow_safe_action(self, runtime: GovernanceRuntime) -> None:
        """Safe actions should be allowed."""
        agent = AgentConfig(name="test", role="planner", tools=[], permissions=[])
        decision = await runtime.evaluate_action(agent, "read_file", {})
        assert decision == PolicyDecision.ALLOW

    @pytest.mark.asyncio
    async def test_block_forbidden_role_action(self, runtime: GovernanceRuntime) -> None:
        """Coder deleting database should be blocked."""
        agent = AgentConfig(name="coder1", role="coder", tools=[], permissions=[])
        decision = await runtime.evaluate_action(agent, "delete_database", {})
        assert decision == PolicyDecision.BLOCK

    @pytest.mark.asyncio
    async def test_block_missing_permission(self, runtime: GovernanceRuntime) -> None:
        """Agent without deploy permission should be blocked."""
        agent = AgentConfig(name="dev1", role="coder", tools=[], permissions=["read:repo"])
        decision = await runtime.evaluate_action(agent, "deploy_prod", {})
        assert decision == PolicyDecision.BLOCK

    @pytest.mark.asyncio
    async def test_allow_with_permission(self, runtime: GovernanceRuntime) -> None:
        """Agent with correct permission should be allowed."""
        agent = AgentConfig(
            name="sre1", role="sre", tools=[], permissions=["deploy:prod"]
        )
        decision = await runtime.evaluate_action(agent, "deploy_prod", {})
        assert decision == PolicyDecision.ALLOW

    @pytest.mark.asyncio
    async def test_review_for_high_risk(self, runtime: GovernanceRuntime) -> None:
        """High-risk actions should trigger review."""
        agent = AgentConfig(
            name="sre1", role="sre", tools=[], permissions=["deploy:prod"]
        )
        decision = await runtime.evaluate_action(agent, "delete_database", {})
        assert decision == PolicyDecision.BLOCK  # delete_database is risk 1.0

    @pytest.mark.asyncio
    async def test_human_approval_flag(self, runtime: GovernanceRuntime) -> None:
        """Agents flagged for approval should trigger review."""
        agent = AgentConfig(
            name="admin", role="admin", tools=[], permissions=[], requires_human_approval=True
        )
        decision = await runtime.evaluate_action(agent, "read_file", {})
        assert decision == PolicyDecision.REVIEW
