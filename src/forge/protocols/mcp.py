"""MCP (Model Context Protocol) server protocol.

Forge's MCP Mesh discovers and routes to MCP servers dynamically.
This protocol abstracts the client side.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server_id: str


@dataclass
class ToolCall:
    """A request to invoke an MCP tool."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass
class ToolResult:
    """Result of an MCP tool invocation."""

    call_id: str | None
    success: bool
    data: Any
    error: str | None = None
    latency_ms: int = 0


class MCPServer(ABC):
    """Abstract MCP server client.

    Implementations wrap specific MCP servers (GitHub, Jira, AWS, Razorpay, etc.).
    """

    def __init__(self, server_id: str, endpoint: str, credentials: dict[str, str] | None = None) -> None:
        self.server_id = server_id
        self.endpoint = endpoint
        self.credentials = credentials or {}
        self._tools: list[MCPTool] | None = None

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection and discover available tools."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up connection resources."""
        ...

    @abstractmethod
    async def list_tools(self) -> list[MCPTool]:
        """Return all tools exposed by this server."""
        ...

    @abstractmethod
    async def call_tool(self, call: ToolCall) -> ToolResult:
        """Invoke a tool with the given arguments."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if server is reachable and healthy."""
        ...

    def get_tool(self, name: str) -> MCPTool | None:
        """Get a specific tool by name."""
        if self._tools is None:
            return None
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None
