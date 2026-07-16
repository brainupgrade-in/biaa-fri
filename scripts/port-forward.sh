#!/usr/bin/env bash
# =============================================================================
# Port Forward Script - Set up port forwarding for local access
# =============================================================================

set -euo pipefail

NAMESPACE="financial-agent"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

cleanup() {
    log_info "Stopping port forwarding..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

log_info "Setting up port forwarding..."
echo ""

# Frontend
log_info "Frontend: http://localhost:3000"
kubectl port-forward svc/frontend-service 3000:3000 -n "${NAMESPACE}" &

# Backend
log_info "Backend: http://localhost:8000"
kubectl port-forward svc/backend-service 8000:8000 -n "${NAMESPACE}" &

# API Docs
log_info "API Docs: http://localhost:8000/docs"
# (Same as backend)

# PostgreSQL (optional)
# log_info "PostgreSQL: localhost:5432"
# kubectl port-forward svc/postgres-service 5432:5432 -n "${NAMESPACE}" &

# Chroma (optional)
# log_info "Chroma: localhost:8001"
# kubectl port-forward svc/chroma-service 8001:8000 -n "${NAMESPACE}" &

echo ""
log_success "Port forwarding active. Press Ctrl+C to stop."
echo ""

# Wait for background processes
wait
