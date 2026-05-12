"""Coder Agent -- implements code changes from spec steps."""

from __future__ import annotations
from typing import Any
from forge.protocols.agent import Agent, AgentConfig, AgentResult, AgentStatus
from forge.utils.logging import get_logger
logger = get_logger("forge.agents.coder")

class CoderAgent(Agent):
    async def execute(self, task_input: dict[str, Any], context: dict[str, Any]) -> AgentResult:
        step = task_input.get("step", {})
        spec_id = task_input.get("spec_id", "unknown")
        step_id = step.get("id", "unknown")
        plan = context.get("plan", {})
        logger.info("coder_executing", spec_id=spec_id, step_id=step_id)
        code_artifacts = self._generate_mock_code(step.get("description", ""), plan, step)
        return AgentResult(
            agent_name=self.config.name, status=AgentStatus.COMPLETED,
            output={"code": code_artifacts, "spec_id": spec_id, "step_id": step_id, "files_generated": list(code_artifacts.keys())},
            artifacts=list(code_artifacts.keys()),
            logs=[f"Generated {len(code_artifacts)} files for {spec_id}:{step_id}"],
            execution_time_ms=3500, token_usage={"input": 1200, "output": 800}, risk_score=0.25,
        )
    async def health_check(self) -> bool:
        return True
    def _generate_mock_code(self, description: str, plan: dict[str, Any], step: dict[str, Any]) -> dict[str, str]:
        module_name = step.get("id", "module").replace("-", "_")
        if "auth" in description.lower():
            return {
                "src/auth/service.py": "class AuthService:\\n    def authenticate(self, email, password):\\n        pass\\n",
                "tests/test_auth.py": "def test_auth():\\n    assert True\\n",
            }
        return {
            f"src/{module_name}.py": f"class {module_name.title()}Service:\\n    def process(self, data):\\n        return data\\n",
            f"tests/test_{module_name}.py": f"def test_{module_name}():\\n    assert True\\n",
        }
