"""Logto Management API helper for stack-provisioned clients."""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

import httpx
import structlog

logger = structlog.get_logger()

_DEFAULT_RESOURCE = "https://default.logto.app/api"


class LogtoAdmin:
    def __init__(self) -> None:
        self.public = (os.environ.get("LOGTO_ENDPOINT") or "https://id.cronnecture.com").rstrip("/")
        self.management = (
            os.environ.get("LOGTO_MANAGEMENT_ENDPOINT")
            or os.environ.get("LOGTO_INTERNAL_ENDPOINT")
            or "http://logto.identity.svc.cluster.local:3001"
        ).rstrip("/")
        self.m2m_id = (os.environ.get("LOGTO_M2M_APP_ID") or "").strip()
        self.m2m_secret = (os.environ.get("LOGTO_M2M_APP_SECRET") or "").strip()
        self.resource = (os.environ.get("LOGTO_M2M_RESOURCE") or _DEFAULT_RESOURCE).strip()

    @property
    def configured(self) -> bool:
        return bool(self.m2m_id and self.m2m_secret)

    async def discovery(self) -> Dict[str, Any]:
        url = f"{self.public}/oidc/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            resp = await client.get(url)
        data = resp.json() if resp.content else {}
        auth = str(data.get("authorization_endpoint") or "")
        token = str(data.get("token_endpoint") or "")
        issuer = str(data.get("issuer") or "")
        https = (
            issuer.startswith("https://")
            and auth.startswith("https://")
            and token.startswith("https://")
        )
        return {
            "url": url,
            "status": resp.status_code,
            "issuer": issuer,
            "authorization_endpoint": auth,
            "token_endpoint": token,
            "https": https,
            "healthy": resp.status_code == 200 and https,
        }

    async def snapshot(self) -> Dict[str, Any]:
        disc = await self.discovery()
        out: Dict[str, Any] = {
            "configured": self.configured,
            "endpoint": self.public,
            "management": self.management,
            "oidc": disc,
        }
        if not self.configured:
            out["apps"] = []
            return out
        try:
            apps = await self._api("GET", "/api/applications")
            rows = apps if isinstance(apps, list) else []
            out["apps"] = [
                {"id": a.get("id"), "name": a.get("name"), "type": a.get("type")}
                for a in rows
                if isinstance(a, dict)
            ]
            out["app_count"] = len(out["apps"])
        except Exception as exc:
            logger.warning("logto applications list failed", error=str(exc))
            out["error"] = str(exc)
        return out

    async def ensure_client_app(self, client_id: str, domain: str) -> Dict[str, Any]:
        if not self.configured:
            return {"configured": False, "skipped": True}
        name = f"stack-{client_id}"
        origin = f"https://{domain}"
        existing = await self._find_app(name)
        body = {
            "name": name,
            "description": f"Provisioned by stack for {client_id}",
            "type": "Traditional",
            "oidcClientMetadata": {
                "redirectUris": [f"{origin}/oauth2/callback", f"{origin}/"],
                "postLogoutRedirectUris": [origin, f"{origin}/"],
            },
        }
        if existing:
            app_id = existing["id"]
            await self._api("PATCH", f"/api/applications/{app_id}", json=body)
            secret = existing.get("secret") or ""
        else:
            created = await self._api("POST", "/api/applications", json=body)
            app_id = created["id"]
            secret = created.get("secret") or ""
        return {
            "configured": True,
            "app_id": app_id,
            "app_secret": secret,
            "name": name,
            "issuer": f"{self.public}/oidc",
        }

    async def delete_client_app(self, app_id: Optional[str], client_id: str) -> Dict[str, Any]:
        if not self.configured:
            return {"configured": False, "skipped": True}
        if not app_id:
            found = await self._find_app(f"stack-{client_id}")
            app_id = (found or {}).get("id")
        if not app_id:
            return {"configured": True, "deleted": False, "reason": "not found"}
        await self._api("DELETE", f"/api/applications/{app_id}")
        return {"configured": True, "deleted": True, "app_id": app_id}

    async def _find_app(self, name: str) -> Optional[Dict[str, Any]]:
        apps = await self._api("GET", "/api/applications")
        for row in apps if isinstance(apps, list) else []:
            if isinstance(row, dict) and row.get("name") == name:
                return row
        return None

    async def _token(self) -> str:
        basic = base64.b64encode(f"{self.m2m_id}:{self.m2m_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.management}/oidc/token",
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "client_credentials",
                    "resource": self.resource,
                    "scope": "all",
                },
            )
        resp.raise_for_status()
        token = (resp.json() or {}).get("access_token")
        if not token:
            raise RuntimeError("Logto M2M token missing access_token")
        return token

    async def _api(self, method: str, path: str, json: Optional[dict] = None) -> Any:
        token = await self._token()
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(
                method,
                f"{self.management}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=json,
            )
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise RuntimeError(f"Logto {method} {path} -> {resp.status_code} {resp.text[:300]}")
        if not resp.content:
            return {}
        return resp.json()
