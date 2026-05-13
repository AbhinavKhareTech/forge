"""Forge configuration management.

Uses pydantic-settings for environment-aware configuration with validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ForgeConfig(BaseSettings):
    """Global Forge configuration.

    All values can be overridden via environment variables with the FORGE_ prefix,
    e.g. FORGE_ENV=production, FORGE_LOG_LEVEL=debug.
    """

    model_config = SettingsConfigDict(
        env_prefix="FORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Runtime environment",
    )
    log_level: Literal["debug", "info", "warning", "error", "critical"] = Field(
        default="info",
        description="Logging verbosity",
    )
    spec_dir: Path = Field(
        default=Path("./specs"),
        description="Directory containing executable specs",
    )
    agent_registry_path: Path = Field(
        default=Path("./agents.yaml"),
        description="Path to agent registry configuration",
    )
    memory_backend: Literal["redis", "inmemory"] = Field(
        default="inmemory",
        description="Backend for shared agent memory",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    governance_enabled: bool = Field(
        default=True,
        description="Enable policy enforcement runtime",
    )
    trident_enabled: bool = Field(
        default=False,
        description="Enable BGI Trident graph-native governance",
    )
    trident_graph_dir: Path = Field(
        default=Path("./.forge/graph"),
        description="Directory for BGI Trident graph storage",
    )
    mcp_discovery_interval: int = Field(
        default=30,
        description="Seconds between MCP server health checks",
    )
    max_concurrent_agents: int = Field(
        default=10,
        description="Maximum agents running in parallel per orchestration",
    )
    human_checkpoint_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Risk score above which human approval is required",
    )

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.env == "production"


# Singleton config instance
_config: ForgeConfig | None = None


def get_config() -> ForgeConfig:
    """Get or create the global Forge configuration."""
    global _config
    if _config is None:
        _config = ForgeConfig()
    return _config


def reset_config() -> None:
    """Reset the global config (useful for testing)."""
    global _config
    _config = None
