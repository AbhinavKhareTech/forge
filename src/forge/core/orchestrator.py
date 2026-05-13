"""Orchestrator -- DAG-based multi-agent workflow engine.

The Orchestrator takes a compiled spec DAG and dispatches agents
according to topological order, handling concurrency, retries,
checkpoints, and governance gates.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from forge.config import get_config
from forge.core.agent_registry import AgentRegistry
from forge.core.spec_engine import Spec, SpecEngine, SpecStep
from forge.governance.runtime import GovernanceRuntime
from forge.memory.fabric import MemoryFabric
from forge.persistence.store import WorkflowStore
from forge.protocols.agent import AgentResult, AgentStatus
from forge.resilience.circuit_breaker import CircuitBreaker
from forge.resilience.retry import RetryPolicy
from forge.utils.logging import get_logger

logger = get_logger("forge.orchestrator")


class WorkflowStatus(str, Enum):
    """Lifecycle states of a Forge workflow."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"           # Waiting for human approval
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StepExecution:
    """Runtime state of a single step execution."""

    step_id: str
    status: AgentStatus = AgentStatus.PENDING
    result: AgentResult | None = None
    start_time: float | None = None
    end_time: float | None = None
    retry_count: int = 0
    checkpoint_id: str | None = None
    logs: list[str] = field(default_factory=list)


@dataclass
class Workflow:
    """A running or completed Forge workflow."""

    workflow_id: str
    spec_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: dict[str, StepExecution] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    error: str | None = None

    def is_blocked(self) -> bool:
        """Check if any step is awaiting human approval."""
        return any(s.status == AgentStatus.BLOCKED for s in self.steps.values())

    def completion_rate(self) -> float:
        """Return fraction of steps completed (0.0 - 1.0)."""
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps.values() if s.status == AgentStatus.COMPLETED)
        return completed / len(self.steps)


class Orchestrator:
    """Multi-agent workflow orchestrator.

    Responsibilities:
    - Compile spec DAGs from the SpecEngine
    - Dispatch agents via the AgentRegistry
    - Manage shared workflow context through MemoryFabric
    - Enforce governance via GovernanceRuntime
    - Handle retries, timeouts, and human checkpoints
    """

    def __init__(
        self,
        spec_engine: SpecEngine,
        agent_registry: AgentRegistry,
        memory: MemoryFabric,
        governance: GovernanceRuntime | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        retry_policy: RetryPolicy | None = None,
        store: WorkflowStore | None = None,
    ) -> None:
        self.spec_engine = spec_engine
        self.agent_registry = agent_registry
        self.memory = memory
        self.governance = governance
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=3, base_delay=1.0)
        self.store = store or WorkflowStore()
        self.config = get_config()
        self._workflows: dict[str, Workflow] = {}
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_agents)

    async def start_workflow(self, spec_id: str, initial_context: dict[str, Any] | None = None) -> Workflow:
        """Start a new workflow from a spec.

        Args:
            spec_id: The spec to execute.
            initial_context: Optional seed context (e.g. PR description, user intent).

        Returns:
            Workflow instance tracking execution state.
        """
        spec = self.spec_engine.get_spec(spec_id)
        if not spec:
            raise ValueError(f"Spec not found: {spec_id}")

        workflow_id = f"wf-{spec_id}-{time.time():.0f}"
        workflow = Workflow(
            workflow_id=workflow_id,
            spec_id=spec_id,
            context=initial_context or {},
        )

        # Initialize step execution states
        for step in spec.steps:
            workflow.steps[step.id] = StepExecution(step_id=step.id)

        self._workflows[workflow_id] = workflow
        logger.info("workflow_started", workflow_id=workflow_id, spec_id=spec_id)

        # Kick off execution in background
        asyncio.create_task(self._execute_workflow(workflow_id))

        return workflow

    async def _execute_workflow(self, workflow_id: str) -> None:
        """Internal workflow execution loop."""
        workflow = self._workflows[workflow_id]
        spec = self.spec_engine.get_spec(workflow.spec_id)
        if not spec:
            workflow.status = WorkflowStatus.FAILED
            workflow.error = f"Spec disappeared: {workflow.spec_id}"
            return

        workflow.status = WorkflowStatus.RUNNING
        execution_order = spec.execution_order()

        try:
            for step_id in execution_order:
                step = spec.get_step(step_id)
                if not step:
                    continue

                # Wait for dependencies
                await self._wait_for_dependencies(workflow, step)

                # Check if workflow was cancelled
                if workflow.status == WorkflowStatus.CANCELLED:
                    break

                # Execute step with concurrency limit
                async with self._semaphore:
                    await self._execute_step(workflow, step)

            if workflow.status != WorkflowStatus.CANCELLED:
                if all(
                    s.status == AgentStatus.COMPLETED for s in workflow.steps.values()
                ):
                    workflow.status = WorkflowStatus.COMPLETED
                    workflow.completed_at = time.time()
                    logger.info("workflow_completed", workflow_id=workflow_id)
                else:
                    workflow.status = WorkflowStatus.FAILED
                    workflow.error = "One or more steps failed"
                    logger.error("workflow_failed", workflow_id=workflow_id)

        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.error = str(e)
            logger.exception("workflow_error", workflow_id=workflow_id, error=str(e))

    async def _wait_for_dependencies(self, workflow: Workflow, step: SpecStep) -> None:
        """Wait until all dependency steps have completed successfully."""
        while True:
            deps_complete = all(
                workflow.steps.get(dep_id, StepExecution(step_id="")).status
                == AgentStatus.COMPLETED
                for dep_id in step.depends_on
            )
            if deps_complete:
                break
            # Check for failed dependencies
            any_failed = any(
                workflow.steps.get(dep_id, StepExecution(step_id="")).status
                == AgentStatus.FAILED
                for dep_id in step.depends_on
            )
            if any_failed:
                raise RuntimeError(f"Dependency failed for step {step.id}")
            await asyncio.sleep(0.5)

    async def _execute_step(self, workflow: Workflow, step: SpecStep) -> None:
        """Execute a single step through the appropriate agent."""
        step_exec = workflow.steps[step.id]
        step_exec.status = AgentStatus.RUNNING
        step_exec.start_time = time.time()

        logger.info("step_started", workflow_id=workflow.workflow_id, step_id=step.id)

        # Find agent for this step's role
        agent_configs = self.agent_registry.list_by_role(step.agent_role)
        if not agent_configs:
            step_exec.status = AgentStatus.FAILED
            step_exec.logs.append(f"No agent found for role: {step.agent_role}")
            return

        agent_config = agent_configs[0]  # Simple round-robin; can be smarter
        agent = self.agent_registry.get_agent(agent_config.name)
        if not agent:
            step_exec.status = AgentStatus.FAILED
            step_exec.logs.append(f"Agent not instantiated: {agent_config.name}")
            return

        # Build task input from spec step + workflow context
        task_input = {
            "step": step.model_dump(),
            "spec_id": workflow.spec_id,
            "workflow_id": workflow.workflow_id,
        }

        # Governance check before execution
        if self.governance:
            decision = await self.governance.evaluate_action(
                agent=agent_config,
                action="execute_step",
                context={"step": step.model_dump(), "workflow": workflow.context},
            )
            if decision == "BLOCK":
                step_exec.status = AgentStatus.BLOCKED
                step_exec.logs.append("Blocked by governance runtime")
                logger.warning("step_blocked_by_governance", step_id=step.id)
                return
            elif decision == "REVIEW":
                step_exec.status = AgentStatus.BLOCKED
                step_exec.checkpoint_id = f"chk-{workflow.workflow_id}-{step.id}"
                logger.info("step_awaiting_approval", step_id=step.id, checkpoint=step_exec.checkpoint_id)
                return

        # Execute agent with retry and circuit breaker
        async def _execute_with_resilience() -> AgentResult:
            return await agent.execute(task_input, workflow.context)

        try:
            result = await self.circuit_breaker.call(
                target=agent_config.name,
                fn=lambda: self.retry_policy.execute(_execute_with_resilience),
            )
            step_exec.result = result
            step_exec.status = result.status
            step_exec.end_time = time.time()

            # Store result in memory fabric
            await self.memory.write_step_result(workflow.workflow_id, step.id, result)

            # Update workflow context with outputs
            workflow.context.update(result.output)

            # Persist workflow state
            self.store.save(workflow)

            logger.info(
                "step_completed",
                workflow_id=workflow.workflow_id,
                step_id=step.id,
                status=result.status.value,
                duration_ms=result.execution_time_ms,
            )

        except Exception as e:
            step_exec.status = AgentStatus.FAILED
            step_exec.end_time = time.time()
            step_exec.logs.append(str(e))
            step_exec.retry_count += 1

            # Persist failed state
            self.store.save(workflow)

            logger.exception("step_failed", workflow_id=workflow.workflow_id, step_id=step.id)

    async def approve_checkpoint(self, workflow_id: str, checkpoint_id: str) -> None:
        """Human approves a blocked step and resumes execution."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        for step_exec in workflow.steps.values():
            if step_exec.checkpoint_id == checkpoint_id:
                step_exec.status = AgentStatus.PENDING
                step_exec.checkpoint_id = None
                logger.info("checkpoint_approved", workflow_id=workflow_id, checkpoint=checkpoint_id)
                # Re-trigger workflow execution
                asyncio.create_task(self._execute_workflow(workflow_id))
                return

        raise ValueError(f"Checkpoint not found: {checkpoint_id}")

    async def cancel_workflow(self, workflow_id: str) -> None:
        """Cancel a running workflow."""
        workflow = self._workflows.get(workflow_id)
        if workflow:
            workflow.status = WorkflowStatus.CANCELLED
            logger.info("workflow_cancelled", workflow_id=workflow_id)

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Get workflow state."""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        """List all workflows."""
        return list(self._workflows.values())
