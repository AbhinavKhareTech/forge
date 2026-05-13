"""Tests for the production governance runtime.

Covers rule-based fallback, audit logging, and Trident integration.
"""

from __future__ import annotations

import pytest

from forge.config import get_settings
from forge.governance.runtime import (
    GovernanceRuntime,
    GovernanceDecision,
    GovernanceContext,
    RuleBasedGovernance,
    AuditLogger,
)


class TestRuleBasedGovernance:
    """Test the fallback rule-based governance engine."""

    def test_blocked_actions_always_blocked(self):
        """Critical blocked actions should always return BLOCK."""
        engine = RuleBasedGovernance()
        context = GovernanceContext(
            spec_id="SPEC-001",
            agent_id="agent-1",
            agent_type="coder",
            action="delete_all_data",
            resource="production_db",
        )
        result = engine.evaluate(context)
        assert result.decision == GovernanceDecision.BLOCK
        assert result.confidence == 1.0
        assert "permanently blocked" in result.reason

    def test_critical_action_on_sensitive_resource_blocked(self):
        """Critical actions on sensitive resources should be blocked."""
        engine = RuleBasedGovernance()
        context = GovernanceContext(
            spec_id="SPEC-001",
            agent_id="agent-1",
            agent_type="sre",
            action="delete_database",
            resource="production_customer_data",
        )
        result = engine.evaluate(context)
        assert result.decision == GovernanceDecision.BLOCK
        assert result.confidence == 0.95

    def test_critical_action_requires_review(self):
        """Critical actions on non-sensitive resources require review."""
        engine = RuleBasedGovernance()
        context = GovernanceContext(
            spec_id="SPEC-001",
            agent_id="agent-1",
            agent_type="sre",
            action="deploy_to_production",
            resource="staging_app",
        )
        result = engine.evaluate(context)
        assert result.decision == GovernanceDecision.REVIEW
        assert result.confidence == 0.85

    def test_sensitive_resource_requires_review(self):
        """Actions on sensitive resources require review."""
        engine = RuleBasedGovernance()
        context = GovernanceContext(
            spec_id="SPEC-001",
            agent_id="agent-1",
            agent_type="coder",
            action="read_data",
            resource="customer_payment_records",
        )
        result = engine.evaluate(context)
        assert result.decision == GovernanceDecision.REVIEW
        assert result.confidence == 0.75

    def test_safe_action_allowed(self):
        """Safe actions should be allowed."""
        engine = RuleBasedGovernance()
        context = GovernanceContext(
            spec_id="SPEC-001",
            agent_id="agent-1",
            agent_type="planner",
            action="design_flow",
            resource="spec_document",
        )
        result = engine.evaluate(context)
        assert result.decision == GovernanceDecision.ALLOW
        assert result.confidence == 0.99


class TestAuditLogger:
    """Test audit logging functionality."""

    def test_audit_entry_computed_hash(self, tmp_path):
        """Audit entries should have a computed hash for tamper detection."""
        import json

        settings = get_settings()
        # Override audit log path for testing
        settings.governance_audit_log_path = str(tmp_path / "audit.log")

        logger = AuditLogger(settings)
        context = GovernanceContext(
            spec_id="SPEC-001",
            agent_id="agent-1",
            agent_type="coder",
            action="test_action",
            resource="test_resource",
        )
        result = GovernanceResult(
            decision=GovernanceDecision.ALLOW,
            confidence=0.95,
            reason="Test reason",
            context=context,
        )
        logger.log(result)

        # Read the audit log
        with open(settings.governance_audit_log_path) as f:
            entry = json.loads(f.readline())

        assert entry["event_type"] == "governance_decision"
        assert entry["decision"] == "ALLOW"
        assert "entry_hash" in entry
        assert len(entry["entry_hash"]) == 64  # SHA-256 hex


class TestGovernanceRuntime:
    """Test the full governance runtime with fallback."""

    @pytest.mark.asyncio
    async def test_fallback_to_rules_when_trident_disabled(self, test_settings):
        """When Trident is disabled, should use rule-based fallback."""
        test_settings.trident_mode = "disabled"
        runtime = GovernanceRuntime(test_settings)

        result = await runtime.evaluate(
            spec_id="SPEC-001",
            agent_id="agent-1",
            agent_type="coder",
            action="delete_database",
            resource="production_db",
        )

        assert result.decision == GovernanceDecision.BLOCK
        assert "[FALLBACK]" in result.reason
        assert result.metadata.get("trident_fallback") is True

    @pytest.mark.asyncio
    async def test_fail_closed_when_trident_fails_strict_mode(self, test_settings):
        """In strict mode, Trident failure should fail closed (BLOCK)."""
        test_settings.trident_mode = "enabled"
        test_settings.trident_url = "http://invalid-host:9999"  # Will fail
        runtime = GovernanceRuntime(test_settings)

        result = await runtime.evaluate(
            spec_id="SPEC-001",
            agent_id="agent-1",
            agent_type="coder",
            action="read_data",
            resource="test_resource",
        )

        assert result.decision == GovernanceDecision.BLOCK
        assert "fail_closed" in result.metadata

    @pytest.mark.asyncio
    async def test_batch_evaluate(self, test_settings):
        """Batch evaluation should process multiple requests."""
        test_settings.trident_mode = "disabled"
        runtime = GovernanceRuntime(test_settings)

        requests = [
            {
                "spec_id": "SPEC-001",
                "agent_id": "agent-1",
                "agent_type": "coder",
                "action": "safe_action",
                "resource": "test",
            },
            {
                "spec_id": "SPEC-002",
                "agent_id": "agent-2",
                "agent_type": "sre",
                "action": "delete_database",
                "resource": "production",
            },
        ]

        results = await runtime.batch_evaluate(requests)
        assert len(results) == 2
        assert results[0].decision == GovernanceDecision.ALLOW
        assert results[1].decision == GovernanceDecision.BLOCK
