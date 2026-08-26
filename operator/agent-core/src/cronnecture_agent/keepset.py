"""Mail and identity as first-class stack workloads.

Control is limited: status + restart. Never delete PVCs, secrets, or namespaces.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger()

MAIL_DEPLOYMENTS = ["stalwart"]
IDENTITY_DEPLOYMENTS = [
    "vaultwarden",
    "authentik-server",
    "authentik-worker",
    "passbolt",
    "passbolt-db",
    "hanko",
    "identity-redis",
    "cerbos",
]
IDENTITY_STATEFULSETS = ["identity-postgres"]

IDENTITY_APPS = [
    {"name": "Vaultwarden", "deploy": "vaultwarden", "url": "https://vault.cronnecture.com"},
    {"name": "Authentik", "deploy": "authentik-server", "url": "https://auth.cronnecture.com"},
    {"name": "Passbolt", "deploy": "passbolt", "url": "https://passbolt.cronnecture.com"},
    {"name": "Hanko", "deploy": "hanko", "url": "https://passkeys.cronnecture.com"},
    {"name": "Cerbos", "deploy": "cerbos", "url": None},
]


class KeepSetController:
    def __init__(self, infra):
        self.infra = infra

    def _core(self):
        if not self.infra.core or not self.infra.apps:
            raise RuntimeError("Kubernetes client is not initialized")
        return self.infra.core, self.infra.apps

    def _workload(self, apps, namespace: str, name: str) -> Dict[str, Any]:
        try:
            dep = apps.read_namespaced_deployment(name, namespace)
            ready = dep.status.ready_replicas or 0
            desired = dep.spec.replicas or 0
            return {
                "name": name,
                "kind": "Deployment",
                "ready": ready,
                "desired": desired,
                "healthy": ready >= desired and desired > 0,
            }
        except Exception:
            pass
        try:
            sts = apps.read_namespaced_stateful_set(name, namespace)
            ready = sts.status.ready_replicas or 0
            desired = sts.spec.replicas or 0
            return {
                "name": name,
                "kind": "StatefulSet",
                "ready": ready,
                "desired": desired,
                "healthy": ready >= desired and desired > 0,
            }
        except Exception:
            return {"name": name, "kind": "unknown", "ready": 0, "desired": 0, "healthy": False}

    async def describe(self, namespace: str) -> Dict[str, Any]:
        core, apps = self._core()
        names: List[str]
        extra: Dict[str, Any] = {}
        if namespace == "mail":
            names = list(MAIL_DEPLOYMENTS)
            extra["public_ports"] = ["25/tcp", "587/tcp"]
            extra["hostname"] = "mail.cronnecture.com"
        elif namespace == "identity":
            names = list(IDENTITY_DEPLOYMENTS) + list(IDENTITY_STATEFULSETS)
            extra["apps"] = IDENTITY_APPS
            extra["secret"] = "identity-secrets"
        else:
            raise ValueError(f"not a keep-set control namespace: {namespace}")

        pods = core.list_namespaced_pod(namespace)
        pvcs = core.list_namespaced_persistent_volume_claim(namespace)
        secrets = [s.metadata.name for s in core.list_namespaced_secret(namespace).items if s.type == "Opaque"]
        workloads = [self._workload(apps, namespace, n) for n in names]
        extra["pods"] = [
            {
                "name": p.metadata.name,
                "status": (p.status.phase or "").lower(),
                "node": p.spec.node_name or "",
            }
            for p in pods.items
            if (p.status.phase or "") not in ("Succeeded",)
        ]
        extra["pvcs"] = [
            {
                "name": c.metadata.name,
                "phase": (c.status.phase or ""),
                "storage": ((c.spec.resources.requests or {}).get("storage") if c.spec.resources else None),
            }
            for c in pvcs.items
        ]
        extra["workloads"] = workloads
        extra["secrets_present"] = (
            namespace != "identity" or "identity-secrets" in secrets
        )
        extra["healthy"] = all(w["healthy"] for w in workloads) and extra["secrets_present"]
        extra["namespace"] = namespace
        if namespace == "identity":
            extra["authentik_url"] = "https://auth.cronnecture.com"
        return extra

    async def restart(self, namespace: str, name: str) -> Dict[str, Any]:
        allowed = set(MAIL_DEPLOYMENTS) if namespace == "mail" else set(IDENTITY_DEPLOYMENTS) | set(
            IDENTITY_STATEFULSETS
        )
        if name not in allowed:
            raise ValueError(f"{name} is not a controlled {namespace} workload")
        _, apps = self._core()
        stamp = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"cronnecture.com/restartedAt": stamp}
                    }
                }
            }
        }
        if name in IDENTITY_STATEFULSETS and namespace == "identity":
            apps.patch_namespaced_stateful_set(name, namespace, body)
        else:
            apps.patch_namespaced_deployment(name, namespace, body)
        logger.info("restarted keep-set workload", namespace=namespace, name=name)
        return {"status": "restarting", "namespace": namespace, "name": name, "at": stamp}
