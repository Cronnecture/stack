#!/usr/bin/env python3
"""Control portal Docs board talks to agent-core /api/portal-docs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROUTER = (ROOT / "router.py").read_text(encoding="utf-8")


def must(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"OK: {msg}")


def main() -> None:
    must("/api/portal-docs" in ROUTER, "portal-docs route")
    must("_proxy_portal_docs" in ROUTER, "proxies to control-plane-legacy")
    must("platform.request" in ROUTER, "uses PlatformAPI")
    print("portal-docs proxy characterization passed.")


if __name__ == "__main__":
    main()
