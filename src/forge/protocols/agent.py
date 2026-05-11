"""Agent protocol definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class AgentConfig(BaseModel):
    """Declarative configuration for an agent."""

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
        return tool_name in self.tools

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


@dataclass
class AgentResult:
    """Outcome of a single agent execution."""

    agent_name: str
    status: AgentStatus
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    execution_time_ms: int = 0
    token_usage: dict[str, int] = field(default_factory=dict)
    risk_score: float = 0.0
    checkpoint_id: str | None = None


class Agent(ABC):
    """Abstract base class for all Forge agents."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    @abstractmethod
    async def execute(
        self,
        task_input: dict[str, Any],
        context: dict[str, Any],
    ) -> AgentResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...
