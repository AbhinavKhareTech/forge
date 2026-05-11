"""Forge CLI — command-line interface for the agent-native SDLC platform.

Commands:
    forge init          Initialize a new Forge project
    forge spec create   Create a new spec from template
    forge spec validate Validate a spec file
    forge run           Execute a spec through the orchestrator
    forge status        Check workflow status
    forge approve       Approve a human checkpoint
    forge agent list    List registered agents
    forge mcp discover  Discover available MCP servers
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from forge.config import get_config
from forge.core.agent_registry import AgentRegistry
from forge.core.orchestrator import Orchestrator
from forge.core.spec_engine import SpecEngine
from forge.governance.runtime import GovernanceRuntime
from forge.memory.fabric import MemoryFabric
from forge.mcp.mesh import MCPMesh
from forge.utils.logging import configure_logging, get_logger

logger = get_logger("forge.cli")


def _init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Forge — Agent-Native SDLC Control Plane",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to Forge configuration file",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new Forge project")
    init_parser.add_argument("path", type=Path, default=Path("."), nargs="?", help="Project path")

    # spec
    spec_parser = subparsers.add_parser("spec", help="Spec management")
    spec_sub = spec_parser.add_subparsers(dest="spec_command")
    spec_create = spec_sub.add_parser("create", help="Create a spec from template")
    spec_create.add_argument("name", help="Spec name/ID")
    spec_create.add_argument("--title", default="", help="Spec title")
    spec_validate = spec_sub.add_parser("validate", help="Validate a spec file")
    spec_validate.add_argument("path", type=Path, help="Path to spec file")

    # run
    run_parser = subparsers.add_parser("run", help="Execute a spec")
    run_parser.add_argument("spec_id", help="Spec ID to execute")
    run_parser.add_argument("--context", type=str, default="{}", help="JSON context string")

    # status
    status_parser = subparsers.add_parser("status", help="Check workflow status")
    status_parser.add_argument("workflow_id", help="Workflow ID")

    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve a checkpoint")
    approve_parser.add_argument("workflow_id", help="Workflow ID")
    approve_parser.add_argument("checkpoint_id", help="Checkpoint ID")

    # agent
    agent_parser = subparsers.add_parser("agent", help="Agent management")
    agent_sub = agent_parser.add_subparsers(dest="agent_command")
    agent_sub.add_parser("list", help="List registered agents")

    # mcp
    mcp_parser = subparsers.add_parser("mcp", help="MCP mesh management")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_sub.add_parser("discover", help="Discover MCP servers and tools")

    return parser


async def _cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new Forge project."""
    project_path = args.path.resolve()
    project_path.mkdir(parents=True, exist_ok=True)

    # Create directory structure
    dirs = ["specs", "agents", "constitutions", ".forge/graph"]
    for d in dirs:
        (project_path / d).mkdir(parents=True, exist_ok=True)

    # Create sample agents.yaml
    agents_yaml = """agents:
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

  - name: coder
    role: coder
    version: "1.0.0"
    description: "Implements code changes from spec steps"
    tools:
      - github_read_file
      - github_write_file
      - github_create_pr
    permissions:
      - read:repo
      - write:file
    memory_scope:
      - coding
      - planning
    max_retries: 3
    timeout_seconds: 300

  - name: reviewer
    role: reviewer
    version: "1.0.0"
    description: "Reviews code for quality and compliance"
    tools:
      - github_read_file
      - github_pr_review
    permissions:
      - read:repo
    memory_scope:
      - coding
    max_retries: 2
    timeout_seconds: 180
    requires_human_approval: false
"""
    (project_path / "agents.yaml").write_text(agents_yaml, encoding="utf-8")

    # Create sample constitution
    constitution = """# Organization Constitution — Security & Compliance

## General Principles
1. All code must pass static analysis before deployment
2. No secrets or credentials in source code
3. All database migrations require review
4. Production deployments require explicit approval

## Prohibited Actions
- Direct production database writes
- Hardcoded API keys or passwords
- Unauthenticated endpoints
- Unsanitized user input in queries
"""
    (project_path / "constitutions" / "security.md").write_text(constitution, encoding="utf-8")

    # Create sample spec
    sample_spec = """---
id: SPEC-001
title: Sample Authentication Flow
description: |
  Implement user authentication with MFA support.
author: forge
constitution_refs:
  - security
---

## Context
We need a secure authentication system with multi-factor authentication.

#### STEP: plan-auth
**Type:** plan
**Agent:** planner
**Depends:** []

Design the authentication flow including:
- Login endpoint with rate limiting
- MFA via TOTP
- Session management
- Password reset flow

#### STEP: code-auth
**Type:** code
**Agent:** coder
**Depends:** [plan-auth]

Implement the authentication service based on the plan.
Generate tests covering happy path and edge cases.

#### STEP: review-auth
**Type:** review
**Agent:** reviewer
**Depends:** [code-auth]

Review the implementation against the security constitution.
Check for secrets, injection risks, and compliance.
"""
    (project_path / "specs" / "sample-auth.md").write_text(sample_spec, encoding="utf-8")

    print(f"✓ Forge project initialized at {project_path}")
    print(f"  specs/          — Executable specifications")
    print(f"  agents.yaml     — Agent registry configuration")
    print(f"  constitutions/  — Organizational policies")
    print(f"  .forge/graph    — BGI Trident graph storage")
    return 0


async def _cmd_spec_validate(args: argparse.Namespace) -> int:
    """Validate a spec file."""
    engine = SpecEngine()
    try:
        if args.path.suffix in (".yaml", ".yml"):
            spec = engine.load_from_yaml(args.path)
        else:
            spec = engine.load_from_markdown(args.path)
        print(f"✓ Spec valid: {spec.id}")
        print(f"  Title: {spec.title}")
        print(f"  Steps: {len(spec.steps)}")
        print(f"  Execution order: {spec.execution_order()}")
        return 0
    except Exception as e:
        print(f"✗ Spec invalid: {e}")
        return 1


async def _cmd_run(args: argparse.Namespace) -> int:
    """Execute a spec."""
    import json

    config = get_config()
    configure_logging("debug" if args.verbose else config.log_level)

    engine = SpecEngine()
    registry = AgentRegistry()
    memory = MemoryFabric()
    governance = GovernanceRuntime() if config.governance_enabled else None
    orchestrator = Orchestrator(engine, registry, memory, governance)

    # Load specs and agents
    for spec_file in config.spec_dir.glob("**/*.md"):
        engine.load_from_markdown(spec_file)
    for spec_file in config.spec_dir.glob("**/*.yaml"):
        engine.load_from_yaml(spec_file)
    registry.load_configs(config.agent_registry_path)

    context = json.loads(args.context)
    workflow = await orchestrator.start_workflow(args.spec_id, context)

    print(f"✓ Workflow started: {workflow.workflow_id}")
    print(f"  Spec: {workflow.spec_id}")
    print(f"  Status: {workflow.status.value}")
    return 0


async def _cmd_status(args: argparse.Namespace) -> int:
    """Check workflow status."""
    print(f"Workflow: {args.workflow_id}")
    print("(Full status tracking requires persistent storage)")
    return 0


async def _cmd_approve(args: argparse.Namespace) -> int:
    """Approve a checkpoint."""
    print(f"Approving checkpoint {args.checkpoint_id} for workflow {args.workflow_id}")
    print("(Requires running orchestrator instance)")
    return 0


async def _cmd_agent_list(args: argparse.Namespace) -> int:
    """List registered agents."""
    config = get_config()
    registry = AgentRegistry()
    count = registry.load_configs(config.agent_registry_path)

    if count == 0:
        print("No agents registered. Run `forge init` to create sample config.")
        return 0

    print(f"Registered agents ({count}):")
    for cfg in registry.list_configs():
        approval = " [REQUIRES APPROVAL]" if cfg.requires_human_approval else ""
        print(f"  • {cfg.name} ({cfg.role}){approval}")
        print(f"    Tools: {', '.join(cfg.tools) or 'none'}")
        print(f"    Permissions: {', '.join(cfg.permissions) or 'none'}")
    return 0


async def _cmd_mcp_discover(args: argparse.Namespace) -> int:
    """Discover MCP servers."""
    mesh = MCPMesh()
    print("MCP Mesh discovery:")
    print(f"  Registered servers: {len(mesh.list_servers())}")
    print(f"  Discovered tools: {len(mesh.list_tools())}")
    for tool_name in mesh.list_tools():
        print(f"    • {tool_name}")
    return 0


async def main_async(argv: list[str] | None = None) -> int:
    """Async entry point."""
    parser = _init_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    configure_logging("debug" if args.verbose else "info")

    command_map = {
        "init": _cmd_init,
        "spec": {
            "create": lambda a: (print(f"Create spec: {a.name}"), 0)[1],
            "validate": _cmd_spec_validate,
        },
        "run": _cmd_run,
        "status": _cmd_status,
        "approve": _cmd_approve,
        "agent": {
            "list": _cmd_agent_list,
        },
        "mcp": {
            "discover": _cmd_mcp_discover,
        },
    }

    handler = command_map.get(args.command)
    if isinstance(handler, dict):
        sub = getattr(args, f"{args.command}_command", None)
        handler = handler.get(sub)

    if handler:
        return await handler(args)

    parser.print_help()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Synchronous entry point."""
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    sys.exit(main())
