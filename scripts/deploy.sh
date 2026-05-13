#!/bin/bash
set -euo pipefail

# Forge Production Deployment Script
# Usage: ./scripts/deploy.sh [environment]

ENVIRONMENT="${1:-staging}"
NAMESPACE="forge"
HELM_CHART="./helm/forge"
RELEASE_NAME="forge"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate environment
if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
    log_error "Invalid environment: $ENVIRONMENT. Must be 'staging' or 'production'"
    exit 1
fi

log_info "Deploying Forge to $ENVIRONMENT..."

# Pre-deployment checks
log_info "Running pre-deployment checks..."

# Check kubectl context
CURRENT_CONTEXT=$(kubectl config current-context)
log_info "Current context: $CURRENT_CONTEXT"

if [[ "$ENVIRONMENT" == "production" && ! "$CURRENT_CONTEXT" =~ "prod" ]]; then
    log_error "Production deployment requires a production context!"
    exit 1
fi

# Check secrets exist
if ! kubectl get secret forge-secrets -n "$NAMESPACE" >/dev/null 2>&1; then
    log_error "Secret 'forge-secrets' not found in namespace '$NAMESPACE'"
    log_error "Create it first with: kubectl create secret generic forge-secrets --from-env-file=.env"
    exit 1
fi

# Validate Helm chart
log_info "Validating Helm chart..."
helm lint "$HELM_CHART"

# Run database migrations
log_info "Running database migrations..."
kubectl exec -n "$NAMESPACE" deploy/forge -- alembic upgrade head || log_warn "Migration step skipped or failed"

# Deploy with Helm
log_info "Deploying with Helm..."
helm upgrade --install "$RELEASE_NAME" "$HELM_CHART" \
    --namespace "$NAMESPACE" \
    --create-namespace \
    --values "$HELM_CHART/values-$ENVIRONMENT.yaml" \
    --set image.tag="${IMAGE_TAG:-latest}" \
    --wait \
    --timeout 10m

# Verify deployment
log_info "Verifying deployment..."
kubectl rollout status deployment/forge -n "$NAMESPACE" --timeout=5m

# Health check
log_info "Running health checks..."
FORGE_POD=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=forge -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n "$NAMESPACE" "$FORGE_POD" -- curl -sf http://localhost:8000/health/ready

log_info "Deployment to $ENVIRONMENT completed successfully!"

# Post-deployment verification
log_info "Running smoke tests..."
./scripts/smoke-tests.sh "$ENVIRONMENT"

log_info "All checks passed. Forge is live in $ENVIRONMENT!"
