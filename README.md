# Forge — Agent-Native SDLC Control Plane

> **Powered by BGI Trident** — graph-native governance and reasoning for agent teams.

[![CI](https://github.com/ahinsaai/forge/actions/workflows/ci.yml/badge.svg)](https://github.com/ahinsaai/forge/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Forge orchestrates **agent teams** across the software development lifecycle. Unlike individual coding assistants, Forge coordinates multiple specialized agents — planners, coders, reviewers, SREs — through a spec-driven, governed, traceable workflow.

## The Problem

Current AI coding tools are **individual agents** that help one developer write code. What teams actually need:

- **Multi-agent coordination** — planner → coder → reviewer → SRE, not one agent doing everything
- **Spec-driven execution** — "I wrote a spec. Now agents implement it, test it, and deploy it."
- **Governance at the boundary** — "This agent wants to delete a production database → BLOCK"
- **Cross-agent memory** — "The reviewer agent remembers what the coder agent did last Tuesday"
- **Human checkpoints** — "Approve this deployment before it goes live"

No existing tool does this. Forge does.

## Architecture

```
┌─────────────────────────────────────────┐
│           DEVELOPER / PM                │
│  Writes spec in Markdown, commits to git │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         FORGE SPEC ENGINE                 │
│  Parses spec → dependency graph → execution DAG │
└─────────────────┬───────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌───────┐    ┌───────┐    ┌───────┐
│PLANNER│───→│ CODER │───→│ REVIEW│
│ Agent │    │ Agent │    │ Agent │
└───┬───┘    └───┬───┘    └───┬───┘
    │            │            │
    └────────────┼────────────┘
                 ▼
        ┌──────────────┐
        │  GOVERNANCE  │
        │   RUNTIME    │  ← BGI Trident powers this layer
        │  (ALLOW/     │     Graph-native policy enforcement
        │   REVIEW/    │     Agent relationship detection
        │   BLOCK)     │     Cross-agent memory & audit
        └──────┬───────┘
               │
        ┌──────▼───────┐
        │   MCP MESH   │
        │  GitHub/Jira/│
        │  AWS/Datadog │
        └──────────────┘
```

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Initialize a Project

```bash
forge init my-project
cd my-project
```

This creates:
```
my-project/
├── specs/              # Executable specifications
├── agents.yaml         # Agent registry
├── constitutions/      # Organizational policies
└── .forge/graph        # BGI Trident graph storage
```

### Write a Spec

```markdown
---
id: SPEC-001
title: User Authentication
description: Implement secure auth with MFA
constitution_refs:
  - security
---

#### STEP: plan-auth
**Type:** plan
**Agent:** planner
**Depends:** []

Design the authentication flow.

#### STEP: code-auth
**Type:** code
**Agent:** coder
**Depends:** [plan-auth]

Implement the auth service.

#### STEP: review-auth
**Type:** review
**Agent:** reviewer
**Depends:** [code-auth]

Review against security constitution.
```

### Validate the Spec

```bash
forge spec validate specs/auth.md
```

### Run the Workflow

```bash
forge run SPEC-001
```

## Core Components

| Component | Purpose |
|-----------|---------|
| **Spec Engine** | Parse Markdown/YAML specs into executable DAGs |
| **Agent Registry** | Declarative agent definitions (Kubernetes-style YAML) |
| **Orchestrator** | DAG-based multi-agent workflow engine with checkpoints |
| **Memory Fabric** | Shared episodic + semantic memory across agent sessions |
| **Governance Runtime** | Policy enforcement with BGI Trident graph-native scoring |
| **MCP Mesh** | Dynamic Model Context Protocol server discovery and routing |

## BGI Trident Integration

When `trident_enabled: true`, the Governance Runtime uses your three-prong ensemble:

- **Prong 1 (PyG/ID-GNN):** Detect anomalous agent relationship patterns
- **Prong 2 (DGL/R-GCN):** Catch temporal drift in agent behavior
- **Prong 3 (XGBoost):** Enforce threshold-based policy rules

Same graph engine that powers fraud detection and consumption prediction — now securing your SDLC.

## Development

```bash
# Install dev dependencies
make install

# Run linting
make lint

# Run tests
make test

# Serve docs locally
make docs
```

## Roadmap

- [x] v0.1.0 — Core scaffold (Spec Engine, Agent Registry, Orchestrator)
- [X] v0.2.0 — Memory Fabric with Redis backend + vector search
- [X] v0.3.0 — MCP Mesh with GitHub, Jira, AWS integrations
- [X] v0.4.0 — BGI Trident governance runtime (full three-prong)
- [X] v0.5.0 — Reference agents (Planner, Coder, Reviewer, SRE)
- [X] v0.6.0 — Voice-driven spec creation via Swar integration
- [ ] v1.0.0 — Production-ready with managed cloud offering

## License

MIT — see [LICENSE](LICENSE)

## Author

**Abhinav Khare** — Cofounder & CTO, AhinsaAI  
20+ years in payments infrastructure, fraud/risk systems, and voice AI for BFSI.

---

> *"Portkey secured the traffic layer. Forge secures the agent lifecycle layer."*
