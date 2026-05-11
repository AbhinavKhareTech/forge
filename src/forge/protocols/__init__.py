"""Forge protocols — abstract interfaces for agents, memory, and MCP.

All components in Forge communicate through these protocols, enabling
swappable implementations and testability.
"""

from forge.protocols.agent import Agent, AgentConfig, AgentResult, AgentStatus
from forge.protocols.memory import MemoryBackend, MemoryEntry
from forge.protocols.mcp import MCPServer, MCPTool, ToolCall

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentResult",
    "AgentStatus",
    "MemoryBackend",
    "MemoryEntry",
    "MCPServer",
    "MCPTool",
    "ToolCall",
]
