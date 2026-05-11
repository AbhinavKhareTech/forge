"""MCP Mesh — dynamic server discovery and routing.

The MCP Mesh maintains a registry of available MCP servers, performs
health checks, and routes tool calls to the appropriate server.

Agents discover tools dynamically rather than hardcoding server endpoints.
"""

from __future__ import annotations

import asyncio
from typing import Any

from forge.config import get_config
from forge.protocols.mcp import MCPServer, MCPTool, ToolCall, ToolResult
from forge.utils.logging import get_logger

logger = get_logger("forge.mcp.mesh")


class MCPMesh:
    """Dynamic MCP server mesh manager.

    Handles:
    - Server registration and discovery
    - Periodic health checks
    - Tool routing (find server by tool name)
    - Load balancing across multiple servers with same tool
    """

    def __init__(self) -> None:
        self.config = get_config()
        self._servers: dict[str, MCPServer] = {}
        self._tool_index: dict[str, list[str]] = {}  # tool_name -> [server_id, ...]
        self._health_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the mesh and begin periodic health checks."""
        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())
        logger.info("mcp_mesh_started")

    async def stop(self) -> None:
        """Stop health checks and disconnect all servers."""
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        for server in self._servers.values():
            await server.disconnect()

        logger.info("mcp_mesh_stopped")

    def register_server(self, server: MCPServer) -> None:
        """Register an MCP server with the mesh."""
        self._servers[server.server_id] = server
        logger.info("mcp_server_registered", server_id=server.server_id)

    async def discover_tools(self) -> dict[str, list[MCPTool]]:
        """Discover all tools across all registered servers.

        Returns:
            Dict mapping server_id to list of tools.
        """
        discovered: dict[str, list[MCPTool]] = {}
        for server_id, server in self._servers.items():
            try:
                tools = await server.list_tools()
                discovered[server_id] = tools
                for tool in tools:
                    if tool.name not in self._tool_index:
                        self._tool_index[tool.name] = []
                    if server_id not in self._tool_index[tool.name]:
                        self._tool_index[tool.name].append(server_id)
            except Exception as e:
                logger.error("tool_discovery_failed", server=server_id, error=str(e))
        return discovered

    async def call_tool(self, call: ToolCall) -> ToolResult:
        """Route a tool call to the appropriate server.

        If multiple servers expose the same tool, uses simple round-robin.
        """
        server_ids = self._tool_index.get(call.tool_name)
        if not server_ids:
            return ToolResult(
                call_id=call.call_id,
                success=False,
                data=None,
                error=f"Tool not found in mesh: {call.tool_name}",
            )

        # Simple round-robin: pick first available
        for server_id in server_ids:
            server = self._servers.get(server_id)
            if server and await server.health_check():
                return await server.call_tool(call)

        return ToolResult(
            call_id=call.call_id,
            success=False,
            data=None,
            error=f"No healthy server available for tool: {call.tool_name}",
        )

    def list_servers(self) -> list[str]:
        """List all registered server IDs."""
        return list(self._servers.keys())

    def list_tools(self) -> list[str]:
        """List all discovered tool names."""
        return list(self._tool_index.keys())

    def get_server_for_tool(self, tool_name: str) -> MCPServer | None:
        """Get a healthy server that exposes a given tool."""
        server_ids = self._tool_index.get(tool_name, [])
        for sid in server_ids:
            server = self._servers.get(sid)
            if server:
                return server
        return None

    async def _health_check_loop(self) -> None:
        """Periodic health check of all registered servers."""
        while self._running:
            await asyncio.sleep(self.config.mcp_discovery_interval)
            for server_id, server in self._servers.items():
                try:
                    healthy = await server.health_check()
                    if not healthy:
                        logger.warning("mcp_server_unhealthy", server_id=server_id)
                except Exception as e:
                    logger.error("mcp_health_check_error", server_id=server_id, error=str(e))
