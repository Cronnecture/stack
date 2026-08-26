"""East-west calls to the platform control-plane (CRM, jobs, mail, home).

The operator UI talks only to this stack. Platform remains the product API
(portals, billing, provision jobs) and is not an operator surface.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger()

DEFAULT_URL = "http://control-plane.platform.svc.cluster.local:8080"
PROTECTED_SLUGS = {"noorddriveautos", "cronnecture", "previews"}


class PlatformAPI:
    def __init__(self) -> None:
        self.base = (os.environ.get("PLATFORM_API") or DEFAULT_URL).rstrip("/")
        self.token = (os.environ.get("OPS_API_TOKEN") or "").strip()
        self._http: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=2.0),
                follow_redirects=False,
            )
        return self._http

    @property
    def configured(self) -> bool:
        return bool(self.token)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[dict] = None,
    ) -> tuple[int, Any]:
        if not self.configured:
            return 503, {"detail": "Platform API token is not mounted"}
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = await self._client().request(
            method,
            f"{self.base}{path}",
            headers=headers,
            json=json,
            params=params,
        )
        try:
            body = resp.json() if resp.content else {}
        except Exception:
            body = {"detail": resp.text[:400]}
        return resp.status_code, body

    async def get(self, path: str, params: Optional[dict] = None) -> tuple[int, Any]:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: Any = None) -> tuple[int, Any]:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, json: Any = None) -> tuple[int, Any]:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str, params: Optional[dict] = None) -> tuple[int, Any]:
        return await self.request("DELETE", path, params=params)


def is_protected_slug(slug: str) -> bool:
    s = (slug or "").strip().lower().removeprefix("client-")
    extra = {
        x.strip()
        for x in os.environ.get("KEEP_CLIENT_NAMESPACES", "").split(",")
        if x.strip()
    }
    extra = {x.removeprefix("client-") for x in extra}
    return s in PROTECTED_SLUGS or s in extra
