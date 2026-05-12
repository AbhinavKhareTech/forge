"""Planner Agent -- decomposes specs into executable tasks.

The Planner takes a high-level spec and produces a detailed
execution plan with sub-tasks, dependencies, and acceptance criteria.
"""

from __future__ import annotations

from typing import Any

from forge.protocols.agent import Agent, AgentConfig, AgentResult, AgentStatus
from forge.utils.logging import get_logger

logger = get_logger("forge.agents.planner")


class PlannerAgent(Agent):
    """Agent that decomposes requirements into structured plans.

    In production, this would call an LLM (Claude, GPT-4, etc.) to
    generate the plan. For now, it produces mock plans based on
    heuristics and templates.
    """

    async def execute(
        self,
        task_input: dict[str, Any],
        context: dict[str, Any],
    ) -> AgentResult:
        """Generate a plan from the spec step.

        Args:
            task_input: Contains the spec step with description and requirements.
            context: Shared workflow context.

        Returns:
            AgentResult with the generated plan as structured output.
        """
        step = task_input.get("step", {})
        description = step.get("description", "")
        spec_id = task_input.get("spec_id", "unknown")

        logger.info("planner_executing", spec_id=spec_id, step_id=step.get("id"))

        # Mock planning logic -- in production, replace with LLM call
        plan = self._generate_mock_plan(description, step)

        return AgentResult(
            agent_name=self.config.name,
            status=AgentStatus.COMPLETED,
            output={
                "plan": plan,
                "spec_id": spec_id,
                "step_id": step.get("id"),
            },
            artifacts=[],
            logs=[f"Generated plan for {spec_id}:{step.get('id')}"],
            execution_time_ms=1500,
            token_usage={"input": 500, "output": 300},
            risk_score=0.1,
        )

    async def health_check(self) -> bool:
        """Planner is healthy if it can access planning templates."""
        return True

    def _generate_mock_plan(self, description: str, step: dict[str, Any]) -> dict[str, Any]:
        """Generate a heuristic plan based on step type and description.

        In production, this would be an LLM prompt like:
            "You are a senior software architect. Given these requirements,
            produce a detailed implementation plan..."
        """
        step_type = step.get("type", "custom")

        if "auth" in description.lower() or "login" in description.lower():
            return {
                "overview": "Implement secure authentication with MFA",
                "subtasks": [
                    {"id": "auth-1", "task": "Design user model with password hashing"},
                    {"id": "auth-2", "task": "Implement login endpoint with rate limiting"},
                    {"id": "auth-3", "task": "Add TOTP-based MFA flow"},
                    {"id": "auth-4", "task": "Implement session management with JWT"},
                    {"id": "auth-5", "task": "Add password reset via email"},
                ],
                "dependencies": [
                    ["auth-1", "auth-2"],
                    ["auth-2", "auth-3"],
                    ["auth-2", "auth-4"],
                    ["auth-4", "auth-5"],
                ],
                "acceptance_criteria": [
                    "Users can register with email and password",
                    "Login rate limited to 5 attempts per minute",
                    "MFA required for admin roles",
                    "Sessions expire after 24 hours of inactivity",
                ],
            }

        if "payment" in description.lower() or "fraud" in description.lower():
            return {
                "overview": "Implement payment processing with fraud detection",
                "subtasks": [
                    {"id": "pay-1", "task": "Design payment intent API"},
                    {"id": "pay-2", "task": "Integrate Razorpay/Stripe gateway"},
                    {"id": "pay-3", "task": "Add webhook handlers for payment events"},
                    {"id": "pay-4", "task": "Implement BGI Trident fraud scoring"},
                    {"id": "pay-5", "task": "Add refund and chargeback handling"},
                ],
                "dependencies": [
                    ["pay-1", "pay-2"],
                    ["pay-2", "pay-3"],
                    ["pay-2", "pay-4"],
                    ["pay-3", "pay-5"],
                ],
                "acceptance_criteria": [
                    "Payment intents created within 200ms",
                    "Fraud score computed for every transaction",
                    "Webhooks handle idempotency keys",
                    "Refunds processed within 7 business days",
                ],
            }

        # Generic plan template
        return {
            "overview": f"Implement {step.get('title', step_type)} functionality",
            "subtasks": [
                {"id": f"{step_type}-1", "task": "Analyze requirements and design approach"},
                {"id": f"{step_type}-2", "task": "Implement core functionality"},
                {"id": f"{step_type}-3", "task": "Write unit and integration tests"},
                {"id": f"{step_type}-4", "task": "Add documentation and examples"},
            ],
            "dependencies": [
                [f"{step_type}-1", f"{step_type}-2"],
                [f"{step_type}-2", f"{step_type}-3"],
                [f"{step_type}-3", f"{step_type}-4"],
            ],
            "acceptance_criteria": [
                "All tests pass",
                "Code coverage > 80%",
                "Documentation is complete",
            ],
        }
