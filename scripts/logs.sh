#!/usr/bin/env bash
# =============================================================================
# Logs Script - View logs from services
# =============================================================================

set -euo pipefail

NAMESPACE="financial-agent"
SERVICE="${1:-all}"
TAIL="${2:-100}"

BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }

show_usage() {
    echo "Usage: $0 [SERVICE] [TAIL_LINES]"
    echo ""
    echo "Services:"
    echo "  backend   - View backend logs"
    echo "  frontend  - View frontend logs"
    echo "  postgres  - View postgres logs"
    echo "  chroma    - View chroma logs"
    echo "  sandbox   - View sandbox logs"
    echo "  all       - View logs from all services (default)"
    echo ""
    echo "Examples:"
    echo "  $0 backend 50    # View last 50 lines of backend logs"
    echo "  $0 frontend      # View last 100 lines of frontend logs"
}

if [ "${SERVICE}" == "--help" ] || [ "${SERVICE}" == "-h" ]; then
    show_usage
    exit 0
fi

show_logs() {
    local deployment=$1
    log_info "Logs for ${deployment} (last ${TAIL} lines):"
    echo "---"
    kubectl logs -f "deployment/${deployment}" -n "${NAMESPACE}" --tail="${TAIL}" 2>/dev/null || \
        kubectl logs "deployment/${deployment}" -n "${NAMESPACE}" --tail="${TAIL}" 2>/dev/null || \
        echo "No logs available for ${deployment}"
    echo ""
}

case "${SERVICE}" in
    backend)
        show_logs "backend"
        ;;
    frontend)
        show_logs "frontend"
        ;;
    postgres)
        show_logs "postgres"
        ;;
    chroma)
        show_logs "chroma"
        ;;
    sandbox)
        show_logs "sandbox"
        ;;
    all)
        for svc in backend frontend postgres chroma sandbox; do
            show_logs "${svc}"
        done
        ;;
    *)
        echo "Unknown service: ${SERVICE}"
        show_usage
        exit 1
        ;;
esac
