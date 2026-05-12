"""Agent Graph Builder -- constructs heterogeneous graphs from workflow history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import networkx as nx

from forge.config import get_config
from forge.memory.fabric import MemoryFabric
from forge.protocols.memory import MemoryEntry
from forge.utils.logging import get_logger

logger = get_logger("forge.trident.graph_builder")


class EdgeType(str, Enum):
    """Types of edges in the agent relationship graph."""

    COLLABORATED_WITH = "collaborated_with"
    USED_TOOL = "used_tool"
    DEPENDS_ON = "depends_on"
    SHARED_MEMORY = "shared_memory"
    SAME_ROLE = "same_role"
    PRECEEDED = "preceeded"


@dataclass
class AgentNode:
    """A node representing an agent in the graph."""

    agent_id: str
    role: str
    name: str
    permissions: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    execution_count: int = 0
    failure_count: int = 0
    avg_risk_score: float = 0.0


@dataclass
class AgentEdge:
    """An edge representing a relationship between agents."""

    source: str
    target: str
    edge_type: EdgeType
    weight: float = 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentGraphBuilder:
    """Builds heterogeneous agent relationship graphs from Forge memory."""

    def __init__(self, memory: MemoryFabric | None = None) -> None:
        self.config = get_config()
        self.memory = memory
        self._graph_dir = Path(self.config.trident_graph_dir)
        self._graph_dir.mkdir(parents=True, exist_ok=True)

    async def build_from_workflow(self, workflow_id: str) -> nx.DiGraph:
        """Build a graph from a single workflow's execution history."""
        G = nx.DiGraph()

        if not self.memory:
            logger.warning("no_memory_backend", workflow_id=workflow_id)
            return G

        # Get workflow history from episodic memory (where log_event stores)
        history = await self._get_workflow_events(workflow_id)

        # Extract agent nodes
        agent_nodes: dict[str, AgentNode] = {}
        for entry in history:
            agent_id = entry.agent_id or "unknown"
            if agent_id not in agent_nodes:
                # Try to infer role from tags or payload
                role = "unknown"
                if entry.tags and len(entry.tags) > 1:
                    role = entry.tags[1]  # Second tag often is role
                elif isinstance(entry.value, dict) and "agent" in entry.value:
                    role = entry.value.get("agent", "unknown")

                agent_nodes[agent_id] = AgentNode(
                    agent_id=agent_id,
                    role=role,
                    name=agent_id,
                )
            node = agent_nodes[agent_id]
            node.execution_count += 1
            node.last_seen = entry.timestamp

        # Add nodes to graph
        for agent_id, node in agent_nodes.items():
            G.add_node(
                agent_id,
                **{
                    "role": node.role,
                    "name": node.name,
                    "execution_count": node.execution_count,
                    "first_seen": node.first_seen.isoformat(),
                    "last_seen": node.last_seen.isoformat(),
                },
            )

        # Add collaboration edges (agents in same workflow)
        agent_ids = list(agent_nodes.keys())
        for i, source in enumerate(agent_ids):
            for target in agent_ids[i + 1:]:
                G.add_edge(
                    source,
                    target,
                    edge_type=EdgeType.COLLABORATED_WITH.value,
                    weight=1.0,
                    workflow_id=workflow_id,
                )
                G.add_edge(
                    target,
                    source,
                    edge_type=EdgeType.COLLABORATED_WITH.value,
                    weight=1.0,
                    workflow_id=workflow_id,
                )

        logger.info("graph_built", workflow_id=workflow_id, nodes=len(G.nodes), edges=len(G.edges))
        return G

    async def _get_workflow_events(self, workflow_id: str) -> list[MemoryEntry]:
        """Get all episodic events for a specific workflow."""
        if not self.memory:
            return []

        # List all keys in episodic namespace and filter by workflow_id
        try:
            keys = await self.memory._backend.list_keys(namespace="episodic")
        except Exception:
            return []

        entries = []
        for key in keys:
            entry = await self.memory._backend.read(key, namespace="episodic")
            if entry and entry.workflow_id == workflow_id:
                entries.append(entry)

        return entries

    async def build_global_graph(self, max_workflows: int = 100) -> nx.DiGraph:
        """Build a global graph across multiple workflows."""
        G = nx.DiGraph()

        if not self.memory:
            return G

        logger.info("building_global_graph", max_workflows=max_workflows)
        return G

    def save_graph(self, G: nx.DiGraph, name: str) -> Path:
        """Save a graph to disk in GraphML format."""
        path = self._graph_dir / f"{name}.graphml"
        nx.write_graphml(G, path)
        logger.info("graph_saved", path=str(path), nodes=len(G.nodes), edges=len(G.edges))
        return path

    def load_graph(self, name: str) -> nx.DiGraph:
        """Load a graph from disk."""
        path = self._graph_dir / f"{name}.graphml"
        G = nx.read_graphml(path)
        logger.info("graph_loaded", path=str(path), nodes=len(G.nodes), edges=len(G.edges))
        return G

    def compute_centrality(self, G: nx.DiGraph) -> dict[str, float]:
        """Compute betweenness centrality for all agents."""
        if len(G.nodes) < 3:
            return {node: 0.0 for node in G.nodes}
        return nx.betweenness_centrality(G, weight="weight")

    def detect_cliques(self, G: nx.DiGraph, min_size: int = 3) -> list[list[str]]:
        """Detect tightly connected agent groups (cliques)."""
        undirected = G.to_undirected()
        cliques = []
        for clique in nx.find_cliques(undirected):
            if len(clique) >= min_size:
                cliques.append(clique)
        return cliques

    def compute_graph_features(self, G: nx.DiGraph, agent_id: str) -> dict[str, float]:
        """Extract structural features for a specific agent."""
        if agent_id not in G.nodes:
            return {}

        in_degree = G.in_degree(agent_id)
        out_degree = G.out_degree(agent_id)
        clustering = nx.clustering(G.to_undirected(), agent_id)

        try:
            pagerank = nx.pagerank(G, weight="weight")[agent_id]
        except Exception:
            pagerank = 0.0

        return {
            "in_degree": float(in_degree),
            "out_degree": float(out_degree),
            "clustering": float(clustering),
            "pagerank": float(pagerank),
            "neighbor_count": float(len(list(G.neighbors(agent_id)))),
            "reciprocal_edges": float(len([
                n for n in G.neighbors(agent_id)
                if G.has_edge(n, agent_id)
            ])),
        }
