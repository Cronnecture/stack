"""Map control-portal actions to k8s, platform jobs, or keep-set restarts."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .envelope import job_status

ACTION_TYPES = frozenset(
    {
        "operator.notice",
        "nodes.add",
        "nodes.cordon",
        "nodes.drain",
        "nodes.reboot",
        "k8s.quota",
        "k8s.ns.create",
        "k8s.ns.psa",
        "k8s.ns.network",
        "k8s.restart",
        "k8s.scale",
        "k8s.rollout",
        "k8s.apply",
        "k8s.delete",
        "k8s.pod.delete",
        "k8s.secrets.rotate",
        "k8s.netpol.apply",
        "guards.set",
        "edge.purge",
        "edge.access",
        "ansible.run",
        "ansible.rerun",
        "ansible.cancel",
        "ansible.ping",
        "ansible.converge",
        "ansible.vars.set",
        "policy.apply",
        "tenants.create",
        "tenants.deploy",
        "tenants.expose",
        "tenants.delete",
        "tunnels.rotate",
        "tunnels.expose",
        "dns.edit",
        "mail.dkim",
        "mail.create",
        "mail.reset",
        "identity.restart",
        "jobs.retry",
        "jobs.retryFailed",
        "jobs.cancel",
        "backups.run",
        "registry.delete",
        "previews.publish",
        "tickets.close",
        "invoices.send",
        "apis.restart",
        "backups.restore",
        "certs.renew",
        "cron.run",
    }
)

CHECK_FIRST = frozenset(
    {
        "k8s.apply",
        "k8s.ns.create",
        "k8s.netpol.apply",
        "ansible.run",
        "ansible.converge",
        "policy.apply",
        "backups.restore",
    }
)


def _payload(action: dict[str, Any]) -> dict[str, Any]:
    raw = action.get("payload")
    return raw if isinstance(raw, dict) else {}


def _dry(payload: dict[str, Any], action_type: str) -> bool:
    if "dryRun" in payload:
        return bool(payload.get("dryRun"))
    if "mode" in payload:
        return str(payload.get("mode")).lower() != "apply"
    return action_type in CHECK_FIRST


class ActionDispatcher:
    def __init__(self, *, infra, platform, keepset, reads):
        self.infra = infra
        self.platform = platform
        self.keepset = keepset
        self.reads = reads

    async def dispatch(self, action: dict[str, Any], *, actor: str) -> dict[str, Any]:
        atype = str(action.get("type") or "").strip()
        target = str(action.get("target") or "").strip()
        payload = _payload(action)
        if atype not in ACTION_TYPES:
            raise ValueError(f"unknown action type: {atype}")
        if atype == "operator.notice":
            return {"id": f"notice-{uuid.uuid4().hex[:8]}", "status": "ok"}

        job_id = f"act-{uuid.uuid4().hex[:12]}"
        self.reads.record_audit(actor, atype, target)

        if atype.startswith("k8s.") or atype == "identity.restart":
            result = await self._k8s(atype, target, payload)
            return {"id": job_id, "status": "ok", "result": result}

        if atype == "nodes.add":
            ip = payload.get("ip") or target
            code, body = await self.platform.post("/api/fleet/nodes", json={"ip": ip, "node_class": payload.get("node_class") or "auto"})
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"add-node failed ({code})")
            return {"id": str((body or {}).get("job_id") or job_id), "status": job_status(str((body or {}).get("status") or "queued"))}

        if atype in ("nodes.cordon", "nodes.drain", "nodes.reboot"):
            hostname = target or payload.get("hostname")
            verb = atype.split(".")[-1]
            if verb in ("cordon", "drain"):
                code, body = await self.platform.post(f"/api/fleet/nodes/{hostname}/{verb}", json={})
            else:
                code, body = await self.platform.post(
                    f"/api/fleet/operations/reboot",
                    json={"extra_vars": {"hostname": hostname}, "limit": hostname},
                )
            if code >= 400:
                code, body = await self._enqueue("fleet_converge", {"operation_id": atype, "hostname": hostname})
            return {"id": str((body or {}).get("job_id") or (body or {}).get("id") or job_id), "status": "queued"}

        if atype in ("ansible.rerun", "ansible.cancel"):
            mapped = "jobs.retry" if atype == "ansible.rerun" else "jobs.cancel"
            return await self.dispatch(
                {"type": mapped, "target": payload.get("id") or target, "payload": {"ids": [str(payload.get("id") or target)]}},
                actor=actor,
            )

        if atype == "ansible.ping":
            group = str(payload.get("group") or payload.get("limit") or target or "all").strip()
            limit = None if group in ("", "all", "*") else group
            code, body = await self._operation("ping", limit=limit)
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"ping failed ({code})")
            return self._queued(body, job_id)

        if atype in ("ansible.run", "ansible.converge", "policy.apply"):
            op = str(payload.get("tag") or payload.get("id") or target or "site").strip()
            op = {"site.yml": "site"}.get(op, op)
            if atype == "ansible.converge":
                op = "site"
            mode = payload.get("mode") or ("check" if _dry(payload, atype) else "apply")
            code, body = await self._operation(
                op,
                limit=payload.get("limit") or payload.get("group"),
                extra_vars={"mode": mode, "diff": payload.get("diff", True)},
            )
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"enqueue failed ({code})")
            return self._queued(body, job_id)

        if atype.startswith("tenants."):
            return await self._tenant(atype, target, payload, job_id)

        if atype == "mail.create":
            code, body = await self.platform.post("/api/mail/mailboxes", json={"address": payload.get("address") or target})
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"mailbox create failed ({code})")
            return {"id": job_id, "status": "ok"}

        if atype == "jobs.retryFailed":
            rows = await self.reads.jobs()
            ids = [
                str(row.get("id"))
                for row in rows
                if isinstance(row, dict) and row.get("status") == "failed" and row.get("id")
            ]
            if not ids:
                return {"id": job_id, "status": "ok", "result": {"retried": 0}, "detail": "No failed jobs"}
            last = await self.dispatch(
                {"type": "jobs.retry", "target": ",".join(ids), "payload": {"ids": ids}},
                actor=actor,
            )
            last["result"] = {"retried": len(ids)}
            last["detail"] = f"Retried {len(ids)} job{'s' if len(ids) != 1 else ''}"
            return last

        if atype in ("jobs.retry", "jobs.cancel"):
            raw = payload.get("ids") or target
            ids = raw if isinstance(raw, list) else [x for x in str(raw).split(",") if x]
            last = job_id
            retry = atype == "jobs.retry"
            for jid in ids:
                code, body = await self.platform.post(
                    f"/api/jobs/{str(jid).strip()}/dismiss",
                    json={"retry": retry},
                )
                if code < 400 and isinstance(body, dict) and (body.get("id") or body.get("job_id")):
                    last = str(body.get("id") or body.get("job_id"))
            return {"id": str(last), "status": "queued", "result": {"count": len(ids)}}

        if atype == "tickets.close":
            ticket_id = payload.get("id") or target
            code, body = await self.platform.patch(
                f"/api/support/tickets/{ticket_id}",
                json={"status": "done"},
            )
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"ticket close failed ({code})")
            return {"id": str(ticket_id), "status": "ok"}

        if atype == "backups.run":
            code, body = await self._operation("backup")
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"backup failed ({code})")
            return self._queued(body, job_id)

        if atype == "cron.run":
            name = str(payload.get("name") or target).strip()
            op = {
                "cloudflare-sync": "cloudflare",
                "fleet-heartbeat": "health",
                "incident-watchdog": "auto_heal",
                "fleet-backup": "backup",
            }.get(name, name)
            code, body = await self._operation(op)
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"{name} failed ({code})")
            return self._queued(body, job_id)

        if atype == "backups.restore":
            stamp = payload.get("stamp") or payload.get("id") or target
            plan = payload.get("plan") or payload.get("plan_id") or "emergency_inventory"
            apply = not _dry(payload, atype)
            code, body = await self.platform.request(
                "POST",
                f"/api/backups/{stamp}/restore/{plan}",
                params={"apply": "true" if apply else "false"},
            )
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"restore failed ({code})")
            return {"id": str((body or {}).get("job_id") or stamp), "status": "queued" if apply else "ok"}

        if atype == "certs.renew":
            host = payload.get("host") or target
            try:
                result = self.reads.k8s.renew_certificate(host)
                return {"id": job_id, "status": "ok", "result": result}
            except Exception:
                code, body = await self.platform.post(
                    "/api/fleet/operations/cert_check",
                    json={"extra_vars": {"host": host}},
                )
                if code >= 400:
                    raise RuntimeError((body or {}).get("detail") or f"cert renew failed ({code})")
                return {"id": str((body or {}).get("job_id") or job_id), "status": "queued"}

        if atype in ("tunnels.expose", "tunnels.rotate", "edge.purge", "edge.access", "dns.edit"):
            code, body = await self._operation("cloudflare", extra_vars={"target": target, **payload})
            if code >= 400:
                raise RuntimeError((body or {}).get("detail") or f"{atype} failed ({code})")
            return self._queued(body, job_id)

        # Remaining writes enqueue a named fleet operation when one exists.
        op = str(payload.get("operation_id") or atype.split(".")[-1] or "baseline")
        code, body = await self._operation(op, extra_vars={"target": target, **payload})
        if code >= 400:
            raise RuntimeError((body or {}).get("detail") or f"{atype} failed ({code})")
        return self._queued(body, job_id)

    def _queued(self, body: Any, fallback: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        row = body if isinstance(body, dict) else {}
        out = {
            "id": str(row.get("job_id") or row.get("id") or fallback),
            "status": job_status(str(row.get("status") or "queued")),
        }
        if extra:
            out.update(extra)
        return out

    async def _operation(
        self,
        operation_id: str,
        *,
        limit: Any = None,
        extra_vars: dict[str, Any] | None = None,
        tags: Any = None,
    ) -> tuple[int, Any]:
        payload: dict[str, Any] = {}
        if extra_vars:
            payload["extra_vars"] = extra_vars
        if limit:
            payload["limit"] = limit
        if tags:
            payload["tags"] = tags
        return await self.platform.post(
            f"/api/fleet/operations/{operation_id}",
            json=payload or None,
        )

    async def _enqueue(self, job_type: str, payload: dict[str, Any]) -> tuple[int, Any]:
        return await self._operation(
            str(payload.get("operation_id") or "baseline"),
            limit=payload.get("limit"),
            extra_vars=payload,
            tags=payload.get("tags"),
        )

    async def _tenant(self, atype: str, target: str, payload: dict[str, Any], job_id: str) -> dict[str, Any]:
        slug = payload.get("slug") or target
        if atype == "tenants.create":
            code, body = await self.platform.post(
                "/api/clients",
                json={"slug": slug, "name": payload.get("name") or slug, "contact_email": payload.get("email")},
            )
        elif atype == "tenants.delete":
            code, body = await self.platform.delete(f"/api/clients/{slug}", params={"force": "false"})
        elif atype == "tenants.deploy":
            code, body = await self.platform.post(f"/api/clients/{slug}/apps/{payload.get('app') or 'site'}/deploy", json={})
        else:
            code, body = await self.platform.post(f"/api/clients/{slug}/apps/{payload.get('app') or 'site'}/expose", json={})
        if code >= 400:
            raise RuntimeError((body or {}).get("detail") or f"{atype} failed ({code})")
        return {"id": str((body or {}).get("id") or (body or {}).get("job_id") or job_id), "status": "queued"}

    async def _k8s(self, atype: str, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        if atype == "identity.restart":
            name = payload.get("name") or target
            return await self.keepset.restart("identity", name)

        if not self.infra or not self.infra.apps:
            raise RuntimeError("Kubernetes client is not initialized")
        ns = str(payload.get("namespace") or "default")
        name = str(payload.get("name") or target)
        dry = _dry(payload, atype)
        from ..infrastructure_manager import PROTECTED_NAMESPACES

        if atype == "k8s.pod.delete":
            if ns in PROTECTED_NAMESPACES and ns not in ("platform", "cronnecture-system"):
                raise ValueError(f"refusing to delete pods in {ns}")
            if dry:
                return {"dryRun": True, "name": name, "namespace": ns}
            self.infra.core.delete_namespaced_pod(name, ns)
            return {"deleted": name, "namespace": ns}

        if atype == "k8s.ns.create":
            from kubernetes import client

            if dry:
                return {"dryRun": True, "name": name, "psa": payload.get("psa") or "restricted"}
            body = client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name=name,
                    labels={"pod-security.kubernetes.io/enforce": str(payload.get("psa") or "restricted")},
                )
            )
            self.infra.core.create_namespace(body)
            return {"created": name}

        if atype in ("k8s.restart", "k8s.rollout"):
            if dry:
                return {"dryRun": True, "name": name, "namespace": ns}
            stamp = datetime.now(timezone.utc).isoformat()
            patch = {
                "spec": {
                    "template": {
                        "metadata": {"annotations": {"cronnecture.com/restartedAt": stamp}}
                    }
                }
            }
            self.infra.apps.patch_namespaced_deployment(name, ns, patch)
            return {"restarted": name, "namespace": ns, "at": stamp}

        if atype == "k8s.scale":
            replicas = int(payload.get("replicas") or 0)
            if dry:
                return {"dryRun": True, "name": name, "namespace": ns, "replicas": replicas}
            self.infra.apps.patch_namespaced_deployment(name, ns, {"spec": {"replicas": replicas}})
            return {"scaled": name, "replicas": replicas}

        if atype == "k8s.delete":
            if ns in PROTECTED_NAMESPACES:
                raise ValueError(f"refusing to delete workloads in {ns}")
            if dry:
                return {"dryRun": True, "name": name, "namespace": ns}
            self.infra.apps.delete_namespaced_deployment(name, ns)
            return {"deleted": name, "namespace": ns}

        if atype == "k8s.apply":
            return {"dryRun": True, "accepted": False, "reason": "manifest apply is check-only until confirmed"}

        return {"accepted": True, "type": atype, "dryRun": dry}
