"""Agent protocol definitions.

Agents are the fundamental unit of work in Forge. Each agent has a role,
a set of capabilities, and participates in orchestrated workflows.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """Lifecycle states of an agent execution."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Governance runtime blocked this agent


class AgentConfig(BaseModel):
    """Declarative configuration for an agent.

    Analogous to a Kubernetes Pod spec -- defines what the agent is,
    what it can do, and how it behaves.
    """

    name: str = Field(..., description="Unique agent identifier")
    role: str = Field(..., description="Agent role, e.g. planner, coder, reviewer")
    version: str = Field(default="1.0.0", description="Agent implementation version")
    description: str = Field(default="", description="Human-readable purpose")
    tools: list[str] = Field(default_factory=list, description="Allowed MCP tool names")
    memory_scope: list[str] = Field(
        default_factory=list,
        description="Memory namespaces this agent can read/write",
    )
    permissions: list[str] = Field(
        default_factory=list,
        description="Capability grants, e.g. read:repo, write:file, deploy:prod",
    )
    max_retries: int = Field(default=3, ge=0, description="Auto-retry on transient failures")
    timeout_seconds: int = Field(default=300, ge=1, description="Hard execution timeout")
    requires_human_approval: bool = Field(
        default=False,
        description="If True, governance runtime forces human checkpoint",
    )
    constitution_refs: list[str] = Field(
        default_factory=list,
        description="Org constitution files this agent must follow",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extensible metadata")

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if this agent is permitted to use a given MCP tool."""
        return tool_name in self.tools

    def has_permission(self, permission: str) -> bool:
        """Check if this agent has a specific capability grant."""
        return permission in self.permissions


@dataclass
class AgentResult:
    """Outcome of a single agent execution."""

    agent_name: str
    status: AgentStatus
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)  # Paths to generated files
    logs: list[str] = field(default_factory=list)
    execution_time_ms: int = 0
    token_usage: dict[str, int] = field(default_factory=dict)
    risk_score: float = 0.0  # 0.0-1.0, from governance runtime
    checkpoint_id: str | None = None  # If human approval was required


class Agent(ABC):
    """Abstract base class for all Forge agents.

    Implementations must be async and stateless -- all state lives in the
    MemoryFabric or external stores.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    @abstractmethod
    async def execute(
        self,
        task_input: dict[str, Any],
        context: dict[str, Any],
    ) -> AgentResult:
        """Execute the agent's core logic.

        Args:
            task_input: The specific task payload from the orchestrator.
            context: Shared workflow context (spec content, prior agent outputs, etc.).

        Returns:
            AgentResult with status, output, and metadata.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the agent and its dependencies are healthy."""
        ...
