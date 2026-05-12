"""BGI Trident configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TridentConfig(BaseSettings):
    """Configuration for BGI Trident integration."""

    model_config = SettingsConfigDict(
        env_prefix="TRIDENT_",
        env_file=".env",
        extra="ignore",
    )

    # Graph storage
    graph_dir: Path = Field(default=Path("./.forge/graph"), description="Directory for graph storage")
    graph_format: Literal["pyg", "dgl", "networkx"] = Field(default="networkx", description="Graph library format")

    # Prong 1: PyG / ID-GNN
    prong1_enabled: bool = Field(default=True, description="Enable agent relationship graph anomaly detection")
    prong1_model_path: Path | None = Field(default=None, description="Path to pre-trained PyG model")
    prong1_hidden_dim: int = Field(default=64, description="Hidden dimension for GNN layers")
    prong1_num_layers: int = Field(default=3, description="Number of GNN layers")
    prong1_dropout: float = Field(default=0.3, ge=0.0, le=1.0, description="Dropout rate")
    prong1_anomaly_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Score above which anomaly is flagged")

    # Prong 2: DGL / R-GCN
    prong2_enabled: bool = Field(default=True, description="Enable temporal behavior drift detection")
    prong2_model_path: Path | None = Field(default=None, description="Path to pre-trained DGL model")
    prong2_num_relations: int = Field(default=5, description="Number of relation types in R-GCN")
    prong2_time_window_hours: int = Field(default=24, description="Time window for temporal analysis")
    prong2_drift_threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="Drift score threshold")

    # Prong 3: XGBoost
    prong3_enabled: bool = Field(default=True, description="Enable threshold-based policy rules")
    prong3_model_path: Path | None = Field(default=None, description="Path to pre-trained XGBoost model")
    prong3_max_depth: int = Field(default=6, description="XGBoost max tree depth")
    prong3_learning_rate: float = Field(default=0.1, description="XGBoost learning rate")
    prong3_n_estimators: int = Field(default=100, description="Number of XGBoost estimators")

    # Ensemble
    ensemble_weights: list[float] = Field(default=[0.4, 0.35, 0.25], description="Weights for [Prong1, Prong2, Prong3]")
    ensemble_meta_learner: Literal["mean", "weighted", "stacking"] = Field(default="weighted", description="Ensemble combination method")

    # Feature extraction
    max_history_events: int = Field(default=1000, description="Max events to consider for feature extraction")
    feature_cache_ttl: int = Field(default=300, description="Feature cache TTL in seconds")

    def validate_weights(self) -> bool:
        """Check that ensemble weights sum to 1.0."""
        return abs(sum(self.ensemble_weights) - 1.0) < 1e-6
