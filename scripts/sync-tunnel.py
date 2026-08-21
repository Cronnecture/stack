#!/usr/bin/env python3
"""Point node-tunnel HTTP origins at Traefik ClusterIP and add stack.cronnecture.com.

Preserves SSH and Wazuh routes. Uses Ansible vault tokens. Does not print secrets.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

VAULT = "/home/dev/ansible/config/inventory/group_vars/all/vault.yml"
PASS = "/home/dev/.ansible/vault_pass"
HTTP_ORIGIN = "http://10.43.125.134:80"
STACK_HOST = "stack.cronnecture.com"
TUNNEL_NAME = "node-tunnel"

REWRITE_PREFIXES = (
    "http://31.97.126.9:30",
    "http://31.97.126.9:301",
    "http://135.181.58.45:80",
)


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

    if STACK_HOST not in hosts:
        kept.append({"hostname": STACK_HOST, "service": HTTP_ORIGIN})
        print(f"added {STACK_HOST}")
    else:
        print(f"kept {STACK_HOST}")

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

    records = cf(
        f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records?type=CNAME&name={STACK_HOST}",
        dns_tok,
    )
    target = f"{tid}.cfargotunnel.com"
    existing = records.get("result") or []
    body = {
        "type": "CNAME",
        "name": STACK_HOST,
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
        print("dns updated", STACK_HOST)
    else:
        cf(
            f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records",
            dns_tok,
            method="POST",
            data=body,
        )
        print("dns created", STACK_HOST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
