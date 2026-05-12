"""Agent Graph Builder -- constructs heterogeneous graphs from workflow history.

Builds graph representations of agent interactions, tool usage, and
workflow execution patterns for input to the three-prong ensemble.
"""

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

    COLLABORATED_WITH = "collaborated_with"      # Agents worked on same workflow
    USED_TOOL = "used_tool"                       # Agent used an MCP tool
    DEPENDS_ON = "depends_on"                     # Step dependency
    SHARED_MEMORY = "shared_memory"               # Agents accessed same memory namespace
    SAME_ROLE = "same_role"                       # Agents have same role
    PRECEEDED = "preceeded"                       # Agent action came before another


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
    """Builds heterogeneous agent relationship graphs from Forge memory.

    Extracts workflow history, agent interactions, and tool usage patterns
to construct graph structures suitable for GNN analysis.
    """

    def __init__(self, memory: MemoryFabric | None = None) -> None:
        self.config = get_config()
        self.memory = memory
        self._graph_dir = Path(self.config.trident_graph_dir)
        self._graph_dir.mkdir(parents=True, exist_ok=True)

    async def build_from_workflow(self, workflow_id: str) -> nx.DiGraph:
        """Build a graph from a single workflow's execution history.

        Args:
            workflow_id: The workflow to analyze.

        Returns:
            NetworkX DiGraph with agents as nodes and interactions as edges.
        """
        G = nx.DiGraph()

        if not self.memory:
            logger.warning("no_memory_backend", workflow_id=workflow_id)
            return G

        # Get workflow history
        history = await self.memory.get_workflow_history(workflow_id)

        # Extract agent nodes
        agent_nodes: dict[str, AgentNode] = {}
        for entry in history:
            agent_id = entry.agent_id or "unknown"
            if agent_id not in agent_nodes:
                agent_nodes[agent_id] = AgentNode(
                    agent_id=agent_id,
                    role=entry.tags[0] if entry.tags else "unknown",
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

    async def build_global_graph(self, max_workflows: int = 100) -> nx.DiGraph:
        """Build a global graph across multiple workflows.

        Args:
            max_workflows: Maximum number of recent workflows to include.

        Returns:
            NetworkX DiGraph representing global agent interactions.
        """
        G = nx.DiGraph()

        if not self.memory:
            return G

        # Get all workflow namespaces
        # This is a simplified approach -- in production, maintain an index
        logger.info("building_global_graph", max_workflows=max_workflows)

        # For now, return empty graph with proper structure
        # Full implementation would scan all workflow:* namespaces
        return G

    def save_graph(self, G: nx.DiGraph, name: str) -> Path:
        """Save a graph to disk in GraphML format.

        Args:
            G: The graph to save.
            name: Filename (without extension).

        Returns:
            Path to the saved file.
        """
        path = self._graph_dir / f"{name}.graphml"
        nx.write_graphml(G, path)
        logger.info("graph_saved", path=str(path), nodes=len(G.nodes), edges=len(G.edges))
        return path

    def load_graph(self, name: str) -> nx.DiGraph:
        """Load a graph from disk.

        Args:
            name: Filename (without extension).

        Returns:
            Loaded NetworkX DiGraph.
        """
        path = self._graph_dir / f"{name}.graphml"
        G = nx.read_graphml(path)
        logger.info("graph_loaded", path=str(path), nodes=len(G.nodes), edges=len(G.edges))
        return G

    def compute_centrality(self, G: nx.DiGraph) -> dict[str, float]:
        """Compute betweenness centrality for all agents.

        High centrality indicates agents that bridge different parts
        of the workflow -- potential single points of failure or
        targets for compromise.

        Returns:
            Dict mapping agent_id to centrality score.
        """
        if len(G.nodes) < 3:
            return {node: 0.0 for node in G.nodes}
        return nx.betweenness_centrality(G, weight="weight")

    def detect_cliques(self, G: nx.DiGraph, min_size: int = 3) -> list[list[str]]:
        """Detect tightly connected agent groups (cliques).

        Cliques may indicate collusion rings or over-coupled teams.

        Returns:
            List of cliques, each a list of agent IDs.
        """
        # Convert to undirected for clique detection
        undirected = G.to_undirected()
        cliques = []
        for clique in nx.find_cliques(undirected):
            if len(clique) >= min_size:
                cliques.append(clique)
        return cliques

    def compute_graph_features(self, G: nx.DiGraph, agent_id: str) -> dict[str, float]:
        """Extract structural features for a specific agent.

        These features feed into Prong 1 (PyG/ID-GNN) for anomaly detection.

        Returns:
            Dict of feature names to values.
        """
        if agent_id not in G.nodes:
            return {}

        in_degree = G.in_degree(agent_id)
        out_degree = G.out_degree(agent_id)
        clustering = nx.clustering(G.to_undirected(), agent_id)

        # Pagerank as influence score
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
