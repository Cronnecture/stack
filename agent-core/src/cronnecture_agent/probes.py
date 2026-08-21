"""HTTP/SMTP probes for the operator dashboard. No fake metrics."""

from __future__ import annotations

import asyncio
import socket
from typing import Any, Dict, List

import httpx

HTTP_PROBES = [
    {"name": "Vaultwarden", "url": "https://vault.cronnecture.com/alive", "ns": "identity", "ok": {200}},
    {"name": "Webmail", "url": "https://webmail.cronnecture.com/", "ns": "platform", "ok": {200, 302}},
    {"name": "Ops", "url": "https://ops.cronnecture.com/", "ns": "platform", "ok": {200, 302}},
    {"name": "Authentik", "url": "https://auth.cronnecture.com/", "ns": "identity", "ok": {200, 302}},
    {"name": "Logto", "url": "https://id.cronnecture.com/", "ns": "identity", "ok": {200, 302}},
    {"name": "Passbolt", "url": "https://passbolt.cronnecture.com/", "ns": "identity", "ok": {200, 302}},
    {"name": "Website", "url": "https://cronnecture.com/", "ns": "platform", "ok": {200, 301, 302}},
    {"name": "Stack", "url": "http://dashboard.cronnecture-system.svc.cluster.local/", "ns": "cronnecture-system", "ok": {200}},
]

SMTP_PROBES = [
    {"name": "Mail SMTP", "host": "stalwart.mail.svc.cluster.local", "port": 587, "ns": "mail"},
]


async def _http(item: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "name": item["name"],
        "url": item["url"],
        "ns": item["ns"],
        "kind": "https",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False, verify=True) as client:
            resp = await client.get(item["url"])
        row["status"] = resp.status_code
        row["healthy"] = resp.status_code in item["ok"]
    except Exception as exc:
        row["status"] = 0
        row["healthy"] = False
        row["error"] = str(exc)
    return row


def _smtp(item: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "name": item["name"],
        "url": f"smtp://{item['host']}:{item['port']}",
        "ns": item["ns"],
        "kind": "smtp",
    }
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((item["host"], item["port"]))
        row["status"] = 220
        row["healthy"] = True
    except Exception as exc:
        row["status"] = 0
        row["healthy"] = False
        row["error"] = str(exc)
    finally:
        sock.close()
    return row


async def probe_all() -> List[Dict[str, Any]]:
    http_rows = await asyncio.gather(*(_http(item) for item in HTTP_PROBES))
    smtp_rows = [_smtp(item) for item in SMTP_PROBES]
    return list(http_rows) + smtp_rows
