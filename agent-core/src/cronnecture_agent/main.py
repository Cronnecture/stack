"""
Unified Cronnecture control plane: agent-core + live fleet API.
"""

from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import structlog

from .orchestrator import AgentOrchestrator
from .cloudflare import CloudflareStatus
from .probes import probe_all
from .keepset import KeepSetController
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


def _orch(request_app=None) -> AgentOrchestrator:
    return app.state.orchestrator


@app.get("/health")
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
    clients = await orch.infrastructure_manager.list_clients()
    exposure = await orch.infrastructure_manager.exposure()
    routes = await orch.infrastructure_manager.routes()
    cloudflare = await CloudflareStatus().snapshot()
    probes = await probe_all()
    failed = [
        w
        for w in snap.get("workloads", [])
        if w.get("status") not in ("running", "succeeded", "pending", "")
    ]
    return {
        "keep_set": keep,
        "nodes": snap.get("nodes", []),
        "clients": clients,
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


@app.get("/api/identity")
async def identity_status():
    return await KeepSetController(_orch().infrastructure_manager).describe("identity")


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
    return await _orch().infrastructure_manager.list_clients()


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
