#!/bin/bash
# Copy Cloudflare tokens from Ansible vault into cluster secrets.
# Never prints secret values.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../lib/stack_paths.sh
source "$ROOT/lib/stack_paths.sh"
VAULT="${ANSIBLE_VAULT_FILE}"
PASS="${ANSIBLE_VAULT_PASSWORD_FILE}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG

if [[ ! -f "$VAULT" || ! -f "$PASS" ]]; then
  echo "Ansible vault or password file missing; skip Cloudflare secret sync" >&2
  exit 0
fi

python3 - "$VAULT" "$PASS" << 'PY'
import os, subprocess, sys, tempfile

vault, passfile = sys.argv[1], sys.argv[2]
raw = subprocess.check_output(
    ["ansible-vault", "view", vault, "--vault-password-file", passfile],
    text=True,
)
vals = {}
for line in raw.splitlines():
    if ":" not in line or line.strip().startswith("#"):
        continue
    k, _, v = line.partition(":")
    k, v = k.strip(), v.strip().strip('"').strip("'")
    if k.startswith("vault_cf_"):
        vals[k] = v

required = [
    "vault_cf_account_id",
    "vault_cf_zone_id",
    "vault_cf_readonly_token",
    "vault_cf_dns_token",
    "vault_cf_tunnel_token",
]
missing = [k for k in required if not vals.get(k)]
if missing:
    raise SystemExit(f"vault missing {missing}")

env = os.environ.copy()
env.update({
    "CF_ACCOUNT_ID": vals["vault_cf_account_id"],
    "CF_ZONE_ID": vals["vault_cf_zone_id"],
    "CF_READONLY": vals["vault_cf_readonly_token"],
    "CF_DNS": vals["vault_cf_dns_token"],
    "CF_TUNNEL": vals["vault_cf_tunnel_token"],
    "CF_TUNNEL_ID": "c698c546-91d8-44fc-b37a-a28d7f589080",
})

for ns in ("cronnecture-system", "cronnecture-intelligence"):
    subprocess.run(["kubectl", "get", "ns", ns], check=True, stdout=subprocess.DEVNULL)
    cmd = [
        "kubectl", "-n", ns, "create", "secret", "generic", "cloudflare",
        "--from-literal=account_id=" + env["CF_ACCOUNT_ID"],
        "--from-literal=zone_id=" + env["CF_ZONE_ID"],
        "--from-literal=readonly_token=" + env["CF_READONLY"],
        "--from-literal=dns_token=" + env["CF_DNS"],
        "--from-literal=tunnel_token=" + env["CF_TUNNEL"],
        "--from-literal=tunnel_id=" + env["CF_TUNNEL_ID"],
        "--dry-run=client", "-o", "yaml",
    ]
    rendered = subprocess.check_output(cmd, env=env)
    apply = subprocess.run(["kubectl", "apply", "-f", "-"], input=rendered, check=True)
print("Cloudflare secrets applied to cronnecture-system and cronnecture-intelligence")
PY
