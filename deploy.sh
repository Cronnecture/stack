#!/bin/bash
# Primary deploy entry for /home/dev/stack
# Overlay + control plane + Cloudflare tunnel HTTP + ClusterIP services.
# Never wipes mail, identity, platform, or client namespaces.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG

echo "== Cronnecture stack deploy =="
kubectl get ns mail identity platform >/dev/null

echo
echo "== Mail + identity (live data, stack-owned YAML) =="
bash "$ROOT/scripts/apply-keep-set.sh"

echo
echo "== Intelligence overlay =="
bash "$ROOT/deploy-overlay.sh"

echo
echo "== Identity HTTP via Traefik =="
kubectl apply -f "$ROOT/kubernetes/identity-ingress.yaml"

echo "Waiting for vault Traefik route..."
for i in $(seq 1 20); do
  code=$(curl -sS -o /dev/null -w "%{http_code}" -H "Host: vault.cronnecture.com" http://10.43.125.134/alive || true)
  if [[ "$code" == "200" ]]; then
    echo "vault via Traefik: $code"
    break
  fi
  sleep 1
done
if [[ "${code:-}" != "200" ]]; then
  echo "WARN: vault Traefik route returned ${code:-none}" >&2
fi

echo
echo "== Control plane images =="
sudo docker build -t cronnecture-agent-core:local "$ROOT/agent-core"
sudo docker save cronnecture-agent-core:local | sudo k3s ctr images import -
sudo docker build -t cronnecture-dashboard:local "$ROOT/dashboard"
sudo docker save cronnecture-dashboard:local | sudo k3s ctr images import -

kubectl apply -f "$ROOT/kubernetes/control-plane.yaml"

echo
echo "== Cloudflare secrets from Ansible vault =="
bash "$ROOT/scripts/sync-cloudflare-secret.sh"
kubectl rollout restart deployment/cloudflare-manager -n cronnecture-intelligence
kubectl rollout restart deployment/agent-core -n cronnecture-system

kubectl rollout status deployment/agent-core -n cronnecture-system --timeout=180s
kubectl rollout status deployment/dashboard -n cronnecture-system --timeout=180s
kubectl rollout status deployment/cloudflare-manager -n cronnecture-intelligence --timeout=180s

echo
echo "== Cloudflare node-tunnel HTTP origins =="
python3 "$ROOT/scripts/sync-tunnel.py"

echo
echo "== Close HTTP NodePorts (mail hostPorts stay) =="
sudo python3 "$ROOT/scripts/close-http-nodeports.py" --manifests
python3 "$ROOT/scripts/close-http-nodeports.py" --live

echo
echo "== Verify keep-set URLs =="
curl -sS -o /dev/null -w "vault %{http_code}\n" https://vault.cronnecture.com/alive
curl -sS -o /dev/null -w "webmail %{http_code}\n" https://webmail.cronnecture.com/
curl -sS -o /dev/null -w "ops %{http_code}\n" https://ops.cronnecture.com/
curl -sS -o /dev/null -w "stack %{http_code}\n" -H "Host: stack.cronnecture.com" http://10.43.125.134/

echo
echo "NodePorts remaining:"
kubectl get svc -A --field-selector spec.type=NodePort
echo
echo "hostPorts remaining:"
kubectl get pods -A -o json | python3 -c '
import json, sys
data = json.load(sys.stdin)
for pod in data.get("items", []):
    for container in pod.get("spec", {}).get("containers", []):
        for port in container.get("ports") or []:
            if port.get("hostPort"):
                ns = pod["metadata"]["namespace"]
                name = pod["metadata"]["name"]
                print(ns, name, port.get("hostPort"), port.get("hostIP") or "*")
'
echo
echo "Stack deploy complete. Dashboard: https://stack.cronnecture.com"
echo "Mail SMTP remains on host ports 25/587. HTTP is Cloudflare tunnel -> Traefik."
