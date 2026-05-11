"""Governance Runtime -- BGI Trident-powered policy enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from forge.config import get_config
from forge.protocols.agent import AgentConfig
from forge.utils.logging import get_logger

logger = get_logger("forge.governance")


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


@dataclass
class GovernanceResult:
    decision: PolicyDecision
    score: float
    reasons: list[str] = field(default_factory=list)
    policy_violations: list[str] = field(default_factory=list)
    trident_signals: list[dict[str, Any]] = field(default_factory=list)
    suggested_mitigations: list[str] = field(default_factory=list)


class GovernanceRuntime:
    def __init__(self) -> None:
        self.config = get_config()
        self._policies: list[dict[str, Any]] = []
        self._trident_enabled = self.config.trident_enabled

    def load_policies(self, policies: list[dict[str, Any]]) -> None:
        self._policies.extend(policies)
        logger.info("policies_loaded", count=len(policies))

    async def evaluate_action(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> PolicyDecision:
        result = await self._evaluate(agent, action, context)
        logger.info(
            "governance_decision",
            agent=agent.name,
            action=action,
            decision=result.decision.value,
            score=result.score,
            reasons=result.reasons,
        )
        return result.decision

    async def _evaluate(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> GovernanceResult:
        reasons: list[str] = []
        violations: list[str] = []
        score = 0.0

        # 1. Rule-based policy checks
        for policy in self._policies:
            triggered, policy_score = self._check_policy(policy, agent, action, context)
            if triggered:
                score = max(score, policy_score)
                violations.append(policy["name"])
                reasons.append(f"Policy violated: {policy['name']}")

        # 2. Agent-level governance flags
        if agent.requires_human_approval:
            score = max(score, 0.8)
            reasons.append("Agent requires human approval by configuration")

        # 3. Action sensitivity (reduced if agent has explicit permission)
        action_risk = self._action_risk_score(action, agent)
        score = max(score, action_risk)
        if action_risk > 0.5:
            reasons.append(f"High-risk action: {action}")

        # 4. BGI Trident (placeholder)
        if self._trident_enabled:
            trident_score, _ = await self._trident_evaluate(agent, action, context)
            score = max(score, trident_score)
            if trident_score > 0:
                reasons.append("BGI Trident anomaly detected")

        if score >= 0.9:
            decision = PolicyDecision.BLOCK
        elif score >= self.config.human_checkpoint_threshold:
            decision = PolicyDecision.REVIEW
        else:
            decision = PolicyDecision.ALLOW

        return GovernanceResult(
            decision=decision,
            score=score,
            reasons=reasons,
            policy_violations=violations,
        )

    def _check_policy(
        self,
        policy: dict[str, Any],
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> tuple[bool, float]:
        """Check if a single policy is triggered."""
        condition = policy.get("condition", {})

        # Forbidden actions + roles
        if "forbidden_actions" in condition:
            if action not in condition["forbidden_actions"]:
                return False, 0.0
            if "forbidden_roles" in condition:
                if agent.role in condition["forbidden_roles"]:
                    return True, 1.0
            return True, 1.0

        # Permission-based: only apply to relevant actions
        if "required_permissions" in condition:
            action_perm_map = {
                "deploy_prod": "deploy:prod",
                "delete_database": "admin:database",
                "delete_file": "write:file",
            }
            required = condition["required_permissions"][0]
            mapped = action_perm_map.get(action)
            if mapped and mapped == required:
                if not agent.has_permission(required):
                    return True, 0.9
            return False, 0.0

        if "max_amount" in condition:
            amount = context.get("amount", 0)
            if isinstance(amount, (int, float)) and amount > condition["max_amount"]:
                return True, 0.85

        return False, 0.0

    def _action_risk_score(self, action: str, agent: AgentConfig) -> float:
        """Return risk score. Reduced if agent has permission for the action."""
        risk_map = {
            "execute_step": 0.1,
            "read_file": 0.05,
            "write_file": 0.3,
            "delete_file": 0.7,
            "deploy_prod": 0.9,
            "delete_database": 1.0,
            "create_payment_link": 0.6,
            "issue_refund": 0.5,
        }
        base = risk_map.get(action, 0.3)

        # Reduce risk if agent has explicit permission
        action_perm_map = {
            "deploy_prod": "deploy:prod",
            "delete_database": "admin:database",
            "delete_file": "write:file",
            "write_file": "write:file",
        }
        required = action_perm_map.get(action)
        if required and agent.has_permission(required):
            base = min(base, 0.6)

        return base

    async def _trident_evaluate(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> tuple[float, list[dict[str, Any]]]:
        logger.debug("trident_evaluation_placeholder", agent=agent.name, action=action)
        return 0.0, []
