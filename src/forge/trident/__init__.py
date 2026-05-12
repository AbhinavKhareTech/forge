"""BGI Trident integration for Forge.

Provides graph-native governance and reasoning through the three-prong ensemble:
- Prong 1 (PyG/ID-GNN): Agent relationship graph anomaly detection
- Prong 2 (DGL/R-GCN): Temporal behavior drift in agent actions
- Prong 3 (XGBoost): Threshold-based policy rule enforcement

This module bridges Forge's Governance Runtime with the BGI Trident
graph engine for deep, contextual risk scoring.
"""

from forge.trident.ensemble import TridentEnsemble
from forge.trident.graph_builder import AgentGraphBuilder
from forge.trident.features import AgentFeatureExtractor

__all__ = ["TridentEnsemble", "AgentGraphBuilder", "AgentFeatureExtractor"]
