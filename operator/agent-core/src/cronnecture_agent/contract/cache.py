"""Short TTL cache so dashboard fan-out does not re-walk Kubernetes/Cloudflare."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class TtlCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._async_wait: dict[str, asyncio.Future] = {}

    def get(self, key: str) -> Any | None:
        row = self._data.get(key)
        if row is None:
            return None
        exp, val = row
        if time.monotonic() >= exp:
            self._data.pop(key, None)
            return None
        return val

    def set(self, key: str, value: Any, ttl: float) -> Any:
        self._data[key] = (time.monotonic() + ttl, value)
        return value

    def cached(self, key: str, ttl: float, fn: Callable[[], T]) -> T:
        hit = self.get(key)
        if hit is not None:
            return hit
        return self.set(key, fn(), ttl)

    async def get_or_load(self, key: str, ttl: float, factory: Callable[[], Awaitable[T]]) -> T:
        hit = self.get(key)
        if hit is not None:
            return hit
        wait = self._async_wait.get(key)
        if wait is not None:
            return await wait
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._async_wait[key] = fut
        try:
            val = await factory()
            self.set(key, val, ttl)
            if not fut.done():
                fut.set_result(val)
            return val
        except Exception as exc:
            if not fut.done():
                fut.set_exception(exc)
            raise
        finally:
            self._async_wait.pop(key, None)


CACHE = TtlCache()
