"""Base MCP Server implementation.

Provides a concrete base class for MCP server adapters.
Specific implementations (GitHub, Jira, AWS, etc.) extend this.
"""

from __future__ import annotations

from typing import Any

from forge.protocols.mcp import MCPServer, MCPTool, ToolCall, ToolResult
from forge.utils.logging import get_logger

logger = get_logger("forge.mcp.server")


class BaseMCPServer(MCPServer):
    """Base implementation of the MCP server protocol.

    Handles common concerns like connection state, tool caching,
    and error handling. Subclasses implement the actual transport.
    """

    def __init__(
        self,
        server_id: str,
        endpoint: str,
        credentials: dict[str, str] | None = None,
    ) -> None:
        super().__init__(server_id, endpoint, credentials)
        self._connected = False

    async def connect(self) -> bool:
        """Establish connection and discover tools.

        Subclasses should override _do_connect() for transport-specific logic.
        """
        try:
            await self._do_connect()
            self._tools = await self._discover_tools()
            self._connected = True
            logger.info(
                "mcp_server_connected",
                server_id=self.server_id,
                tools=len(self._tools or []),
            )
            return True
        except Exception as e:
            logger.error("mcp_server_connect_failed", server_id=self.server_id, error=str(e))
            return False

    async def disconnect(self) -> None:
        """Clean up connection."""
        try:
            await self._do_disconnect()
        except Exception as e:
            logger.warning("mcp_server_disconnect_error", server_id=self.server_id, error=str(e))
        finally:
            self._connected = False
            self._tools = None

    async def list_tools(self) -> list[MCPTool]:
        """Return cached tools, discovering if necessary."""
        if self._tools is None:
            self._tools = await self._discover_tools()
        return self._tools or []

    async def call_tool(self, call: ToolCall) -> ToolResult:
        """Invoke a tool with error handling."""
        if not self._connected:
            return ToolResult(
                call_id=call.call_id,
                success=False,
                data=None,
                error="Server not connected",
            )

        tool = self.get_tool(call.tool_name)
        if not tool:
            return ToolResult(
                call_id=call.call_id,
                success=False,
                data=None,
                error=f"Tool not found: {call.tool_name}",
            )

        try:
            data = await self._invoke_tool(tool, call.arguments)
            return ToolResult(
                call_id=call.call_id,
                success=True,
                data=data,
            )
        except Exception as e:
            logger.exception("tool_call_failed", tool=call.tool_name, server=self.server_id)
            return ToolResult(
                call_id=call.call_id,
                success=False,
                data=None,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Return connection status."""
        return self._connected

    # --- Subclass hooks ---

    async def _do_connect(self) -> None:
        """Transport-specific connection logic. Override in subclass."""
        pass

    async def _do_disconnect(self) -> None:
        """Transport-specific disconnection logic. Override in subclass."""
        pass

    async def _discover_tools(self) -> list[MCPTool]:
        """Discover available tools from the server. Override in subclass."""
        return []

    async def _invoke_tool(self, tool: MCPTool, arguments: dict[str, Any]) -> Any:
        """Actually invoke the tool. Override in subclass."""
        raise NotImplementedError
