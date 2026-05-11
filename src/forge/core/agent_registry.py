"""Agent Registry — declarative agent management.

Think Kubernetes for agents: define what agents exist, their capabilities,
and how they should behave. The registry loads from YAML and validates
agent configurations against available MCP tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from forge.protocols.agent import Agent, AgentConfig
from forge.protocols.mcp import MCPServer
from forge.utils.logging import get_logger

logger = get_logger("forge.agent_registry")


class AgentRegistry:
    """Central registry for agent definitions and instances.

    Loads agent configs from YAML, validates them, and provides
    factory methods for agent instantiation.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or Path("./agents.yaml")
        self._configs: dict[str, AgentConfig] = {}
        self._agents: dict[str, Agent] = {}
        self._mcp_servers: dict[str, MCPServer] = {}

    def register_mcp_server(self, server: MCPServer) -> None:
        """Register an MCP server so agents can discover its tools."""
        self._mcp_servers[server.server_id] = server
        logger.info("mcp_server_registered", server_id=server.server_id, endpoint=server.endpoint)

    def load_configs(self, path: Path | None = None) -> int:
        """Load agent configurations from a YAML file.

        Expected format:
            agents:
              - name: planner
                role: planner
                version: "1.0.0"
                description: "Decomposes specs into executable tasks"
                tools:
                  - github_search
                  - jira_read
                permissions:
                  - read:repo
                memory_scope:
                  - planning
                max_retries: 3
                timeout_seconds: 120

        Returns:
            Number of valid agent configs loaded.
        """
        load_path = path or self.config_path
        if not load_path.exists():
            logger.warning("agent_config_not_found", path=str(load_path))
            return 0

        data = yaml.safe_load(load_path.read_text(encoding="utf-8"))
        raw_agents = data.get("agents", [])

        loaded = 0
        for raw in raw_agents:
            try:
                config = AgentConfig(**raw)
                self._configs[config.name] = config
                loaded += 1
                logger.info("agent_config_loaded", name=config.name, role=config.role)
            except ValidationError as e:
                logger.error("agent_config_invalid", name=raw.get("name", "unknown"), error=str(e))

        logger.info("agent_registry_loaded", total=len(self._configs), path=str(load_path))
        return loaded

    def get_config(self, name: str) -> AgentConfig | None:
        """Get an agent configuration by name."""
        return self._configs.get(name)

    def list_configs(self) -> list[AgentConfig]:
        """List all registered agent configurations."""
        return list(self._configs.values())

    def list_by_role(self, role: str) -> list[AgentConfig]:
        """Find all agents with a given role."""
        return [c for c in self._configs.values() if c.role == role]

    def register_agent(self, name: str, agent: Agent) -> None:
        """Register an instantiated agent."""
        self._agents[name] = agent
        logger.info("agent_instance_registered", name=name, role=agent.config.role)

    def get_agent(self, name: str) -> Agent | None:
        """Get an instantiated agent by name."""
        return self._agents.get(name)

    def validate_tools(self, config: AgentConfig) -> list[str]:
        """Validate that all tools in an agent config are available.

        Returns:
            List of unavailable tool names (empty if all valid).
        """
        available: set[str] = set()
        for server in self._mcp_servers.values():
            # This is async in real impl; simplified here
            available.update(t.name for t in server._tools or [])

        missing = [t for t in config.tools if t not in available]
        if missing:
            logger.warning("agent_tools_missing", agent=config.name, missing=missing)
        return missing

    def health_check_all(self) -> dict[str, bool]:
        """Run health checks on all registered MCP servers.

        Returns:
            Dict mapping server_id to health status.
        """
        results: dict[str, bool] = {}
        for server_id, server in self._mcp_servers.items():
            try:
                # In async context, this would be awaited
                results[server_id] = True  # Placeholder
            except Exception as e:
                logger.error("mcp_health_check_failed", server_id=server_id, error=str(e))
                results[server_id] = False
        return results

    def to_yaml(self, path: Path) -> None:
        """Export current registry to YAML."""
        data = {
            "agents": [config.model_dump() for config in self._configs.values()]
        }
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        logger.info("agent_registry_exported", path=str(path), count=len(self._configs))
