#!/bin/bash
# Copy Logto Management API credentials from the platform control-plane
# secret into cronnecture-system so the stack can create/delete client apps.
# Never prints secret values.

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG

kubectl -n platform get secret control-plane-cf >/dev/null
kubectl get ns cronnecture-system >/dev/null

python3 - << 'PY'
import json, subprocess

raw = subprocess.check_output(
    ["kubectl", "-n", "platform", "get", "secret", "control-plane-cf", "-o", "json"]
)
data = json.loads(raw)["data"]
keys = [
    "LOGTO_ENDPOINT",
    "LOGTO_INTERNAL_ENDPOINT",
    "LOGTO_MANAGEMENT_ENDPOINT",
    "LOGTO_M2M_APP_ID",
    "LOGTO_M2M_APP_SECRET",
    "LOGTO_M2M_RESOURCE",
]
missing = [k for k in keys if k not in data]
if missing:
    raise SystemExit(f"platform secret missing {missing}")

patch = {"data": {k: data[k] for k in keys}}
subprocess.run(
    [
        "kubectl",
        "-n",
        "cronnecture-system",
        "create",
        "secret",
        "generic",
        "logto-m2m",
        "--dry-run=client",
        "-o",
        "json",
    ],
    check=True,
    stdout=subprocess.DEVNULL,
)
rendered = subprocess.check_output(
    [
        "kubectl",
        "-n",
        "cronnecture-system",
        "create",
        "secret",
        "generic",
        "logto-m2m",
        "--dry-run=client",
        "-o",
        "json",
    ]
)
obj = json.loads(rendered)
obj["data"] = patch["data"]
subprocess.run(
    ["kubectl", "apply", "-f", "-"],
    input=json.dumps(obj).encode(),
    check=True,
    stdout=subprocess.DEVNULL,
)
print("logto-m2m secret applied to cronnecture-system")
PY
