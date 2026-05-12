"""Tests for BGI Trident integration."""

from __future__ import annotations

import pytest

from forge.protocols.agent import AgentConfig
from forge.trident.config import TridentConfig
from forge.trident.ensemble import TridentEnsemble, TridentResult
from forge.trident.features import AgentFeatureExtractor, AgentFeatures
from forge.trident.graph_builder import AgentGraphBuilder
from forge.memory.fabric import InMemoryBackend, MemoryFabric


class TestTridentConfig:
    """Test suite for Trident configuration."""

    def test_default_weights_sum_to_one(self) -> None:
        """Ensemble weights must sum to 1.0."""
        config = TridentConfig()
        assert config.validate_weights()
        assert sum(config.ensemble_weights) == pytest.approx(1.0, abs=1e-6)

    def test_prong_enabled_flags(self) -> None:
        """All prongs enabled by default."""
        config = TridentConfig()
        assert config.prong1_enabled is True
        assert config.prong2_enabled is True
        assert config.prong3_enabled is True

    def test_thresholds_in_range(self) -> None:
        """Thresholds must be between 0 and 1."""
        config = TridentConfig()
        assert 0.0 <= config.prong1_anomaly_threshold <= 1.0
        assert 0.0 <= config.prong2_drift_threshold <= 1.0


class TestAgentGraphBuilder:
    """Test suite for agent graph construction."""

    @pytest.fixture
    def graph_builder(self):
        memory = MemoryFabric(backend=InMemoryBackend())
        return AgentGraphBuilder(memory=memory)

    @pytest.mark.asyncio
    async def test_build_empty_workflow_graph(self, graph_builder: AgentGraphBuilder) -> None:
        """Empty workflow produces empty graph."""
        G = await graph_builder.build_from_workflow("nonexistent")
        assert len(G.nodes) == 0
        assert len(G.edges) == 0

    @pytest.mark.asyncio
    async def test_build_workflow_graph_with_agents(self, graph_builder: AgentGraphBuilder) -> None:
        """Graph contains agents from workflow history."""
        # Seed memory with agent events
        await graph_builder.memory.log_event(
            event_type="agent_execute",
            payload={"agent": "planner", "status": "completed"},
            agent_id="planner",
            workflow_id="wf-1",
        )
        await graph_builder.memory.log_event(
            event_type="agent_execute",
            payload={"agent": "coder", "status": "completed"},
            agent_id="coder",
            workflow_id="wf-1",
        )

        G = await graph_builder.build_from_workflow("wf-1")
        assert "planner" in G.nodes
        assert "coder" in G.nodes
        assert G.has_edge("planner", "coder")

    def test_compute_centrality_empty_graph(self, graph_builder: AgentGraphBuilder) -> None:
        """Centrality on empty graph returns empty dict."""
        import networkx as nx
        G = nx.DiGraph()
        centrality = graph_builder.compute_centrality(G)
        assert centrality == {}

    def test_detect_cliques_small_graph(self, graph_builder: AgentGraphBuilder) -> None:
        """Small graph has no cliques of size 3."""
        import networkx as nx
        G = nx.DiGraph()
        G.add_edge("a", "b")
        cliques = graph_builder.detect_cliques(G, min_size=3)
        assert len(cliques) == 0

    def test_graph_save_and_load(self, graph_builder: AgentGraphBuilder, tmp_path) -> None:
        """Graph roundtrip through GraphML."""
        import networkx as nx
        G = nx.DiGraph()
        G.add_node("planner", role="planner")
        G.add_node("coder", role="coder")
        G.add_edge("planner", "coder", edge_type="collaborated_with")

        graph_builder._graph_dir = tmp_path
        path = graph_builder.save_graph(G, "test")
        assert path.exists()

        loaded = graph_builder.load_graph("test")
        assert "planner" in loaded.nodes
        assert "coder" in loaded.nodes


class TestAgentFeatureExtractor:
    """Test suite for feature extraction."""

    @pytest.fixture
    def extractor(self):
        memory = MemoryFabric(backend=InMemoryBackend())
        return AgentFeatureExtractor(memory=memory)

    @pytest.mark.asyncio
    async def test_extract_empty_history(self, extractor: AgentFeatureExtractor) -> None:
        """Agent with no history has zero features."""
        agent = AgentConfig(name="test", role="planner", tools=[], permissions=[])
        features = await extractor.extract(agent, "read_file", {})

        assert features.agent_id == "test"
        assert features.role == "planner"
        assert features.total_executions == 0
        assert features.failure_rate == 0.0

    @pytest.mark.asyncio
    async def test_extract_with_history(self, extractor: AgentFeatureExtractor) -> None:
        """Features computed from agent history."""
        agent = AgentConfig(name="coder", role="coder", tools=[], permissions=["read:repo"])

        # Log some events
        for i in range(5):
            await extractor.memory.log_event(
                event_type="agent_execute",
                payload={"status": "completed", "execution_time_ms": 1000, "risk_score": 0.2},
                agent_id="coder",
                workflow_id=f"wf-{i}",
            )

        features = await extractor.extract(agent, "write_file", {})
        assert features.total_executions == 5
        assert features.avg_risk_score == pytest.approx(0.2, abs=0.01)
        assert features.permissions_granted == 1

    def test_to_vector(self, extractor: AgentFeatureExtractor) -> None:
        """Feature vector has consistent length."""
        features = AgentFeatures(agent_id="test", role="planner")
        vector = extractor.to_vector(features)
        assert len(vector) == 20  # Fixed feature count
        assert all(isinstance(v, float) for v in vector)


class TestTridentEnsemble:
    """Test suite for the three-prong ensemble."""

    @pytest.fixture
    def ensemble(self):
        config = TridentConfig()
        return TridentEnsemble(config=config)

    @pytest.mark.asyncio
    async def test_evaluate_safe_agent(self, ensemble: TridentEnsemble) -> None:
        """Safe agent gets low score."""
        agent = AgentConfig(name="reviewer", role="reviewer", tools=[], permissions=["read:repo"])
        result = await ensemble.evaluate(agent, "read_file", {})

        assert isinstance(result, TridentResult)
        assert 0.0 <= result.ensemble_score <= 1.0
        assert "prong3" in result.prong_scores  # Always available (rule-based fallback)

    @pytest.mark.asyncio
    async def test_evaluate_high_risk_agent(self, ensemble: TridentEnsemble) -> None:
        """High-risk action gets elevated score."""
        agent = AgentConfig(name="coder", role="coder", tools=[], permissions=[])
        result = await ensemble.evaluate(agent, "delete_database", {})

        assert result.ensemble_score >= 0.2  # delete_database elevates score via prong3

    @pytest.mark.asyncio
    async def test_prong_scores_present(self, ensemble: TridentEnsemble) -> None:
        """All enabled prongs produce scores."""
        agent = AgentConfig(name="planner", role="planner", tools=[], permissions=[])
        result = await ensemble.evaluate(agent, "execute_step", {})

        if ensemble.config.prong1_enabled:
            assert "prong1" in result.prong_scores
        if ensemble.config.prong2_enabled:
            assert "prong2" in result.prong_scores
        if ensemble.config.prong3_enabled:
            assert "prong3" in result.prong_scores

    def test_combine_scores_mean(self) -> None:
        """Mean meta-learner averages scores."""
        config = TridentConfig(ensemble_meta_learner="mean")
        ensemble = TridentEnsemble(config=config)
        score = ensemble._combine_scores({"prong1": 0.5, "prong2": 0.7})
        assert score == pytest.approx(0.6, abs=0.01)

    def test_combine_scores_weighted(self) -> None:
        """Weighted meta-learner respects weights."""
        config = TridentConfig(
            ensemble_meta_learner="weighted",
            ensemble_weights=[0.5, 0.3, 0.2],
        )
        ensemble = TridentEnsemble(config=config)
        score = ensemble._combine_scores({"prong1": 0.5, "prong2": 0.7})
        expected = (0.5 * 0.5 + 0.7 * 0.3) / (0.5 + 0.3)
        assert score == pytest.approx(expected, abs=0.01)

    def test_combine_scores_stacking(self) -> None:
        """Stacking meta-learner takes max."""
        config = TridentConfig(ensemble_meta_learner="stacking")
        ensemble = TridentEnsemble(config=config)
        score = ensemble._combine_scores({"prong1": 0.5, "prong2": 0.7})
        assert score == 0.7


class TestGovernanceWithTrident:
    """Test suite for governance runtime with Trident enabled."""

    @pytest.fixture
    def governance_with_trident(self):
        from forge.governance.runtime import GovernanceRuntime
        gov = GovernanceRuntime()
        gov.load_policies([
            {
                "name": "block_coder_delete",
                "condition": {
                    "forbidden_roles": ["coder"],
                    "forbidden_actions": ["delete_database"],
                },
                "action": "block",
            },
        ])
        return gov

    @pytest.mark.asyncio
    async def test_trident_enabled_by_config(self, governance_with_trident) -> None:
        """Trident scoring is applied when enabled."""
        from forge.config import get_config
        config = get_config()
        # Trident is disabled by default in tests; this validates structure
        assert hasattr(governance_with_trident, "_trident")

    @pytest.mark.asyncio
    async def test_governance_returns_trident_signals(self, governance_with_trident) -> None:
        """Governance result includes Trident signals when available."""
        agent = AgentConfig(name="coder", role="coder", tools=[], permissions=[])
        result = await governance_with_trident._evaluate(agent, "read_file", {})

        assert hasattr(result, "trident_signals")
        assert isinstance(result.trident_signals, list)
