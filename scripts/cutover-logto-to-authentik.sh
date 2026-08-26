#!/bin/bash
# Finish Logto → Authentik cutover on the live cluster.
# Requires kubeconfig sudo, images built separately if needed.
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
K=(sudo -n kubectl)
ENV_FILE=/home/dev/stack/ansible/config/.identity/authentik_portal_oidc.env
API_TOKEN_FILE=/home/dev/stack/ansible/config/.identity/authentik_api_token
SITE_NS=client-noorddriveautos

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
API_TOKEN="$(tr -d '\n' < "$API_TOKEN_FILE")"

echo "== patch leftover secret =="
"${K[@]}" -n platform patch secret control-plane-cf --type=json -p="[$(
  python3 - <<PY
import json, os, base64
keys = {
  "AUTHENTIK_URL": os.environ["AUTHENTIK_URL"],
  "AUTHENTIK_INTERNAL_URL": os.environ["AUTHENTIK_INTERNAL_URL"],
  "AUTHENTIK_PORTAL_ISSUER": os.environ["AUTHENTIK_PORTAL_ISSUER"],
  "AUTHENTIK_PORTAL_CLIENT_ID": os.environ["AUTHENTIK_PORTAL_CLIENT_ID"],
  "AUTHENTIK_PORTAL_CLIENT_SECRET": os.environ["AUTHENTIK_PORTAL_CLIENT_SECRET"],
  "AUTHENTIK_API_TOKEN": """$API_TOKEN""",
}
ops = []
for k,v in keys.items():
    ops.append({"op":"add","path":f"/data/{k}","value": __import__("base64").b64encode(v.encode()).decode()})
print(",".join(json.dumps(o) for o in ops))
PY
)]"

echo "== leftover AUTHENTIK env =="
for key in AUTHENTIK_URL AUTHENTIK_INTERNAL_URL AUTHENTIK_PORTAL_ISSUER AUTHENTIK_PORTAL_CLIENT_ID AUTHENTIK_PORTAL_CLIENT_SECRET AUTHENTIK_API_TOKEN; do
  "${K[@]}" -n platform set env deploy/control-plane "$key=placeholder" >/dev/null 2>&1 || true
done
"${K[@]}" -n platform set env deploy/control-plane \
  --from-literal=AUTHENTIK_URL="$AUTHENTIK_URL" \
  --from-literal=AUTHENTIK_INTERNAL_URL="$AUTHENTIK_INTERNAL_URL" \
  --from-literal=AUTHENTIK_PORTAL_ISSUER="$AUTHENTIK_PORTAL_ISSUER" \
  --from-literal=AUTHENTIK_PORTAL_CLIENT_ID="$AUTHENTIK_PORTAL_CLIENT_ID" \
  --from-literal=AUTHENTIK_PORTAL_CLIENT_SECRET="$AUTHENTIK_PORTAL_CLIENT_SECRET" \
  --from-literal=AUTHENTIK_API_TOKEN="$API_TOKEN"

echo "== site-gate secret + apply =="
"${K[@]}" -n "$SITE_NS" create secret generic site-logto \
  --from-literal=client-id="$AUTHENTIK_SITE_CLIENT_ID" \
  --from-literal=client-secret="$AUTHENTIK_SITE_CLIENT_SECRET" \
  --from-literal=cookie-secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --dry-run=client -o yaml | "${K[@]}" apply -f -
# keep existing cookie-secret if present
if "${K[@]}" -n "$SITE_NS" get secret site-logto >/dev/null 2>&1; then
  "${K[@]}" -n "$SITE_NS" patch secret site-logto --type=merge -p "$(python3 - <<PY
import json, os, base64
print(json.dumps({"data":{
  "client-id": base64.b64encode(os.environ["AUTHENTIK_SITE_CLIENT_ID"].encode()).decode(),
  "client-secret": base64.b64encode(os.environ["AUTHENTIK_SITE_CLIENT_SECRET"].encode()).decode(),
}}))
PY
)"
fi
"${K[@]}" apply -f /home/dev/stack/ansible/services/site-gate/k8s.yaml
"${K[@]}" -n "$SITE_NS" rollout restart deploy/site-logto deploy/site-gate || true

echo "== delete Logto =="
"${K[@]}" -n identity delete ingressroute.traefik.io logto --ignore-not-found
"${K[@]}" -n identity delete ingressroute.traefik.io logto-client-noorddriveautos --ignore-not-found
"${K[@]}" -n identity delete pdb logto --ignore-not-found
"${K[@]}" -n identity delete deploy logto logto-postgres --ignore-not-found
"${K[@]}" -n identity delete svc logto logto-postgres --ignore-not-found
"${K[@]}" -n identity delete pvc logto-postgres --ignore-not-found
"${K[@]}" -n identity delete cm logto-postgres-init --ignore-not-found
"${K[@]}" -n cronnecture-system delete secret logto-m2m --ignore-not-found

echo "== apply identity ingress =="
"${K[@]}" apply -f /home/dev/stack/kubernetes/identity-ingress.yaml

echo "== bind portal group onto portal/site apps =="
AK=$("${K[@]}" -n identity get svc authentik -o jsonpath='{.spec.clusterIP}')
python3 - <<PY
import json, os, urllib.request
AK=os.environ.get("AK_IP","$AK")
TOKEN=open("$API_TOKEN_FILE").read().strip()
BASE=f"http://{AK}:9000"
def api(method, path, body=None):
    req=urllib.request.Request(BASE+path, data=None if body is None else json.dumps(body).encode(), method=method, headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json","Accept":"application/json","User-Agent":"cronnecture-authentik-bootstrap/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw=r.read(); return json.loads(raw) if raw else {}
    except Exception as exc:
        print("skip", path, exc); return {}
apps=api("GET","/api/v3/core/applications/?superuser_full_list=true&page_size=50").get("results") or []
groups=api("GET","/api/v3/core/groups/?page_size=50").get("results") or []
portal_g=next(g for g in groups if g.get("name")=="cronnecture-portal-noorddriveautos")
ops_g=next(g for g in groups if g.get("name")=="cronnecture-ops")
wanted={
    "cronnecture-client-portal": [portal_g["pk"]],
    "noorddriveautos-site": [ops_g["pk"], portal_g["pk"]],
    "cloudflare-access": [ops_g["pk"]],
}
for app in apps:
    slug=app.get("slug")
    if slug not in wanted: continue
    target=app["pk"]
    existing=api("GET", f"/api/v3/policies/bindings/?target={target}").get("results") or []
    for gpk in wanted[slug]:
        if any(row.get("group")==gpk for row in existing):
            print("group already bound", slug, gpk); continue
        api("POST","/api/v3/policies/bindings/", {"group": gpk, "target": target, "order": 0, "enabled": True, "timeout": 30, "failure_result": False})
        print("bound group", slug, gpk)
PY

echo "== done cluster mutations =="
