#!/bin/bash
# Build a product checkout from stack/apps and load it into the cluster.
# Usage: build-app.sh marketing|portfolio
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../lib/stack_paths.sh
source "$ROOT/lib/stack_paths.sh"

APP="${1:-}"
case "$APP" in
  marketing)
    SRC="$APPS_DIR/marketing"
    IMAGE_LOCAL="cronnecture-website:local"
    REGISTRY_APP="cronnecture-website"
    DEPLOY_NS=platform
    DEPLOY_NAME=cronnecture-website
    CONTAINER=website
    ;;
  portfolio)
    SRC="$APPS_DIR/portfolio"
    IMAGE_LOCAL="cronnecture-portfolio:local"
    REGISTRY_APP="cronnecture-portfolio"
    DEPLOY_NS=""
    DEPLOY_NAME=""
    CONTAINER=""
    ;;
  *)
    echo "Usage: $0 marketing|portfolio" >&2
    exit 1
    ;;
esac

test -f "$SRC/Dockerfile" || { echo "missing $SRC/Dockerfile" >&2; exit 1; }
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG

TAG="$(git -C "$SRC" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)"
REG_IMAGE="fleet-registry.platform.svc.cluster.local:5000/platform/${REGISTRY_APP}:${TAG}"

NODE_IMAGE="127.0.0.1:30500/platform/${REGISTRY_APP}:${TAG}"

echo "Building $APP from $SRC (tag $TAG)"
sudo docker build -t "$IMAGE_LOCAL" -t "$REG_IMAGE" -t "$NODE_IMAGE" "$SRC"
sudo docker save "$IMAGE_LOCAL" | sudo k3s ctr images import -

# Local containerd import is master-only. Workers pull from fleet-registry
# (NodePort 30500, R2-backed). Push so a pin on a general worker can start.
if sudo docker push "$NODE_IMAGE"; then
  echo "Pushed $NODE_IMAGE"
else
  echo "Registry push failed — workers will ImagePullBackOff until this tag is in fleet-registry." >&2
fi

if [[ -n "$DEPLOY_NS" ]]; then
  echo "Pointing $DEPLOY_NS/$DEPLOY_NAME at $REG_IMAGE"
  kubectl -n "$DEPLOY_NS" set image "deploy/${DEPLOY_NAME}" "${CONTAINER}=${REG_IMAGE}"
  kubectl -n "$DEPLOY_NS" rollout status "deploy/${DEPLOY_NAME}" --timeout=180s
fi

echo "Built $IMAGE_LOCAL and $REG_IMAGE"
