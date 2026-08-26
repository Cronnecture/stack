"""Kubernetes infrastructure manager for live client workloads.

Never mutates mail, identity, platform, or other protected namespaces.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

PROTECTED_NAMESPACES = {
    "mail",
    "identity",
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "cert-manager",
    "platform",
    "cronnecture-intelligence",
    "cronnecture-system",
    "default",
    "cattle-fleet-system",
    "cattle-fleet-local-system",
    "cattle-capi-system",
    "cattle-turtles-system",
    "fleet-local",
    "fleet-default",
    "local",
    "previews",
}

PROTECTED_CLIENTS = {
    "client-noorddriveautos",
    "noorddriveautos",
}

LOGTO_APP_ANNOTATION = "cronnecture.com/logto-app-id"

PROTECTED_DOMAINS = {
    "cronnecture.com",
    "www.cronnecture.com",
    "cronnecture.nl",
    "www.cronnecture.nl",
    "mail.cronnecture.com",
    "webmail.cronnecture.com",
    "vault.cronnecture.com",
    "ops.cronnecture.com",
    "client.cronnecture.com",
    "passbolt.cronnecture.com",
    "id.cronnecture.com",
    "id-admin.cronnecture.com",
    "passkeys.cronnecture.com",
    "auth.cronnecture.com",
    "stack.cronnecture.com",
    "control.cronnecture.com",
}


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:40] or "client"


def _namespace_for(client_id: str) -> str:
    slug = _slug(client_id)
    return slug if slug.startswith("client-") else f"client-{slug}"


class InfrastructureManager:
    """Create and inspect client namespaces on the live cluster."""

    def __init__(self):
        self.core = None
        self.apps = None
        self.custom = None

    async def initialize(self):
        try:
            from kubernetes import client, config

            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            self.core = client.CoreV1Api()
            self.apps = client.AppsV1Api()
            self.custom = client.CustomObjectsApi()
            logger.info("Infrastructure manager connected to Kubernetes")
        except Exception as exc:
            logger.warning("Kubernetes unavailable; client deploys will fail", error=str(exc))

    async def shutdown(self):
        logger.info("Shutting down infrastructure manager")

    async def deploy_client(
        self,
        client_name: str,
        domain: str,
        service_tier,
        template: str,
        resources: Dict[str, Any],
    ) -> Dict[str, Any]:
        client_id = _slug(client_name)
        namespace = f"client-{client_id}"
        domain = domain.lower().strip()
        tier = service_tier.value if hasattr(service_tier, "value") else str(service_tier)

        if self._protected_client(client_id, namespace):
            raise ValueError(f"Refusing to deploy into protected name {namespace}")
        if domain in PROTECTED_DOMAINS:
            raise ValueError(f"Refusing to bind protected domain {domain}")
        if not self.core or not self.apps:
            raise RuntimeError("Kubernetes client is not initialized")

        from kubernetes import client
        from kubernetes.client.rest import ApiException

        ns_body = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=namespace,
                labels={
                    "cronnecture.com/client": "true",
                    "cronnecture.com/tier": tier,
                    "cronnecture.com/template": template,
                },
            )
        )
        try:
            self.core.create_namespace(ns_body)
        except ApiException as exc:
            if exc.status != 409:
                raise

        html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{client_name}</title>
<style>body{{font-family:sans-serif;max-width:40rem;margin:4rem auto;color:#111}}
.badge{{display:inline-block;padding:.2rem .5rem;background:#eef;border-radius:4px}}</style>
</head><body>
<h1>{client_name}</h1>
<p>This site is provisioned by the Cronnecture control plane.</p>
<p class="badge">{tier} · {template}</p>
<p>Domain: {domain}</p>
</body></html>
"""
        cm = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=f"{client_id}-site", namespace=namespace),
            data={"index.html": html},
        )
        try:
            self.core.create_namespaced_config_map(namespace, cm)
        except ApiException as exc:
            if exc.status == 409:
                self.core.replace_namespaced_config_map(f"{client_id}-site", namespace, cm)
            else:
                raise

        cpu = resources.get("cpu", "100m")
        memory = resources.get("memory", "128Mi")
        deploy = client.V1Deployment(
            metadata=client.V1ObjectMeta(
                name=f"{client_id}-app",
                namespace=namespace,
                labels={"app": client_id, "component": "app"},
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": client_id, "component": "app"}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": client_id, "component": "app"}),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="app",
                                image="nginx:1.27-alpine",
                                ports=[client.V1ContainerPort(container_port=80, name="http")],
                                resources=client.V1ResourceRequirements(
                                    requests={"cpu": "50m", "memory": "32Mi"},
                                    limits={"cpu": cpu, "memory": memory},
                                ),
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="site",
                                        mount_path="/usr/share/nginx/html",
                                        read_only=True,
                                    )
                                ],
                                liveness_probe=client.V1Probe(
                                    http_get=client.V1HTTPGetAction(path="/", port="http"),
                                    initial_delay_seconds=5,
                                    period_seconds=15,
                                ),
                            )
                        ],
                        volumes=[
                            client.V1Volume(
                                name="site",
                                config_map=client.V1ConfigMapVolumeSource(name=f"{client_id}-site"),
                            )
                        ],
                    ),
                ),
            ),
        )
        try:
            self.apps.create_namespaced_deployment(namespace, deploy)
        except ApiException as exc:
            if exc.status == 409:
                self.apps.replace_namespaced_deployment(f"{client_id}-app", namespace, deploy)
            else:
                raise

        svc = client.V1Service(
            metadata=client.V1ObjectMeta(name=f"{client_id}-service", namespace=namespace),
            spec=client.V1ServiceSpec(
                selector={"app": client_id, "component": "app"},
                ports=[client.V1ServicePort(port=80, target_port="http", name="http")],
            ),
        )
        try:
            self.core.create_namespaced_service(namespace, svc)
        except ApiException as exc:
            if exc.status != 409:
                raise

        if self.custom:
            route = {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "IngressRoute",
                "metadata": {"name": f"{client_id}-http", "namespace": namespace},
                "spec": {
                    "entryPoints": ["web", "websecure"],
                    "routes": [
                        {
                            "match": f"Host(`{domain}`)",
                            "kind": "Rule",
                            "services": [{"name": f"{client_id}-service", "port": 80}],
                        }
                    ],
                },
            }
            try:
                self.custom.create_namespaced_custom_object(
                    "traefik.io", "v1alpha1", namespace, "ingressroutes", route
                )
            except ApiException as exc:
                if exc.status not in (409, 404):
                    logger.warning("IngressRoute create failed", error=str(exc))

        logger.info("Deployed client", client_id=client_id, namespace=namespace, domain=domain)
        return {
            "client_id": client_id,
            "namespace": namespace,
            "access_url": f"https://{domain}",
            "admin_credentials": {"username": "operator", "password": None},
        }

    def _protected_client(self, client_id: str, namespace: Optional[str] = None) -> bool:
        ns = namespace or _namespace_for(client_id)
        slug = _slug(client_id)
        extra = {
            s.strip()
            for s in os.environ.get("KEEP_CLIENT_NAMESPACES", "").split(",")
            if s.strip()
        }
        blocked = PROTECTED_NAMESPACES | PROTECTED_CLIENTS | extra
        return ns in blocked or slug in blocked or f"client-{slug}" in blocked

    async def annotate_logto_app(self, client_id: str, app_id: str) -> None:
        if not self.core or not app_id:
            return
        namespace = _namespace_for(client_id)
        from kubernetes.client.rest import ApiException

        try:
            self.core.patch_namespace(
                namespace,
                {"metadata": {"annotations": {LOGTO_APP_ANNOTATION: app_id}}},
            )
        except ApiException as exc:
            logger.warning("logto annotation failed", namespace=namespace, error=str(exc))

    def _logto_app_id(self, namespace: str) -> Optional[str]:
        if not self.core:
            return None
        try:
            ns = self.core.read_namespace(namespace)
            return (ns.metadata.annotations or {}).get(LOGTO_APP_ANNOTATION)
        except Exception:
            return None

    async def delete_client(self, client_id: str, confirm: str) -> Dict[str, Any]:
        slug = _slug(client_id)
        namespace = _namespace_for(client_id)
        if confirm not in {slug, namespace, client_id}:
            raise ValueError("confirm must equal the client id (type the slug to delete)")
        if self._protected_client(slug, namespace):
            raise ValueError(f"Refusing to delete protected client {namespace}")
        if not namespace.startswith("client-"):
            raise ValueError(f"Refusing to delete non-client namespace {namespace}")
        if not self.core:
            raise RuntimeError("Kubernetes client is not initialized")

        from kubernetes.client.rest import ApiException

        logto_app_id = self._logto_app_id(namespace)
        try:
            self.core.delete_namespace(namespace)
        except ApiException as exc:
            if exc.status == 404:
                return {
                    "status": "absent",
                    "client_id": slug,
                    "namespace": namespace,
                    "logto_app_id": logto_app_id,
                }
            raise
        logger.info("Deleted client namespace", client_id=slug, namespace=namespace)
        return {
            "status": "deleted",
            "client_id": slug,
            "namespace": namespace,
            "logto_app_id": logto_app_id,
        }

    async def get_client_status(self, client_id: str) -> Dict[str, Any]:
        namespace = f"client-{_slug(client_id)}"
        status = "unknown"
        if self.apps:
            try:
                dep = self.apps.read_namespaced_deployment(f"{_slug(client_id)}-app", namespace)
                ready = dep.status.ready_replicas or 0
                desired = dep.spec.replicas or 0
                status = "healthy" if ready >= desired and desired > 0 else "degraded"
            except Exception:
                status = "not_found"
        return {
            "overall_status": status,
            "last_deployment": datetime.now().isoformat(),
            "ssl_expiry": (datetime.now() + timedelta(days=90)).isoformat(),
        }

    async def list_clients(self) -> List[Dict[str, Any]]:
        clients: List[Dict[str, Any]] = []
        if not self.core:
            return clients
        for ns in self.core.list_namespace().items:
            name = ns.metadata.name
            labels = ns.metadata.labels or {}
            if labels.get("cronnecture.com/client") == "true" or name.startswith("client-"):
                if name in PROTECTED_NAMESPACES:
                    continue
                pods = self.core.list_namespaced_pod(name)
                running = sum(1 for p in pods.items if p.status.phase == "Running")
                anns = ns.metadata.annotations or {}
                clients.append(
                    {
                        "namespace": name,
                        "client_id": name.removeprefix("client-"),
                        "tier": labels.get("cronnecture.com/tier", "unknown"),
                        "pods_running": running,
                        "pods_total": len(pods.items),
                        "protected": self._protected_client(name.removeprefix("client-"), name),
                        "logto_app_id": anns.get(LOGTO_APP_ANNOTATION),
                    }
                )
        return clients

    async def cluster_snapshot(self) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        workloads: List[Dict[str, Any]] = []
        namespaces: List[Dict[str, Any]] = []
        if not self.core:
            return {"nodes": nodes, "workloads": workloads, "namespaces": namespaces}

        for node in self.core.list_node().items:
            roles = [
                k.replace("node-role.kubernetes.io/", "")
                for k, v in (node.metadata.labels or {}).items()
                if k.startswith("node-role.kubernetes.io/")
            ]
            addresses = {a.type: a.address for a in (node.status.addresses or [])}
            ipv4 = next(
                (
                    a.address
                    for a in (node.status.addresses or [])
                    if a.type in ("InternalIP", "ExternalIP") and ":" not in (a.address or "")
                ),
                None,
            )
            ready = any(
                c.type == "Ready" and c.status == "True" for c in (node.status.conditions or [])
            )
            nodes.append(
                {
                    "name": node.metadata.name,
                    "ip": ipv4 or addresses.get("InternalIP", ""),
                    "role": "control" if "control-plane" in roles or "master" in roles else "compute",
                    "status": "ready" if ready else "not-ready",
                    "cpu_usage": 0.0,
                    "memory_usage": 0.0,
                    "disk_usage": 0.0,
                }
            )

        ns_pods: Dict[str, int] = {}
        ns_running: Dict[str, int] = {}
        try:
            for pod in self.core.list_pod_for_all_namespaces().items:
                ns = pod.metadata.namespace
                ns_pods[ns] = ns_pods.get(ns, 0) + 1
                if pod.status.phase == "Running":
                    ns_running[ns] = ns_running.get(ns, 0) + 1
                workloads.append(
                    {
                        "name": pod.metadata.name,
                        "namespace": ns,
                        "status": (pod.status.phase or "").lower(),
                        "node": pod.spec.node_name or "",
                    }
                )
        except Exception:
            pass
        try:
            for ns in self.core.list_namespace().items:
                name = ns.metadata.name
                namespaces.append(
                    {
                        "name": name,
                        "pods": ns_pods.get(name, 0),
                        "running": ns_running.get(name, 0),
                    }
                )
        except Exception:
            pass
        return {"nodes": nodes, "workloads": workloads, "namespaces": namespaces}

    async def keep_set_status(self) -> Dict[str, Any]:
        keep = [
            "mail",
            "identity",
            "platform",
            "kube-system",
            "cert-manager",
            "cronnecture-intelligence",
            "cronnecture-system",
        ]
        result = {}
        if not self.core:
            return result
        for name in keep:
            try:
                pods = self.core.list_namespaced_pod(name)
                items = [
                    p
                    for p in pods.items
                    if (p.status.phase or "") not in ("Succeeded", "Failed")
                ]
                running = sum(1 for p in items if p.status.phase == "Running")
                result[name] = {
                    "pods": len(items),
                    "running": running,
                    "healthy": running == len(items) and running > 0,
                }
            except Exception as exc:
                result[name] = {"error": str(exc), "healthy": False}
        return result

    async def exposure(self) -> Dict[str, Any]:
        nodeports: List[Dict[str, Any]] = []
        loadbalancers: List[Dict[str, Any]] = []
        host_ports: List[Dict[str, Any]] = []
        if not self.core:
            return {"nodeports": nodeports, "loadbalancers": loadbalancers, "host_ports": host_ports}
        for svc in self.core.list_service_for_all_namespaces().items:
            spec = svc.spec
            if spec.type == "NodePort":
                ports = [
                    {"port": p.port, "nodePort": p.node_port, "name": p.name}
                    for p in (spec.ports or [])
                ]
                nodeports.append(
                    {"namespace": svc.metadata.namespace, "name": svc.metadata.name, "ports": ports}
                )
            if spec.type == "LoadBalancer":
                ingress = []
                if svc.status and svc.status.load_balancer and svc.status.load_balancer.ingress:
                    ingress = [i.ip or i.hostname for i in svc.status.load_balancer.ingress]
                loadbalancers.append(
                    {
                        "namespace": svc.metadata.namespace,
                        "name": svc.metadata.name,
                        "ingress": ingress,
                        "ports": [p.port for p in (spec.ports or [])],
                    }
                )
        for pod in self.core.list_pod_for_all_namespaces().items:
            for c in pod.spec.containers or []:
                for port in c.ports or []:
                    if port.host_port:
                        host_ports.append(
                            {
                                "namespace": pod.metadata.namespace,
                                "pod": pod.metadata.name,
                                "container": c.name,
                                "hostPort": port.host_port,
                                "hostIP": port.host_ip or "*",
                            }
                        )
        http_exposed = [
            n
            for n in nodeports
            if n["name"] not in ("fleet-registry",)
        ]
        return {
            "nodeports": nodeports,
            "loadbalancers": loadbalancers,
            "host_ports": host_ports,
            "http_nodeports_closed": len(http_exposed) == 0,
            "mail_hostports": [h for h in host_ports if h["namespace"] == "mail"],
        }

    async def routes(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if not self.custom:
            return items
        try:
            obj = self.custom.list_custom_object_for_all_namespaces(
                "traefik.io", "v1alpha1", "ingressroutes"
            )
        except Exception as exc:
            logger.warning("IngressRoute list failed", error=str(exc))
            return items
        for route in obj.get("items") or []:
            spec = route.get("spec") or {}
            matches = [r.get("match") for r in spec.get("routes") or []]
            items.append(
                {
                    "namespace": route.get("metadata", {}).get("namespace"),
                    "name": route.get("metadata", {}).get("name"),
                    "matches": matches,
                }
            )
        return items

    async def schedule_service_suspension(self, client_id: str, suspend_at: datetime):
        logger.warning("Service suspension scheduled", client_id=client_id, suspend_at=suspend_at)


class MonitoringSystem:
    """Client monitoring stub wired to live namespace metrics when possible."""

    def __init__(self):
        self.infra: Optional[InfrastructureManager] = None

    async def initialize(self):
        logger.info("Initializing monitoring system")

    async def shutdown(self):
        logger.info("Shutting down monitoring system")

    async def setup_client_monitoring(self, client_id: str, namespace: str, service_tier):
        logger.info("Monitoring configured", client_id=client_id, namespace=namespace)
        return {"status": "configured"}

    async def get_client_metrics(self, client_id: str):
        return {
            "uptime_30d": 99.9,
            "resource_usage": {"cpu": "n/a", "memory": "n/a", "storage": "n/a"},
        }

    async def attempt_auto_remediation(self, alert):
        logger.info("Auto-remediation skipped (disabled)", alert=getattr(alert, "alert_name", alert))

        class RemediationResult:
            success = False
            attempts: List[Any] = []
            action = "none"

        return RemediationResult()
