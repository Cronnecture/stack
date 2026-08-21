"""Read-only Cloudflare edge status for the control plane dashboard."""

from __future__ import annotations

import os
from typing import Any, Dict

import httpx
import structlog

logger = structlog.get_logger()

HTTP_HOSTS = [
    "vault.cronnecture.com",
    "webmail.cronnecture.com",
    "ops.cronnecture.com",
    "client.cronnecture.com",
    "auth.cronnecture.com",
    "id.cronnecture.com",
    "id-admin.cronnecture.com",
    "passbolt.cronnecture.com",
    "passkeys.cronnecture.com",
    "stack.cronnecture.com",
    "cronnecture.com",
    "www.cronnecture.com",
]


class CloudflareStatus:
    def __init__(self) -> None:
        self.account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        self.zone_id = os.environ.get("CLOUDFLARE_ZONE_ID", "")
        self.token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        self.tunnel_id = os.environ.get("CLOUDFLARE_TUNNEL_ID", "")
        self.http_origin = os.environ.get("CLOUDFLARE_HTTP_ORIGIN", "http://10.43.125.134:80")

    @property
    def configured(self) -> bool:
        return bool(self.account_id and self.zone_id and self.token)

    async def snapshot(self) -> Dict[str, Any]:
        if not self.configured:
            return {
                "configured": False,
                "message": "Cloudflare secret not mounted",
                "http_origin": self.http_origin,
            }
        headers = {"Authorization": f"Bearer {self.token}"}
        base = "https://api.cloudflare.com/client/v4"
        out: Dict[str, Any] = {
            "configured": True,
            "http_origin": self.http_origin,
            "tunnel_id": self.tunnel_id,
            "routes": [],
            "dns": [],
            "errors": [],
        }
        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            try:
                tunnels = await client.get(f"{base}/accounts/{self.account_id}/cfd_tunnel")
                tunnels.raise_for_status()
                payload = tunnels.json()
                names = [
                    {"name": t.get("name"), "id": t.get("id"), "deleted": bool(t.get("deleted_at"))}
                    for t in payload.get("result") or []
                    if not t.get("deleted_at")
                ]
                out["tunnels"] = names
                tid = self.tunnel_id or next(
                    (t["id"] for t in names if t.get("name") == "node-tunnel"), ""
                )
                out["tunnel_id"] = tid
                if tid:
                    cfg = await client.get(
                        f"{base}/accounts/{self.account_id}/cfd_tunnel/{tid}/configurations"
                    )
                    cfg.raise_for_status()
                    ingress = (
                        ((cfg.json().get("result") or {}).get("config") or {}).get("ingress") or []
                    )
                    for rule in ingress:
                        out["routes"].append(
                            {
                                "hostname": rule.get("hostname") or "*",
                                "service": rule.get("service"),
                                "via_traefik": (rule.get("service") or "") == self.http_origin,
                            }
                        )
            except Exception as exc:
                logger.warning("cloudflare tunnel status failed", error=str(exc))
                out["errors"].append(str(exc))
            try:
                dns = await client.get(
                    f"{base}/zones/{self.zone_id}/dns_records",
                    params={"per_page": 100},
                )
                dns.raise_for_status()
                wanted = set(HTTP_HOSTS) | {"mail.cronnecture.com"}
                for rec in dns.json().get("result") or []:
                    if rec.get("name") in wanted:
                        out["dns"].append(
                            {
                                "name": rec.get("name"),
                                "type": rec.get("type"),
                                "content": rec.get("content"),
                                "proxied": rec.get("proxied"),
                            }
                        )
            except Exception as exc:
                logger.warning("cloudflare dns status failed", error=str(exc))
                out["errors"].append(str(exc))
        http_routes = [r for r in out.get("routes", []) if (r.get("service") or "").startswith("http://")]
        out["http_on_traefik"] = all(r.get("via_traefik") for r in http_routes) if http_routes else False
        out["stack_routed"] = any(r.get("hostname") == "stack.cronnecture.com" for r in out.get("routes", []))
        return out
