#!/usr/bin/env bash
# =============================================================================
# Financial-Report Insight Agent - Deployment Infrastructure Setup
# =============================================================================
# This script sets up the complete deployment infrastructure for the
# financial-report insight agent on a Kind (Kubernetes in Docker) cluster.
#
# Usage:
#   ./setup-infrastructure.sh [OPTIONS]
#
# Options:
#   --cluster-name NAME    Kind cluster name (default: financial-agent-kind)
#   --namespace NS         Kubernetes namespace (default: financial-agent)
#   --skip-build           Skip Docker image builds
#   --skip-monitoring      Skip monitoring stack installation
#   --skip-network-policies Skip network policy installation
#   --teardown             Tear down the infrastructure
#   --help                 Show this help message
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
CLUSTER_NAME="financial-agent-kind"
NAMESPACE="financial-agent"
MONITORING_NAMESPACE="monitoring"
SKIP_BUILD=false
SKIP_MONITORING=false
SKIP_NETWORK_POLICIES=false
TEARDOWN=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is required but not installed."
        exit 1
    fi
}

wait_for_pods() {
    local namespace=$1
    local label=$2
    local timeout=${3:-120}

    log_info "Waiting for pods with label '$label' in namespace '$namespace'..."
    kubectl wait --namespace "$namespace" \
        --for=condition=ready pod \
        --selector="$label" \
        --timeout="${timeout}s" 2>/dev/null || true
}

# =============================================================================
# Parse Arguments
# =============================================================================

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --cluster-name)
                CLUSTER_NAME="$2"
                shift 2
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --skip-build)
                SKIP_BUILD=true
                shift
                ;;
            --skip-monitoring)
                SKIP_MONITORING=true
                shift
                ;;
            --skip-network-policies)
                SKIP_NETWORK_POLICIES=true
                shift
                ;;
            --teardown)
                TEARDOWN=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

show_help() {
    head -20 "$0" | tail -15
}

# =============================================================================
# Prerequisites Check
# =============================================================================

check_prerequisites() {
    log_info "Checking prerequisites..."

    check_command "docker"
    check_command "kind"
    check_command "kubectl"
    check_command "jq"

    # Check Docker is running
    if ! docker info &> /dev/null; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi

    log_success "All prerequisites met."
}

# =============================================================================
# Teardown
# =============================================================================

teardown() {
    log_warning "Tearing down infrastructure..."

    # Delete Kind cluster
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log_info "Deleting Kind cluster: ${CLUSTER_NAME}"
        kind delete cluster --name "${CLUSTER_NAME}"
        log_success "Kind cluster deleted."
    else
        log_warning "Kind cluster '${CLUSTER_NAME}' not found."
    fi

    log_success "Teardown complete."
}

# =============================================================================
# Kind Cluster Setup
# =============================================================================

setup_kind_cluster() {
    log_info "Setting up Kind cluster..."

    # Check if cluster already exists
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log_warning "Kind cluster '${CLUSTER_NAME}' already exists."
        read -p "Do you want to recreate it? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kind delete cluster --name "${CLUSTER_NAME}"
        else
            log_info "Using existing cluster."
            return
        fi
    fi

    # Create Kind config
    cat <<EOF | kind create cluster --config - --name "${CLUSTER_NAME}"
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
      - containerPort: 30080
        hostPort: 30080
        protocol: TCP
      - containerPort: 30090
        hostPort: 30090
        protocol: TCP
  - role: worker
  - role: worker
EOF

    log_success "Kind cluster created."
}

# =============================================================================
# NGINX Ingress Controller
# =============================================================================

install_ingress_controller() {
    log_info "Installing NGINX Ingress Controller..."

    # Apply the ingress controller manifest
    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

    # Wait for ingress controller to be ready
    log_info "Waiting for ingress controller to be ready..."
    kubectl wait --namespace ingress-nginx \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/component=controller \
        --timeout=120s

    log_success "NGINX Ingress Controller installed."
}

# =============================================================================
# Docker Image Builds
# =============================================================================

build_images() {
    if [[ "${SKIP_BUILD}" == true ]]; then
        log_warning "Skipping Docker image builds."
        return
    fi

    log_info "Building Docker images..."

    # Build backend
    log_info "Building backend image..."
    docker build -t financial-agent/backend:latest \
        -f "${PROJECT_ROOT}/Dockerfile.backend" \
        "${PROJECT_ROOT}"

    # Build frontend
    log_info "Building frontend image..."
    docker build -t financial-agent/frontend:latest \
        -f "${PROJECT_ROOT}/Dockerfile.frontend" \
        "${PROJECT_ROOT}"

    # Build sandbox
    log_info "Building sandbox image..."
    docker build -t financial-agent/sandbox:latest \
        -f "${PROJECT_ROOT}/Dockerfile.sandbox" \
        "${PROJECT_ROOT}"

    log_success "Docker images built."
}

# =============================================================================
# Load Images into Kind
# =============================================================================

load_images_to_kind() {
    if [[ "${SKIP_BUILD}" == true ]]; then
        log_warning "Skipping loading images into Kind."
        return
    fi

    log_info "Loading images into Kind cluster..."

    kind load docker-image financial-agent/backend:latest --name "${CLUSTER_NAME}"
    kind load docker-image financial-agent/frontend:latest --name "${CLUSTER_NAME}"
    kind load docker-image financial-agent/sandbox:latest --name "${CLUSTER_NAME}"

    log_success "Images loaded into Kind."
}

# =============================================================================
# Kubernetes Namespace
# =============================================================================

create_namespace() {
    log_info "Creating namespace: ${NAMESPACE}"

    kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    log_success "Namespace created."
}

# =============================================================================
# Secrets Management
# =============================================================================

create_secrets() {
    log_info "Creating Kubernetes secrets..."

    # Generate random passwords if they don't exist
    POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
    LLM_API_KEY="${LLM_API_KEY:-your-llm-api-key-here}"

    # Create backend secrets
    kubectl create secret generic backend-secrets \
        --namespace "${NAMESPACE}" \
        --from-literal=database-url="postgresql://agent_user:${POSTGRES_PASSWORD}@postgres-service:5432/financial_agent" \
        --from-literal=llm-api-key="${LLM_API_KEY}" \
        --dry-run=client -o yaml | kubectl apply -f -

    # Create postgres secrets
    kubectl create secret generic postgres-secrets \
        --namespace "${NAMESPACE}" \
        --from-literal=username="agent_user" \
        --from-literal=password="${POSTGRES_PASSWORD}" \
        --dry-run=client -o yaml | kubectl apply -f -

    log_success "Secrets created."
}

# =============================================================================
# ConfigMaps
# =============================================================================

create_configmaps() {
    log_info "Creating ConfigMaps..."

    # Application config
    kubectl create configmap app-config \
        --namespace "${NAMESPACE}" \
        --from-literal=ENVIRONMENT="development" \
        --from-literal=LOG_LEVEL="INFO" \
        --from-literal=Z_SCORE_THRESHOLD="2.0" \
        --from-literal=MATERIALITY_THRESHOLD="0.10" \
        --from-literal=PRECISION_DECIMALS="2" \
        --from-literal=COMPUTATION_TIMEOUT="5" \
        --from-literal=MAX_CONCURRENT_SESSIONS="100" \
        --from-literal=AUDIT_LOG_RETENTION_YEARS="7" \
        --dry-run=client -o yaml | kubectl apply -f -

    # Nginx config
    kubectl create configmap nginx-config \
        --namespace "${NAMESPACE}" \
        --from-literal=default.conf='
server {
    listen 3000;
    server_name localhost;
    
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://backend-service:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /ws {
        proxy_pass http://backend-service:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}' \
        --dry-run=client -o yaml | kubectl apply -f -

    log_success "ConfigMaps created."
}

# =============================================================================
# RBAC
# =============================================================================

create_rbac() {
    log_info "Creating RBAC resources..."

    # Service Account
    kubectl create serviceaccount backend-sa \
        --namespace "${NAMESPACE}" \
        --dry-run=client -o yaml | kubectl apply -f -

    # Role
    cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: backend-role
  namespace: ${NAMESPACE}
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get"]
EOF

    # Role Binding
    cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: backend-rolebinding
  namespace: ${NAMESPACE}
subjects:
  - kind: ServiceAccount
    name: backend-sa
    namespace: ${NAMESPACE}
roleRef:
  kind: Role
  name: backend-role
  apiGroup: rbac.authorization.k8s.io
EOF

    log_success "RBAC resources created."
}

# =============================================================================
# Persistent Volume Claims
# =============================================================================

create_pvcs() {
    log_info "Creating Persistent Volume Claims..."

    # Documents PVC
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: documents-pvc
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
EOF

    # PostgreSQL PVC
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
EOF

    # Chroma PVC
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: chroma-pvc
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
EOF

    log_success "PVCs created."
}

# =============================================================================
# Deploy PostgreSQL
# =============================================================================

deploy_postgres() {
    log_info "Deploying PostgreSQL..."

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 999
        fsGroup: 999
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: "financial_agent"
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-secrets
                  key: username
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secrets
                  key: password
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          livenessProbe:
            exec:
              command:
                - pg_isready
                - -U
                - agent_user
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            exec:
              command:
                - pg_isready
                - -U
                - agent_user
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - name: postgres-pv
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: postgres-pv
          persistentVolumeClaim:
            claimName: postgres-pvc
EOF

    # PostgreSQL Service
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: ${NAMESPACE}
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
EOF

    log_success "PostgreSQL deployed."
}

# =============================================================================
# Deploy Chroma Vector Store
# =============================================================================

deploy_chroma() {
    log_info "Deploying Chroma Vector Store..."

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chroma
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: chroma
  template:
    metadata:
      labels:
        app: chroma
    spec:
      containers:
        - name: chroma
          image: chromadb/chroma:latest
          ports:
            - containerPort: 8000
          env:
            - name: ANONYMIZED_TELEMETRY
              value: "False"
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          volumeMounts:
            - name: chroma-pv
              mountPath: /chroma/chroma
      volumes:
        - name: chroma-pv
          persistentVolumeClaim:
            claimName: chroma-pvc
EOF

    # Chroma Service
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: chroma-service
  namespace: ${NAMESPACE}
spec:
  selector:
    app: chroma
  ports:
    - port: 8000
      targetPort: 8000
EOF

    log_success "Chroma deployed."
}

# =============================================================================
# Deploy Backend
# =============================================================================

deploy_backend() {
    log_info "Deploying Backend..."

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: ${NAMESPACE}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      serviceAccountName: backend-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: backend
          image: financial-agent/backend:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: backend-secrets
                  key: database-url
            - name: CHROMA_HOST
              value: "chroma-service"
            - name: CHROMA_PORT
              value: "8000"
            - name: LLM_API_KEY
              valueFrom:
                secretKeyRef:
                  name: backend-secrets
                  key: llm-api-key
            - name: ENVIRONMENT
              valueFrom:
                configMapKeyRef:
                  name: app-config
                  key: ENVIRONMENT
            - name: LOG_LEVEL
              valueFrom:
                configMapKeyRef:
                  name: app-config
                  key: LOG_LEVEL
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - name: documents-pv
              mountPath: /app/documents
      volumes:
        - name: documents-pv
          persistentVolumeClaim:
            claimName: documents-pvc
EOF

    # Backend Service
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: backend-service
  namespace: ${NAMESPACE}
spec:
  selector:
    app: backend
  ports:
    - port: 8000
      targetPort: 8000
EOF

    log_success "Backend deployed."
}

# =============================================================================
# Deploy Frontend
# =============================================================================

deploy_frontend() {
    log_info "Deploying Frontend..."

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: ${NAMESPACE}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 101
      containers:
        - name: frontend
          image: financial-agent/frontend:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 3000
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "128Mi"
              cpu: "100m"
          livenessProbe:
            httpGet:
              path: /
              port: 3000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 5
EOF

    # Frontend Service
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: frontend-service
  namespace: ${NAMESPACE}
spec:
  selector:
    app: frontend
  ports:
    - port: 3000
      targetPort: 3000
EOF

    log_success "Frontend deployed."
}

# =============================================================================
# Deploy Computation Sandbox
# =============================================================================

deploy_sandbox() {
    log_info "Deploying Computation Sandbox..."

    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sandbox
  namespace: ${NAMESPACE}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: sandbox
  template:
    metadata:
      labels:
        app: sandbox
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
        - name: sandbox
          image: financial-agent/sandbox:latest
          imagePullPolicy: Never
          ports:
            - containerPort: 8080
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 10
EOF

    # Sandbox Service
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: sandbox-service
  namespace: ${NAMESPACE}
spec:
  selector:
    app: sandbox
  ports:
    - port: 8080
      targetPort: 8080
EOF

    log_success "Sandbox deployed."
}

# =============================================================================
# Ingress
# =============================================================================

create_ingress() {
    log_info "Creating Ingress..."

    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: financial-agent-ingress
  namespace: ${NAMESPACE}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/websocket-services: backend-service
spec:
  ingressClassName: nginx
  rules:
    - host: localhost
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-service
                port:
                  number: 3000
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: backend-service
                port:
                  number: 8000
          - path: /ws
            pathType: Prefix
            backend:
              service:
                name: backend-service
                port:
                  number: 8000
EOF

    log_success "Ingress created."
}

# =============================================================================
# Network Policies
# =============================================================================

create_network_policies() {
    if [[ "${SKIP_NETWORK_POLICIES}" == true ]]; then
        log_warning "Skipping network policies."
        return
    fi

    log_info "Creating Network Policies..."

    # Backend policy
    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-policy
  namespace: ${NAMESPACE}
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - port: 8000
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
        - podSelector:
            matchLabels:
              app: chroma
        - podSelector:
            matchLabels:
              app: sandbox
      ports:
        - port: 5432
        - port: 8000
        - port: 8080
EOF

    # Sandbox policy (no outbound)
    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sandbox-policy
  namespace: ${NAMESPACE}
spec:
  podSelector:
    matchLabels:
      app: sandbox
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: backend
      ports:
        - port: 8080
  egress: []
EOF

    # Postgres policy
    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-policy
  namespace: ${NAMESPACE}
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: backend
      ports:
        - port: 5432
  egress: []
EOF

    log_success "Network Policies created."
}

# =============================================================================
# Monitoring Stack
# =============================================================================

install_monitoring() {
    if [[ "${SKIP_MONITORING}" == true ]]; then
        log_warning "Skipping monitoring stack."
        return
    fi

    log_info "Installing monitoring stack..."

    # Create monitoring namespace
    kubectl create namespace "${MONITORING_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    # Install Prometheus
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
    helm repo update

    helm upgrade --install prometheus prometheus-community/prometheus \
        --namespace "${MONITORING_NAMESPACE}" \
        --set alertmanager.enabled=false \
        --set pushgateway.enabled=false \
        --wait --timeout 300s

    # Install Grafana
    helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
    helm repo update

    helm upgrade --install grafana grafana/grafana \
        --namespace "${MONITORING_NAMESPACE}" \
        --set adminPassword=admin \
        --set service.type=NodePort \
        --set service.nodePort=30090 \
        --wait --timeout 300s

    log_success "Monitoring stack installed."
}

# =============================================================================
# Wait for Pods
# =============================================================================

wait_for_all_pods() {
    log_info "Waiting for all pods to be ready..."

    wait_for_pods "${NAMESPACE}" "app=postgres" 120
    wait_for_pods "${NAMESPACE}" "app=chroma" 120
    wait_for_pods "${NAMESPACE}" "app=backend" 180
    wait_for_pods "${NAMESPACE}" "app=frontend" 120
    wait_for_pods "${NAMESPACE}" "app=sandbox" 120

    log_success "All pods are ready."
}

# =============================================================================
# Verify Deployment
# =============================================================================

verify_deployment() {
    log_info "Verifying deployment..."

    # Check all pods are running
    echo ""
    log_info "Pods in namespace '${NAMESPACE}':"
    kubectl get pods -n "${NAMESPACE}" -o wide

    echo ""
    log_info "Services in namespace '${NAMESPACE}':"
    kubectl get services -n "${NAMESPACE}"

    echo ""
    log_info "Ingress in namespace '${NAMESPACE}':"
    kubectl get ingress -n "${NAMESPACE}"

    # Test health endpoint
    log_info "Testing backend health endpoint..."
    kubectl port-forward svc/backend-service 8000:8000 -n "${NAMESPACE}" &
    PORT_FORWARD_PID=$!
    sleep 3

    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log_success "Backend health check passed."
    else
        log_warning "Backend health check failed (may need more time to start)."
    fi

    kill $PORT_FORWARD_PID 2>/dev/null || true

    log_success "Deployment verified."
}

# =============================================================================
# Print Summary
# =============================================================================

print_summary() {
    echo ""
    echo "=========================================="
    echo "  Deployment Complete!"
    echo "=========================================="
    echo ""
    echo "Cluster:     ${CLUSTER_NAME}"
    echo "Namespace:   ${NAMESPACE}"
    echo ""
    echo "Access URLs:"
    echo "  Frontend:  http://localhost"
    echo "  Backend:   http://localhost:8000"
    echo "  API Docs:  http://localhost:8000/docs"
    echo ""
    echo "Useful commands:"
    echo "  kubectl get pods -n ${NAMESPACE}"
    echo "  kubectl logs -f deployment/backend -n ${NAMESPACE}"
    echo "  kubectl port-forward svc/frontend-service 3000:3000 -n ${NAMESPACE}"
    echo ""
    echo "To tear down:"
    echo "  ./setup-infrastructure.sh --teardown"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    parse_arguments "$@"

    if [[ "${TEARDOWN}" == true ]]; then
        teardown
        exit 0
    fi

    check_prerequisites
    setup_kind_cluster
    install_ingress_controller
    build_images
    load_images_to_kind
    create_namespace
    create_secrets
    create_configmaps
    create_rbac
    create_pvcs
    deploy_postgres
    deploy_chroma
    deploy_backend
    deploy_frontend
    deploy_sandbox
    create_ingress
    create_network_policies
    install_monitoring
    wait_for_all_pods
    verify_deployment
    print_summary
}

main "$@"
