"""Persist operator books (ledger + invoice PDFs) on disk, etcd, and R2."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import structlog
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .s3compat import S3Store, load_s3_config
from .btw import hydrate_ledger

log = structlog.get_logger()

NS = os.environ.get("BOOKS_NAMESPACE", "cronnecture-system")
CM_NAME = "operator-books"
FILES_DIR = Path(os.environ.get("BOOKS_FILES_DIR", "/var/lib/cronnecture/books"))
MAX_LEDGER_BYTES = 900_000
MAX_PDF_BYTES = 8 * 1024 * 1024
FILE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_LEDGER_TTL = 15.0
_ledger_cache: tuple[float, dict[str, Any]] | None = None


def empty_ledger() -> dict[str, Any]:
    return {
        "version": 1,
        "account": {"name": "Business", "iban": "", "balance": 0, "asOf": ""},
        "entries": [],
        "invoices": [],
    }


def is_ledger(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    account = value.get("account")
    return (
        value.get("version") == 1
        and isinstance(account, dict)
        and isinstance(value.get("entries"), list)
        and isinstance(value.get("invoices"), list)
    )


def ledger_score(state: dict[str, Any]) -> int:
    if not is_ledger(state):
        return -1
    account = state.get("account") or {}
    balance = 1 if account.get("balance") else 0
    as_of = 1 if account.get("asOf") else 0
    return len(state.get("entries") or []) * 10 + len(state.get("invoices") or []) * 10 + balance + as_of


def _files_root() -> Path:
    path = FILES_DIR / "files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_id(file_id: str) -> str:
    if not FILE_ID_RE.match(file_id or ""):
        raise ValueError("Invalid file id")
    return file_id


def _offsite() -> S3Store | None:
    cfg = load_s3_config()
    if cfg is None:
        return None
    return S3Store(cfg)


def _encode_ledger(state: dict[str, Any]) -> str:
    if not is_ledger(state):
        raise ValueError("Not a books ledger")
    raw = json.dumps(state, separators=(",", ":"), ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_LEDGER_BYTES:
        raise ValueError("Books ledger is too large")
    return raw


def _parse_ledger(raw: str | bytes | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if is_ledger(parsed) else None


def _load_disk() -> dict[str, Any] | None:
    disk = FILES_DIR / "ledger.json"
    if not disk.exists():
        return None
    try:
        return _parse_ledger(disk.read_text(encoding="utf-8"))
    except OSError:
        return None


def _write_disk(state: dict[str, Any]) -> None:
    raw = _encode_ledger(state)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILES_DIR / "ledger.json.tmp"
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(FILES_DIR / "ledger.json")


def _load_cm(infra: Any) -> dict[str, Any] | None:
    core = getattr(infra, "core", None)
    if core is None:
        return None
    try:
        cm = core.read_namespaced_config_map(CM_NAME, NS)
        return _parse_ledger((cm.data or {}).get("ledger.json") or "")
    except ApiException as exc:
        if exc.status != 404:
            raise
        return None


def _write_cm(infra: Any, state: dict[str, Any]) -> None:
    core = getattr(infra, "core", None)
    if core is None:
        return
    raw = _encode_ledger(state)
    body = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=CM_NAME,
            namespace=NS,
            labels={"app": "agent-core", "cronnecture.com/kind": "operator-books"},
        ),
        data={"ledger.json": raw},
    )
    try:
        core.replace_namespaced_config_map(CM_NAME, NS, body)
    except ApiException as exc:
        if exc.status == 404:
            core.create_namespaced_config_map(NS, body)
        else:
            raise


def _load_r2() -> dict[str, Any] | None:
    store = _offsite()
    if store is None:
        return None
    try:
        blob = store.get("ledger.json")
    except Exception as exc:
        log.warning("books_r2_get_ledger_failed", error=str(exc)[:300])
        return None
    return _parse_ledger(blob)


def _write_r2(state: dict[str, Any]) -> None:
    store = _offsite()
    if store is None:
        log.warning("books_r2_not_configured")
        return
    store.put("ledger.json", _encode_ledger(state).encode("utf-8"), "application/json")


def load_ledger(infra: Any) -> dict[str, Any]:
    global _ledger_cache
    now = time.monotonic()
    if _ledger_cache and now - _ledger_cache[0] < _LEDGER_TTL:
        return _ledger_cache[1]
    disk = _load_disk()
    remote = _load_r2()
    etcd = _load_cm(infra)
    best = empty_ledger()
    for candidate in (disk, remote, etcd):
        if candidate and ledger_score(candidate) >= ledger_score(best):
            best = candidate
    if ledger_score(best) > 0:
        if disk is None or ledger_score(disk) < ledger_score(best):
            try:
                _write_disk(best)
            except OSError as exc:
                log.warning("books_disk_hydrate_failed", error=str(exc)[:200])
        if remote is None or ledger_score(remote) < ledger_score(best):
            try:
                _write_r2(best)
            except Exception as exc:
                log.warning("books_r2_hydrate_failed", error=str(exc)[:300])
    _ledger_cache = (now, hydrate_ledger(best))
    return _ledger_cache[1]


def save_ledger(infra: Any, state: dict[str, Any]) -> None:
    global _ledger_cache
    _write_disk(state)
    _write_cm(infra, state)
    try:
        _write_r2(state)
    except Exception as exc:
        log.warning("books_r2_save_failed", error=str(exc)[:300])
        raise RuntimeError("Could not copy books off this server") from exc
    _ledger_cache = (time.monotonic(), state)


def _load_file_disk(safe: str) -> tuple[bytes, str, str] | None:
    blob = _files_root() / safe
    meta_path = _files_root() / f"{safe}.meta"
    if not blob.exists():
        return None
    name = f"{safe}.pdf"
    mime = "application/pdf"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            name = str(meta.get("name") or name)
            mime = str(meta.get("type") or mime)
        except (OSError, json.JSONDecodeError):
            pass
    return blob.read_bytes(), name, mime


def _write_file_disk(safe: str, data: bytes, name: str, mime: str) -> None:
    root = _files_root()
    tmp = root / f"{safe}.tmp"
    tmp.write_bytes(data)
    tmp.replace(root / safe)
    (root / f"{safe}.meta").write_text(
        json.dumps(
            {"name": unquote(name or "") or f"{safe}.pdf", "type": mime or "application/pdf"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _load_file_r2(safe: str) -> tuple[bytes, str, str] | None:
    store = _offsite()
    if store is None:
        return None
    try:
        data = store.get(f"files/{safe}")
        meta_raw = store.get(f"files/{safe}.meta")
    except Exception as exc:
        log.warning("books_r2_get_file_failed", file_id=safe, error=str(exc)[:300])
        return None
    if data is None:
        return None
    name = f"{safe}.pdf"
    mime = "application/pdf"
    if meta_raw:
        try:
            meta = json.loads(meta_raw)
            name = str(meta.get("name") or name)
            mime = str(meta.get("type") or mime)
        except (TypeError, json.JSONDecodeError):
            pass
    return data, name, mime


def _write_file_r2(safe: str, data: bytes, name: str, mime: str) -> None:
    store = _offsite()
    if store is None:
        log.warning("books_r2_not_configured")
        return
    meta = json.dumps(
        {"name": unquote(name or "") or f"{safe}.pdf", "type": mime or "application/pdf"},
        ensure_ascii=False,
    ).encode("utf-8")
    store.put(f"files/{safe}", data, mime or "application/pdf")
    store.put(f"files/{safe}.meta", meta, "application/json")


def load_file(file_id: str) -> tuple[bytes, str, str] | None:
    safe = _safe_id(file_id)
    hit = _load_file_disk(safe)
    if hit:
        return hit
    hit = _load_file_r2(safe)
    if not hit:
        return None
    data, name, mime = hit
    try:
        _write_file_disk(safe, data, name, mime)
    except OSError as exc:
        log.warning("books_disk_file_hydrate_failed", file_id=safe, error=str(exc)[:200])
    return hit


def save_file(file_id: str, data: bytes, name: str, mime: str) -> None:
    if len(data) > MAX_PDF_BYTES:
        raise ValueError("PDF must be 8 MB or smaller")
    if not data:
        raise ValueError("Empty file")
    safe = _safe_id(file_id)
    _write_file_disk(safe, data, name, mime)
    try:
        _write_file_r2(safe, data, name, mime)
    except Exception as exc:
        log.warning("books_r2_save_file_failed", file_id=safe, error=str(exc)[:300])
        raise RuntimeError("Could not copy invoice PDF off this server") from exc


def delete_file(file_id: str) -> None:
    safe = _safe_id(file_id)
    root = _files_root()
    for path in (root / safe, root / f"{safe}.meta"):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    store = _offsite()
    if store is None:
        return
    try:
        store.delete(f"files/{safe}")
        store.delete(f"files/{safe}.meta")
    except Exception as exc:
        log.warning("books_r2_delete_file_failed", file_id=safe, error=str(exc)[:300])
