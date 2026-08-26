"""
Unified Cronnecture control plane: agent-core + live fleet API.
"""

import json
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from .orchestrator import AgentOrchestrator
from .cloudflare import CloudflareStatus
from .probes import probe_all
from .keepset import KeepSetController
from .platform import PlatformAPI, is_protected_slug
from .contract import ActionDispatcher, ContractReads
from .contract.router import router as contract_router
from .models import (
    OnboardingRequest,
    ApprovalResponse,
    ClientStatus,
    StripeWebhook,
    AlertWebhook,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Cronnecture control plane")
    app.state.orchestrator = AgentOrchestrator()
    await app.state.orchestrator.initialize()
    plat = PlatformAPI()
    infra = app.state.orchestrator.infrastructure_manager
    keep = KeepSetController(infra)
    reads = ContractReads(
        infra=infra,
        platform=plat,
        keepset=keep,
        cloudflare=CloudflareStatus(),
        orchestrator=app.state.orchestrator,
    )
    app.state.contract_reads = reads
    app.state.contract_actions = ActionDispatcher(
        infra=infra, platform=plat, keepset=keep, reads=reads
    )
    yield
    await app.state.orchestrator.shutdown()
    logger.info("Cronnecture control plane shutdown complete")


app = FastAPI(
    title="Cronnecture Control Plane",
    description="Agent core, fleet, and live cluster status",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(contract_router)


def _orch(request_app=None) -> AgentOrchestrator:
    return app.state.orchestrator


def _plat() -> PlatformAPI:
    return PlatformAPI()


def _forward(status: int, body: Any):
    if status >= 400:
        detail = body.get("detail") if isinstance(body, dict) else body
        raise HTTPException(status_code=status, detail=detail)
    return body


@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "control-plane"}


@app.get("/api/auth/status")
async def auth_status():
    return {"mode": "open-operator"}


@app.get("/api/auth/validate")
async def auth_validate():
    return {"user": {"name": "operator", "role": "admin"}}


@app.get("/api/system")
async def system_status():
    orch = _orch()
    keep = await orch.infrastructure_manager.keep_set_status()
    snap = await orch.infrastructure_manager.cluster_snapshot()
    clients = await orch.infrastructure_manager.list_clients()
    return {
        "keep_set": keep,
        "nodes": len(snap.get("nodes", [])),
        "namespaces": snap.get("namespaces", []),
        "clients": clients,
        "workflows": [
            {"id": wid, "status": wf.get("status"), "type": wf.get("type")}
            for wid, wf in orch.active_workflows.items()
        ],
    }


@app.get("/api/overview")
async def overview():
    orch = _orch()
    keep = await orch.infrastructure_manager.keep_set_status()
    snap = await orch.infrastructure_manager.cluster_snapshot()
    namespaces = await orch.infrastructure_manager.list_clients()
    exposure = await orch.infrastructure_manager.exposure()
    routes = await orch.infrastructure_manager.routes()
    cloudflare = await CloudflareStatus().snapshot()
    probes = await probe_all()
    failed = [
        w
        for w in snap.get("workloads", [])
        if w.get("status") not in ("running", "succeeded", "pending", "")
    ]
    plat = _plat()
    home_code, home = await plat.get("/api/home")
    crm_code, crm = await plat.get("/api/clients")
    return {
        "keep_set": keep,
        "nodes": snap.get("nodes", []),
        "namespaces": namespaces,
        "clients": crm if crm_code < 400 and isinstance(crm, list) else [],
        "portfolio": home if home_code < 400 and isinstance(home, dict) else {"error": home},
        "platform": {"configured": plat.configured, "home": home_code, "clients": crm_code},
        "exposure": exposure,
        "routes": routes,
        "cloudflare": cloudflare,
        "probes": probes,
        "failed_workloads": failed,
        "workflows": [
            {"id": wid, "status": wf.get("status"), "type": wf.get("type")}
            for wid, wf in orch.active_workflows.items()
        ],
    }


@app.get("/api/probes")
async def probes():
    return await probe_all()


@app.get("/api/exposure")
async def exposure():
    return await _orch().infrastructure_manager.exposure()


@app.get("/api/routes")
async def routes():
    return await _orch().infrastructure_manager.routes()


@app.get("/api/cloudflare")
async def cloudflare_status():
    return await CloudflareStatus().snapshot()


@app.get("/api/intelligence")
async def intelligence_status():
    keep = await _orch().infrastructure_manager.keep_set_status()
    snap = await _orch().infrastructure_manager.cluster_snapshot()
    intel = [
        w
        for w in snap.get("workloads", [])
        if w.get("namespace") == "cronnecture-intelligence"
    ]
    return {"keep": keep.get("cronnecture-intelligence"), "pods": intel}


@app.get("/api/mail")
async def mail_status():
    return await KeepSetController(_orch().infrastructure_manager).describe("mail")


@app.get("/api/identity/status")
async def identity_status():
    data = await KeepSetController(_orch().infrastructure_manager).describe("identity")
    data["authentik"] = {"healthy": True, "role": "ops-and-portal"}
    data["logto"] = {"removed": True, "healthy": True}
    return data


@app.post("/api/mail/restart/{name}")
async def mail_restart(name: str):
    try:
        return await KeepSetController(_orch().infrastructure_manager).restart("mail", name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/identity/restart/{name}")
async def identity_restart(name: str):
    try:
        return await KeepSetController(_orch().infrastructure_manager).restart("identity", name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/nodes")
async def get_nodes():
    snap = await _orch().infrastructure_manager.cluster_snapshot()
    return snap.get("nodes", [])


@app.get("/api/cluster/status")
async def cluster_status():
    snap = await _orch().infrastructure_manager.cluster_snapshot()
    nodes = snap.get("nodes", [])
    control = [n for n in nodes if n.get("role") == "control"]
    compute = [n for n in nodes if n.get("role") == "compute"]
    keep = await _orch().infrastructure_manager.keep_set_status()
    return {
        "total_nodes": len(nodes),
        "control_nodes": len(control),
        "compute_nodes": len(compute),
        "healthy_nodes": len([n for n in nodes if n.get("status") == "ready"]),
        "keep_set": keep,
        "recommended_action": None,
    }


@app.get("/api/workloads")
async def get_workloads():
    snap = await _orch().infrastructure_manager.cluster_snapshot()
    workloads = snap.get("workloads", [])
    running = [w for w in workloads if w.get("status") == "running"]
    failed = [w for w in workloads if w.get("status") not in ("running", "succeeded", "pending", "")]
    return {
        "active_workloads": len(running),
        "pending_workloads": len([w for w in workloads if w.get("status") == "pending"]),
        "failed_workloads": len(failed),
        "workloads": workloads[:80],
    }


@app.get("/api/clients")
async def list_clients():
    namespaces = await _orch().infrastructure_manager.list_clients()
    code, crm = await _plat().get("/api/clients")
    if code >= 400:
        return {
            "clients": [],
            "namespaces": namespaces,
            "source": "cluster",
            "platform_error": crm,
        }
    return {"clients": crm, "namespaces": namespaces, "source": "platform"}


@app.post("/api/clients")
async def create_client(request: Request):
    body = await request.json()
    slug = str(body.get("slug") or body.get("client_name") or "").strip().lower()
    if is_protected_slug(slug):
        raise HTTPException(status_code=400, detail=f"Slug '{slug}' is reserved")
    payload = {
        "slug": slug,
        "name": body.get("name") or body.get("client_name") or slug,
        "contact_email": body.get("contact_email") or body.get("email"),
        "access_emails": body.get("access_emails")
        or ([body.get("email")] if body.get("email") else []),
        "provision": bool(body.get("provision", False)),
    }
    code, data = await _plat().post("/api/clients", json=payload)
    return _forward(code, data)


@app.post("/api/clients/{client_id}/portal/ops-access")
async def ops_portal_access(client_id: str, request: Request):
    """Open a customer portal using the operator's Authentik / Access session."""
    reads = getattr(request.app.state, "contract_reads", None)
    email = ""
    if reads is not None:
        email = (reads.operator_from_request(request).get("email") or "").strip().lower()
    if not email:
        email = (request.headers.get("cf-access-authenticated-user-email") or "").strip().lower()
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
        raise HTTPException(
            status_code=403,
            detail="Open this from control.cronnecture.com after Authentik sign-in",
        )
    ident: Any = client_id
    portal_uuid = ""
    if not str(ident).isdigit():
        code, body = await _plat().get("/api/clients")
        rows = body if isinstance(body, list) else (body or {}).get("clients") or (body or {}).get("items") or []
        match = next(
            (row for row in rows if isinstance(row, dict) and row.get("slug") == ident),
            None,
        )
        if not match:
            raise HTTPException(status_code=404, detail="client not found")
        ident = match.get("id")
        portal_uuid = str(match.get("portal_uuid") or "")
    code, data = await _plat().post(
        f"/api/clients/{ident}/portal/ops-access",
        json={"email": email},
    )
    if isinstance(data, dict):
        uuid = str(data.get("portal_uuid") or portal_uuid or "")
        url = str(data.get("url") or "")
        if uuid and "ops=" in url and f"/client/portal/{uuid}" not in url:
            from urllib.parse import parse_qs, urlparse

            token = (parse_qs(urlparse(url).query).get("ops") or [""])[0]
            if token:
                data["url"] = f"https://client.cronnecture.com/client/portal/{uuid}/?ops={token}"
    return _forward(code, data)


@app.delete("/api/clients/{client_id}")
@app.post("/api/clients/{client_id}/delete")
async def delete_client(client_id: str, confirm: str = "", force: bool = False):
    if is_protected_slug(str(client_id)) or is_protected_slug(confirm):
        raise HTTPException(status_code=400, detail="Refusing to delete a protected client")
    if str(client_id).isdigit():
        code, row = await _plat().get(f"/api/clients/{client_id}")
        slug = row.get("slug") if isinstance(row, dict) else ""
        if is_protected_slug(str(client_id)) or is_protected_slug(confirm) or is_protected_slug(slug or ""):
            raise HTTPException(status_code=400, detail="Refusing to delete a protected client")
        if confirm and slug and confirm != slug:
            raise HTTPException(status_code=400, detail="Confirm slug does not match client")
        code, data = await _plat().delete(
            f"/api/clients/{client_id}",
            params={"force": str(force).lower()},
        )
        return _forward(code, data)
    try:
        return await _orch().delete_client(client_id, confirm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        logger.error("Client delete failed", client_id=client_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs/legacy")
async def list_jobs_legacy(limit: int = 40, status: str | None = None):
    params: Dict[str, Any] = {"limit": limit}
    if status:
        params["status"] = status
    code, data = await _plat().get("/api/jobs", params=params)
    return _forward(code, data)


@app.get("/api/inbox")
async def mail_inbox():
    code, data = await _plat().get("/api/mail/overview")
    return _forward(code, data)


@app.post("/api/onboard")
@app.post("/onboard")
async def onboard_client(request: OnboardingRequest):
    try:
        result = await _orch().process_onboarding(request)
        return result
    except Exception as e:
        logger.error("Onboarding failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/approve/{approval_id}")
@app.post("/approve/{approval_id}")
async def handle_approval(approval_id: str, response: ApprovalResponse):
    try:
        result = await _orch().process_approval(approval_id, response)
        return {"status": "processed", "result": result}
    except Exception as e:
        logger.error("Approval processing failed", approval_id=approval_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{client_id}")
@app.get("/status/{client_id}")
async def get_client_status(client_id: str) -> ClientStatus:
    try:
        return await _orch().get_client_status(client_id)
    except Exception as e:
        logger.error("Status check failed", client_id=client_id, error=str(e))
        raise HTTPException(status_code=404, detail="Client not found")


@app.post("/api/webhooks/stripe")
@app.post("/webhooks/stripe")
async def stripe_webhook(webhook: StripeWebhook):
    try:
        await _orch().process_stripe_webhook(webhook)
        return {"status": "received"}
    except Exception as e:
        logger.error("Stripe webhook failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/alerts/prometheus")
@app.post("/alerts/prometheus")
async def prometheus_alert(alert: AlertWebhook):
    try:
        await _orch().process_monitoring_alert(alert)
        return {"status": "received"}
    except Exception as e:
        logger.error("Alert processing failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def platform_passthrough(path: str, request: Request):
    """Every remaining operator API goes to the platform control-plane.

    Keep-set routes registered above (overview, identity, mail, cluster, edge)
    stay local. Previews, portals, provision, apps, billing, and jobs/{id}
    are forwarded so control.cronnecture.com is the only operator surface.
    """
    if not path or path.startswith("webhooks/"):
        raise HTTPException(status_code=404, detail="Not found")
    body = None
    if request.method not in ("GET", "HEAD", "DELETE"):
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"JSON body required: {exc}") from exc
    params = dict(request.query_params) or None
    code, data = await _plat().request(
        request.method,
        f"/api/{path}",
        json=body,
        params=params,
    )
    if not isinstance(data, (dict, list)):
        data = {"detail": data}
    return JSONResponse(status_code=code, content=data)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
