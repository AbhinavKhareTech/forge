# Forge Architecture

## Design Principles

1. **Spec-driven**: Markdown-native specs are the single source of truth
2. **Agent-agnostic**: Any agent implementing the `Agent` protocol can participate
3. **Governed by default**: Every action passes through the Governance Runtime
4. **Memory-shared**: Agents are stateless; all context lives in the Memory Fabric
5. **MCP-native**: Tools are discovered dynamically, not hardcoded

## Component Deep Dive

### Spec Engine

The Spec Engine transforms human-readable specifications into executable directed acyclic graphs (DAGs).

**Input formats:**
- Markdown with YAML frontmatter (preferred — git-friendly)
- Pure YAML (machine-generated specs)

**Validation:**
- Circular dependency detection
- Agent role existence (against Agent Registry)
- Constitution reference resolution

**Output:**
- Topologically sorted execution order
- Adjacency list for the orchestrator

### Agent Registry

Declarative agent management inspired by Kubernetes Pod specs.

```yaml
agents:
  - name: planner
    role: planner
    version: "1.0.0"
    tools:
      - github_search
      - jira_read
    permissions:
      - read:repo
    memory_scope:
      - planning
    requires_human_approval: false
```

The registry validates that:
- All referenced tools exist in the MCP Mesh
- Permissions are well-formed
- Memory scopes are valid namespaces

### Orchestrator

Async DAG executor with the following responsibilities:

1. **Dependency resolution**: Wait for all `depends_on` steps to complete
2. **Concurrency control**: Semaphore-limited parallel agent execution
3. **Retry logic**: Configurable max attempts with exponential backoff
4. **Checkpointing**: Human approval gates pause and resume workflows
5. **Context propagation**: Agent outputs flow into shared workflow context

### Governance Runtime

Two-tier evaluation:

**Fast path (rule-based):**
- Forbidden role/action combinations
- Required permission checks
- Threshold-based triggers (amount limits, etc.)

**Deep path (BGI Trident):**
- Agent relationship graph anomaly detection
- Temporal behavior drift scoring
- Cross-agent collusion pattern recognition

Decision outcomes: `ALLOW` | `REVIEW` | `BLOCK`

### Memory Fabric

Structured namespaces:

| Namespace | Purpose |
|-----------|---------|
| `workflow:{id}` | Step results and context for a specific workflow |
| `agent:{name}` | Agent-specific learning and preferences |
| `org` | Constitution documents and global policies |
| `episodic` | Time-indexed audit event log |

Backends:
- `InMemoryBackend`: Development and testing
- `RedisBackend`: Production with TTL and pub/sub
- `VectorBackend`: Semantic search over agent outputs (future)

### MCP Mesh

Dynamic server registry with health checks:

```python
mesh = MCPMesh()
mesh.register_server(GitHubMCPServer(...))
mesh.register_server(JiraMCPServer(...))
await mesh.discover_tools()
result = await mesh.call_tool(ToolCall(tool_name="github_create_pr", arguments={...}))
```

Agents discover tools at runtime rather than hardcoding endpoints.

## Data Flow

```
Developer writes spec → git commit
         ↓
Spec Engine parses → validates → compiles DAG
         ↓
Orchestrator dispatches agents in topological order
         ↓
Governance Runtime evaluates each action
         ↓
Agent executes via MCP Mesh tools
         ↓
Result stored in Memory Fabric
         ↓
Next agent reads context from Memory Fabric
         ↓
Workflow completes → audit log in episodic memory
```

## Security Model

1. **Least privilege**: Agents have explicit permission grants
2. **Defense in depth**: Rule-based + graph-native + human checkpoints
3. **Auditability**: Every action logged with full context
4. **Immutable specs**: Version-controlled, signed, traceable

## Extensibility

| Extension Point | How |
|----------------|-----|
| New agent type | Implement `Agent` protocol + register in `agents.yaml` |
| New MCP server | Extend `BaseMCPServer` + register in MCP Mesh |
| New policy | Add to Governance Runtime policy list |
| New memory backend | Implement `MemoryBackend` protocol |
| Trident integration | Connect `GovernanceRuntime._trident_evaluate()` to BGI ensemble |
