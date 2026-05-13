# ADR-001: Forge Architecture Overview

## Status
Accepted

## Context
Forge is an agent-native SDLC control plane that coordinates multiple specialized AI agents (planner, coder, reviewer, SRE) through a spec-driven, governed workflow. We needed to make fundamental architectural decisions about:

1. How to represent and execute multi-agent workflows
2. How to enforce governance across agent boundaries
3. How to persist state across distributed agent executions
4. How to integrate with external systems (GitHub, Jira, AWS)

## Decision

### 1. Spec-Driven DAG Execution
We chose a **spec-driven DAG (Directed Acyclic Graph)** model where:
- Users write specs in Markdown/YAML with declarative step definitions
- The Spec Engine parses specs into executable dependency graphs
- The Orchestrator executes steps respecting dependencies with checkpointing
- Each step is assigned to a specific agent type with typed inputs/outputs

**Rationale**: This provides explicit, version-controlled, reviewable workflows. Unlike imperative scripts, specs are self-documenting and auditable.

### 2. Graph-Native Governance with BGI Trident
We integrated **BGI Trident** as the primary governance engine:
- Prong 1 (PyG/ID-GNN): Detects anomalous agent relationship patterns
- Prong 2 (DGL/R-GCN): Catches temporal drift in agent behavior
- Prong 3 (XGBoost): Enforces threshold-based policy rules

**Fallback**: When Trident is unavailable, the system falls back to a deterministic rule-based engine (fail-safe, not fail-open).

**Rationale**: Graph-native analysis can detect complex attack patterns (e.g., compromised agent chains) that rule-based systems miss.

### 3. PostgreSQL + Redis Persistence
- **PostgreSQL**: Stores orchestrator checkpoints, spec execution history, and audit logs
- **Redis**: Provides shared episodic/semantic memory across agent sessions

**Rationale**: PostgreSQL gives us ACID guarantees for workflow state. Redis provides sub-millisecond latency for agent memory access.

### 4. MCP Mesh for External Integrations
We adopted the **Model Context Protocol (MCP)** for external integrations:
- Dynamic server discovery and routing
- Standardized tool calling interface
- Pluggable adapters for GitHub, Jira, AWS, Datadog

**Rationale**: MCP is emerging as the standard for AI tool integration. It decouples Forge from specific vendor APIs.

## Consequences

### Positive
- Explicit, reviewable workflows
- Deep governance with graph analysis
- Crash-recoverable execution via checkpoints
- Extensible integration ecosystem

### Negative
- Added complexity from dual governance engines
- PostgreSQL dependency adds operational overhead
- MCP is still evolving; adapters may need frequent updates

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|----------------|
| Imperative workflow scripts | Not auditable, hard to review |
| Pure rule-based governance | Cannot detect sophisticated attacks |
| SQLite for production | No HA, no concurrent writes |
| Direct API integrations | Tight coupling to vendor APIs |

## References
- [BGI Trident Documentation](https://github.com/ahinsaai/bgi-trident)
- [Model Context Protocol Spec](https://modelcontextprotocol.io/)
- [Forge README](../README.md)
