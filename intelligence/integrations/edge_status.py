#!/usr/bin/env python3
"""Read-only Cloudflare edge heartbeat. Does not change DNS, WAF, or tunnels."""

import asyncio
import logging
import os
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cloudflare-edge")


async def heartbeat() -> None:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    enabled = os.environ.get("CLOUDFLARE_ENABLED", "").lower() in ("1", "true", "yes")
    if not enabled or not token or not account:
        log.info("idle: Cloudflare credentials missing or CLOUDFLARE_ENABLED=false")
        while True:
            time.sleep(3600)

    import aiohttp

    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/cfd_tunnel"
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    data = await resp.json()
            tunnels = [t.get("name") for t in data.get("result") or [] if not t.get("deleted_at")]
            log.info("cloudflare ok tunnels=%s", ",".join(tunnels))
        except Exception as exc:
            log.warning("cloudflare heartbeat failed: %s", exc)
        await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(heartbeat())
