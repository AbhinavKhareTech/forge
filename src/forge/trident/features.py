"""Feature extraction for BGI Trident ensemble."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from forge.config import get_config
from forge.memory.fabric import MemoryFabric
from forge.protocols.agent import AgentConfig
from forge.utils.logging import get_logger

logger = get_logger("forge.trident.features")


@dataclass
class AgentFeatures:
    """Tabular features extracted for an agent."""

    agent_id: str
    role: str

    # Execution history
    total_executions: int = 0
    total_failures: int = 0
    total_blocks: int = 0
    avg_execution_time_ms: float = 0.0
    avg_risk_score: float = 0.0

    # Temporal patterns
    executions_last_hour: int = 0
    executions_last_day: int = 0
    executions_last_week: int = 0
    peak_hour_executions: int = 0
    off_hours_executions: int = 0

    # Tool usage
    unique_tools_used: int = 0
    most_used_tool: str = ""
    tool_diversity_ratio: float = 0.0

    # Permission utilization
    permissions_granted: int = 0
    permissions_used: int = 0
    permission_utilization: float = 0.0

    # Workflow patterns
    unique_workflows: int = 0
    avg_steps_per_workflow: float = 0.0
    max_steps_in_workflow: int = 0

    # Anomaly indicators
    failure_rate: float = 0.0
    block_rate: float = 0.0
    risk_score_trend: float = 0.0
    time_since_last_execution_hours: float = 0.0


class AgentFeatureExtractor:
    """Extracts features from agent execution history for Trident scoring."""

    def __init__(self, memory: MemoryFabric | None = None) -> None:
        self.config = get_config()
        self.memory = memory

    async def extract(self, agent: AgentConfig, action: str, context: dict[str, Any]) -> AgentFeatures:
        """Extract features for a specific agent and action."""
        features = AgentFeatures(
            agent_id=agent.name,
            role=agent.role,
            permissions_granted=len(agent.permissions),
        )

        if not self.memory:
            logger.debug("no_memory_for_features", agent=agent.name)
            return features

        # Get agent history from episodic memory
        history = await self._get_agent_history(agent.name)

        # Compute execution stats
        features.total_executions = len(history)
        features.total_failures = sum(
            1 for h in history
            if isinstance(h.value, dict) and h.value.get("status") == "failed"
        )
        features.total_blocks = sum(
            1 for h in history
            if isinstance(h.value, dict) and h.value.get("status") == "blocked"
        )

        if features.total_executions > 0:
            features.failure_rate = features.total_failures / features.total_executions
            features.block_rate = features.total_blocks / features.total_executions

            exec_times = [
                h.value.get("execution_time_ms", 0)
                for h in history
                if isinstance(h.value, dict) and isinstance(h.value.get("execution_time_ms"), (int, float))
            ]
            if exec_times:
                features.avg_execution_time_ms = sum(exec_times) / len(exec_times)

            risk_scores = [
                h.value.get("risk_score", 0)
                for h in history
                if isinstance(h.value, dict) and isinstance(h.value.get("risk_score"), (int, float))
            ]
            if risk_scores:
                features.avg_risk_score = sum(risk_scores) / len(risk_scores)
                if len(risk_scores) >= 4:
                    recent = sum(risk_scores[-2:]) / 2
                    older = sum(risk_scores[:-2]) / len(risk_scores[:-2])
                    features.risk_score_trend = recent - older

        # Temporal patterns
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(weeks=1)

        for h in history:
            ts = h.timestamp
            if ts > hour_ago:
                features.executions_last_hour += 1
            if ts > day_ago:
                features.executions_last_day += 1
            if ts > week_ago:
                features.executions_last_week += 1

            if ts.hour < 6 or ts.hour >= 22:
                features.off_hours_executions += 1

        # Time since last execution
        if history:
            last_ts = max(h.timestamp for h in history)
            features.time_since_last_execution_hours = (now - last_ts).total_seconds() / 3600

        # Tool usage diversity
        tools_used: set[str] = set()
        tool_counts: dict[str, int] = {}
        for h in history:
            if isinstance(h.value, dict):
                tools = h.value.get("tools_used", [])
                for t in tools:
                    tools_used.add(t)
                    tool_counts[t] = tool_counts.get(t, 0) + 1

        features.unique_tools_used = len(tools_used)
        if tool_counts:
            features.most_used_tool = max(tool_counts, key=tool_counts.get)
            features.tool_diversity_ratio = len(tools_used) / sum(tool_counts.values())

        # Workflow patterns
        workflow_ids: set[str] = set()
        for h in history:
            if h.workflow_id:
                workflow_ids.add(h.workflow_id)
        features.unique_workflows = len(workflow_ids)

        logger.debug(
            "features_extracted",
            agent=agent.name,
            executions=features.total_executions,
            failure_rate=features.failure_rate,
            risk_trend=features.risk_score_trend,
        )

        return features

    async def _get_agent_history(self, agent_name: str) -> list[Any]:
        """Get execution history for an agent from episodic memory."""
        if not self.memory:
            return []

        # List all keys in episodic namespace and filter by agent_id
        try:
            keys = await self.memory._backend.list_keys(namespace="episodic")
        except Exception:
            return []

        entries = []
        for key in keys:
            entry = await self.memory._backend.read(key, namespace="episodic")
            if entry and entry.agent_id == agent_name:
                entries.append(entry)

        return entries

    def to_vector(self, features: AgentFeatures) -> list[float]:
        """Convert features to a flat vector for XGBoost (Prong 3)."""
        return [
            float(features.total_executions),
            float(features.total_failures),
            float(features.total_blocks),
            features.avg_execution_time_ms / 1000.0,
            features.avg_risk_score,
            float(features.executions_last_hour),
            float(features.executions_last_day),
            float(features.executions_last_week),
            float(features.off_hours_executions),
            features.failure_rate,
            features.block_rate,
            features.risk_score_trend,
            features.time_since_last_execution_hours,
            float(features.unique_tools_used),
            features.tool_diversity_ratio,
            float(features.permissions_granted),
            features.permission_utilization,
            float(features.unique_workflows),
            features.avg_steps_per_workflow,
            float(features.max_steps_in_workflow),
        ]
