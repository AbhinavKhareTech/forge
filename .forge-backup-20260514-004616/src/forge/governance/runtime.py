"""Governance Runtime -- BGI Trident-powered policy enforcement.

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
from forge.trident.ensemble import TridentEnsemble
from forge.trident.config import TridentConfig
from forge.trident.graph_builder import AgentGraphBuilder
from forge.trident.features import AgentFeatureExtractor
from forge.memory.fabric import MemoryFabric
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

    def __init__(self, memory: MemoryFabric | None = None) -> None:
        self.config = get_config()
        self._policies: list[dict[str, Any]] = []
        self._trident_enabled = self.config.trident_enabled
        self._trident: TridentEnsemble | None = None
        self._memory = memory

        if self._trident_enabled:
            self._init_trident()

    def _init_trident(self) -> None:
        """Initialize BGI Trident ensemble."""
        try:
            trident_config = TridentConfig()
            graph_builder = AgentGraphBuilder(memory=self._memory)
            feature_extractor = AgentFeatureExtractor(memory=self._memory)
            self._trident = TridentEnsemble(
                config=trident_config,
                graph_builder=graph_builder,
                feature_extractor=feature_extractor,
            )
            logger.info("trident_initialized")
        except Exception as e:
            logger.error("trident_init_failed", error=str(e))
            self._trident_enabled = False

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
        trident_signals: list[dict[str, Any]] = []

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

        # 3. Action sensitivity scoring (reduced if agent has explicit permission)
        action_risk = self._action_risk_score(action, agent)
        score = max(score, action_risk)
        if action_risk > 0.5:
            reasons.append(f"High-risk action: {action}")

        # 4. BGI Trident graph-native scoring (if enabled)
        if self._trident_enabled and self._trident:
            try:
                trident_result = await self._trident.evaluate(agent, action, context)
                score = max(score, trident_result.ensemble_score)
                for signal in trident_result.signals:
                    trident_signals.append({
                        "prong": signal.prong,
                        "type": signal.signal_type,
                        "score": signal.score,
                        "description": signal.description,
                    })
                    reasons.append(f"BGI Trident [{signal.prong}]: {signal.description}")
            except Exception as e:
                logger.error("trident_evaluation_failed", error=str(e))

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
            trident_signals=trident_signals,
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

        # Policy must match the action if forbidden_actions is specified
        if "forbidden_actions" in condition:
            if action not in condition["forbidden_actions"]:
                return False, 0.0
            # If action matches forbidden list, check role restriction
            if "forbidden_roles" in condition:
                if agent.role in condition["forbidden_roles"]:
                    return True, 1.0
            return True, 1.0

        # Permission-based policies only apply to specific actions
        if "required_permissions" in condition:
            action_perm_map = {
                "deploy_prod": "deploy:prod",
                "delete_database": "admin:database",
                "delete_file": "write:file",
            }
            required_perm = condition["required_permissions"][0]
            mapped_action_perm = action_perm_map.get(action)
            if mapped_action_perm and mapped_action_perm == required_perm:
                if not agent.has_permission(required_perm):
                    return True, 0.9
            return False, 0.0

        if "max_amount" in condition:
            amount = context.get("amount", 0)
            if isinstance(amount, (int, float)) and amount > condition["max_amount"]:
                return True, 0.85

        return False, 0.0

    def _action_risk_score(self, action: str, agent: AgentConfig) -> float:
        """Return inherent risk score for common actions.

        If agent has explicit permission for the action, risk is reduced.
        """
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
        base_risk = risk_map.get(action, 0.3)

        # Reduce risk if agent has explicit permission for this action
        action_perm_map = {
            "deploy_prod": "deploy:prod",
            "delete_database": "admin:database",
            "delete_file": "write:file",
            "write_file": "write:file",
        }
        required_perm = action_perm_map.get(action)
        if required_perm and agent.has_permission(required_perm):
            base_risk = min(base_risk, 0.6)

        return base_risk

    async def _trident_evaluate(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> tuple[float, list[dict[str, Any]]]:
        """Evaluate using BGI Trident three-prong ensemble.

        DEPRECATED: Now handled by TridentEnsemble directly.
        Kept for backward compatibility.
        """
        if self._trident:
            result = await self._trident.evaluate(agent, action, context)
            signals = [
                {
                    "prong": s.prong,
                    "type": s.signal_type,
                    "score": s.score,
                    "description": s.description,
                }
                for s in result.signals
            ]
            return result.ensemble_score, signals
        return 0.0, []
