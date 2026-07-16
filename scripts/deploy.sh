#!/bin/bash
# scripts/deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Building new images..."
docker build -t financial-agent/backend:latest -f "$PROJECT_ROOT/Dockerfile.backend" "$PROJECT_ROOT"
docker build -t financial-agent/frontend:latest -f "$PROJECT_ROOT/Dockerfile.frontend" "$PROJECT_ROOT"
docker build -t financial-agent/sandbox:latest -f "$PROJECT_ROOT/Dockerfile.sandbox" "$PROJECT_ROOT"

echo "Loading images into Kind..."
kind load docker-image financial-agent/backend:latest --name financial-agent
kind load docker-image financial-agent/frontend:latest --name financial-agent
kind load docker-image financial-agent/sandbox:latest --name financial-agent

echo "Rolling update deployments..."
kubectl rollout restart deployment/backend -n financial-agent
kubectl rollout restart deployment/frontend -n financial-agent
kubectl rollout restart deployment/sandbox -n financial-agent

echo "Waiting for rollout to complete..."
kubectl rollout status deployment/backend -n financial-agent --timeout=180s
kubectl rollout status deployment/frontend -n financial-agent --timeout=180s
kubectl rollout status deployment/sandbox -n financial-agent --timeout=180s

echo "Deployment complete!"