#!/bin/bash
# Make this stack the source of truth for mail + identity without losing data.
# - Never deletes PVCs or the identity-secrets Secret
# - Orphans the Secret from the k3s addon so removing it from the YAML
#   does not wipe passwords
# - Copies stack YAML into k3s manifests so k3s keeps applying it

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG
MANIFESTS=/var/lib/rancher/k3s/server/manifests

echo "Checking live mail/identity data..."
kubectl get ns mail identity >/dev/null
kubectl get secret identity-secrets -n identity >/dev/null
kubectl get pvc stalwart-data -n mail >/dev/null
for pvc in identity-postgres identity-redis vaultwarden-data passbolt-mariadb passbolt-data passbolt-jwt logto-postgres; do
  kubectl get pvc "$pvc" -n identity >/dev/null
done

echo "Orphaning identity-secrets from k3s addon ownership (keeps the Secret)..."
kubectl -n identity annotate secret identity-secrets \
  objectset.rio.cattle.io/owner-gvk- \
  objectset.rio.cattle.io/owner-name- \
  objectset.rio.cattle.io/owner-namespace- \
  objectset.rio.cattle.io/id- \
  objectset.rio.cattle.io/applied- \
  --overwrite >/dev/null
kubectl -n identity label secret identity-secrets objectset.rio.cattle.io/hash- --overwrite >/dev/null || true

echo "Installing stack YAML as k3s addons..."
sudo cp "$ROOT/kubernetes/mail.yaml" "$MANIFESTS/stalwart.yaml"
sudo cp "$ROOT/kubernetes/identity.yaml" "$MANIFESTS/identity-stack.yaml"
sudo cp "$ROOT/kubernetes/identity-cerbos.yaml" "$MANIFESTS/identity-cerbos.yaml"
sudo chmod 644 "$MANIFESTS/stalwart.yaml" "$MANIFESTS/identity-stack.yaml" "$MANIFESTS/identity-cerbos.yaml"

kubectl apply -f "$ROOT/kubernetes/identity-ingress.yaml"

echo "Waiting for mail + identity..."
kubectl rollout status deployment/stalwart -n mail --timeout=180s
kubectl rollout status deployment/vaultwarden -n identity --timeout=180s
kubectl get deploy,sts,pvc -n mail
kubectl get deploy,sts,pvc -n identity
echo "identity-secrets still present:"
kubectl get secret identity-secrets -n identity
