#!/bin/bash
# Identity failsafe helper. Never prints secret values.
# Usage:
#   identity-failsafe.sh status
#   AUTHENTIK_REDIS_HOST=… AUTHENTIK_REDIS_PASSWORD=… [AUTHENTIK_REDIS_PORT=6379] [AUTHENTIK_REDIS_TLS=true] \
#     identity-failsafe.sh apply-redis
#   LOGTO_DATABASE_URL=postgres://… identity-failsafe.sh apply-logto
#   identity-failsafe.sh scale-authentik --i-raised-the-pooler
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG
NS=identity

host_of() {
  python3 -c 'import sys; u=sys.stdin.read().strip();
print(u.split("@",1)[1].split("/",1)[0] if "@" in u else u or "none")'
}

cmd="${1:-status}"

case "$cmd" in
  status)
    echo "=== replicas ==="
    kubectl -n "$NS" get deploy authentik-server authentik-worker logto hanko cerbos identity-redis logto-postgres \
      -o custom-columns='NAME:.metadata.name,READY:.status.readyReplicas,DESIRED:.spec.replicas' --no-headers
    echo
    echo "=== data plane (still SPOF if on a worker) ==="
    echo -n "authentik redis host: "
    kubectl -n "$NS" exec deploy/authentik-server -- printenv AUTHENTIK_REDIS__HOST 2>/dev/null || echo unavailable
    echo -n "authentik postgres: "
    kubectl -n "$NS" exec deploy/authentik-server -- printenv AUTHENTIK_POSTGRESQL__HOST 2>/dev/null || echo unavailable
    echo -n "logto db: "
    kubectl -n "$NS" exec deploy/logto -- printenv DB_URL 2>/dev/null | host_of || echo unavailable
    echo
    echo "=== placement ==="
    kubectl -n "$NS" get pods -l 'app in (authentik-server,authentik-worker,logto,hanko,cerbos,identity-redis,logto-postgres)' \
      -o custom-columns='NAME:.metadata.name,READY:.status.containerStatuses[0].ready,NODE:.spec.nodeName' --no-headers
    echo
    echo "Next operator clicks: docs/runbooks/identity-failsafe.md"
    ;;

  apply-redis)
    host="${AUTHENTIK_REDIS_HOST:-}"
    pass="${AUTHENTIK_REDIS_PASSWORD:-}"
    port="${AUTHENTIK_REDIS_PORT:-6379}"
    tls="${AUTHENTIK_REDIS_TLS:-false}"
    test -n "$host" || { echo "set AUTHENTIK_REDIS_HOST" >&2; exit 1; }
    test -n "$pass" || { echo "set AUTHENTIK_REDIS_PASSWORD" >&2; exit 1; }
    echo "Pointing Authentik Redis at host ${host} port ${port} tls=${tls}"
    kubectl -n "$NS" patch secret identity-secrets --type merge -p "$(python3 - <<PY
import base64, json, os
def b(s): return base64.b64encode(s.encode()).decode()
print(json.dumps({"data": {
  "authentik-redis-host": b(os.environ["AUTHENTIK_REDIS_HOST"]),
  "authentik-redis-port": b(os.environ.get("AUTHENTIK_REDIS_PORT","6379")),
  "authentik-redis-tls": b(os.environ.get("AUTHENTIK_REDIS_TLS","false")),
  "redis-password": b(os.environ["AUTHENTIK_REDIS_PASSWORD"]),
}}))
PY
)"
    kubectl -n "$NS" rollout restart deploy/authentik-server deploy/authentik-worker
    kubectl -n "$NS" rollout status deploy/authentik-server --timeout=300s
    kubectl -n "$NS" rollout status deploy/authentik-worker --timeout=180s
    echo "Authentik Redis now ${host}"
    ;;

  apply-logto)
    url="${LOGTO_DATABASE_URL:-}"
    test -n "$url" || { echo "set LOGTO_DATABASE_URL" >&2; exit 1; }
    echo "Pointing Logto at $(printf '%s' "$url" | host_of)"
    kubectl -n "$NS" patch secret identity-secrets --type merge -p "$(python3 - <<PY
import base64, json, os
def b(s): return base64.b64encode(s.encode()).decode()
print(json.dumps({"data": {"postgres-dsn-logto": b(os.environ["LOGTO_DATABASE_URL"])}}))
PY
)"
    kubectl -n "$NS" rollout restart deploy/logto
    kubectl -n "$NS" rollout status deploy/logto --timeout=300s
    echo "Logto DSN updated (in-cluster logto-postgres PVC left in place)"
    ;;

  scale-authentik)
    if [[ "${2:-}" != "--i-raised-the-pooler" ]]; then
      echo "Refusing to scale Authentik. The session pooler is 15 clients;" >&2
      echo "two servers took auth.cronnecture.com down. After you raise it:" >&2
      echo "  $0 scale-authentik --i-raised-the-pooler" >&2
      exit 2
    fi
    kubectl -n "$NS" scale deploy/authentik-server --replicas=2
    kubectl -n "$NS" rollout status deploy/authentik-server --timeout=300s
    kubectl -n "$NS" get pods -l app=authentik-server -o wide
    ;;

  *)
    echo "Usage: $0 status|apply-redis|apply-logto|scale-authentik" >&2
    exit 1
    ;;
esac
