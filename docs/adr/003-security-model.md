# ADR-003: Security Model and Threat Mitigation

## Status
Accepted

## Context
Forge orchestrates AI agents with access to production systems. A compromised or misbehaving agent could:
1. Delete production databases
2. Exfiltrate customer data
3. Deploy malicious code
4. Disable security controls

We need a defense-in-depth security model.

## Decision

### 1. Defense in Depth
Multiple independent security layers:
- **Authentication**: JWT tokens + API keys with RBAC
- **Authorization**: Role-based access control (admin/operator/viewer/agent)
- **Governance**: BGI Trident + rule-based fallback for every agent action
- **Audit**: Immutable, tamper-evident audit log with SHA-256 hashes
- **Network**: Kubernetes NetworkPolicies for zero-trust networking
- **Secrets**: Vault integration, SecretStr in code, never logged

### 2. Fail-Closed Governance
When the governance engine fails or is unavailable:
- **Strict mode**: BLOCK all actions (fail-closed)
- **Fallback mode**: Use rule-based engine with degraded confidence
- Never fail-open (ALLOW by default)

### 3. Secret Management
- `pydantic.SecretStr` for all secrets in configuration
- HashiCorp Vault or cloud secret managers in production
- Pre-commit hooks to prevent secret leakage
- GPG-signed commits for maintainers

### 4. Input Validation
- Pydantic validators for all API inputs
- Spec schema validation before execution
- YAML/Markdown sanitization to prevent injection
- Max depth limits for spec dependency graphs

## Consequences

### Positive
- Multiple independent security layers
- Immutable audit trail for compliance
- No single point of failure in governance
- Automatic secret protection

### Negative
- Increased latency from governance checks
- Operational complexity from Vault integration
- Stricter development workflow (signed commits)

## Threat Model

| Threat | Mitigation |
|--------|-----------|
| Compromised agent | Governance blocks malicious actions |
| Prompt injection | Input validation + spec schema enforcement |
| Secret leakage | SecretStr + pre-commit hooks + Vault |
| Privilege escalation | RBAC with least privilege |
| Audit tampering | Immutable logs + SHA-256 hashes |
| Network attacks | NetworkPolicies + mTLS |
