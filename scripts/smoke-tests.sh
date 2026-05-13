#!/bin/bash
set -euo pipefail

# Forge Smoke Tests
# Validates basic functionality after deployment

ENVIRONMENT="${1:-staging}"
BASE_URL=""

if [ "$ENVIRONMENT" == "production" ]; then
    BASE_URL="https://forge.ahinsa.ai"
elif [ "$ENVIRONMENT" == "staging" ]; then
    BASE_URL="https://forge-staging.ahinsa.ai"
else
    BASE_URL="http://localhost:8000"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

test_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS++))
}

test_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL++))
}

echo "Running Forge smoke tests against $BASE_URL..."
echo ""

# Test 1: Liveness probe
if curl -sf "$BASE_URL/health/live" >/dev/null 2>&1; then
    test_pass "Liveness probe responds"
else
    test_fail "Liveness probe failed"
fi

# Test 2: Readiness probe
if curl -sf "$BASE_URL/health/ready" >/dev/null 2>&1; then
    test_pass "Readiness probe responds"
else
    test_fail "Readiness probe failed"
fi

# Test 3: Deep health check
HEALTH_STATUS=$(curl -sf "$BASE_URL/health/deep" 2>/dev/null | jq -r '.status' || echo "unknown")
if [ "$HEALTH_STATUS" == "healthy" ]; then
    test_pass "Deep health check: healthy"
elif [ "$HEALTH_STATUS" == "degraded" ]; then
    test_pass "Deep health check: degraded (acceptable)"
else
    test_fail "Deep health check: $HEALTH_STATUS"
fi

# Test 4: Prometheus metrics
if curl -sf "$BASE_URL/metrics" >/dev/null 2>&1; then
    test_pass "Prometheus metrics endpoint responds"
else
    test_fail "Prometheus metrics endpoint failed"
fi

# Test 5: API spec validation (if API key available)
if [ -n "${FORGE_API_KEY:-}" ]; then
    if curl -sf -H "X-API-Key: $FORGE_API_KEY" "$BASE_URL/api/v1/agents" >/dev/null 2>&1; then
        test_pass "API authentication works"
    else
        test_fail "API authentication failed"
    fi
else
    echo -e "${YELLOW}⚠${NC} API key not set, skipping auth test"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
