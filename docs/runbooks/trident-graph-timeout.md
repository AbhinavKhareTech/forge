# Runbook: BGI Trident Graph Timeout

## Symptoms
- Governance decisions taking >10 seconds
- Trident health check failing
- Logs show: `trident_evaluation_failed: Connection timeout`
- System operating in fallback mode

## Impact
- Governance latency increased
- Fallback to rule-based engine (lower confidence)
- Potential security gap if sophisticated attacks are missed

## Diagnosis

### 1. Check Trident Health
```bash
curl -v http://trident:8080/health
curl -v http://trident:8080/metrics
```

### 2. Check Network Connectivity
```bash
kubectl exec -it deploy/forge -- curl -v http://trident:8080/health
```

### 3. Check Trident Resource Usage
```bash
kubectl top pod -l app.kubernetes.io/name=trident
```

### 4. Check Graph Database
```bash
# If using Neo4j
kubectl exec -it neo4j-pod -- cypher-shell -u neo4j -p $PASSWORD "CALL dbms.components()"
```

## Resolution

### Option 1: Restart Trident
```bash
kubectl rollout restart deployment/trident
```

### Option 2: Scale Trident
```bash
kubectl scale deployment/trident --replicas=3
```

### Option 3: Check Graph Database
```bash
# Check if graph DB is responsive
kubectl exec -it neo4j-pod -- cypher-shell "MATCH (n) RETURN count(n)"
```

### Option 4: Reduce Graph Complexity
If the agent relationship graph has grown too large:
```bash
# Archive old graph data
forge trident archive --older-than 30d
```

## Prevention
- Set up Trident auto-scaling based on queue depth
- Monitor graph database disk usage
- Implement graph data retention policies
- Add circuit breaker for Trident calls

## Escalation
If Trident is down for >15 minutes, escalate to:
- ML platform team
- On-call engineer
