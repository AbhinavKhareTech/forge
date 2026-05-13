"""Integration tests using real dependencies via testcontainers.

Tests the full spec execution pipeline with PostgreSQL, Redis, and governance.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from forge.config import get_settings
from forge.core.orchestrator import Orchestrator, OrchestratorSpec, OrchestratorStep, SpecStatus
from forge.governance.runtime import GovernanceRuntime, GovernanceDecision
from forge.telemetry.health import HealthChecker


@pytest.mark.integration
@pytest.mark.asyncio
class TestFullSpecExecution:
    """End-to-end spec execution tests."""

    async def test_simple_spec_execution(self, test_settings, db_engine):
        """Execute a simple two-step spec successfully."""
        orchestrator = Orchestrator(test_settings)

        spec = OrchestratorSpec(
            spec_id="SPEC-INT-001",
            steps=[
                OrchestratorStep(
                    step_id="plan",
                    agent_type="planner",
                    depends_on=[],
                    input_data={"task": "design auth flow"},
                ),
                OrchestratorStep(
                    step_id="code",
                    agent_type="coder",
                    depends_on=["plan"],
                    input_data={"task": "implement auth service"},
                ),
            ],
        )

        result = await orchestrator.execute_spec(spec)
        assert result == SpecStatus.COMPLETED

        # Verify checkpoint persistence
        status = await orchestrator.get_execution_status(spec.execution_id)
        assert status is not None
        assert status["status"] == "completed"
        assert status["total_steps"] == 2
        assert status["completed_steps"] == 2

    async def test_spec_with_blocked_step(self, test_settings, db_engine):
        """Spec with a blocked step should result in PARTIAL status."""
        orchestrator = Orchestrator(test_settings)

        spec = OrchestratorSpec(
            spec_id="SPEC-INT-002",
            steps=[
                OrchestratorStep(
                    step_id="safe-step",
                    agent_type="planner",
                    depends_on=[],
                ),
                OrchestratorStep(
                    step_id="blocked-step",
                    agent_type="sre",
                    depends_on=["safe-step"],
                    input_data={"action": "delete_database"},
                ),
            ],
        )

        result = await orchestrator.execute_spec(spec)
        assert result == SpecStatus.PARTIAL

        status = await orchestrator.get_execution_status(spec.execution_id)
        assert status["completed_steps"] == 1
        assert status["failed_steps"] == 1

    async def test_spec_execution_resumption(self, test_settings, db_engine):
        """Should be able to resume an execution from checkpoints."""
        orchestrator = Orchestrator(test_settings)

        spec = OrchestratorSpec(
            spec_id="SPEC-INT-003",
            steps=[
                OrchestratorStep(step_id="step1", agent_type="planner", depends_on=[]),
                OrchestratorStep(step_id="step2", agent_type="coder", depends_on=["step1"]),
            ],
        )

        # Execute and complete
        result = await orchestrator.execute_spec(spec)
        assert result == SpecStatus.COMPLETED

        # Attempt to resume completed execution
        resumed = await orchestrator.resume_execution(spec.execution_id)
        assert resumed == SpecStatus.COMPLETED  # Already done


@pytest.mark.integration
@pytest.mark.asyncio
class TestHealthChecks:
    """Integration tests for health check system."""

    async def test_deep_health_check(self, test_settings):
        """Deep health check should validate all dependencies."""
        checker = HealthChecker()
        report = await checker.check_all()

        assert report.overall.value in ("healthy", "degraded", "unhealthy")
        assert report.version == test_settings.app_version
        assert len(report.components) >= 3  # database, redis, trident

        # Check component names
        component_names = {c.name for c in report.components}
        assert "database" in component_names
        assert "redis" in component_names
        assert "trident" in component_names

    async def test_liveness_probe(self, test_settings):
        """Liveness probe should always return healthy for running process."""
        checker = HealthChecker()
        report = await checker.liveness()

        assert report.overall.value == "healthy"
        assert report.uptime_seconds > 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestGovernanceIntegration:
    """Integration tests for governance with real dependencies."""

    async def test_governance_audit_logging(self, test_settings, tmp_path):
        """Governance decisions should be written to audit log."""
        import json

        test_settings.governance_audit_log_path = str(tmp_path / "audit.log")
        runtime = GovernanceRuntime(test_settings)

        result = await runtime.evaluate(
            spec_id="SPEC-INT-GOV",
            agent_id="agent-1",
            agent_type="coder",
            action="read_data",
            resource="test_resource",
        )

        assert result.decision in GovernanceDecision

        # Verify audit log
        with open(test_settings.governance_audit_log_path) as f:
            entry = json.loads(f.readline())

        assert entry["event_type"] == "governance_decision"
        assert entry["context"]["spec_id"] == "SPEC-INT-GOV"
        assert "entry_hash" in entry
