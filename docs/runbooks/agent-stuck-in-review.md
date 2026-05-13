# Runbook: Agent Stuck in REVIEW State

## Symptoms
- Spec execution paused at a step with status `REVIEW`
- Governance decision returned `REVIEW` with high confidence
- Human approval workflow not triggered or stalled

## Impact
- Spec execution blocked
- Dependent steps cannot proceed
- Pipeline throughput reduced

## Diagnosis

### 1. Check Governance Decision
```bash
forge governance logs --spec-id SPEC-XXX --step-id step-YYY
```

Look for:
- Decision: `REVIEW`
- Confidence score
- Rule ID that triggered review
- Reason string

### 2. Check Audit Log
```bash
tail -f /var/log/forge/audit.log | jq 'select(.context.spec_id == "SPEC-XXX")'
```

### 3. Check Trident Status
```bash
curl http://trident:8080/health
```

If Trident is down, system falls back to rule-based governance.

## Resolution

### Option 1: Approve the Review (if action is safe)
```bash
forge governance approve --spec-id SPEC-XXX --step-id step-YYY --reason "Manual approval"
```

### Option 2: Override with Admin Privileges
```bash
forge governance override --spec-id SPEC-XXX --step-id step-YYY --role admin
```

⚠️ **Warning**: Override is logged and should trigger post-incident review.

### Option 3: Cancel the Spec
```bash
forge spec cancel --execution-id EXEC-XXX
```

## Prevention
- Review governance rules for false positives
- Tune Trident model thresholds
- Add auto-approval rules for low-risk actions

## Escalation
If unable to resolve within 30 minutes, escalate to:
- Security team (for governance rule review)
- On-call engineer (for system issues)
