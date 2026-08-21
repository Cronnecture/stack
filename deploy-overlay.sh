#!/bin/bash
# Deploy cronnecture-intelligence beside live mail/identity.
# Does NOT delete namespaces. Does NOT run selective-rebuild.sh.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
INTEL="$ROOT/intelligence"
IMAGE="cronnecture-intelligence:local"
NS="cronnecture-intelligence"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG

KEEP_NS=(mail identity kube-system cert-manager platform)

echo "Deploying intelligence overlay (no cluster wipe)"
echo "kubeconfig: $KUBECONFIG"
echo

kubectl get ns mail identity kube-system cert-manager platform >/dev/null

build_and_import_image() {
  echo "Building $IMAGE ..."
  if command -v docker >/dev/null 2>&1; then
    sudo docker build -t "$IMAGE" "$INTEL"
    sudo docker save "$IMAGE" | sudo k3s ctr images import -
    return
  fi
  if command -v nerdctl >/dev/null 2>&1; then
    nerdctl build -t "$IMAGE" "$INTEL"
    return
  fi
  echo "No docker/nerdctl found; cannot build image" >&2
  exit 1
}

build_and_import_image

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

if ! kubectl get secret cronnecture-master-key -n "$NS" >/dev/null 2>&1; then
  echo "Creating master key secret"
  kubectl create secret generic cronnecture-master-key \
    --namespace="$NS" \
    --from-literal=master-key="$(openssl rand -base64 32)"
fi

kubectl apply -f "$INTEL/kubernetes/intelligence-deployment.yaml"

echo "Waiting for overlay pods..."
kubectl rollout status deployment/credential-manager -n "$NS" --timeout=180s
kubectl rollout status deployment/monitoring-system -n "$NS" --timeout=180s
kubectl rollout status deployment/cloudflare-manager -n "$NS" --timeout=180s
kubectl rollout status deployment/master-orchestrator -n "$NS" --timeout=180s

echo
echo "Overlay status:"
kubectl get pods -n "$NS" -o wide

echo
echo "Keep-set still present:"
for n in "${KEEP_NS[@]}"; do
  ready=$(kubectl get pods -n "$n" --no-headers 2>/dev/null | awk '{print $2}' | grep -c '/' || true)
  echo "  $n: $(kubectl get pods -n "$n" --no-headers 2>/dev/null | wc -l) pods"
done

echo
kubectl get deploy,svc -n mail
kubectl get deploy,svc,sts -n identity | head -40
echo
echo "Overlay deployed. Mail and identity were not modified."
