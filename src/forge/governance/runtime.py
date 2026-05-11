"""Governance Runtime — BGI Trident-powered policy enforcement.

Before any agent acts, the Governance Runtime evaluates the action against
organizational policies, security rules, and risk models. It returns one of:

- ALLOW: Proceed with execution
- REVIEW: Pause for human approval (checkpoint)
- BLOCK: Deny the action entirely

When BGI Trident is enabled, the runtime uses graph-native reasoning to
detect anomalous agent behavior patterns, cross-agent collusion, and
temporal drift in agent actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from forge.config import get_config
from forge.protocols.agent import AgentConfig
from forge.utils.logging import get_logger

logger = get_logger("forge.governance")


class PolicyDecision(str, Enum):
    """Possible outcomes of a governance evaluation."""

    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


@dataclass
class GovernanceResult:
    """Detailed result of a governance evaluation."""

    decision: PolicyDecision
    score: float  # 0.0 (safe) to 1.0 (high risk)
    reasons: list[str] = field(default_factory=list)
    policy_violations: list[str] = field(default_factory=list)
    trident_signals: list[dict[str, Any]] = field(default_factory=list)
    suggested_mitigations: list[str] = field(default_factory=list)


class GovernanceRuntime:
    """Policy enforcement engine for agent actions.

    Supports both rule-based policies (fast, deterministic) and
    BGI Trident graph-native scoring (deep, contextual).
    """

    def __init__(self) -> None:
        self.config = get_config()
        self._policies: list[dict[str, Any]] = []
        self._trident_enabled = self.config.trident_enabled

    def load_policies(self, policies: list[dict[str, Any]]) -> None:
        """Load organizational policies.

        Each policy is a dict with:
            - name: str
            - condition: callable or rule dict
            - action: "allow" | "review" | "block"
            - description: str
        """
        self._policies.extend(policies)
        logger.info("policies_loaded", count=len(policies))

    async def evaluate_action(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> PolicyDecision:
        """Evaluate whether an agent action should proceed.

        Args:
            agent: The agent attempting the action.
            action: Action identifier (e.g. "execute_step", "deploy_prod").
            context: Execution context including step details, workflow state.

        Returns:
            ALLOW, REVIEW, or BLOCK.
        """
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
        """Internal evaluation combining rule-based and Trident scoring."""
        reasons: list[str] = []
        violations: list[str] = []
        score = 0.0

        # 1. Rule-based policy checks (fast path)
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

        # 3. Action sensitivity scoring
        action_risk = self._action_risk_score(action)
        score = max(score, action_risk)
        if action_risk > 0.5:
            reasons.append(f"High-risk action: {action}")

        # 4. BGI Trident graph-native scoring (if enabled)
        if self._trident_enabled:
            trident_score, trident_signals = await self._trident_evaluate(agent, action, context)
            score = max(score, trident_score)
            if trident_signals:
                reasons.append("BGI Trident anomaly detected")

        # Determine decision from score
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
        """Check if a single policy is triggered.

        Returns:
            (triggered, risk_score)
        """
        condition = policy.get("condition", {})

        # Simple rule engine: check agent role, action pattern, context values
        if "forbidden_roles" in condition:
            if agent.role in condition["forbidden_roles"]:
                return True, 1.0

        if "forbidden_actions" in condition:
            if action in condition["forbidden_actions"]:
                return True, 1.0

        if "required_permissions" in condition:
            for perm in condition["required_permissions"]:
                if not agent.has_permission(perm):
                    return True, 0.9

        if "max_amount" in condition:
            amount = context.get("amount", 0)
            if isinstance(amount, (int, float)) and amount > condition["max_amount"]:
                return True, 0.85

        return False, 0.0

    def _action_risk_score(self, action: str) -> float:
        """Return inherent risk score for common actions."""
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
        return risk_map.get(action, 0.3)

    async def _trident_evaluate(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> tuple[float, list[dict[str, Any]]]:
        """Evaluate using BGI Trident three-prong ensemble.

        This is a placeholder for the actual Trident integration.
        In production, this calls:
        - Prong 1 (PyG/ID-GNN): Agent relationship graph anomalies
        - Prong 2 (DGL/R-GCN): Temporal behavior drift in agent actions
        - Prong 3 (XGBoost): Threshold-based policy violations

        Returns:
            (trident_risk_score, list_of_detected_signals)
        """
        # TODO: Integrate with bgi_trident graph engine
        # from bgi_trident.graph.ensemble.stacker import EnsembleMetaLearner
        # ensemble = EnsembleMetaLearner(...)
        # score = ensemble.predict(agent_graph_features, temporal_features, tabular_features)

        logger.debug("trident_evaluation_placeholder", agent=agent.name, action=action)
        return 0.0, []
