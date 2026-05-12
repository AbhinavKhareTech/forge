"""Reviewer Agent -- reviews code for quality and compliance.

The Reviewer checks generated code against organizational constitutions,
security standards, and best practices. It produces a review report
with findings and recommendations.
"""

from __future__ import annotations

from typing import Any

from forge.protocols.agent import Agent, AgentConfig, AgentResult, AgentStatus
from forge.utils.logging import get_logger

logger = get_logger("forge.agents.reviewer")


class ReviewerAgent(Agent):
    """Agent that reviews code for quality, security, and compliance.

    In production, this would use an LLM with code review capabilities
    and static analysis tools (Semgrep, Bandit, etc.).
    """

    async def execute(
        self,
        task_input: dict[str, Any],
        context: dict[str, Any],
    ) -> AgentResult:
        """Review code artifacts from prior agent outputs.

        Args:
            task_input: Contains the spec step and review criteria.
            context: Shared workflow context including code artifacts.

        Returns:
            AgentResult with review report.
        """
        step = task_input.get("step", {})
        description = step.get("description", "")
        spec_id = task_input.get("spec_id", "unknown")
        step_id = step.get("id", "unknown")

        # Get code from context (produced by coder agent)
        code_output = context.get("code", {})
        files = context.get("files_generated", [])

        # Get constitution refs
        constitution_refs = step.get("constitution_refs", [])

        logger.info("reviewer_executing", spec_id=spec_id, step_id=step_id, files=len(files))

        # Mock review -- in production, replace with LLM + static analysis
        review = self._generate_mock_review(code_output, files, constitution_refs)

        # Determine status based on review findings
        status = AgentStatus.COMPLETED if review["approved"] else AgentStatus.FAILED

        return AgentResult(
            agent_name=self.config.name,
            status=status,
            output={
                "review": review,
                "spec_id": spec_id,
                "step_id": step_id,
            },
            artifacts=[],
            logs=[f"Reviewed {len(files)} files for {spec_id}:{step_id}"],
            execution_time_ms=2000,
            token_usage={"input": 800, "output": 400},
            risk_score=0.15 if review["approved"] else 0.7,
        )

    async def health_check(self) -> bool:
        """Reviewer is healthy if linting tools are available."""
        return True

    def _generate_mock_review(
        self,
        code_output: dict[str, str],
        files: list[str],
        constitution_refs: list[str],
    ) -> dict[str, Any]:
        """Generate a mock review report.

        In production, this would run:
        - Static analysis (Semgrep, Bandit, mypy)
        - Security scanning (Snyk, Trivy)
        - LLM-based code review
        """
        findings: list[dict[str, Any]] = []
        approved = True

        # Check for common issues in code
        for filename, content in code_output.items():
            # Check for hardcoded secrets
            if "password" in content.lower() and "=" in content:
                if "bcrypt" not in content and "hash" not in content.lower():
                    findings.append({
                        "file": filename,
                        "severity": "high",
                        "category": "security",
                        "message": "Possible plaintext password handling detected",
                        "line": None,
                    })
                    approved = False

            # Check for TODOs
            if "TODO" in content:
                findings.append({
                    "file": filename,
                    "severity": "low",
                    "category": "completeness",
                    "message": "TODO items found -- implementation may be incomplete",
                    "line": None,
                })

            # Check for test coverage
            if filename.startswith("tests/"):
                if "test_" not in content:
                    findings.append({
                        "file": filename,
                        "severity": "medium",
                        "category": "testing",
                        "message": "Test file missing test_ prefix on functions",
                        "line": None,
                    })

        # Constitution checks
        if "security" in constitution_refs:
            findings.append({
                "file": "*",
                "severity": "info",
                "category": "constitution",
                "message": "Security constitution applied -- no secrets in code",
                "line": None,
            })

        return {
            "approved": approved and len([f for f in findings if f["severity"] == "high"]) == 0,
            "findings": findings,
            "summary": {
                "total_files": len(files),
                "total_findings": len(findings),
                "high_severity": len([f for f in findings if f["severity"] == "high"]),
                "medium_severity": len([f for f in findings if f["severity"] == "medium"]),
                "low_severity": len([f for f in findings if f["severity"] == "low"]),
            },
            "recommendations": [
                "Run mypy for type checking" if any(".py" in f for f in files) else None,
                "Add integration tests for edge cases",
                "Update documentation with API examples",
            ],
        }
