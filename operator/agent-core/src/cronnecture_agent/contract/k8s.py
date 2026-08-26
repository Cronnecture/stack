"""Kubernetes slices in the control-portal shapes. Secret values never leave."""

from __future__ import annotations

import base64
import os
import ssl
import tempfile
from datetime import datetime, timezone
from typing import Any

from .cache import CACHE
from .envelope import health_from_ready

NS_PURPOSE = {
    "platform": "JS APIs + leftover Python",
    "cronnecture-system": "Operator UI + agent-core",
    "mail": "Stalwart",
    "identity": "Authentik / Passbolt / Cerbos",
    "kube-system": "k3s",
    "previews": "Demo sites",
    "cronnecture-intelligence": "Overlay (heal/scale off)",
    "cert-manager": "Certificates",
    "default": "Unused",
}

PIN = {
    "platform": "cp-master-01",
    "cronnecture-system": "cp-master-01",
    "mail": "cp-master-01",
    "identity": "pool=general",
    "previews": "pool=general",
}


def _age(ts) -> str:
    if not ts:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _purpose(name: str) -> str:
    if name.startswith("client-"):
        return f"Tenant {name[7:]}"
    return NS_PURPOSE.get(name, "Workload")


def _ns_health(pods: int, running: int, deployments_ready: bool) -> str:
    if pods == 0:
        return "idle"
    if running == pods and deployments_ready:
        return "healthy"
    if running == 0:
        return "down"
    return "degraded"


def _pod_ready(pod) -> bool:
    conds = pod.status.conditions or []
    return any(c.type == "Ready" and c.status == "True" for c in conds)


def _restarts(pod) -> int:
    total = 0
    for st in pod.status.container_statuses or []:
        total += int(st.restart_count or 0)
    return total


def _expiry_health(expires: str) -> str:
    if not expires:
        return "idle"
    raw = expires.replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        try:
            ts = datetime.strptime(expires[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return "idle"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    days = (ts - datetime.now(timezone.utc)).days
    if days < 0:
        return "down"
    if days < 21:
        return "degraded"
    return "healthy"


def _issuer_label(raw: str) -> str:
    name = (raw or "").strip()
    lower = name.lower()
    if "google" in lower or lower == "google_trust_services":
        return "Google Trust Services"
    if "letsencrypt" in lower or "let's encrypt" in lower or "lets-encrypt" in lower:
        return "Let's Encrypt"
    if "digicert" in lower:
        return "DigiCert"
    return name or "unknown"


def _tls_secret_meta(b64_crt: str) -> tuple[str, str, str]:
    """Return (host, expires_iso_date, issuer) from a TLS secret. Never returns the cert."""
    if not b64_crt:
        return "", "", ""
    pem: bytes
    if isinstance(b64_crt, bytes):
        raw = b64_crt
    else:
        raw = b64_crt.encode() if "BEGIN CERTIFICATE" in b64_crt else b""
        if not raw:
            try:
                raw = base64.b64decode(b64_crt)
            except Exception:
                return "", "", ""
    pem = raw
    if b"BEGIN CERTIFICATE" not in pem:
        try:
            pem = ssl.DER_cert_to_PEM_cert(raw).encode()
        except Exception:
            return "", "", ""
    path = ""
    try:
        fd, path = tempfile.mkstemp(suffix=".pem")
        os.write(fd, pem)
        os.close(fd)
        info = ssl._ssl._test_decode_cert(path)  # noqa: SLF001 — metadata only
    except Exception:
        return "", "", ""
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    host = ""
    for san in info.get("subjectAltName") or ():
        if san and san[0] == "DNS":
            host = san[1]
            break
    if not host:
        for part in info.get("subject") or ():
            for key, val in part:
                if key == "commonName":
                    host = val
                    break
    not_after = info.get("notAfter") or ""
    expires = ""
    if not_after:
        try:
            ts = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            expires = ts.date().isoformat()
        except ValueError:
            expires = not_after[:10]
    issuer = ""
    for part in info.get("issuer") or ():
        for key, val in part:
            if key == "organizationName":
                issuer = val
            elif key == "commonName" and not issuer:
                issuer = val
    return host, expires, _issuer_label(issuer)


def _cpu_cores(raw: str) -> float:
    value = (raw or "0").strip().lower()
    if value.endswith("m"):
        return float(value[:-1] or 0) / 1000.0
    if value.endswith("n"):
        return float(value[:-1] or 0) / 1_000_000_000.0
    return float(value or 0)


def _mem_gi(raw: str) -> float:
    value = (raw or "0").strip()
    if not value:
        return 0.0
    num = "".join(ch for ch in value if ch.isdigit() or ch == ".")
    amount = float(num or 0)
    lower = value.lower()
    if lower.endswith("ki"):
        return amount / (1024 * 1024)
    if lower.endswith(("mi", "m")):
        return amount / 1024
    if lower.endswith(("gi", "g")):
        return amount
    if lower.endswith("ti"):
        return amount * 1024
    return amount / (1024 ** 3)


_CERT_PROBE_TTL = 300.0
_cert_probe_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])


def probe_tls_hosts(hosts: list[str], timeout: float = 2.0) -> list[dict[str, Any]]:
    """Public TLS metadata for edge hosts. Never returns private keys."""
    global _cert_probe_cache
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    now = time.monotonic()
    cached_at, cached = _cert_probe_cache
    if cached and now - cached_at < _CERT_PROBE_TTL:
        return cached
    unique = []
    seen: set[str] = set()
    for host in hosts:
        h = (host or "").strip().lower()
        if not h or h in seen:
            continue
        seen.add(h)
        unique.append(h)

    def _one(host: str) -> dict[str, Any] | None:
        try:
            pem = ssl.get_server_certificate((host, 443), timeout=timeout)
        except Exception:
            return None
        name, expires, issuer = _tls_secret_meta(pem)
        host_out = name or host
        return {
            "host": host_out if host_out == host or host_out.startswith("*.") else host,
            "expires": expires,
            "issuer": issuer,
            "status": _expiry_health(expires),
        }

    out: list[dict[str, Any]] = []
    if unique:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(_one, h): h for h in unique}
            by_host: dict[str, dict[str, Any]] = {}
            for fut in as_completed(futs):
                row = fut.result()
                if not row:
                    continue
                by_host[futs[fut]] = {**row, "host": futs[fut]}
            out = [by_host[h] for h in unique if h in by_host]
    _cert_probe_cache = (now, out)
    return out


def _workload_name(pod) -> str:
    owners = pod.metadata.owner_references or []
    if owners:
        return owners[0].name
    return pod.metadata.labels.get("app") or pod.metadata.name


def _psa(ns) -> str:
    labels = ns.metadata.labels or {}
    return labels.get("pod-security.kubernetes.io/enforce") or "baseline"


def _quota_text(quota) -> str | None:
    if not quota:
        return None
    hard = quota.status.hard or quota.spec.hard or {}
    used = quota.status.used or {}
    cpu = hard.get("limits.cpu") or hard.get("cpu")
    mem = hard.get("limits.memory") or hard.get("memory")
    pods = hard.get("pods")
    parts = []
    if cpu:
        parts.append(f"{used.get('limits.cpu') or used.get('cpu') or '0'}/{cpu} CPU")
    if mem:
        parts.append(f"{used.get('limits.memory') or used.get('memory') or '0'}/{mem}")
    if pods:
        parts.append(f"{used.get('pods') or '0'}/{pods} pods")
    return " · ".join(parts) if parts else None


class K8sContract:
    def __init__(self, infra):
        self.infra = infra

    def _ok(self) -> bool:
        return bool(self.infra and self.infra.core)

    def node_resources(self) -> dict[str, dict[str, Any]]:
        """CPU/memory usage from metrics-server + node capacity. Empty if metrics are off."""
        hit = CACHE.get("k8s.node_resources")
        if hit is not None:
            return hit
        out: dict[str, dict[str, Any]] = {}
        if not self._ok():
            return out
        usage: dict[str, dict[str, str]] = {}
        if self.infra.custom:
            try:
                obj = self.infra.custom.list_cluster_custom_object(
                    "metrics.k8s.io", "v1beta1", "nodes"
                )
                for item in obj.get("items") or []:
                    name = (item.get("metadata") or {}).get("name") or ""
                    if name:
                        usage[name] = item.get("usage") or {}
            except Exception:
                usage = {}
        for node in self.infra.core.list_node().items:
            name = node.metadata.name
            cap = node.status.capacity or {}
            used = usage.get(name) or {}
            cores = _cpu_cores(str(cap.get("cpu") or "0"))
            used_cores = _cpu_cores(str(used.get("cpu") or "0"))
            total_gi = _mem_gi(str(cap.get("memory") or "0"))
            used_gi = _mem_gi(str(used.get("memory") or "0"))
            out[name] = {
                "cpu": {"used": (used_cores / cores) if cores else 0.0, "cores": round(cores)},
                "memory": {"usedGi": round(used_gi, 1), "totalGi": round(total_gi)},
            }
        return CACHE.set("k8s.node_resources", out, 15.0)

    def nodes_brief(self) -> list[dict[str, Any]]:
        """Ready/IP/role/pod counts without listing pods per namespace."""
        hit = CACHE.get("k8s.nodes_brief")
        if hit is not None:
            return hit
        if not self._ok():
            return []
        pod_counts: dict[str, int] = {}
        try:
            for pod in self.infra.core.list_pod_for_all_namespaces().items:
                node = pod.spec.node_name or ""
                if node:
                    pod_counts[node] = pod_counts.get(node, 0) + 1
        except Exception:
            pass
        out: list[dict[str, Any]] = []
        for node in self.infra.core.list_node().items:
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
            name = node.metadata.name
            out.append(
                {
                    "name": name,
                    "ip": ipv4 or addresses.get("InternalIP", ""),
                    "role": "control" if "control-plane" in roles or "master" in roles else "compute",
                    "status": "ready" if ready else "not-ready",
                    "pods": pod_counts.get(name, 0),
                    "k3s": (node.status.node_info.kubelet_version if node.status.node_info else "") or "",
                }
            )
        return CACHE.set("k8s.nodes_brief", out, 15.0)

    def namespaces(self) -> list[dict[str, Any]]:
        if not self._ok():
            return []
        hit = CACHE.get("k8s.namespaces")
        if hit is not None:
            return hit
        core, apps = self.infra.core, self.infra.apps
        quotas = {}
        try:
            for q in core.list_resource_quota_for_all_namespaces().items:
                quotas[q.metadata.namespace] = q
        except Exception:
            pass
        net_by_ns: dict[str, int] = {}
        try:
            from kubernetes import client

            net = client.NetworkingV1Api()
            for np in net.list_network_policy_for_all_namespaces().items:
                net_by_ns[np.metadata.namespace] = net_by_ns.get(np.metadata.namespace, 0) + 1
        except Exception:
            pass
        pods_by_ns: dict[str, int] = {}
        running_by_ns: dict[str, int] = {}
        try:
            for p in core.list_pod_for_all_namespaces().items:
                ns = p.metadata.namespace
                pods_by_ns[ns] = pods_by_ns.get(ns, 0) + 1
                if (p.status.phase or "") == "Running":
                    running_by_ns[ns] = running_by_ns.get(ns, 0) + 1
        except Exception:
            pass
        deps_by_ns: dict[str, int] = {}
        dep_ready_by_ns: dict[str, bool] = {}
        try:
            for d in apps.list_deployment_for_all_namespaces().items:
                ns = d.metadata.namespace
                deps_by_ns[ns] = deps_by_ns.get(ns, 0) + 1
                desired = d.spec.replicas or 0
                ready = d.status.ready_replicas or 0
                if desired and ready < desired:
                    dep_ready_by_ns[ns] = False
                elif ns not in dep_ready_by_ns:
                    dep_ready_by_ns[ns] = True
        except Exception:
            pass
        items = []
        for ns in core.list_namespace().items:
            name = ns.metadata.name
            pods = pods_by_ns.get(name, 0)
            running = running_by_ns.get(name, 0)
            deps = deps_by_ns.get(name, 0)
            network = "deny-all"
            if net_by_ns.get(name):
                network = "allow-same"
            elif name in ("kube-system", "kube-public"):
                network = "open"
            items.append(
                {
                    "name": name,
                    "purpose": _purpose(name),
                    "health": _ns_health(pods, running, dep_ready_by_ns.get(name, True)),
                    "pods": pods,
                    "deployments": deps,
                    "deployed": deps > 0 or pods > 0,
                    "quota": _quota_text(quotas.get(name)),
                    "psa": _psa(ns) if _psa(ns) in ("restricted", "baseline", "privileged") else "baseline",
                    "network": network,
                    "note": PIN.get(name, ""),
                }
            )
        return CACHE.set("k8s.namespaces", items, 15.0)

    def workloads(self) -> list[dict[str, Any]]:
        if not self._ok():
            return []
        hit = CACHE.get("k8s.workloads")
        if hit is not None:
            return hit
        apps = self.infra.apps
        out = []
        for dep in apps.list_deployment_for_all_namespaces().items:
            desired = dep.spec.replicas or 0
            ready = dep.status.ready_replicas or 0
            image = ""
            if dep.spec.template.spec.containers:
                image = dep.spec.template.spec.containers[0].image or ""
            ns = dep.metadata.namespace
            out.append(
                {
                    "name": dep.metadata.name,
                    "namespace": ns,
                    "kind": "Deployment",
                    "replicas": {"ready": ready, "desired": desired},
                    "pin": PIN.get(ns, ""),
                    "health": health_from_ready(ready >= desired and desired > 0, desired > 0),
                    "image": image,
                    "notes": "",
                }
            )
        try:
            for sts in apps.list_stateful_set_for_all_namespaces().items:
                desired = sts.spec.replicas or 0
                ready = sts.status.ready_replicas or 0
                image = ""
                if sts.spec.template.spec.containers:
                    image = sts.spec.template.spec.containers[0].image or ""
                out.append(
                    {
                        "name": sts.metadata.name,
                        "namespace": sts.metadata.namespace,
                        "kind": "StatefulSet",
                        "replicas": {"ready": ready, "desired": desired},
                        "pin": PIN.get(sts.metadata.namespace, ""),
                        "health": health_from_ready(ready >= desired and desired > 0, desired > 0),
                        "image": image,
                    }
                )
        except Exception:
            pass
        return CACHE.set("k8s.workloads", out, 15.0)

    def pods(self) -> list[dict[str, Any]]:
        if not self._ok():
            return []
        hit = CACHE.get("k8s.pods")
        if hit is not None:
            return hit
        out = []
        for pod in self.infra.core.list_pod_for_all_namespaces().items:
            phase = pod.status.phase or "Pending"
            if phase not in ("Running", "Pending", "Failed", "Succeeded"):
                phase = "Pending"
            out.append(
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "workload": _workload_name(pod),
                    "node": pod.spec.node_name or "",
                    "phase": phase,
                    "ready": _pod_ready(pod),
                    "restarts": _restarts(pod),
                    "age": _age(pod.metadata.creation_timestamp),
                }
            )
        return CACHE.set("k8s.pods", out, 10.0)

    def events(self) -> list[dict[str, Any]]:
        if not self._ok():
            return []
        hit = CACHE.get("k8s.events")
        if hit is not None:
            return hit
        out = []
        try:
            for ev in self.infra.core.list_event_for_all_namespaces().items:
                obj = ev.involved_object
                kind = (obj.kind or "") if obj else ""
                name = (obj.name or "") if obj else ""
                ns = (obj.namespace or ev.metadata.namespace or "") if obj else ""
                etype = ev.type or "Normal"
                if etype not in ("Normal", "Warning"):
                    etype = "Warning" if etype.lower() != "normal" else "Normal"
                out.append(
                    {
                        "type": etype,
                        "object": f"{kind}/{name}".strip("/") + (f".{ns}" if ns else ""),
                        "reason": ev.reason or "",
                        "age": _age(ev.last_timestamp or ev.metadata.creation_timestamp),
                    }
                )
        except Exception:
            return []
        return CACHE.set("k8s.events", out[:200], 15.0)

    def secrets(self) -> list[dict[str, Any]]:
        if not self._ok():
            return []
        out = []
        for sec in self.infra.core.list_secret_for_all_namespaces().items:
            kind = sec.type or "Opaque"
            if kind not in (
                "Opaque",
                "kubernetes.io/tls",
                "kubernetes.io/dockerconfigjson",
            ):
                kind = "Opaque"
            keys = len((sec.data or {}) | (sec.string_data or {}))
            out.append(
                {
                    "name": sec.metadata.name,
                    "namespace": sec.metadata.namespace,
                    "kind": kind,
                    "keys": keys,
                    "age": _age(sec.metadata.creation_timestamp),
                }
            )
        return out

    def netpols(self) -> list[dict[str, Any]]:
        if not self._ok():
            return []
        try:
            from kubernetes import client

            net = client.NetworkingV1Api()
            items = net.list_network_policy_for_all_namespaces().items
        except Exception:
            return []
        out = []
        for np in items:
            spec = np.spec or None
            if spec is None:
                continue
            ingress = "deny"
            if spec.ingress:
                peers = []
                for r in spec.ingress:
                    peers.extend(getattr(r, "from_", None) or getattr(r, "_from", None) or [])
                ingress = "allow-listed" if peers else "allow-same"
            egress = "deny"
            if spec.egress:
                egress = "dns-only"
                for rule in spec.egress:
                    ports = rule.ports or []
                    if any(getattr(p, "port", None) not in (53, "53", None) for p in ports) or not ports:
                        if getattr(rule, "to", None):
                            egress = "allow-listed"
            out.append(
                {
                    "name": np.metadata.name,
                    "namespace": np.metadata.namespace,
                    "ingress": ingress,
                    "egress": egress,
                }
            )
        return out

    def certificates(self) -> list[dict[str, Any]]:
        if not self._ok():
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        if self.infra.custom:
            try:
                obj = self.infra.custom.list_custom_object_for_all_namespaces(
                    "cert-manager.io", "v1", "certificates"
                )
            except Exception:
                obj = {}
            for item in obj.get("items") or []:
                spec = item.get("spec") or {}
                status = item.get("status") or {}
                hosts = list(spec.get("dnsNames") or [])
                cn = spec.get("commonName")
                if cn and cn not in hosts:
                    hosts.insert(0, cn)
                not_after = (status.get("notAfter") or "")[:10]
                issuer_ref = spec.get("issuerRef") or {}
                issuer = _issuer_label(str(issuer_ref.get("name") or ""))
                ready = False
                for cond in status.get("conditions") or []:
                    if cond.get("type") == "Ready" and cond.get("status") == "True":
                        ready = True
                health = _expiry_health(status.get("notAfter") or "")
                if not ready and health == "healthy":
                    health = "degraded"
                for host in hosts or [item.get("metadata", {}).get("name") or ""]:
                    if not host or host in seen:
                        continue
                    seen.add(host)
                    out.append(
                        {
                            "host": host,
                            "expires": not_after,
                            "issuer": issuer,
                            "status": health,
                        }
                    )
        try:
            for sec in self.infra.core.list_secret_for_all_namespaces().items:
                if (sec.type or "") != "kubernetes.io/tls":
                    continue
                name = sec.metadata.name or ""
                if name in ("kube-root-ca.crt",) or name.endswith("-token"):
                    continue
                data = sec.data or {}
                host, expires, issuer = _tls_secret_meta(data.get("tls.crt") or "")
                if not host or host in seen:
                    continue
                if "." not in host or host.endswith((".svc", ".cluster.local", ".local")):
                    continue
                seen.add(host)
                out.append(
                    {
                        "host": host,
                        "expires": expires,
                        "issuer": issuer,
                        "status": _expiry_health(expires),
                    }
                )
        except Exception:
            pass
        return out

    def find_certificate(self, host: str) -> tuple[str, str] | None:
        """Return (name, namespace) for a cert-manager Certificate covering host."""
        if not self._ok() or not self.infra.custom:
            return None
        try:
            obj = self.infra.custom.list_custom_object_for_all_namespaces(
                "cert-manager.io", "v1", "certificates"
            )
        except Exception:
            return None
        want = (host or "").strip().lower()
        for item in obj.get("items") or []:
            spec = item.get("spec") or {}
            names = [str(n).lower() for n in (spec.get("dnsNames") or [])]
            cn = str(spec.get("commonName") or "").lower()
            if want == cn or want in names:
                meta = item.get("metadata") or {}
                return str(meta.get("name") or ""), str(meta.get("namespace") or "")
        return None

    def renew_certificate(self, host: str) -> dict[str, Any]:
        found = self.find_certificate(host)
        if not found or not self.infra.custom:
            raise RuntimeError(f"no cert-manager Certificate for {host}")
        name, ns = found
        self.infra.custom.patch_namespaced_custom_object(
            "cert-manager.io",
            "v1",
            ns,
            "certificates",
            name,
            {"metadata": {"annotations": {"cert-manager.io/renew-now": datetime.now(timezone.utc).isoformat()}}},
        )
        return {"renewed": name, "namespace": ns, "host": host}

    def routes(self) -> list[dict[str, Any]]:
        if not self.infra or not self.infra.custom:
            return []
        hit = CACHE.get("k8s.routes")
        if hit is not None:
            return hit
        try:
            obj = self.infra.custom.list_custom_object_for_all_namespaces(
                "traefik.io", "v1alpha1", "ingressroutes"
            )
        except Exception:
            return []
        out = []
        for item in obj.get("items") or []:
            meta = item.get("metadata") or {}
            spec = item.get("spec") or {}
            ns = meta.get("namespace") or ""
            for route in spec.get("routes") or []:
                match = route.get("match") or ""
                host = ""
                if "Host(`" in match:
                    host = match.split("Host(`", 1)[-1].split("`)", 1)[0]
                svcs = route.get("services") or []
                backend = ""
                if svcs:
                    backend = f"{svcs[0].get('name')}:{svcs[0].get('port')}"
                via = "client-tunnel" if ns.startswith("client-") else "node-tunnel"
                access = "public"
                if ns.startswith("client-"):
                    access = "public"
                elif host.startswith(("control.", "ops.", "stack.", "id-admin.", "auth.", "vault.", "passbolt.")):
                    access = "access"
                elif host.startswith("client."):
                    access = "skip-access"
                if host:
                    out.append(
                        {
                            "host": host,
                            "namespace": ns,
                            "backend": backend,
                            "via": via,
                            "access": access,
                        }
                    )
        return CACHE.set("k8s.routes", out, 30.0)
