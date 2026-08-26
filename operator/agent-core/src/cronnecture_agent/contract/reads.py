"""Assemble control-portal catalog reads from k8s, platform API, and Cloudflare."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any

import asyncio

from .cache import CACHE

from .envelope import health_from_ready, includes, job_status, parse_query, paginate
from .k8s import K8sContract

NODE_GROUPS = (
    "k3s_server",
    "compute_general",
    "compute_cpu",
    "compute_memory",
    "edge_lb",
    "siem",
)

PLAYBOOKS = [
    {"tag": "baseline", "name": "Baseline hardening", "description": "SSH, firewall, cloudflared", "hosts": "all"},
    {"tag": "cluster", "name": "Sync Kubernetes", "description": "k3s server/agents + Traefik", "hosts": "k3s_cluster"},
    {"tag": "cloudflare", "name": "Sync Cloudflare edge", "description": "Tunnels, DNS, Access", "hosts": "localhost"},
    {"tag": "clients", "name": "Sync client tunnels", "description": "Per-client Cloudflare tunnels", "hosts": "localhost"},
    {"tag": "control_plane", "name": "Control plane", "description": "Platform APIs + registry", "hosts": "k3s_server"},
    {"tag": "identity", "name": "Identity keep-set", "description": "Logto, Authentik, Passbolt, Hanko, Cerbos", "hosts": "compute_general"},
    {"tag": "mail", "name": "Mail keep-set", "description": "Stalwart on the control node", "hosts": "k3s_server"},
    {"tag": "stack", "name": "Stack apply", "description": "Operator YAML, tunnels, close NodePorts", "hosts": "k3s_server"},
    {"tag": "fleet_ops", "name": "Fleet ops", "description": "Backup/health cron + ansible-runner", "hosts": "k3s_server"},
]

POLICIES = [
    {"id": "placement", "file": "config/policies/placement.yml", "title": "Placement", "summary": "Node class counts and pool selection"},
    {"id": "cloudflare", "file": "config/policies/cloudflare.yml", "title": "Cloudflare", "summary": "Edge portals, Access, tokens"},
    {"id": "fleet-operations", "file": "config/policies/fleet-operations.yml", "title": "Fleet operations", "summary": "Playbook catalog and runner allowlist"},
    {"id": "api-catalog", "file": "config/policies/api-catalog.yml", "title": "API catalog", "summary": "JS platform API cutover"},
]

GUARDS = [
    {"id": "psa-restricted", "scope": "kubernetes", "title": "PSA restricted", "detail": "New namespaces default to restricted", "enabled": True, "locked": True},
    {"id": "deny-all-netpol", "scope": "kubernetes", "title": "Deny-all NetworkPolicy", "detail": "Client namespaces get deny-all + DNS egress", "enabled": True, "locked": True},
    {"id": "no-latest-tag", "scope": "kubernetes", "title": "No :latest tags", "detail": "Kaniko and apply reject floating tags", "enabled": True, "locked": False},
    {"id": "ansible-check-first", "scope": "ansible", "title": "Ansible check first", "detail": "ansible.run defaults to --check --diff", "enabled": True, "locked": False},
    {"id": "vault-required", "scope": "ansible", "title": "Vault required", "detail": "Playbooks fail closed without vault", "enabled": True, "locked": True},
    {"id": "access-on-admin", "scope": "fleet", "title": "Access on admin hosts", "detail": "control/ops stay behind Cloudflare Access", "enabled": True, "locked": True},
]

API_SURFACES = [
    {"name": "api-edge", "kind": "js", "pin": "cp-master-01", "notes": "Catalog router, owns ClusterIP control-plane"},
    {"name": "api-data", "kind": "js", "pin": "cp-master-01", "notes": "Only process with the database URL"},
    {"name": "api-ops", "kind": "js", "pin": "cp-master-01", "notes": "CRM writes, GitHub/Kaniko, jobs list"},
    {"name": "api-fleet", "kind": "js", "pin": "cp-master-01", "notes": "Inventory + fleet_add_node"},
    {"name": "api-mail", "kind": "js", "pin": "cp-master-01", "notes": "Mailbox/domain list"},
    {"name": "api-auth", "kind": "js", "pin": "cp-master-01", "notes": "Ops session cookie"},
    {"name": "control-plane-legacy", "kind": "python", "pin": "cp-master-01", "notes": "Portal snapshot, Logto, billing GET, delete-client"},
    {"name": "agent-core", "kind": "python", "pin": "cp-master-01", "notes": "This facade — catalog contract for the control portal"},
    {"name": "cronnecture-job-worker", "kind": "host", "pin": "cp-master-01", "notes": "Claims fleet_* jobs"},
    {"name": "cronnecture-ansible-runner", "kind": "host", "pin": "cp-master-01", "notes": ":18765 allowlisted playbooks"},
]


def _group_for(groups: list[str], hostname: str) -> str:
    for g in NODE_GROUPS:
        if g in groups:
            return g
    if "control" in hostname or hostname.startswith("cp-"):
        return "k3s_server"
    return "compute_general"


def _eur(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(str(value).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return 0.0


def _cents(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(value) / 100.0, 2)
    except (TypeError, ValueError):
        return 0.0


def _iso_day(value: Any) -> str:
    raw = str(value or "").strip()
    return raw[:10] if len(raw) >= 10 else ""


def _handshake(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("handshake")
    return data if isinstance(data, dict) else {}


def _mrr_from_client(row: dict[str, Any]) -> float:
    monthly = _handshake(row).get("monthly_eur")
    if monthly not in (None, ""):
        return _eur(monthly)
    if row.get("mrr") not in (None, "", 0, 0.0):
        return _eur(row.get("mrr"))
    plan = str(row.get("billing_plan") or row.get("plan") or "")
    hit = re.search(r"(\d+[.,]\d+)\s*/\s*mo", plan, re.I)
    return _eur(hit.group(1)) if hit else 0.0


def _active_client(row: dict[str, Any]) -> bool:
    status = str(row.get("billing_status") or "").lower()
    if status not in ("active", "ok", "current", "paid"):
        return False
    if row.get("stripe_subscription_id"):
        return True
    if _handshake(row).get("monthly_eur"):
        return True
    return _mrr_from_client(row) > 0


def _invoice_from_billing(inv: dict[str, Any], slug: str) -> dict[str, Any]:
    if inv.get("total") is not None or inv.get("amount_paid") is not None:
        amount = _cents(inv.get("total") if inv.get("total") is not None else inv.get("amount_paid"))
    else:
        amount = _eur(inv.get("amount"))
    st = str(inv.get("status") or "open").lower()
    if st in ("paid", "complete"):
        mapped = "paid"
    elif st in ("upcoming", "draft"):
        mapped = "upcoming"
    else:
        mapped = "open"
    vat_amount = None
    vat_rate = None
    btw_kind = inv.get("btwKind") or inv.get("btw_kind")
    aangifte = inv.get("aangifteVatAmount") or inv.get("aangifte_vat_amount")
    if inv.get("btw_amount") is not None:
        vat_amount = _eur(inv.get("btw_amount"))
        vat_rate = inv.get("btw_rate")
    elif inv.get("vatAmount") is not None:
        vat_amount = _eur(inv.get("vatAmount"))
        vat_rate = inv.get("vatRate")
    elif inv.get("total_excluding_tax") is not None or inv.get("tax") is not None:
        ex = _cents(inv.get("total_excluding_tax")) if inv.get("total_excluding_tax") is not None else None
        tax = _cents(inv.get("tax")) if inv.get("tax") is not None else None
        if tax is None and ex is not None:
            tax = max(0.0, round(amount - ex, 2))
        vat_amount = tax
        if ex and tax and ex > 0:
            pct = round((tax / ex) * 100)
            vat_rate = 21 if abs(pct - 21) <= 2 else 9 if abs(pct - 9) <= 2 else 0 if tax == 0 else None
    reverse = bool(inv.get("reverseCharge") or inv.get("reverse_charge") or str(inv.get("billing_reason") or "").find("reverse") >= 0)
    if reverse:
        btw_kind = "reverse_charge"
        if aangifte in (None, "") and (vat_amount or 0) > 0:
            aangifte = vat_amount
        vat_amount = 0
        vat_rate = 0
    elif btw_kind is None and vat_rate == 21:
        btw_kind = "standard"
    elif btw_kind is None and vat_rate == 9:
        btw_kind = "reduced"
    elif btw_kind is None and vat_amount == 0:
        btw_kind = "exempt"
    return {
        "id": str(inv.get("id") or inv.get("number") or ""),
        "number": str(inv.get("number") or inv.get("id") or ""),
        "tenant": slug,
        "amount": amount,
        "status": mapped,
        "date": _iso_day(inv.get("paid_at") or inv.get("created_at") or inv.get("date") or inv.get("created")),
        "source": str(inv.get("source") or "stripe"),
        "vatAmount": vat_amount,
        "vatRate": vat_rate,
        "btwKind": btw_kind,
        "aangifteVatAmount": aangifte,
        "reverseCharge": reverse or None,
    }


class ContractReads:
    def __init__(self, *, infra, platform, keepset, cloudflare, orchestrator=None):
        self.infra = infra
        self.platform = platform
        self.keepset = keepset
        self.cloudflare = cloudflare
        self.orchestrator = orchestrator
        self.k8s = K8sContract(infra)
        self._audit: list[dict[str, Any]] = []

    def record_audit(self, actor: str, action: str, target: str) -> None:
        self._audit.insert(
            0,
            {
                "id": str(len(self._audit) + 1),
                "at": datetime.now(timezone.utc).isoformat(),
                "actor": actor or "operator",
                "action": action,
                "target": target,
            },
        )
        self._audit = self._audit[:200]

    async def _plat(self, method: str, path: str, **kwargs) -> Any:
        if method == "GET":
            code, body = await self.platform.get(path, params=kwargs.get("params"))
        elif method == "POST":
            code, body = await self.platform.post(path, json=kwargs.get("json"))
        elif method == "PATCH":
            code, body = await self.platform.patch(path, json=kwargs.get("json"))
        elif method == "DELETE":
            code, body = await self.platform.delete(path, params=kwargs.get("params"))
        else:
            code, body = await self.platform.request(method, path, json=kwargs.get("json"), params=kwargs.get("params"))
        if code >= 400:
            return None
        return body

    def operator_from_request(self, request) -> dict[str, str]:
        email = (
            (request.headers.get("cf-access-authenticated-user-email") or "")
            or (request.headers.get("x-forwarded-email") or "")
        ).strip().lower()
        if not email:
            jwt = (request.headers.get("cf-access-jwt-assertion") or "").strip()
            if jwt.count(".") >= 2:
                try:
                    import base64
                    import json as json_mod

                    payload = jwt.split(".")[1]
                    pad = "=" * (-len(payload) % 4)
                    data = json_mod.loads(base64.urlsafe_b64decode(payload + pad))
                    email = (data.get("email") or "").strip().lower()
                except Exception:
                    email = ""
        if not email:
            email = "operator@cronnecture.com"
        local = email.split("@")[0]
        parts = [p for p in local.replace(".", " ").replace("_", " ").split() if p]
        first = parts[0].title() if parts else "Operator"
        last = parts[-1].title() if len(parts) > 1 else ""
        initials = (first[:1] + (last[:1] or first[1:2])).upper()
        return {
            "firstName": first,
            "lastName": last,
            "email": email,
            "initials": initials or "OP",
            "role": "admin",
        }

    async def operator(self, request) -> dict[str, str]:
        operator = self.operator_from_request(request)
        me = await self._plat("GET", "/api/auth/me")
        if not isinstance(me, dict) or not me.get("email"):
            return operator
        email = str(me.get("email") or operator["email"]).strip().lower()
        local = email.split("@")[0]
        parts = [p for p in local.replace(".", " ").replace("_", " ").split() if p]
        first = parts[0].title() if parts else operator["firstName"]
        last = parts[-1].title() if len(parts) > 1 else operator["lastName"]
        initials = (first[:1] + (last[:1] or first[1:2])).upper()
        return {
            "firstName": first,
            "lastName": last,
            "email": email,
            "initials": initials or operator["initials"],
            "role": str(me.get("role") or operator["role"]),
        }

    async def list_nodes(self) -> list[dict[str, Any]]:
        return await CACHE.get_or_load("contract.nodes", 10.0, self._load_nodes)

    async def _load_nodes(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/fleet/nodes")
        rows = []
        if isinstance(body, dict):
            rows = body.get("nodes") or []
        elif isinstance(body, list):
            rows = body
        brief: list[dict[str, Any]] = []
        resources: dict[str, Any] = {}
        try:
            def _k8s():
                return self.k8s.nodes_brief(), self.k8s.node_resources()

            brief, resources = await asyncio.to_thread(_k8s)
        except Exception:
            brief, resources = [], {}
        by_name = {n.get("name"): n for n in brief if n.get("name")}
        by_ip = {n.get("ip"): n for n in brief if n.get("ip")}

        def _row(
            hostname: str,
            *,
            groups: list,
            ip: str,
            kn: dict,
            provider: str = "",
            region: str = "",
            pool: str = "",
            k3s: str = "",
            pods: int = 0,
            notes: list[str] | None = None,
        ) -> dict[str, Any]:
            group = _group_for(groups, hostname)
            if hostname.startswith("worker-general"):
                group = "compute_general"
            elif kn.get("role") in ("control", "server"):
                group = "k3s_server"
            ready = kn.get("status") == "ready"
            joined = bool(kn)
            res = resources.get(hostname) or {}
            return {
                "id": hostname,
                "hostname": hostname,
                "group": group,
                "role": "server" if group == "k3s_server" else "agent",
                "ip": ip or kn.get("ip") or "",
                "provider": provider,
                "region": region,
                "k3s": k3s or os.environ.get("K3S_VERSION") or "v1.35.4+k3s1",
                "pool": pool or ("control-plane" if group == "k3s_server" else "general"),
                "health": health_from_ready(ready, joined),
                "cpu": res.get("cpu") or {"used": 0, "cores": 0},
                "memory": res.get("memory") or {"usedGi": 0, "totalGi": 0},
                "pods": int(pods or 0),
                "tunnel": {
                    "name": f"node-{hostname}",
                    "status": health_from_ready(ready, joined),
                },
                "publicPorts": ["25/587"] if group == "k3s_server" else [],
                "notes": notes or [],
            }

        merged: dict[str, dict[str, Any]] = {}
        for row in rows:
            hostname = row.get("hostname") or row.get("name") or ""
            ip = str(row.get("ip") or "")
            kn = by_name.get(hostname) or by_ip.get(ip) or {}
            if kn.get("name") and kn["name"] != hostname:
                hostname = kn["name"]
            if not hostname:
                continue
            key = kn.get("ip") or ip or hostname
            notes = [row["remove_block_reason"]] if row.get("remove_block_reason") else []
            merged[key] = _row(
                hostname,
                groups=row.get("groups") or [],
                ip=ip,
                kn=kn,
                provider=row.get("provider") or "",
                region=row.get("region") or row.get("dc") or "",
                pool=row.get("pool") or "",
                k3s=row.get("kubelet_version") or "",
                pods=int(row.get("pod_count") or kn.get("pods") or 0),
                notes=notes,
            )
        for kn in brief:
            hostname = kn.get("name") or ""
            ip = kn.get("ip") or ""
            key = ip or hostname
            if not hostname or key in merged:
                continue
            role = kn.get("role") or "compute"
            group = "k3s_server" if role in ("control", "server") else "compute_general"
            merged[key] = _row(
                hostname,
                groups=[group],
                ip=ip,
                kn=kn,
                k3s=kn.get("k3s") or "",
                pods=int(kn.get("pods") or 0),
            )
        return list(merged.values())

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        for node in await self.list_nodes():
            if node["id"] == node_id or node["hostname"] == node_id:
                detail = await self._plat("GET", f"/api/fleet/nodes/{node_id}/detail")
                if isinstance(detail, dict):
                    notes = list(node.get("notes") or [])
                    extra = detail.get("notes") or detail.get("message")
                    if extra:
                        notes.append(str(extra))
                    node = {**node, "notes": notes}
                    if detail.get("cpu"):
                        node["cpu"] = detail["cpu"]
                    if detail.get("memory"):
                        node["memory"] = detail["memory"]
                return node
        return None

    def attention(self, nodes: list[dict[str, Any]], jobs: list[dict[str, Any]], certs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        down = [n for n in nodes if n.get("health") == "down"]
        for n in down:
            items.append(
                {
                    "id": f"node-{n['id']}",
                    "severity": "critical",
                    "title": f"{n['hostname']} is down",
                    "detail": f"{n.get('ip') or 'no ip'} · {n.get('group')}",
                    "href": f"/nodes/{n['id']}",
                }
            )
        for j in ContractReads._actionable_failed_jobs(jobs):
            jtype = str(j.get("type") or "job")
            target = str(j.get("target") or "")
            items.append(
                {
                    "id": f"job-{j['id']}",
                    "severity": "warn",
                    "title": f"Job {jtype} failed",
                    "detail": j.get("detail") or target,
                    "href": "/jobs",
                }
            )
        for c in certs:
            if c.get("status") != "healthy":
                items.append(
                    {
                        "id": f"cert-{c['host']}",
                        "severity": "warn",
                        "title": f"Certificate {c['host']}",
                        "detail": f"expires {c.get('expires')}",
                        "href": "/health",
                    }
                )
        return items

    @staticmethod
    def _actionable_failed_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Open failures only. Dismissed jobs and older failures after a later success are gone."""
        ordered = sorted(
            jobs,
            key=lambda row: str(row.get("startedAt") or row.get("id") or ""),
            reverse=True,
        )
        cleared: set[tuple[str, str]] = set()
        out: list[dict[str, Any]] = []
        for row in ordered:
            key = (str(row.get("type") or "job"), str(row.get("target") or ""))
            status = str(row.get("status") or "")
            detail = str(row.get("detail") or "").lower()
            if status == "ok" or detail.startswith("dismissed"):
                cleared.add(key)
                continue
            if status != "failed" or key in cleared:
                continue
            out.append(row)
            cleared.add(key)
        return out

    async def jobs(self) -> list[dict[str, Any]]:
        return await CACHE.get_or_load("contract.jobs", 5.0, self._load_jobs)

    async def _load_jobs(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/jobs", params={"limit": 100})
        rows = []
        if isinstance(body, dict):
            rows = body.get("jobs") or body.get("items") or body.get("rows") or []
        elif isinstance(body, list):
            rows = body
        out = []
        for row in rows:
            payload = row.get("payload_json") or row.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            preview = str(row.get("log_preview") or row.get("log") or row.get("error") or "")
            last_line = ""
            for line in reversed(preview.splitlines()):
                text = line.strip()
                if text:
                    last_line = text[:180]
                    break
            target = (
                row.get("operation_id")
                or payload.get("hostname")
                or payload.get("slug")
                or payload.get("operation_id")
                or payload.get("tag")
                or row.get("type")
                or ""
            )
            status = job_status(str(row.get("status") or ""))
            out.append(
                {
                    "id": str(row.get("id")),
                    "type": row.get("type") or "",
                    "target": str(target),
                    "status": status,
                    "startedAt": row.get("started_at") or row.get("created_at") or "",
                    "claimedBy": row.get("claimed_by") or row.get("stage") or "",
                    "detail": last_line,
                }
            )
        return out

    def job_trend(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        days = []
        today = datetime.now(timezone.utc).date()
        by_day: dict[str, dict[str, int]] = {}
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            by_day[d] = {"day": d[-5:], "ok": 0, "failed": 0}
            days.append(d)
        for job in jobs:
            raw = str(job.get("startedAt") or "")[:10]
            if raw in by_day:
                if job.get("status") == "failed":
                    by_day[raw]["failed"] += 1
                elif job.get("status") == "ok":
                    by_day[raw]["ok"] += 1
        return [by_day[d] for d in days]

    async def tenants(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/clients", params={"include": "billing"})
        rows = []
        if isinstance(body, dict):
            rows = body.get("clients") or body.get("items") or []
        elif isinstance(body, list):
            rows = body
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(self._tenant_from_row(row))
        return out

    def _tenant_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        slug = row.get("slug") or ""
        status = (row.get("status") or "live").lower()
        if status in ("active", "deployed", "running"):
            mapped = "live"
        elif status in ("pending", "provisioning", "building"):
            mapped = "building"
        else:
            mapped = "hold"
        zones = row.get("zones") if isinstance(row.get("zones"), list) else []
        domain = str(row.get("domain") or "")
        if not domain:
            active = next((z for z in zones if isinstance(z, dict) and z.get("status") == "active"), None)
            if not isinstance(active, dict) and zones and isinstance(zones[0], dict):
                active = zones[0]
            if isinstance(active, dict):
                domain = str(active.get("domain") or "")
        hostnames: list[str] = []
        if domain:
            hostnames.append(domain)
        apps = []
        for app in row.get("apps") or []:
            if not isinstance(app, dict):
                continue
            hostname = str(app.get("hostname") or "")
            exposures = app.get("exposures") if isinstance(app.get("exposures"), list) else []
            for exp in exposures:
                if not isinstance(exp, dict):
                    continue
                host = str(exp.get("hostname") or "").strip()
                if host and host not in hostnames and not host.startswith(("id.", "www.")):
                    hostnames.append(host)
                    if not hostname:
                        hostname = host
            apps.append(
                {
                    "name": app.get("name") or "",
                    "image": app.get("image") or "",
                    "status": health_from_ready(
                        (app.get("status") or "").lower() in ("deployed", "running", "exposed", "active")
                    ),
                    "hostname": hostname,
                }
            )
        plan = row.get("billing_plan") or row.get("plan") or "standard"
        tunnel = ""
        raw_tunnel = row.get("tunnel")
        if isinstance(raw_tunnel, dict):
            tunnel = str(raw_tunnel.get("name") or "")
        tunnel = tunnel or str(row.get("tunnel_name") or row.get("cf_tunnel_id") or "")
        handshake = _handshake(row)
        active = _active_client(row)
        mrr = _mrr_from_client(row) if active else 0.0
        next_invoice = _iso_day(
            handshake.get("next_invoice_at") or handshake.get("stripe_start") or row.get("next_invoice_at")
        )
        return {
            "id": row.get("id"),
            "slug": slug,
            "name": row.get("name") or slug,
            "namespace": row.get("k8s_namespace") or f"client-{slug}",
            "status": mapped if mapped in ("live", "building", "hold") else "hold",
            "domain": domain,
            "hostnames": hostnames,
            "portalUuid": row.get("portal_uuid") or "",
            "portalUrl": row.get("portal_url") or "https://client.cronnecture.com/",
            "tunnel": tunnel,
            "apps": apps,
            "mailboxes": int(row.get("mailbox_count") or 0),
            "plan": str(plan),
            "mrr": mrr,
            "activeClient": active,
            "nextInvoiceAt": next_invoice,
            "billingNote": str(handshake.get("note") or "").strip(),
        }

    async def get_tenant(self, slug: str) -> dict[str, Any] | None:
        for t in await self.tenants():
            if t["slug"] == slug:
                return t
        body = await self._plat("GET", f"/api/clients/{slug}")
        if isinstance(body, dict) and (body.get("slug") or body.get("id")):
            return self._tenant_from_row(body)
        return None

    async def mail_domains(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/mail/domains")
        rows = []
        if isinstance(body, dict):
            rows = body.get("domains") or body.get("items") or []
        elif isinstance(body, list):
            rows = body
        out = []
        for row in rows:
            if isinstance(row, str):
                out.append({"domain": row, "mailboxes": 0, "status": "healthy", "tenant": ""})
                continue
            out.append(
                {
                    "domain": row.get("domain") or row.get("name") or "",
                    "mailboxes": int(row.get("mailboxes") or row.get("count") or 0),
                    "status": health_from_ready((row.get("status") or "ok").lower() not in ("down", "error")),
                    "tenant": row.get("tenant") or row.get("client") or "",
                }
            )
        return out

    async def mailboxes(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/mail/mailboxes")
        rows = []
        if isinstance(body, dict):
            rows = body.get("mailboxes") or body.get("items") or []
        elif isinstance(body, list):
            rows = body
        out = []
        for row in rows:
            address = row.get("address") or row.get("email") or ""
            domain = address.split("@")[-1] if "@" in address else (row.get("domain") or "")
            out.append(
                {
                    "address": address,
                    "domain": domain,
                    "quota": str(row.get("quota") or row.get("quota_used") or ""),
                    "status": health_from_ready((row.get("status") or "active").lower() in ("active", "ok", "healthy")),
                }
            )
        return out

    async def identity(self) -> list[dict[str, Any]]:
        try:
            data = await self.keepset.describe("identity")
        except Exception:
            return []
        out = []
        for app in data.get("apps") or []:
            name = app.get("name") or app.get("deploy") or ""
            deploy = app.get("deploy") or name.lower()
            wl = next((w for w in (data.get("workloads") or []) if w.get("name") == deploy), None)
            ready = (wl or {}).get("ready") or 0
            desired = (wl or {}).get("desired") or 0
            out.append(
                {
                    "name": name,
                    "namespace": "identity",
                    "replicas": {"ready": ready, "desired": desired},
                    "pool": "general",
                    "health": health_from_ready(bool((wl or {}).get("healthy")), desired > 0),
                    "url": app.get("url") or "",
                    "notes": "",
                }
            )
        return out

    async def previews(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/previews")
        rows = []
        if isinstance(body, dict):
            rows = body.get("previews") or body.get("items") or body.get("sites") or []
        elif isinstance(body, list):
            rows = body
        out = []
        for row in rows:
            uuid = str(row.get("uuid") or row.get("id") or "")
            out.append(
                {
                    "uuid": uuid,
                    "name": row.get("name") or uuid,
                    "path": row.get("path") or f"/previews/{uuid}",
                    "status": health_from_ready((row.get("status") or "live").lower() in ("live", "ok", "active", "healthy")),
                    "updatedAt": row.get("updated_at") or row.get("updatedAt") or "",
                }
            )
        return out

    async def tickets(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/support/tickets") or await self._plat("GET", "/api/leads")
        rows = []
        if isinstance(body, dict):
            rows = body.get("tickets") or body.get("leads") or body.get("items") or []
        elif isinstance(body, list):
            rows = body
        out = []
        for row in rows:
            st = (row.get("status") or "open").lower()
            if st in ("closed", "done", "resolved"):
                mapped = "done"
            elif st in ("waiting", "pending"):
                mapped = "waiting"
            else:
                mapped = "open"
            out.append(
                {
                    "id": str(row.get("id")),
                    "tenant": row.get("client_slug")
                    or row.get("client_name")
                    or row.get("tenant")
                    or row.get("client")
                    or row.get("company")
                    or "",
                    "topic": row.get("topic") or row.get("priority") or row.get("source") or "Account",
                    "title": row.get("title") or row.get("subject") or row.get("name") or "",
                    "status": mapped,
                    "updatedAt": row.get("updated_at") or row.get("created_at") or "",
                }
            )
        return out

    async def invoices(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/clients", params={"include": "billing"})
        clients: list[dict[str, Any]] = []
        if isinstance(body, dict):
            clients = body.get("clients") or body.get("items") or []
        elif isinstance(body, list):
            clients = body

        async def load(row: dict[str, Any]) -> list[dict[str, Any]]:
            if not isinstance(row, dict):
                return []
            slug = str(row.get("slug") or "")
            cid = row.get("id")
            billing = await self._plat("GET", f"/api/clients/{cid}/billing") if cid is not None else None
            if not isinstance(billing, dict):
                billing = {}
            found: list[dict[str, Any]] = []
            seen: set[str] = set()
            for inv in billing.get("invoices") or []:
                if not isinstance(inv, dict):
                    continue
                mapped = _invoice_from_billing(inv, slug)
                if mapped["id"]:
                    seen.add(mapped["id"])
                    found.append(mapped)
            handshake = billing.get("handshake") if isinstance(billing.get("handshake"), dict) else _handshake(row)
            next_at = _iso_day(billing.get("next_invoice_at") or handshake.get("next_invoice_at"))
            monthly = _mrr_from_client({**row, "handshake": handshake})
            if next_at and monthly > 0:
                upcoming_id = f"{slug}-upcoming-{next_at}"
                already = any(item["date"] == next_at and item["status"] in ("upcoming", "open") for item in found)
                if upcoming_id not in seen and not already:
                    found.append(
                        {
                            "id": upcoming_id,
                            "number": f"{handshake.get('pack_label') or row.get('billing_plan') or 'Care'} — next",
                            "tenant": slug,
                            "amount": monthly,
                            "status": "upcoming",
                            "date": next_at,
                            "source": "stripe",
                        }
                    )
            return found

        batches = await asyncio.gather(*(load(row) for row in clients if isinstance(row, dict)))
        out: list[dict[str, Any]] = []
        for batch in batches:
            out.extend(batch)
        out.sort(key=lambda item: item.get("date") or "", reverse=True)
        return out

    async def images(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/registry/images")
        rows = []
        if isinstance(body, dict):
            rows = body.get("images") or body.get("items") or []
        elif isinstance(body, list):
            rows = body
        return [
            {
                "name": row.get("name") or row.get("repository") or "",
                "tag": row.get("tag") or "latest",
                "size": str(row.get("size") or ""),
                "pushedAt": row.get("pushed_at") or row.get("pushedAt") or "",
                "tenant": row.get("tenant") or "",
            }
            for row in rows
            if isinstance(row, dict)
        ]

    async def backups(self) -> list[dict[str, Any]]:
        return await CACHE.get_or_load("contract.backups", 15.0, self._load_backups)

    async def _load_backups(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/backups")
        rows = []
        if isinstance(body, dict):
            rows = (
                body.get("versions")
                or body.get("snapshots")
                or body.get("backups")
                or body.get("items")
                or body.get("inventory")
                or []
            )
        elif isinstance(body, list):
            rows = body
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            st = str(row.get("health") or row.get("status") or "healthy").lower()
            health = "healthy"
            if st in ("failed", "error", "down"):
                health = "down"
            elif st in ("stale", "degraded", "warning", "partial"):
                health = "degraded"
            elif st in ("idle", "pending", "local_only", "remote"):
                health = "idle"
            size = row.get("size") or row.get("size_bytes") or row.get("bytes") or ""
            out.append(
                {
                    "id": str(row.get("id") or row.get("stamp") or row.get("name") or row.get("key") or ""),
                    "target": row.get("backup_type") or row.get("target") or row.get("display_name") or row.get("kind") or "fleet",
                    "at": str(row.get("at") or row.get("created_at") or row.get("mtime") or ""),
                    "size": str(size),
                    "status": health,
                }
            )
        return out

    async def certificates(self) -> list[dict[str, Any]]:
        return await CACHE.get_or_load("contract.certs", 60.0, self._load_certificates)

    async def _load_certificates(self) -> list[dict[str, Any]]:
        from .k8s import probe_tls_hosts
        from ..cloudflare import HTTP_HOSTS

        hosts = list(HTTP_HOSTS) + ["mail.cronnecture.com"]
        try:
            return await asyncio.to_thread(probe_tls_hosts, hosts)
        except Exception:
            return []

    def crons(self) -> list[dict[str, Any]]:
        return [
            {"name": "cloudflare-sync", "schedule": "0 * * * *", "last": "", "status": "healthy"},
            {"name": "fleet-heartbeat", "schedule": "*/5 * * * *", "last": "", "status": "healthy"},
            {"name": "incident-watchdog", "schedule": "*/5 * * * *", "last": "", "status": "healthy"},
            {"name": "fleet-backup", "schedule": "0 3 * * *", "last": "", "status": "idle"},
        ]

    async def playbooks(self) -> list[dict[str, Any]]:
        catalog = [
            {**p, "status": "idle", "allowlisted": True, "lastRun": ""}
            for p in PLAYBOOKS
        ]
        body = await self._plat("GET", "/api/fleet/operations")
        rows = (body or {}).get("operations") if isinstance(body, dict) else body
        if not isinstance(rows, list):
            return catalog
        by_tag = {p["tag"]: p for p in catalog}
        for row in rows:
            if not isinstance(row, dict):
                continue
            tag = str(row.get("id") or row.get("tag") or "")
            if not tag:
                continue
            item = by_tag.get(tag) or {
                "tag": tag,
                "name": row.get("title") or row.get("name") or tag,
                "description": row.get("summary") or row.get("description") or "",
                "hosts": row.get("hosts") or row.get("limit") or "all",
                "status": "idle",
                "allowlisted": True,
                "lastRun": "",
            }
            item["name"] = row.get("title") or item["name"]
            item["description"] = row.get("summary") or item["description"]
            by_tag[tag] = item
        return list(by_tag.values())

    def inventory(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts = {g: 0 for g in NODE_GROUPS}
        for n in nodes:
            g = n.get("group")
            if g in counts:
                counts[g] += 1
        purpose = {
            "k3s_server": "Control plane + etcd",
            "compute_general": "Default workloads",
            "compute_cpu": "CPU pool (tainted)",
            "compute_memory": "Memory pool (tainted)",
            "edge_lb": "HAProxy + keepalived",
            "siem": "Wazuh (retired, empty)",
        }
        return [
            {"group": g, "purpose": purpose[g], "hosts": counts[g], "empty": counts[g] == 0}
            for g in NODE_GROUPS
        ]

    async def ansible_runs(self) -> list[dict[str, Any]]:
        jobs = await self.jobs()
        out = []
        for job in jobs:
            jtype = str(job.get("type") or "")
            if jtype not in ("fleet_converge", "fleet_pipeline", "fleet_add_node", "fleet_remove_node"):
                continue
            out.append(
                {
                    "id": job["id"],
                    "playbook": job.get("target") or jtype,
                    "tags": [t for t in [job.get("target"), jtype] if t],
                    "startedAt": job.get("startedAt") or "",
                    "duration": "",
                    "status": job.get("status") or "idle",
                    "triggeredBy": job.get("claimedBy") or "",
                    "mode": "apply",
                    "claimedBy": job.get("claimedBy") or "",
                }
            )
        return out

    def ansible_vars(self) -> list[dict[str, Any]]:
        return [
            {"key": "k3s_version", "scope": "all", "secret": False, "value": "v1.35.4+k3s1"},
            {"key": "control_plane_replicas", "scope": "all", "secret": False, "value": "2"},
            {"key": "cf_client_ingress_backend", "scope": "all", "secret": False, "value": "Traefik ClusterIP"},
            {"key": "vault_platform_database_url", "scope": "all", "secret": True, "value": "••••"},
        ]

    async def list_audit(self) -> list[dict[str, Any]]:
        body = await self._plat("GET", "/api/audit", params={"limit": 100})
        rows = []
        if isinstance(body, dict):
            rows = body.get("entries") or body.get("items") or []
        elif isinstance(body, list):
            rows = body
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(
                {
                    "id": str(row.get("id") or ""),
                    "at": str(row.get("created_at") or row.get("at") or ""),
                    "actor": row.get("actor") or "operator",
                    "action": row.get("action") or row.get("method") or "",
                    "target": row.get("path") or row.get("target") or "",
                }
            )
        seen = {item["id"] for item in out}
        for item in self._audit:
            if item["id"] not in seen:
                out.append(item)
        return out[:200]

    async def tunnels(self) -> list[dict[str, Any]]:
        return await CACHE.get_or_load("contract.tunnels", 30.0, self._load_tunnels)

    async def _load_tunnels(self) -> list[dict[str, Any]]:
        try:
            routes = await asyncio.to_thread(self.k8s.routes)
        except Exception:
            routes = []
        hosts = [r.get("host") for r in routes if isinstance(r, dict) and r.get("host")]
        node_hosts = [
            r.get("host")
            for r in routes
            if isinstance(r, dict) and r.get("host") and not str(r.get("namespace") or "").startswith("client-")
        ]
        out = [
            {
                "name": "node-tunnel",
                "kind": "node",
                "origin": "Traefik ClusterIP",
                "status": "healthy" if hosts else "idle",
                "hostnames": node_hosts[:40] or ["control.cronnecture.com", "client.cronnecture.com"],
            }
        ]
        by_ns: dict[str, list[str]] = {}
        for r in routes:
            if not isinstance(r, dict):
                continue
            host = r.get("host") or ""
            ns = str(r.get("namespace") or "")
            if ns.startswith("client-") and host:
                by_ns.setdefault(ns, []).append(host)
        for ns, hs in sorted(by_ns.items()):
            out.append(
                {
                    "name": ns,
                    "kind": "client",
                    "origin": "client-tunnel",
                    "status": "healthy",
                    "hostnames": hs,
                }
            )
        return out

    async def dns(self) -> list[dict[str, Any]]:
        async def _load() -> list[dict[str, Any]]:
            snap = await self.cloudflare.snapshot()
            rows = snap.get("dns") or []
            out = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                rtype = (row.get("type") or "A").upper()
                if rtype not in ("A", "CNAME", "MX", "TXT"):
                    continue
                out.append(
                    {
                        "name": row.get("name") or "",
                        "type": rtype,
                        "content": row.get("content") or row.get("value") or "",
                        "proxied": bool(row.get("proxied")),
                    }
                )
            return out

        return await CACHE.get_or_load("contract.dns", 120.0, _load)

    def labels(self) -> list[dict[str, str]]:
        return [
            {"href": "/", "label": "Home"},
            {"href": "/nodes", "label": "Nodes"},
            {"href": "/kubernetes", "label": "Kubernetes"},
            {"href": "/ansible", "label": "Ansible"},
            {"href": "/clients", "label": "Clients"},
            {"href": "/edge", "label": "Edge"},
            {"href": "/mail", "label": "Mail"},
            {"href": "/identity", "label": "Identity"},
            {"href": "/jobs", "label": "Jobs"},
            {"href": "/health", "label": "Health"},
            {"href": "/business", "label": "Business"},
        ]

    async def search(self, q: str) -> list[dict[str, str]]:
        qn = (q or "").strip().lower()
        if not qn:
            return []
        hits: list[dict[str, str]] = []
        body = await self._plat("GET", "/api/search", params={"q": q})
        rows = []
        if isinstance(body, dict):
            rows = body.get("results") or body.get("items") or []
        elif isinstance(body, list):
            rows = body
        kind_href = {
            "client": "/clients",
            "node": "/nodes",
            "job": "/jobs",
            "app": "/clients",
            "mailbox": "/mail",
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind") or row.get("group") or "Search")
            label = str(row.get("title") or row.get("label") or row.get("id") or "")
            hint = str(row.get("subtitle") or row.get("hint") or "")
            href = row.get("href") or kind_href.get(kind.lower(), "/")
            if kind.lower() == "client" and row.get("id"):
                href = f"/clients/{row.get('id')}"
            hits.append({"group": kind.title(), "label": label, "hint": hint, "href": str(href)})
        if hits:
            return hits[:40]
        for node in await self.list_nodes():
            blob = f"{node['hostname']} {node['ip']} {node['group']}"
            if includes(blob, qn):
                hits.append({"group": "Nodes", "label": node["hostname"], "hint": node["ip"], "href": f"/nodes/{node['id']}"})
        for t in await self.tenants():
            if includes(f"{t['slug']} {t['name']} {t['domain']}", qn):
                hits.append({"group": "Clients", "label": t["name"], "hint": t["slug"], "href": f"/clients/{t['slug']}"})
        for p in await self.playbooks():
            if includes(f"{p['tag']} {p['name']}", qn):
                hits.append({"group": "Ansible", "label": p["name"], "hint": p["tag"], "href": "/ansible"})
        return hits[:40]

    async def shell(self, request) -> dict[str, Any]:
        operator = await self.operator(request)

        async def _load() -> dict[str, Any]:
            nodes, jobs, certs, backups = await asyncio.gather(
                self.list_nodes(),
                self.jobs(),
                self.certificates(),
                self.backups(),
            )
            attention = self.attention(nodes, jobs, certs)
            failed = ContractReads._actionable_failed_jobs(jobs)
            healthy = sum(1 for n in nodes if n.get("health") == "healthy")
            last = backups[0] if backups else None
            return {
                "mode": "live",
                "cluster": "cronnecture",
                "k3s": os.environ.get("K3S_VERSION") or "v1.35.4+k3s1",
                "traefik": "ClusterIP origin",
                "nodeCount": len(nodes),
                "healthyNodes": healthy,
                "failedJobCount": len(failed),
                "attentionCount": len(attention),
                "attention": attention,
                "failedJobs": failed[:12],
                "expiringCerts": [c for c in certs if c.get("status") != "healthy"],
                "lastBackup": last,
                "playbooks": [{"tag": p["tag"], "name": p["name"]} for p in PLAYBOOKS],
                "labels": self.labels(),
            }

        payload = await CACHE.get_or_load("contract.shell", 8.0, _load)
        return {**payload, "operator": operator}

    def list_result(self, items: list, params: dict | None, match) -> dict[str, Any]:
        return paginate(items, parse_query(params), match)
