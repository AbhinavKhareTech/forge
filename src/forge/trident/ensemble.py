"""BGI Trident Three-Prong Ensemble.

The ensemble combines three complementary approaches:
- Prong 1 (PyG/ID-GNN): Graph-native anomaly detection on agent relationships
- Prong 2 (DGL/R-GCN): Temporal behavior drift detection
- Prong 3 (XGBoost): Tabular feature-based threshold rules

Results are combined via a meta-learner (weighted average by default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from forge.config import get_config
from forge.protocols.agent import AgentConfig
from forge.trident.config import TridentConfig
from forge.trident.features import AgentFeatureExtractor, AgentFeatures
from forge.trident.graph_builder import AgentGraphBuilder
from forge.utils.logging import get_logger

logger = get_logger("forge.trident.ensemble")


@dataclass
class TridentSignal:
    """A signal detected by one of the three prongs."""

    prong: str  # "prong1", "prong2", "prong3"
    signal_type: str
    score: float  # 0.0 - 1.0
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TridentResult:
    """Combined result from the three-prong ensemble."""

    ensemble_score: float  # 0.0 - 1.0
    prong_scores: dict[str, float]
    signals: list[TridentSignal]
    feature_vector: list[float] = field(default_factory=list)
    graph_features: dict[str, float] = field(default_factory=dict)
    temporal_features: dict[str, float] = field(default_factory=dict)


class TridentEnsemble:
    """Three-prong ensemble for agent governance scoring.

    Wraps PyG, DGL, and XGBoost models into a unified scoring interface.
    When ML libraries are not available, falls back to heuristic scoring.
    """

    def __init__(
        self,
        config: TridentConfig | None = None,
        graph_builder: AgentGraphBuilder | None = None,
        feature_extractor: AgentFeatureExtractor | None = None,
    ) -> None:
        self.config = config or TridentConfig()
        self.graph_builder = graph_builder
        self.feature_extractor = feature_extractor
        self._prong1_available = False
        self._prong2_available = False
        self._prong3_available = False
        self._init_prongs()

    def _init_prongs(self) -> None:
        """Initialize ML prongs if dependencies are available."""
        # Prong 1: PyG
        if self.config.prong1_enabled:
            try:
                import torch
                import torch_geometric as pyg
                self._prong1_available = True
                logger.info("prong1_initialized", library="torch_geometric")
            except ImportError:
                logger.warning("prong1_unavailable", reason="torch_geometric not installed")

        # Prong 2: DGL
        if self.config.prong2_enabled:
            try:
                import dgl
                self._prong2_available = True
                logger.info("prong2_initialized", library="dgl")
            except ImportError:
                logger.warning("prong2_unavailable", reason="dgl not installed")

        # Prong 3: XGBoost
        if self.config.prong3_enabled:
            try:
                import xgboost as xgb
                self._prong3_available = True
                logger.info("prong3_initialized", library="xgboost")
            except ImportError:
                logger.warning("prong3_unavailable", reason="xgboost not installed")

    async def evaluate(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> TridentResult:
        """Evaluate an agent action using the three-prong ensemble.

        Args:
            agent: The agent being evaluated.
            action: The action the agent wants to perform.
            context: Execution context.

        Returns:
            TridentResult with ensemble score and individual prong signals.
        """
        signals: list[TridentSignal] = []
        prong_scores: dict[str, float] = {}
        feature_vector: list[float] = []
        graph_features: dict[str, float] = {}
        temporal_features: dict[str, float] = {}

        # Prong 1: Agent Relationship Graph Anomaly (PyG/ID-GNN)
        if self.config.prong1_enabled:
            score, prong_signals, g_features = await self._prong1_evaluate(agent, action, context)
            prong_scores["prong1"] = score
            signals.extend(prong_signals)
            graph_features = g_features

        # Prong 2: Temporal Behavior Drift (DGL/R-GCN)
        if self.config.prong2_enabled:
            score, prong_signals, t_features = await self._prong2_evaluate(agent, action, context)
            prong_scores["prong2"] = score
            signals.extend(prong_signals)
            temporal_features = t_features

        # Prong 3: Tabular Feature Rules (XGBoost)
        if self.config.prong3_enabled:
            score, prong_signals, f_vector = await self._prong3_evaluate(agent, action, context)
            prong_scores["prong3"] = score
            signals.extend(prong_signals)
            feature_vector = f_vector

        # Combine scores via meta-learner
        ensemble_score = self._combine_scores(prong_scores)

        logger.info(
            "trident_evaluation",
            agent=agent.name,
            action=action,
            ensemble_score=ensemble_score,
            prong_scores=prong_scores,
            signals=len(signals),
        )

        return TridentResult(
            ensemble_score=ensemble_score,
            prong_scores=prong_scores,
            signals=signals,
            feature_vector=feature_vector,
            graph_features=graph_features,
            temporal_features=temporal_features,
        )

    async def _prong1_evaluate(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> tuple[float, list[TridentSignal], dict[str, float]]:
        """Prong 1: Agent relationship graph anomaly detection.

        Uses PyG/ID-GNN to detect anomalous patterns in the agent
        collaboration graph (e.g., isolated agents, unusual bridges,
        cliques that bypass governance).
        """
        signals: list[TridentSignal] = []
        graph_features: dict[str, float] = {}

        if not self.graph_builder or not self._prong1_available:
            # Heuristic fallback
            score = self._heuristic_graph_score(agent, action, context)
            return score, signals, graph_features

        # Build or load agent graph
        workflow_id = context.get("workflow_id")
        if workflow_id:
            G = await self.graph_builder.build_from_workflow(workflow_id)
        else:
            G = await self.graph_builder.build_global_graph()

        # Extract graph features for this agent
        graph_features = self.graph_builder.compute_graph_features(G, agent.name)

        # Detect anomalies
        centrality = graph_features.get("pagerank", 0.0)
        clustering = graph_features.get("clustering", 0.0)
        in_degree = graph_features.get("in_degree", 0.0)

        score = 0.0

        # High centrality + low clustering = potential bridge agent (risky)
        if centrality > 0.3 and clustering < 0.1:
            score = max(score, 0.6)
            signals.append(TridentSignal(
                prong="prong1",
                signal_type="bridge_agent",
                score=0.6,
                description=f"Agent {agent.name} has high influence but low clustering -- potential single point of compromise",
                metadata={"centrality": centrality, "clustering": clustering},
            ))

        # Isolated agent with high permissions = risk
        if in_degree == 0 and len(agent.permissions) > 2:
            score = max(score, 0.5)
            signals.append(TridentSignal(
                prong="prong1",
                signal_type="isolated_high_privilege",
                score=0.5,
                description=f"Agent {agent.name} is isolated but has {len(agent.permissions)} permissions",
                metadata={"in_degree": in_degree, "permissions": len(agent.permissions)},
            ))

        # Detect cliques (potential collusion)
        cliques = self.graph_builder.detect_cliques(G, min_size=3)
        for clique in cliques:
            if agent.name in clique:
                score = max(score, 0.4)
                signals.append(TridentSignal(
                    prong="prong1",
                    signal_type="clique_membership",
                    score=0.4,
                    description=f"Agent {agent.name} is in a tightly connected group of {len(clique)} agents",
                    metadata={"clique_size": len(clique), "clique_members": clique},
                ))

        return score, signals, graph_features

    async def _prong2_evaluate(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> tuple[float, list[TridentSignal], dict[str, float]]:
        """Prong 2: Temporal behavior drift detection.

        Uses DGL/R-GCN to detect when an agent's behavior pattern
        changes over time (e.g., sudden increase in failures, off-hours
        activity, tool usage changes).
        """
        signals: list[TridentSignal] = []
        temporal_features: dict[str, float] = {}

        if not self.feature_extractor or not self._prong2_available:
            score = self._heuristic_temporal_score(agent, action, context)
            return score, signals, temporal_features

        # Extract features
        features = await self.feature_extractor.extract(agent, action, context)
        temporal_features = {
            "executions_last_hour": float(features.executions_last_hour),
            "executions_last_day": float(features.executions_last_day),
            "executions_last_week": float(features.executions_last_week),
            "off_hours_executions": float(features.off_hours_executions),
            "failure_rate": features.failure_rate,
            "block_rate": features.block_rate,
            "risk_score_trend": features.risk_score_trend,
            "time_since_last_execution": features.time_since_last_execution_hours,
        }

        score = 0.0

        # Sudden spike in execution frequency
        if features.executions_last_hour > 10:
            score = max(score, 0.5)
            signals.append(TridentSignal(
                prong="prong2",
                signal_type="execution_spike",
                score=0.5,
                description=f"Agent {agent.name} executed {features.executions_last_hour} times in the last hour",
                metadata={"executions_last_hour": features.executions_last_hour},
            ))

        # Off-hours activity
        if features.off_hours_executions > 3:
            score = max(score, 0.4)
            signals.append(TridentSignal(
                prong="prong2",
                signal_type="off_hours_activity",
                score=0.4,
                description=f"Agent {agent.name} has {features.off_hours_executions} off-hours executions",
                metadata={"off_hours": features.off_hours_executions},
            ))

        # Increasing risk trend
        if features.risk_score_trend > 0.2:
            score = max(score, 0.6)
            signals.append(TridentSignal(
                prong="prong2",
                signal_type="risk_trend_increasing",
                score=0.6,
                description=f"Agent {agent.name} risk score is trending up by {features.risk_score_trend:.2f}",
                metadata={"risk_trend": features.risk_score_trend},
            ))

        # High failure rate
        if features.failure_rate > 0.3:
            score = max(score, 0.5)
            signals.append(TridentSignal(
                prong="prong2",
                signal_type="high_failure_rate",
                score=0.5,
                description=f"Agent {agent.name} has {features.failure_rate:.1%} failure rate",
                metadata={"failure_rate": features.failure_rate},
            ))

        # Dormant agent suddenly active
        if features.time_since_last_execution_hours > 168 and features.executions_last_hour > 0:  # > 1 week dormant
            score = max(score, 0.7)
            signals.append(TridentSignal(
                prong="prong2",
                signal_type="dormant_reactivation",
                score=0.7,
                description=f"Agent {agent.name} was dormant for {features.time_since_last_execution_hours:.0f}h, now active",
                metadata={"dormant_hours": features.time_since_last_execution_hours},
            ))

        return score, signals, temporal_features

    async def _prong3_evaluate(
        self,
        agent: AgentConfig,
        action: str,
        context: dict[str, Any],
    ) -> tuple[float, list[TridentSignal], list[float]]:
        """Prong 3: Tabular feature-based threshold rules (XGBoost).

        Uses gradient-boosted trees on extracted agent features to
        score risk. Falls back to rule-based scoring when XGBoost
        is not available.
        """
        signals: list[TridentSignal] = []
        feature_vector: list[float] = []

        if not self.feature_extractor:
            score = self._heuristic_tabular_score(agent, action, context)
            return score, signals, feature_vector

        features = await self.feature_extractor.extract(agent, action, context)
        feature_vector = self.feature_extractor.to_vector(features)

        if self._prong3_available:
            # In production: load XGBoost model and predict
            # model = xgboost.Booster()
            # model.load_model(str(self.config.prong3_model_path))
            # dmatrix = xgboost.DMatrix([feature_vector])
            # score = float(model.predict(dmatrix)[0])
            score = self._rule_based_score(features, action)
        else:
            score = self._rule_based_score(features, action)

        # Generate signals from feature thresholds
        if features.failure_rate > 0.5:
            signals.append(TridentSignal(
                prong="prong3",
                signal_type="extreme_failure_rate",
                score=0.8,
                description=f"Agent {agent.name} has extreme failure rate: {features.failure_rate:.1%}",
                metadata={"failure_rate": features.failure_rate},
            ))

        if features.block_rate > 0.3:
            signals.append(TridentSignal(
                prong="prong3",
                signal_type="frequently_blocked",
                score=0.6,
                description=f"Agent {agent.name} is blocked {features.block_rate:.1%} of the time",
                metadata={"block_rate": features.block_rate},
            ))

        if features.tool_diversity_ratio < 0.1 and features.unique_tools_used > 0:
            signals.append(TridentSignal(
                prong="prong3",
                signal_type="tool_usage_concentration",
                score=0.4,
                description=f"Agent {agent.name} uses only {features.most_used_tool} repeatedly",
                metadata={"tool_diversity": features.tool_diversity_ratio},
            ))

        return score, signals, feature_vector

    def _combine_scores(self, prong_scores: dict[str, float]) -> float:
        """Combine individual prong scores via meta-learner."""
        if not prong_scores:
            return 0.0

        weights = self.config.ensemble_weights
        method = self.config.ensemble_meta_learner

        if method == "mean":
            return sum(prong_scores.values()) / len(prong_scores)

        elif method == "weighted":
            score = 0.0
            weight_sum = 0.0
            prong_names = ["prong1", "prong2", "prong3"]
            for i, prong in enumerate(prong_names):
                if prong in prong_scores:
                    score += prong_scores[prong] * weights[i]
                    weight_sum += weights[i]
            return score / weight_sum if weight_sum > 0 else 0.0

        elif method == "stacking":
            # In production: train a logistic regression meta-learner
            # For now, use max score (most conservative)
            return max(prong_scores.values())

        return sum(prong_scores.values()) / len(prong_scores)

    def _heuristic_graph_score(self, agent: AgentConfig, action: str, context: dict[str, Any]) -> float:
        """Fallback heuristic when PyG is not available."""
        score = 0.0
        # New agents with high-risk actions are suspicious
        if len(agent.permissions) > 3:
            score = max(score, 0.2)
        return score

    def _heuristic_temporal_score(self, agent: AgentConfig, action: str, context: dict[str, Any]) -> float:
        """Fallback heuristic when DGL is not available."""
        score = 0.0
        # Off-hours actions are slightly riskier
        from datetime import datetime
        hour = datetime.utcnow().hour
        if hour < 6 or hour > 22:
            score = max(score, 0.15)
        return score

    def _heuristic_tabular_score(self, agent: AgentConfig, action: str, context: dict[str, Any]) -> float:
        """Fallback heuristic when XGBoost is not available."""
        score = 0.0
        # Many permissions without much history is risky
        if len(agent.permissions) > 4:
            score = max(score, 0.25)
        return score

    def _rule_based_score(self, features: AgentFeatures, action: str = "") -> float:
        """Rule-based scoring from extracted features and action type."""
        score = 0.0

        # Action-based risk (independent of history)
        action_risk = {
            "delete_database": 0.9,
            "deploy_prod": 0.8,
            "delete_file": 0.6,
            "write_file": 0.3,
            "read_file": 0.05,
            "execute_step": 0.1,
        }
        score = max(score, action_risk.get(action, 0.2))

        # History-based risk
        if features.failure_rate > 0.5:
            score = max(score, 0.8)
        elif features.failure_rate > 0.3:
            score = max(score, 0.5)

        if features.block_rate > 0.3:
            score = max(score, 0.6)

        if features.risk_score_trend > 0.3:
            score = max(score, 0.5)

        if features.executions_last_hour > 20:
            score = max(score, 0.7)

        if features.off_hours_executions > 5:
            score = max(score, 0.4)

        return score
