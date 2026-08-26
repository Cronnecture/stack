"""Read-only Cloudflare edge status for the control plane dashboard."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict

import httpx
import structlog

logger = structlog.get_logger()

_SNAP_TTL = 120.0

HTTP_HOSTS = [
    "vault.cronnecture.com",
    "webmail.cronnecture.com",
    "ops.cronnecture.com",
    "control.cronnecture.com",
    "stack.cronnecture.com",
    "client.cronnecture.com",
    "auth.cronnecture.com",
    "id.cronnecture.com",
    "id-admin.cronnecture.com",
    "passbolt.cronnecture.com",
    "cronnecture.com",
    "www.cronnecture.com",
]


class CloudflareStatus:
    def __init__(self) -> None:
        self.account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        self.zone_id = os.environ.get("CLOUDFLARE_ZONE_ID", "")
        self.token = (
            os.environ.get("CLOUDFLARE_READONLY_TOKEN")
            or os.environ.get("CLOUDFLARE_API_TOKEN")
            or ""
        )
        self.tunnel_id = os.environ.get("CLOUDFLARE_TUNNEL_ID", "")
        self.http_origin = os.environ.get("CLOUDFLARE_HTTP_ORIGIN", "http://10.43.125.134:80")
        self._snap: Dict[str, Any] | None = None
        self._snap_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.account_id and self.zone_id and self.token)

    async def snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        if self._snap is not None and now - self._snap_at < _SNAP_TTL:
            return self._snap
        out = await self._snapshot()
        self._snap, self._snap_at = out, now
        return out

    async def _snapshot(self) -> Dict[str, Any]:
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
            "certificates": [],
            "errors": [],
        }
        timeout = httpx.Timeout(1.2, connect=0.6)
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            async def _tunnels():
                tunnels = await client.get(f"{base}/accounts/{self.account_id}/cfd_tunnel")
                tunnels.raise_for_status()
                payload = tunnels.json()
                names = [
                    {"name": t.get("name"), "id": t.get("id"), "deleted": bool(t.get("deleted_at"))}
                    for t in payload.get("result") or []
                    if not t.get("deleted_at")
                ]
                tid = self.tunnel_id or next(
                    (t["id"] for t in names if t.get("name") == "node-tunnel"), ""
                )
                routes = []
                if tid:
                    cfg = await client.get(
                        f"{base}/accounts/{self.account_id}/cfd_tunnel/{tid}/configurations"
                    )
                    cfg.raise_for_status()
                    ingress = (
                        ((cfg.json().get("result") or {}).get("config") or {}).get("ingress") or []
                    )
                    for rule in ingress:
                        routes.append(
                            {
                                "hostname": rule.get("hostname") or "*",
                                "service": rule.get("service"),
                                "via_traefik": (rule.get("service") or "") == self.http_origin,
                            }
                        )
                return names, tid, routes

            async def _dns():
                dns = await client.get(
                    f"{base}/zones/{self.zone_id}/dns_records",
                    params={"per_page": 100},
                )
                dns.raise_for_status()
                wanted = set(HTTP_HOSTS) | {"mail.cronnecture.com"}
                rows = []
                for rec in dns.json().get("result") or []:
                    if rec.get("name") in wanted:
                        rows.append(
                            {
                                "name": rec.get("name"),
                                "type": rec.get("type"),
                                "content": rec.get("content"),
                                "proxied": rec.get("proxied"),
                            }
                        )
                return rows

            tun_res, dns_res = await asyncio.gather(_tunnels(), _dns(), return_exceptions=True)
            if isinstance(tun_res, Exception):
                logger.warning("cloudflare tunnel status failed", error=str(tun_res))
                out["errors"].append(str(tun_res))
            else:
                names, tid, routes = tun_res
                out["tunnels"] = names
                out["tunnel_id"] = tid
                out["routes"] = routes
            if isinstance(dns_res, Exception):
                logger.warning("cloudflare dns status failed", error=str(dns_res))
                out["errors"].append(str(dns_res))
            else:
                out["dns"] = dns_res
            # Certificate packs need Zone SSL read; this token 403s. Public TLS
            # probes on HTTP_HOSTS fill /api/health/certs instead.
        http_routes = [r for r in out.get("routes", []) if (r.get("service") or "").startswith("http://")]
        out["http_on_traefik"] = all(r.get("via_traefik") for r in http_routes) if http_routes else False
        out["control_routed"] = any(r.get("hostname") == "control.cronnecture.com" for r in out.get("routes", []))
        out["stack_routed"] = any(r.get("hostname") == "stack.cronnecture.com" for r in out.get("routes", []))
        return out
