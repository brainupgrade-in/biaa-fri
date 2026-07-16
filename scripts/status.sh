#!/usr/bin/env bash
# =============================================================================
# Status Script - Check deployment status
# =============================================================================

set -euo pipefail

NAMESPACE="financial-agent"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

echo ""
echo "=========================================="
echo "  Financial Agent Deployment Status"
echo "=========================================="
echo ""

# Check if namespace exists
if ! kubectl get namespace "${NAMESPACE}" &>/dev/null; then
    log_warning "Namespace '${NAMESPACE}' does not exist."
    exit 1
fi

# Pod Status
log_info "Pods:"
kubectl get pods -n "${NAMESPACE}" -o wide
echo ""

# Service Status
log_info "Services:"
kubectl get services -n "${NAMESPACE}"
echo ""

# Ingress Status
log_info "Ingress:"
kubectl get ingress -n "${NAMESPACE}"
echo ""

# PVC Status
log_info "Persistent Volume Claims:"
kubectl get pvc -n "${NAMESPACE}"
echo ""

# Deployment Status
log_info "Deployments:"
kubectl get deployments -n "${NAMESPACE}"
echo ""

# Check pod health
log_info "Pod Health Check:"
NOT_READY=$(kubectl get pods -n "${NAMESPACE}" --field-selector=status.phase!=Running -o name 2>/dev/null | wc -l)
if [ "${NOT_READY}" -gt 0 ]; then
    log_warning "${NOT_READY} pod(s) are not running."
else
    log_success "All pods are running."
fi
echo ""

# Check resource usage
log_info "Resource Usage:"
kubectl top pods -n "${NAMESPACE}" 2>/dev/null || log_warning "Metrics server not available."
echo ""

# Port forwarding status
log_info "To access the application:"
echo "  Frontend:  kubectl port-forward svc/frontend-service 3000:3000 -n ${NAMESPACE}"
echo "  Backend:   kubectl port-forward svc/backend-service 8000:8000 -n ${NAMESPACE}"
echo ""
