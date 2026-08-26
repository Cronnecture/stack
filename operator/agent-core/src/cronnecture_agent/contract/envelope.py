"""ListResult + query helpers matching the control-portal BFF contract."""

from __future__ import annotations

from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")

DEFAULT_LIMIT = 200
MAX_LIMIT = 500


def parse_query(params: dict[str, Any] | None) -> dict[str, Any]:
    raw = params or {}
    limit_raw = raw.get("limit")
    try:
        limit = int(limit_raw) if limit_raw not in (None, "") else DEFAULT_LIMIT
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))
    try:
        offset = int(raw.get("cursor") or 0)
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)
    return {
        "q": str(raw.get("q") or "").strip().lower(),
        "status": str(raw.get("status") or "").strip().lower(),
        "group": str(raw.get("group") or "").strip().lower(),
        "tenant": str(raw.get("tenant") or "").strip().lower(),
        "namespace": str(raw.get("namespace") or "").strip().lower(),
        "limit": limit,
        "offset": offset,
    }


def paginate(
    items: Iterable[T],
    query: dict[str, Any] | None = None,
    match: Callable[[T], bool] | None = None,
) -> dict[str, Any]:
    q = query or parse_query(None)
    filtered = [item for item in items if (match(item) if match else True)]
    limit = q["limit"]
    offset = q["offset"]
    page = filtered[offset : offset + limit]
    nxt = offset + limit
    result: dict[str, Any] = {
        "items": page,
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
    }
    if nxt < len(filtered):
        result["nextCursor"] = str(nxt)
    return result


def includes(haystack: Any, q: str) -> bool:
    if not q:
        return True
    return q in str(haystack or "").lower()


def health_from_ready(ready: bool, joined: bool = True) -> str:
    if not joined:
        return "idle"
    return "healthy" if ready else "down"


def job_status(raw: str) -> str:
    value = (raw or "").lower()
    if value in ("queued", "pending"):
        return "queued"
    if value in ("running", "claimed"):
        return "running"
    if value in ("ok", "completed", "success", "succeeded", "dismissed"):
        return "ok"
    if value in ("failed", "error"):
        return "failed"
    return "queued" if not value else "failed"


def job_view(row: dict[str, Any] | None) -> dict[str, Any]:
    body = row if isinstance(row, dict) else {}
    log = str(body.get("log") or body.get("log_preview") or body.get("error") or "")
    detail = ""
    for line in reversed(log.splitlines()):
        text = line.strip()
        if text:
            detail = text[:240]
            break
    return {
        "id": str(body.get("id") or body.get("job_id") or ""),
        "type": body.get("type") or "",
        "status": job_status(str(body.get("status") or "")),
        "log": log[-20_000:],
        "detail": detail,
        "stage": str(body.get("stage_label") or body.get("stage") or ""),
    }
