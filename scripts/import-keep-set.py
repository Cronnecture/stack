#!/usr/bin/env python3
"""Import live mail/identity k3s addons into this stack, without secret values.

Does not modify the cluster. Writes kubernetes/mail.yaml, identity.yaml, identity-cerbos.yaml.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "kubernetes"
MANIFESTS = Path("/var/lib/rancher/k3s/server/manifests")

DROP_ANN = {
    "kubectl.kubernetes.io/last-applied-configuration",
    "objectset.rio.cattle.io/applied",
    "objectset.rio.cattle.io/id",
    "objectset.rio.cattle.io/owner-gvk",
    "objectset.rio.cattle.io/owner-name",
    "objectset.rio.cattle.io/owner-namespace",
}
DROP_LABEL = {"objectset.rio.cattle.io/hash"}
META_DROP = {
    "resourceVersion",
    "uid",
    "generation",
    "creationTimestamp",
    "managedFields",
    "selfLink",
}


def clean(doc: dict) -> dict:
    doc = copy.deepcopy(doc)
    md = doc.get("metadata") or {}
    for k in list(md.keys()):
        if k in META_DROP:
            md.pop(k, None)
    ann = md.get("annotations") or {}
    for k in list(ann.keys()):
        if k in DROP_ANN or k.startswith("kubectl.kubernetes.io/"):
            ann.pop(k, None)
    if ann:
        md["annotations"] = ann
    else:
        md.pop("annotations", None)
    labels = md.get("labels") or {}
    for k in list(labels.keys()):
        if k in DROP_LABEL:
            labels.pop(k, None)
    labels["cronnecture.com/managed-by"] = "stack"
    md["labels"] = labels
    doc["metadata"] = md
    doc.pop("status", None)
    return doc


def load_docs(path: Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def dump_docs(path: Path, docs: list[dict], header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [header.rstrip(), ""]
    for doc in docs:
        parts.append("---")
        parts.append(yaml.safe_dump(doc, sort_keys=False).rstrip())
    path.write_text("\n".join(parts) + "\n")


def main() -> None:
    mail = [clean(d) for d in load_docs(MANIFESTS / "stalwart.yaml")]
    identity = []
    for d in load_docs(MANIFESTS / "identity-stack.yaml"):
        if d.get("kind") == "Secret":
            continue
        identity.append(clean(d))
    cerbos = [clean(d) for d in load_docs(MANIFESTS / "identity-cerbos.yaml")]

    dump_docs(
        OUT / "mail.yaml",
        mail,
        "# Live Stalwart mail. Source of truth for the mail namespace.\n"
        "# PVC stalwart-data is never deleted. hostPorts 25/587 stay.\n",
    )
    dump_docs(
        OUT / "identity.yaml",
        identity,
        "# Live identity stack (Vaultwarden, Authentik, Passbolt, Cerbos).\n"
        "# Secret identity-secrets stays in-cluster only and is never written from git.\n"
        "# PVCs are never deleted.\n",
    )
    dump_docs(
        OUT / "identity-cerbos.yaml",
        cerbos,
        "# Cerbos policies for the identity namespace.\n",
    )
    print("wrote", OUT / "mail.yaml")
    print("wrote", OUT / "identity.yaml", "docs", len(identity), "(secret omitted)")
    print("wrote", OUT / "identity-cerbos.yaml")


if __name__ == "__main__":
    main()
