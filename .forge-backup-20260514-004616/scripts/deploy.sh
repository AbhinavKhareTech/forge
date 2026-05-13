#!/bin/bash
set -e

# Forge Deployment Script
# Usage: ./scripts/deploy.sh [environment]

ENVIRONMENT=${1:-production}
VERSION=${2:-latest}
NAMESPACE=${3:-forge}

echo "Deploying Forge to ${ENVIRONMENT}..."
echo "  Version: ${VERSION}"
echo "  Namespace: ${NAMESPACE}"

# Validate prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker required"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl required"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "Helm required"; exit 1; }

# Build Docker image
echo "Building Docker image..."
docker build -t ahinsaai/forge:${VERSION} -f docker/Dockerfile .

# Push to registry (optional)
if [ "${PUSH_IMAGE}" = "true" ]; then
    echo "Pushing to registry..."
    docker push ahinsaai/forge:${VERSION}
fi

# Deploy with Helm
echo "Deploying with Helm..."
helm upgrade --install forge ./helm/forge \
    --namespace ${NAMESPACE} \
    --create-namespace \
    --set image.tag=${VERSION} \
    --set forge.env=${ENVIRONMENT} \
    --wait \
    --timeout 5m

# Verify deployment
echo "Verifying deployment..."
kubectl rollout status deployment/forge -n ${NAMESPACE}
kubectl get pods -n ${NAMESPACE}

echo "Deployment complete!"
echo ""
echo "Forge is available at:"
echo "  kubectl port-forward svc/forge 8080:8080 -n ${NAMESPACE}"
