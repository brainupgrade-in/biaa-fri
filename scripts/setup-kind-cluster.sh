#!/bin/bash
# scripts/setup-kind-cluster.sh

set -euo pipefail

CLUSTER_NAME="financial-agent-kind"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Creating Kind cluster..."
kind create cluster --config "$PROJECT_ROOT/k8s/kind-config.yaml" --name "$CLUSTER_NAME"

echo "Installing NGINX Ingress Controller..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

echo "Waiting for ingress controller..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

echo "Building Docker images..."
docker build -t financial-agent/backend:latest -f "$PROJECT_ROOT/Dockerfile.backend" "$PROJECT_ROOT"
docker build -t financial-agent/frontend:latest -f "$PROJECT_ROOT/Dockerfile.frontend" "$PROJECT_ROOT"
docker build -t financial-agent/sandbox:latest -f "$PROJECT_ROOT/Dockerfile.sandbox" "$PROJECT_ROOT"

echo "Loading images into Kind..."
kind load docker-image financial-agent/backend:latest --name "$CLUSTER_NAME"
kind load docker-image financial-agent/frontend:latest --name "$CLUSTER_NAME"
kind load docker-image financial-agent/sandbox:latest --name "$CLUSTER_NAME"

echo "Applying Kubernetes manifests..."
kubectl apply -k "$PROJECT_ROOT/k8s/base"

echo "Waiting for pods to be ready..."
kubectl wait --namespace financial-agent \
  --for=condition=ready pod \
  --selector=app=backend \
  --timeout=180s

echo "Cluster setup complete!"
echo "Frontend: http://localhost"
echo "Backend API: http://localhost/api"
echo "PostgreSQL: localhost:5432 (via port-forward)"