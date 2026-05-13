"""Load and performance tests for Forge.

Simulates high-concurrency scenarios to validate scalability.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from forge.config import get_settings
from forge.core.orchestrator import Orchestrator, OrchestratorSpec, OrchestratorStep


@pytest.mark.slow
@pytest.mark.asyncio
class TestLoadOrchestrator:
    """Load tests for the orchestrator."""

    async def test_concurrent_spec_executions(self, test_settings, db_engine):
        """Execute multiple specs concurrently."""
        orchestrator = Orchestrator(test_settings)
        num_specs = 10

        specs = [
            OrchestratorSpec(
                spec_id=f"SPEC-LOAD-{i}",
                steps=[
                    OrchestratorStep(step_id="plan", agent_type="planner", depends_on=[]),
                    OrchestratorStep(step_id="code", agent_type="coder", depends_on=["plan"]),
                ],
            )
            for i in range(num_specs)
        ]

        start = time.monotonic()
        tasks = [orchestrator.execute_spec(spec) for spec in specs]
        results = await asyncio.gather(*tasks)
        duration = time.monotonic() - start

        # All should complete
        assert all(r.value == "completed" for r in results)
        assert duration < 30.0  # Should complete within 30 seconds

    async def test_many_agents_per_spec(self, test_settings, db_engine):
        """Execute a spec with many agents."""
        orchestrator = Orchestrator(test_settings)
        num_steps = 20

        # Create a linear chain of steps
        steps = []
        for i in range(num_steps):
            steps.append(OrchestratorStep(
                step_id=f"step-{i}",
                agent_type="coder" if i % 2 == 0 else "reviewer",
                depends_on=[f"step-{i-1}"] if i > 0 else [],
            ))

        spec = OrchestratorSpec(spec_id="SPEC-LOAD-CHAIN", steps=steps)

        start = time.monotonic()
        result = await orchestrator.execute_spec(spec)
        duration = time.monotonic() - start

        assert result.value == "completed"
        assert duration < 60.0  # Should complete within 60 seconds

    async def test_orchestrator_rate_limiting(self, test_settings, db_engine):
        """Orchestrator should respect max concurrent specs limit."""
        orchestrator = Orchestrator(test_settings)
        max_concurrent = test_settings.orchestrator_max_concurrent_specs

        # Create more specs than the limit
        specs = [
            OrchestratorSpec(
                spec_id=f"SPEC-RATE-{i}",
                steps=[
                    OrchestratorStep(step_id="plan", agent_type="planner", depends_on=[]),
                ],
            )
            for i in range(max_concurrent + 5)
        ]

        # All should eventually complete (some will queue)
        tasks = [orchestrator.execute_spec(spec) for spec in specs]
        results = await asyncio.gather(*tasks)

        assert all(r.value == "completed" for r in results)
