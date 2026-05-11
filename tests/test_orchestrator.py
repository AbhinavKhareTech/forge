"""Tests for the Orchestrator."""

from __future__ import annotations

import pytest

from forge.core.orchestrator import Orchestrator, WorkflowStatus
from forge.core.spec_engine import SpecEngine


class TestOrchestrator:
    """Test suite for workflow orchestration."""

    @pytest.mark.asyncio
    async def test_start_workflow(self, orchestrator: Orchestrator, tmp_path) -> None:
        """Start a workflow from a valid spec."""
        spec_file = tmp_path / "specs" / "test.yaml"
        spec_file.parent.mkdir(parents=True)
        spec_file.write_text("""
id: SPEC-ORCH-001
title: Orchestrator Test
steps:
  - id: step-1
    type: plan
    title: Plan
    agent_role: planner
    depends_on: []
""")
        orchestrator.spec_engine.load_from_yaml(spec_file)
        workflow = await orchestrator.start_workflow("SPEC-ORCH-001")

        assert workflow.workflow_id.startswith("wf-SPEC-ORCH-001-")
        assert workflow.spec_id == "SPEC-ORCH-001"
        assert workflow.status in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING)

    def test_workflow_completion_rate(self) -> None:
        """Calculate workflow completion percentage."""
        from forge.core.orchestrator import Workflow, StepExecution
        from forge.protocols.agent import AgentStatus

        wf = Workflow(workflow_id="wf-1", spec_id="SPEC-1")
        wf.steps["s1"] = StepExecution(step_id="s1", status=AgentStatus.COMPLETED)
        wf.steps["s2"] = StepExecution(step_id="s2", status=AgentStatus.PENDING)

        assert wf.completion_rate() == 0.5

    def test_workflow_not_blocked(self) -> None:
        """Workflow with no blocked steps."""
        from forge.core.orchestrator import Workflow, StepExecution
        from forge.protocols.agent import AgentStatus

        wf = Workflow(workflow_id="wf-1", spec_id="SPEC-1")
        wf.steps["s1"] = StepExecution(step_id="s1", status=AgentStatus.COMPLETED)
        assert not wf.is_blocked()
