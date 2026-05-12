"""Jira MCP Server Adapter.

Provides MCP tools for Jira operations:
- Read issues
- Create/update issues
- Search issues
- Add comments
"""

from __future__ import annotations

from typing import Any

from forge.protocols.mcp import MCPTool, ToolCall, ToolResult
from forge.mcp.server import BaseMCPServer
from forge.utils.logging import get_logger

logger = get_logger("forge.mcp.jira")


class JiraMCPServer(BaseMCPServer):
    """MCP server adapter for Jira API.

    In production, this wraps the Jira REST API. The mock
    implementation simulates responses for testing.
    """

    def __init__(
        self,
        server_id: str = "jira",
        endpoint: str = "https://ahinsaai.atlassian.net",
        credentials: dict[str, str] | None = None,
    ) -> None:
        super().__init__(server_id, endpoint, credentials)
        self._project = credentials.get("project", "FORGE") if credentials else "FORGE"
        self._token = credentials.get("token", "") if credentials else ""

    async def _do_connect(self) -> None:
        logger.info("jira_connecting", endpoint=self.endpoint, project=self._project)

    async def _do_disconnect(self) -> None:
        logger.info("jira_disconnected")

    async def _discover_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="jira_read",
                description="Read a Jira issue by key",
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_key": {"type": "string", "description": "Jira issue key (e.g. FORGE-123)"},
                    },
                    "required": ["issue_key"],
                },
                server_id=self.server_id,
            ),
            MCPTool(
                name="jira_search",
                description="Search Jira issues using JQL",
                input_schema={
                    "type": "object",
                    "properties": {
                        "jql": {"type": "string", "description": "JQL query string"},
                        "max_results": {"type": "integer", "default": 10},
                    },
                    "required": ["jql"],
                },
                server_id=self.server_id,
            ),
            MCPTool(
                name="jira_create",
                description="Create a new Jira issue",
                input_schema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "description": {"type": "string"},
                        "issue_type": {"type": "string", "default": "Task"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary"],
                },
                server_id=self.server_id,
            ),
            MCPTool(
                name="jira_comment",
                description="Add a comment to a Jira issue",
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_key": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["issue_key", "body"],
                },
                server_id=self.server_id,
            ),
        ]

    async def _invoke_tool(self, tool: MCPTool, arguments: dict[str, Any]) -> Any:
        if tool.name == "jira_read":
            return self._mock_read(arguments)
        elif tool.name == "jira_search":
            return self._mock_search(arguments)
        elif tool.name == "jira_create":
            return self._mock_create(arguments)
        elif tool.name == "jira_comment":
            return self._mock_comment(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool.name}")

    def _mock_read(self, args: dict[str, Any]) -> dict[str, Any]:
        key = args.get("issue_key", "FORGE-1")
        return {
            "key": key,
            "summary": f"Issue {key}",
            "status": "In Progress",
            "assignee": "abhinav.khare",
            "labels": ["agentic", "sdlc"],
            "description": "Mock Jira issue for testing",
        }

    def _mock_search(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "total": 2,
            "issues": [
                {
                    "key": "FORGE-1",
                    "summary": "Implement auth service",
                    "status": "In Progress",
                },
                {
                    "key": "FORGE-2",
                    "summary": "Add MCP mesh",
                    "status": "Done",
                },
            ],
        }

    def _mock_create(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "key": "FORGE-42",
            "summary": args.get("summary", "New issue"),
            "status": "To Do",
            "url": f"{self.endpoint}/browse/FORGE-42",
        }

    def _mock_comment(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": "10001",
            "issue_key": args.get("issue_key"),
            "body": args.get("body", ""),
            "author": "forge-agent",
        }
