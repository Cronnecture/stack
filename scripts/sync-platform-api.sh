#!/bin/bash
# Copy platform OPS_API_TOKEN into cronnecture-system. Never prints the token.
set -euo pipefail
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG

token=$(kubectl -n platform get secret control-plane-cf -o jsonpath='{.data.OPS_API_TOKEN}')
if [[ -z "$token" ]]; then
  echo "platform control-plane-cf OPS_API_TOKEN missing" >&2
  exit 1
fi
kubectl -n cronnecture-system create secret generic platform-api \
  --from-literal=OPS_API_TOKEN="$(printf '%s' "$token" | base64 -d)" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "synced platform-api secret"
