#!/usr/bin/env python3
"""Convert HTTP NodePorts to ClusterIP in live k3s addon manifests.

Keeps mail hostPorts and fleet-registry NodePort 30500 (cluster-internal).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

MANIFESTS = Path("/var/lib/rancher/k3s/server/manifests")


def rewrite_identity(text: str) -> str:
    text = text.replace("  type: NodePort\n", "  type: ClusterIP\n")
    text = re.sub(r"\n      nodePort: 3011[0-6]", "", text)
    text = text.replace(
        "    - {}  # NodePort + in-cluster; perimeter is Cloudflare + UFW",
        "    - {}  # ClusterIP; HTTP via Traefik + Cloudflare tunnel; UFW is WAN perimeter",
    )
    return text


def rewrite_control_plane(text: str) -> str:
    text = re.sub(
        r"(metadata:\n  name: control-plane\n  namespace: platform\nspec:\n  type: )NodePort",
        r"\1ClusterIP",
        text,
    )
    text = re.sub(r"(\n    - port: 8080\n      targetPort: 8080)\n      nodePort: 30080", r"\1", text)
    return text


def rewrite_traefik_monitoring(text: str) -> str:
    if "type: ClusterIP" in text:
        return text
    if "service:" in text:
        return text
    return text.replace(
        "    metrics:\n      prometheus:\n        addRoutersLabels: true\n        addServicesLabels: true\n",
        "    metrics:\n      prometheus:\n        addRoutersLabels: true\n        addServicesLabels: true\n    service:\n      type: ClusterIP\n      spec:\n        clusterIP: 10.43.125.134\n",
    )


def rewrite_manifests() -> None:
    identity = MANIFESTS / "identity-stack.yaml"
    control = MANIFESTS / "control-plane.yaml"
    traefik = MANIFESTS / "traefik-monitoring-config.yaml"
    for path in (identity, control, traefik):
        if not path.exists():
            raise SystemExit(f"missing {path}")
        bak = path.with_suffix(path.suffix + ".bak.stack")
        if not bak.exists():
            shutil.copy2(path, bak)
            print(f"backed up {path} -> {bak}")

    identity.write_text(rewrite_identity(identity.read_text()))
    print("rewrote identity-stack HTTP services to ClusterIP")
    control.write_text(rewrite_control_plane(control.read_text()))
    print("rewrote platform control-plane service to ClusterIP")
    traefik.write_text(rewrite_traefik_monitoring(traefik.read_text()))
    print("set Traefik service type ClusterIP")


def live_patch() -> None:
    patches = [
        ("identity", "vaultwarden"),
        ("identity", "authentik"),
        ("identity", "passbolt"),
        ("platform", "control-plane"),
        ("cronnecture-system", "agent-core"),
        ("cronnecture-system", "dashboard"),
    ]
    for ns, name in patches:
        r = subprocess.run(
            ["kubectl", "-n", ns, "patch", "svc", name, "-p", '{"spec":{"type":"ClusterIP"}}'],
            capture_output=True,
            text=True,
        )
        print(f"{ns}/{name}: {r.stdout.strip() or r.stderr.strip()}")
    r = subprocess.run(
        ["kubectl", "-n", "kube-system", "patch", "svc", "traefik", "-p", '{"spec":{"type":"ClusterIP"}}'],
        capture_output=True,
        text=True,
    )
    print(f"kube-system/traefik: {r.stdout.strip() or r.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifests", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.manifests and not args.live:
        parser.error("specify --manifests and/or --live")
    if args.manifests:
        rewrite_manifests()
    if args.live:
        live_patch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
