"""FastAPI routes that match docs/INTEGRATION.md in cronnecture-control-portal."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from urllib.parse import quote

from .actions import ACTION_TYPES, ActionDispatcher
from .books import delete_file, load_file, load_ledger, save_file, save_ledger
from .envelope import includes, job_view, parse_query
from .reads import API_SURFACES, GUARDS, POLICIES, ContractReads

router = APIRouter()


def _reads(request: Request) -> ContractReads:
    return request.app.state.contract_reads


def _actions(request: Request) -> ActionDispatcher:
    return request.app.state.contract_actions


def _params(request: Request) -> dict[str, Any]:
    return dict(request.query_params)


def _filter(items: list[dict[str, Any]], params: dict[str, Any], *fields: str):
    q = parse_query(params)
    reads = None

    def match(item: dict[str, Any]) -> bool:
        if q["status"] and str(item.get("status") or item.get("health") or item.get("phase") or "").lower() != q["status"]:
            if q["status"] not in str(item.get("status") or item.get("health") or item.get("phase") or "").lower():
                return False
        if q["group"] and str(item.get("group") or "").lower() != q["group"]:
            return False
        if q["namespace"] and str(item.get("namespace") or "").lower() != q["namespace"]:
            return False
        if q["tenant"] and q["tenant"] not in str(item.get("tenant") or item.get("slug") or "").lower():
            return False
        if q["q"]:
            blob = " ".join(str(item.get(f) or "") for f in (fields or item.keys()))
            if not includes(blob, q["q"]):
                return False
        return True

    from .envelope import paginate

    return paginate(items, q, match)


@router.get("/api/me")
async def api_me(request: Request):
    return await _reads(request).operator(request)


@router.get("/api/fleet/shell")
async def fleet_shell(request: Request):
    return await _reads(request).shell(request)


@router.get("/api/fleet/cluster")
async def fleet_cluster():
    return {"cluster": "cronnecture", "k3s": "v1.35.4+k3s1", "traefik": "ClusterIP origin"}


@router.get("/api/fleet/attention")
async def fleet_attention(request: Request):
    reads = _reads(request)
    nodes = await reads.list_nodes()
    jobs = await reads.jobs()
    return reads.attention(nodes, jobs, await reads.certificates())


@router.get("/api/fleet/nodes")
async def fleet_nodes(request: Request):
    items = await _reads(request).list_nodes()
    return _filter(items, _params(request), "hostname", "ip", "group", "provider")


@router.get("/api/fleet/nodes/{node_id}")
async def fleet_node(node_id: str, request: Request):
    node = await _reads(request).get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    return node


@router.get("/api/fleet/guards")
async def fleet_guards(request: Request):
    return _filter(list(GUARDS), _params(request), "id", "title", "scope")


@router.get("/api/k8s/namespaces")
async def k8s_namespaces(request: Request):
    items = await asyncio.to_thread(_reads(request).k8s.namespaces)
    return _filter(items, _params(request), "name", "purpose")


@router.get("/api/k8s/workloads")
async def k8s_workloads(request: Request):
    items = await asyncio.to_thread(_reads(request).k8s.workloads)
    return _filter(items, _params(request), "name", "namespace", "kind")


@router.get("/api/k8s/pods")
async def k8s_pods(request: Request):
    items = await asyncio.to_thread(_reads(request).k8s.pods)
    return _filter(items, _params(request), "name", "namespace", "node", "workload")


@router.get("/api/k8s/secrets")
async def k8s_secrets(request: Request):
    items = await asyncio.to_thread(_reads(request).k8s.secrets)
    return _filter(items, _params(request), "name", "namespace")


@router.get("/api/k8s/netpols")
async def k8s_netpols(request: Request):
    items = await asyncio.to_thread(_reads(request).k8s.netpols)
    return _filter(items, _params(request), "name", "namespace")


@router.get("/api/k8s/events")
async def k8s_events(request: Request):
    items = await asyncio.to_thread(_reads(request).k8s.events)
    return _filter(items, _params(request), "object", "reason")


@router.get("/api/edge/hosts")
async def edge_hosts(request: Request):
    items = await asyncio.to_thread(_reads(request).k8s.routes)
    return _filter(items, _params(request), "host", "namespace", "backend")


@router.get("/api/edge/tunnels")
async def edge_tunnels(request: Request):
    return _filter(await _reads(request).tunnels(), _params(request), "name", "origin")


@router.get("/api/edge/dns")
async def edge_dns(request: Request):
    return _filter(await _reads(request).dns(), _params(request), "name", "content", "type")


@router.get("/api/ansible/playbooks")
async def ansible_playbooks(request: Request):
    return _filter(await _reads(request).playbooks(), _params(request), "tag", "name", "description")


@router.get("/api/ansible/runs")
async def ansible_runs(request: Request):
    return _filter(await _reads(request).ansible_runs(), _params(request), "playbook", "id")


@router.get("/api/ansible/inventory")
async def ansible_inventory(request: Request):
    nodes = await _reads(request).list_nodes()
    return _filter(_reads(request).inventory(nodes), _params(request), "group", "purpose")


@router.get("/api/ansible/vars")
async def ansible_vars(request: Request):
    return _filter(_reads(request).ansible_vars(), _params(request), "key", "value")


@router.get("/api/ansible/policies")
async def ansible_policies(request: Request):
    return _filter(list(POLICIES), _params(request), "id", "title", "file")


@router.get("/api/tenants")
async def tenants(request: Request):
    return _filter(await _reads(request).tenants(), _params(request), "slug", "name", "domain")


@router.get("/api/tenants/{slug}")
async def tenant(slug: str, request: Request):
    row = await _reads(request).get_tenant(slug)
    if not row:
        raise HTTPException(status_code=404, detail="tenant not found")
    return row


@router.get("/api/mail/domains")
async def mail_domains(request: Request):
    return _filter(await _reads(request).mail_domains(), _params(request), "domain", "tenant")


@router.get("/api/mail/boxes")
async def mail_boxes(request: Request):
    return _filter(await _reads(request).mailboxes(), _params(request), "address", "domain")


@router.get("/api/identity")
async def identity(request: Request):
    return _filter(await _reads(request).identity(), _params(request), "name", "url")


@router.get("/api/jobs")
async def jobs(request: Request):
    return _filter(await _reads(request).jobs(), _params(request), "type", "target", "id")


@router.get("/api/jobs/trend")
async def jobs_trend(request: Request):
    jobs = await _reads(request).jobs()
    return _reads(request).job_trend(jobs)


@router.get("/api/jobs/{job_id}")
async def job_detail(job_id: str, request: Request):
    code, body = await _actions(request).platform.get(f"/api/jobs/{job_id}")
    if code >= 400 or not isinstance(body, dict):
        detail = (body or {}).get("detail") if isinstance(body, dict) else "job not found"
        raise HTTPException(status_code=code if code >= 400 else 404, detail=detail)
    return job_view(body)


@router.get("/api/registry/images")
async def registry_images(request: Request):
    return _filter(await _reads(request).images(), _params(request), "name", "tag", "tenant")


@router.get("/api/previews")
async def previews(request: Request):
    return _filter(await _reads(request).previews(), _params(request), "uuid", "name", "path")


@router.get("/api/business/tickets")
async def tickets(request: Request):
    return _filter(await _reads(request).tickets(), _params(request), "title", "tenant", "topic")


@router.get("/api/business/invoices")
async def invoices(request: Request):
    return _filter(await _reads(request).invoices(), _params(request), "id", "tenant")


@router.get("/api/business/books")
async def get_books(request: Request):
    return load_ledger(_reads(request).infra)


@router.put("/api/business/books")
async def put_books(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="JSON body required") from exc
    try:
        save_ledger(_reads(request).infra, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/api/business/books/files/{file_id}")
async def get_book_file(file_id: str):
    try:
        hit = load_file(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not hit:
        raise HTTPException(status_code=404, detail="PDF not found")
    data, name, mime = hit
    safe_name = name.replace('"', "")
    return Response(
        content=data,
        media_type=mime or "application/pdf",
        headers={
            "X-File-Name": quote(safe_name),
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )


@router.put("/api/business/books/files/{file_id}")
async def put_book_file(file_id: str, request: Request):
    data = await request.body()
    name = request.headers.get("x-file-name") or f"{file_id}.pdf"
    mime = request.headers.get("content-type") or "application/pdf"
    try:
        save_file(file_id, data, name, mime.split(";")[0].strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "id": file_id}


@router.delete("/api/business/books/files/{file_id}")
async def delete_book_file(file_id: str):
    try:
        delete_file(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/api/platform/catalog")
async def platform_catalog(request: Request):
    return _filter(list(API_SURFACES), _params(request), "name", "kind", "notes")


@router.get("/api/audit")
async def audit(request: Request):
    return _filter(await _reads(request).list_audit(), _params(request), "actor", "action", "target")


@router.get("/api/health/backups")
async def health_backups(request: Request):
    return _filter(await _reads(request).backups(), _params(request), "id", "target")


@router.get("/api/health/certs")
async def health_certs(request: Request):
    return _filter(await _reads(request).certificates(), _params(request), "host")


@router.get("/api/health/cron")
async def health_cron(request: Request):
    return _filter(_reads(request).crons(), _params(request), "name", "schedule")


@router.get("/api/search")
async def search(request: Request):
    q = request.query_params.get("q") or ""
    return await _reads(request).search(q)


@router.post("/api/jobs")
async def enqueue(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON body required: {exc}") from exc
    atype = str((body or {}).get("type") or "").strip()
    if atype not in ACTION_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown action type: {atype}")
    actor = _reads(request).operator_from_request(request).get("email") or "operator"
    try:
        result = await _actions(request).dispatch(body or {}, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    out = dict(result) if isinstance(result, dict) else {"id": str(result)}
    out["id"] = str(out.get("id") or "")
    return out
