#!/usr/bin/env bash
# =============================================================================
# Deploy Script - Rebuild and redeploy application
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

CLUSTER_NAME="financial-agent-kind"
NAMESPACE="financial-agent"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

log_info "Building new images..."
docker build -t financial-agent/backend:latest -f "${PROJECT_ROOT}/Dockerfile.backend" "${PROJECT_ROOT}"
docker build -t financial-agent/frontend:latest -f "${PROJECT_ROOT}/Dockerfile.frontend" "${PROJECT_ROOT}"
docker build -t financial-agent/sandbox:latest -f "${PROJECT_ROOT}/Dockerfile.sandbox" "${PROJECT_ROOT}"

log_info "Loading images into Kind..."
kind load docker-image financial-agent/backend:latest --name "${CLUSTER_NAME}"
kind load docker-image financial-agent/frontend:latest --name "${CLUSTER_NAME}"
kind load docker-image financial-agent/sandbox:latest --name "${CLUSTER_NAME}"

log_info "Rolling update deployments..."
kubectl rollout restart deployment/backend -n "${NAMESPACE}"
kubectl rollout restart deployment/frontend -n "${NAMESPACE}"
kubectl rollout restart deployment/sandbox -n "${NAMESPACE}"

log_info "Waiting for rollout to complete..."
kubectl rollout status deployment/backend -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/frontend -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/sandbox -n "${NAMESPACE}" --timeout=120s

log_success "Deployment complete!"
