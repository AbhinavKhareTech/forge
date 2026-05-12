"""GitHub MCP Server Adapter.

Provides MCP tools for common GitHub operations:
- Search repositories and code
- Read/write files
- Create pull requests
- Review PRs
- Manage issues
"""

from __future__ import annotations

from typing import Any

from forge.protocols.mcp import MCPTool, ToolCall, ToolResult
from forge.mcp.server import BaseMCPServer
from forge.utils.logging import get_logger

logger = get_logger("forge.mcp.github")


class GitHubMCPServer(BaseMCPServer):
    """MCP server adapter for GitHub API.

    In production, this wraps the GitHub REST/GraphQL API using
    PyGithub or direct HTTP calls. The mock implementation simulates
    responses for testing and development.
    """

    def __init__(
        self,
        server_id: str = "github",
        endpoint: str = "https://api.github.com",
        credentials: dict[str, str] | None = None,
    ) -> None:
        super().__init__(server_id, endpoint, credentials)
        self._owner = credentials.get("owner", "ahinsaai") if credentials else "ahinsaai"
        self._repo = credentials.get("repo", "forge") if credentials else "forge"
        self._token = credentials.get("token", "") if credentials else ""

    async def _do_connect(self) -> None:
        """Validate GitHub credentials."""
        logger.info("github_connecting", endpoint=self.endpoint, owner=self._owner, repo=self._repo)
        # In production: validate token with GET /user

    async def _do_disconnect(self) -> None:
        """Clean up GitHub connection."""
        logger.info("github_disconnected")

    async def _discover_tools(self) -> list[MCPTool]:
        """Return available GitHub tools."""
        return [
            MCPTool(
                name="github_search",
                description="Search repositories, code, issues, or users on GitHub",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "GitHub search query"},
                        "type": {"type": "string", "enum": ["repositories", "code", "issues", "users"]},
                    },
                    "required": ["query"],
                },
                server_id=self.server_id,
            ),
            MCPTool(
                name="github_read_file",
                description="Read a file from a GitHub repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path in repo"},
                        "ref": {"type": "string", "description": "Branch or commit SHA", "default": "main"},
                    },
                    "required": ["path"],
                },
                server_id=self.server_id,
            ),
            MCPTool(
                name="github_write_file",
                description="Create or update a file in a GitHub repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path in repo"},
                        "content": {"type": "string", "description": "File content"},
                        "message": {"type": "string", "description": "Commit message"},
                        "branch": {"type": "string", "description": "Target branch", "default": "main"},
                    },
                    "required": ["path", "content", "message"],
                },
                server_id=self.server_id,
            ),
            MCPTool(
                name="github_create_pr",
                description="Create a pull request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "head": {"type": "string", "description": "Source branch"},
                        "base": {"type": "string", "description": "Target branch", "default": "main"},
                    },
                    "required": ["title", "head"],
                },
                server_id=self.server_id,
            ),
            MCPTool(
                name="github_pr_review",
                description="Submit a review on a pull request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pr_number": {"type": "integer"},
                        "body": {"type": "string"},
                        "event": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"]},
                    },
                    "required": ["pr_number", "body", "event"],
                },
                server_id=self.server_id,
            ),
        ]

    async def _invoke_tool(self, tool: MCPTool, arguments: dict[str, Any]) -> Any:
        """Execute a GitHub tool."""
        if tool.name == "github_search":
            return self._mock_search(arguments)
        elif tool.name == "github_read_file":
            return self._mock_read_file(arguments)
        elif tool.name == "github_write_file":
            return self._mock_write_file(arguments)
        elif tool.name == "github_create_pr":
            return self._mock_create_pr(arguments)
        elif tool.name == "github_pr_review":
            return self._mock_pr_review(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool.name}")

    def _mock_search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query", "")
        return {
            "total_count": 1,
            "items": [
                {
                    "name": "forge",
                    "full_name": f"{self._owner}/forge",
                    "description": "Agent-Native SDLC Control Plane",
                    "url": f"https://github.com/{self._owner}/forge",
                }
            ],
        }

    def _mock_read_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args.get("path", "")
        return {
            "path": path,
            "content": f"# Mock content for {path}\n\nprint('hello world')\n",
            "sha": "abc123",
            "size": 42,
        }

    def _mock_write_file(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args.get("path", "")
        return {
            "path": path,
            "commit": {
                "sha": "def456",
                "message": args.get("message", "Update file"),
            },
            "branch": args.get("branch", "main"),
        }

    def _mock_create_pr(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "number": 42,
            "title": args.get("title", "PR"),
            "url": f"https://github.com/{self._owner}/{self._repo}/pull/42",
            "state": "open",
            "head": args.get("head", "feature"),
            "base": args.get("base", "main"),
        }

    def _mock_pr_review(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": 123,
            "pr_number": args.get("pr_number"),
            "event": args.get("event"),
            "body": args.get("body", ""),
        }
