# Runbook: Memory Fabric Partition

## Symptoms
- Redis connection errors in logs
- Agents operating with degraded memory (local cache only)
- `forge_memory_hits_total` metric drops to zero
- Health check shows Redis as `unhealthy`

## Impact
- Agents lose cross-session memory
- Contextual awareness degraded
- Potential for repeated mistakes across sessions

## Diagnosis

### 1. Check Redis Health
```bash
redis-cli -h redis ping
redis-cli -h redis info replication
```

### 2. Check Network Partition
```bash
# From Forge pod
kubectl exec -it deploy/forge -- redis-cli -h redis ping
```

### 3. Check Redis Memory
```bash
redis-cli info memory | grep used_memory_human
```

### 4. Check Redis Connections
```bash
redis-cli info clients | grep connected_clients
```

## Resolution

### Option 1: Restart Redis
```bash
kubectl rollout restart statefulset/redis
```

### Option 2: Clear Redis and Rebuild
```bash
# ⚠️ Destructive — only if data is corrupted
redis-cli FLUSHDB
# Agents will rebuild memory from checkpoints
```

### Option 3: Switch to Backup Redis
```bash
# Update FORGE_REDIS_URL to backup instance
kubectl set env deployment/forge FORGE_REDIS_URL=redis://backup-redis:6379/0
```

### Option 4: Enable Local Cache Mode
```bash
# Fallback is automatic, but can be forced
kubectl set env deployment/forge FORGE_MEMORY_BACKEND=in_memory
```

## Prevention
- Redis Sentinel or Redis Cluster for HA
- Regular Redis backups (RDB + AOF)
- Memory usage alerts
- Connection pool monitoring

## Escalation
If Redis is down for >30 minutes, escalate to:
- Infrastructure team
- On-call engineer
