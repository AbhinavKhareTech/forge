"""Forge CLI -- command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from forge.__version__ import __version__
from forge.config import get_config
from forge.core.agent_registry import AgentRegistry
from forge.core.orchestrator import Orchestrator
from forge.core.spec_engine import SpecEngine
from forge.governance.runtime import GovernanceRuntime
from forge.memory.fabric import MemoryFabric
from forge.mcp.mesh import MCPMesh
from forge.utils.logging import configure_logging, get_logger
from forge.voice.session import VoiceSession
from forge.voice.transcriber import Language
from forge.web.health import HealthCheck

logger = get_logger("forge.cli")


def _init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Forge -- Agent-Native SDLC Control Plane",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}",
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

    # health
    health_parser = subparsers.add_parser("health", help="Health checks")
    health_sub = health_parser.add_subparsers(dest="health_command")
    health_sub.add_parser("live", help="Liveness probe")
    health_sub.add_parser("ready", help="Readiness probe")
    health_sub.add_parser("deep", help="Deep health check")

    # voice
    voice_parser = subparsers.add_parser("voice", help="Voice-driven spec creation")
    voice_sub = voice_parser.add_subparsers(dest="voice_command")

    voice_start = voice_sub.add_parser("start", help="Start a voice session")
    voice_start.add_argument("--language", default="hi-en", choices=["en", "hi", "hi-en", "ta", "te"], help="Input language")
    voice_start.add_argument("--session-id", default=None, help="Session ID")

    voice_speak = voice_sub.add_parser("speak", help="Process voice utterance (text mode)")
    voice_speak.add_argument("text", help="Text to process")
    voice_speak.add_argument("--session-id", required=True, help="Session ID")

    voice_confirm = voice_sub.add_parser("confirm", help="Confirm generated spec")
    voice_confirm.add_argument("--session-id", required=True, help="Session ID")
    voice_confirm.add_argument("--output", type=Path, default=None, help="Output file path")

    voice_status = voice_sub.add_parser("status", help="Check voice session status")
    voice_status.add_argument("--session-id", required=True, help="Session ID")

    return parser


async def _cmd_init(args: argparse.Namespace) -> int:
    project_path = args.path.resolve()
    project_path.mkdir(parents=True, exist_ok=True)

    dirs = ["specs", "agents", "constitutions", ".forge/graph", "demo"]
    for d in dirs:
        (project_path / d).mkdir(parents=True, exist_ok=True)

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

    constitution = """# Organization Constitution -- Security & Compliance

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

    print(f"Forge project initialized at {project_path}")
    return 0


async def _cmd_spec_validate(args: argparse.Namespace) -> int:
    engine = SpecEngine()
    try:
        if args.path.suffix in (".yaml", ".yml"):
            spec = engine.load_from_yaml(args.path)
        else:
            spec = engine.load_from_markdown(args.path)
        print(f"Spec valid: {spec.id}")
        print(f"  Title: {spec.title}")
        print(f"  Steps: {len(spec.steps)}")
        print(f"  Execution order: {spec.execution_order()}")
        return 0
    except Exception as e:
        print(f"Spec invalid: {e}")
        return 1


async def _cmd_run(args: argparse.Namespace) -> int:
    import json
    config = get_config()
    configure_logging("debug" if args.verbose else config.log_level)

    engine = SpecEngine()
    registry = AgentRegistry()
    memory = MemoryFabric()
    governance = GovernanceRuntime() if config.governance_enabled else None
    orchestrator = Orchestrator(engine, registry, memory, governance)

    for spec_file in config.spec_dir.glob("**/*.md"):
        engine.load_from_markdown(spec_file)
    for spec_file in config.spec_dir.glob("**/*.yaml"):
        engine.load_from_yaml(spec_file)
    registry.load_configs(config.agent_registry_path)

    context = json.loads(args.context)
    workflow = await orchestrator.start_workflow(args.spec_id, context)

    print(f"Workflow started: {workflow.workflow_id}")
    print(f"  Spec: {workflow.spec_id}")
    print(f"  Status: {workflow.status.value}")
    return 0


async def _cmd_status(args: argparse.Namespace) -> int:
    print(f"Workflow: {args.workflow_id}")
    return 0


async def _cmd_approve(args: argparse.Namespace) -> int:
    print(f"Approving checkpoint {args.checkpoint_id} for workflow {args.workflow_id}")
    return 0


async def _cmd_agent_list(args: argparse.Namespace) -> int:
    config = get_config()
    registry = AgentRegistry()
    count = registry.load_configs(config.agent_registry_path)

    if count == 0:
        print("No agents registered. Run `forge init` to create sample config.")
        return 0

    print(f"Registered agents ({count}):")
    for cfg in registry.list_configs():
        approval = " [REQUIRES APPROVAL]" if cfg.requires_human_approval else ""
        print(f"  {cfg.name} ({cfg.role}){approval}")
        print(f"    Tools: {', '.join(cfg.tools) or 'none'}")
        print(f"    Permissions: {', '.join(cfg.permissions) or 'none'}")
    return 0


async def _cmd_mcp_discover(args: argparse.Namespace) -> int:
    mesh = MCPMesh()
    print("MCP Mesh discovery:")
    print(f"  Registered servers: {len(mesh.list_servers())}")
    print(f"  Discovered tools: {len(mesh.list_tools())}")
    for tool_name in mesh.list_tools():
        print(f"    {tool_name}")
    return 0


async def _cmd_health(args: argparse.Namespace) -> int:
    """Health check commands."""
    health = HealthCheck()
    cmd = getattr(args, "health_command", "deep")

    if cmd == "live":
        status = health.liveness()
    elif cmd == "ready":
        status = health.readiness()
    else:
        status = health.deep()

    result = health.to_dict(status)
    import json
    print(json.dumps(result, indent=2))
    return 0 if status.status == "healthy" else 1


async def _cmd_voice_start(args: argparse.Namespace) -> int:
    lang_map = {
        "en": Language.ENGLISH,
        "hi": Language.HINDI,
        "hi-en": Language.HINGLISH,
        "ta": Language.TAMIL,
        "te": Language.TELUGU,
    }
    language = lang_map.get(args.language, Language.HINGLISH)

    session = VoiceSession(session_id=args.session_id, language=language)

    print(f"Voice session started: {session.session_id}")
    print(f"  Language: {language.value}")
    print(f"  Status: {session.state.status}")
    print()
    print("Speak your spec description. Examples:")
    print('  "Create authentication system with MFA"')
    print('  "Ek auth system banana hai with JWT and rate limiting"')
    print('  "Build payment gateway with fraud detection"')
    print()
    print(f"Use: forge voice speak --session-id {session.session_id} "<your text>"")
    return 0


async def _cmd_voice_speak(args: argparse.Namespace) -> int:
    session = VoiceSession(session_id=args.session_id)

    result = await session.process_utterance(text_input=args.text)

    print(f"Processed utterance:")
    print(f"  Text: {result['utterance']}")
    print(f"  Intent: {result['intent']}")
    print(f"  Entities: {len(result['entities'])}")
    for entity in result['entities']:
        print(f"    - {entity['type']}: {entity['value']}")
    print()
    print(f"Spec Preview:")
    print(f"  ID: {result['spec_preview']['id']}")
    print(f"  Title: {result['spec_preview']['title']}")
    print(f"  Steps: {', '.join(result['spec_preview']['steps'])}")
    print(f"  Confidence: {result['spec_preview']['confidence']:.2f}")
    print()

    if result['missing_info']:
        print("Missing Information:")
        for gap in result['missing_info']:
            print(f"  ! {gap}")
        print()

    if result['suggestions']:
        print("Suggestions:")
        for suggestion in result['suggestions']:
            print(f"  > {suggestion}")
        print()

    print(f"Status: {result['status']}")
    print(f"Use 'forge voice confirm --session-id {args.session_id}' to save")
    return 0


async def _cmd_voice_confirm(args: argparse.Namespace) -> int:
    session = VoiceSession(session_id=args.session_id)

    try:
        generated = session.confirm_spec()
        spec = generated.spec

        config = get_config()
        output_path = args.output or (config.spec_dir / f"{spec.id}.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        spec_md = _spec_to_markdown(spec)
        output_path.write_text(spec_md, encoding="utf-8")

        print(f"Spec confirmed and saved: {output_path}")
        print(f"  ID: {spec.id}")
        print(f"  Title: {spec.title}")
        print(f"  Steps: {len(spec.steps)}")
        print(f"  Confidence: {generated.confidence:.2f}")
        return 0
    except ValueError as e:
        print(f"Error: {e}")
        return 1


async def _cmd_voice_status(args: argparse.Namespace) -> int:
    session = VoiceSession(session_id=args.session_id)
    summary = session.get_session_summary()

    print(f"Voice Session: {summary['session_id']}")
    print(f"  Language: {summary['language']}")
    print(f"  Status: {summary['status']}")
    print(f"  Utterances: {summary['utterance_count']}")
    print(f"  Duration: {summary['duration_seconds']:.0f}s")
    if summary['spec']:
        print(f"  Spec: {summary['spec']['title']}")
        print(f"  Confirmed: {summary['spec']['confirmed']}")
    return 0


def _spec_to_markdown(spec) -> str:
    lines = [
        "---",
        f"id: {spec.id}",
        f"title: {spec.title}",
        f"description: |",
        f"  {spec.description}",
        "author: voice-user",
    ]

    if spec.tags:
        lines.append(f"tags: {spec.tags}")
    if spec.constitution_refs:
        lines.append(f"constitution_refs: {spec.constitution_refs}")

    lines.extend(["---", ""])

    for step in spec.steps:
        lines.extend([
            f"#### STEP: {step.id}",
            f"**Type:** {step.type.value}",
            f"**Agent:** {step.agent_role}",
            f"**Depends:** {step.depends_on}",
            "",
            step.description,
            "",
        ])

    return "\n".join(lines)


async def main_async(argv: list[str] | None = None) -> int:
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
        "health": _cmd_health,
        "voice": {
            "start": _cmd_voice_start,
            "speak": _cmd_voice_speak,
            "confirm": _cmd_voice_confirm,
            "status": _cmd_voice_status,
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
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    sys.exit(main())
