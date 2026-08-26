#!/usr/bin/env python3
"""Point node-tunnel HTTP origins at Traefik ClusterIP and add operator hostnames.

Preserves SSH and Wazuh routes. Uses Ansible vault tokens. Does not print secrets.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from stack_paths import vault_file, vault_pass_file

VAULT = str(vault_file())
PASS = str(vault_pass_file())
HTTP_ORIGIN = "http://10.43.125.134:80"
CONTROL_HOST = "control.cronnecture.com"
STACK_HOST = "stack.cronnecture.com"
TUNNEL_NAME = "node-tunnel"
OPERATOR_HOSTS = (CONTROL_HOST, STACK_HOST)


def vault_values() -> dict[str, str]:
    raw = subprocess.check_output(
        ["ansible-vault", "view", VAULT, "--vault-password-file", PASS],
        text=True,
    )
    vals: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k.startswith("vault_cf_"):
            vals[k] = v
    return vals


def cf(url: str, token: str, method: str = "GET", data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.load(resp)
    if not payload.get("success", False):
        raise SystemExit(f"Cloudflare API error: {payload.get('errors')}")
    return payload


def rewrite_service(service: str) -> str:
    if not service.startswith("http://"):
        return service
    if service.startswith("https://"):
        return service
    if service == HTTP_ORIGIN:
        return service
    if service.startswith("http://31.97.126.9:") or service.startswith("http://135.181.58.45:80"):
        return HTTP_ORIGIN
    return service


def ensure_dns(dns_tok: str, zone: str, hostname: str, target: str) -> None:
    records = cf(
        f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records?type=CNAME&name={hostname}",
        dns_tok,
    )
    existing = records.get("result") or []
    body = {
        "type": "CNAME",
        "name": hostname,
        "content": target,
        "proxied": True,
        "ttl": 1,
    }
    if existing:
        rid = existing[0]["id"]
        cf(
            f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records/{rid}",
            dns_tok,
            method="PUT",
            data=body,
        )
        print("dns updated", hostname)
    else:
        cf(
            f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records",
            dns_tok,
            method="POST",
            data=body,
        )
        print("dns created", hostname)


def ensure_access(vals: dict[str, str]) -> None:
    token = vals.get("vault_cf_access_token") or ""
    acct = vals["vault_cf_account_id"]
    if not token:
        print("access token missing; skip Zero Trust app for", CONTROL_HOST)
        return
    try:
        apps = cf(
            f"https://api.cloudflare.com/client/v4/accounts/{acct}/access/apps?per_page=100",
            token,
        )
    except Exception as exc:
        print("access list failed:", type(exc).__name__)
        return
    ops_app = None
    control_app = None
    for app in apps.get("result") or []:
        domains = []
        if app.get("domain"):
            domains.append(app["domain"])
        for item in app.get("self_hosted_domains") or []:
            if isinstance(item, str):
                domains.append(item)
            elif isinstance(item, dict):
                domains.append(item.get("self_hosted_domain") or item.get("domain") or "")
        if "ops.cronnecture.com" in domains:
            ops_app = app
        if CONTROL_HOST in domains:
            control_app = app
    if control_app:
        print("access kept", CONTROL_HOST)
        return
    if not ops_app:
        print("no ops Access app to clone")
        return
    payload = {
        "name": "Cronnecture Control",
        "domain": CONTROL_HOST,
        "type": ops_app.get("type") or "self_hosted",
        "session_duration": ops_app.get("session_duration") or "8h",
        "auto_redirect_to_identity": bool(ops_app.get("auto_redirect_to_identity", True)),
        "allowed_idps": ops_app.get("allowed_idps") or [],
        "app_launcher_visible": True,
    }
    created = cf(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/access/apps",
        token,
        method="POST",
        data=payload,
    )
    new_id = (created.get("result") or {}).get("id")
    print("access app created", CONTROL_HOST)
    if not new_id:
        return
    policies = cf(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/access/apps/{ops_app['id']}/policies",
        token,
    )
    for pol in policies.get("result") or []:
        body = {
            "name": pol.get("name") or "Allow operators",
            "decision": pol.get("decision") or "allow",
            "include": pol.get("include") or [],
            "exclude": pol.get("exclude") or [],
            "require": pol.get("require") or [],
        }
        cf(
            f"https://api.cloudflare.com/client/v4/accounts/{acct}/access/apps/{new_id}/policies",
            token,
            method="POST",
            data=body,
        )
    print("access policies copied")


def main() -> int:
    vals = vault_values()
    acct = vals["vault_cf_account_id"]
    tunnel_tok = vals["vault_cf_tunnel_token"]
    dns_tok = vals["vault_cf_dns_token"]
    zone = vals["vault_cf_zone_id"]

    tunnels = cf(f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel", tunnel_tok)
    tunnel = next(
        t for t in tunnels["result"] if t.get("name") == TUNNEL_NAME and not t.get("deleted_at")
    )
    tid = tunnel["id"]
    cfg = cf(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel/{tid}/configurations",
        tunnel_tok,
    )
    config = (cfg.get("result") or {}).get("config") or {}
    ingress = list(config.get("ingress") or [])

    catch_all = None
    kept = []
    hosts = set()
    for rule in ingress:
        if not rule.get("hostname"):
            catch_all = rule
            continue
        rule = dict(rule)
        rule["service"] = rewrite_service(rule.get("service") or "")
        kept.append(rule)
        hosts.add(rule["hostname"])

    for host in OPERATOR_HOSTS:
        if host not in hosts:
            kept.append({"hostname": host, "service": HTTP_ORIGIN})
            print(f"added {host}")
        else:
            print(f"kept {host}")

    if catch_all is None:
        catch_all = {"service": "http_status:404"}
    new_ingress = kept + [catch_all]

    for rule in new_ingress:
        host = rule.get("hostname") or "*"
        print(f"  {host} -> {rule.get('service')}")

    put = cf(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel/{tid}/configurations",
        tunnel_tok,
        method="PUT",
        data={"config": {**config, "ingress": new_ingress}},
    )
    print("tunnel configuration updated", put.get("success"))

    target = f"{tid}.cfargotunnel.com"
    for host in OPERATOR_HOSTS:
        ensure_dns(dns_tok, zone, host, target)

    ensure_access(vals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
