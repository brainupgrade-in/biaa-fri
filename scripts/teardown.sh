#!/bin/bash
# scripts/teardown.sh

set -euo pipefail

echo "Deleting Kind cluster..."
kind delete cluster --name financial-agent

echo "Cleanup complete!"