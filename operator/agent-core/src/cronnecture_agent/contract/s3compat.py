"""Minimal S3-compatible PUT/GET/DELETE (Cloudflare R2 path-style)."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import httpx

DEFAULT_ENV_FILE = "/etc/cronnecture/backup-r2.env"
DEFAULT_PREFIX = "operator-books"


@dataclass(frozen=True)
class S3Config:
    access_key: str
    secret_key: str
    bucket: str
    endpoint: str
    region: str
    prefix: str


def _parse_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, _, value = raw.partition("=")
                out[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return out


def load_s3_config() -> S3Config | None:
    file_vals = _parse_env_file(os.environ.get("BOOKS_S3_ENV_FILE") or DEFAULT_ENV_FILE)
    access = (
        os.environ.get("BOOKS_S3_ACCESS_KEY")
        or os.environ.get("AWS_ACCESS_KEY_ID")
        or file_vals.get("AWS_ACCESS_KEY_ID")
        or ""
    )
    secret = (
        os.environ.get("BOOKS_S3_SECRET_KEY")
        or os.environ.get("AWS_SECRET_ACCESS_KEY")
        or file_vals.get("AWS_SECRET_ACCESS_KEY")
        or ""
    )
    bucket = os.environ.get("BOOKS_S3_BUCKET") or file_vals.get("BUCKET") or ""
    endpoint = os.environ.get("BOOKS_S3_ENDPOINT") or file_vals.get("ENDPOINT") or ""
    region = os.environ.get("BOOKS_S3_REGION") or file_vals.get("AWS_DEFAULT_REGION") or "auto"
    prefix = (os.environ.get("BOOKS_S3_PREFIX") or DEFAULT_PREFIX).strip().strip("/")
    if not access or not secret or not bucket or not endpoint:
        return None
    return S3Config(
        access_key=access,
        secret_key=secret,
        bucket=bucket,
        endpoint=endpoint.rstrip("/"),
        region=region or "auto",
        prefix=prefix or DEFAULT_PREFIX,
    )


def object_key(cfg: S3Config, name: str) -> str:
    return f"{cfg.prefix}/{name.lstrip('/')}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    k_date = _sign(f"AWS4{secret}".encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def signed_headers(
    *,
    method: str,
    url: str,
    access_key: str,
    secret_key: str,
    region: str,
    body: bytes,
    content_type: str | None,
    now: dt.datetime | None = None,
) -> dict[str, str]:
    parsed = urlparse(url)
    now = now or dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = _sha256(body)
    headers = {
        "host": parsed.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        headers["content-type"] = content_type
    signed = ";".join(sorted(headers))
    canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
    canonical_uri = parsed.path or "/"
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            parsed.query,
            canonical_headers,
            signed,
            payload_hash,
        ]
    )
    scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            _sha256(canonical_request.encode("utf-8")),
        ]
    )
    signature = hmac.new(_signing_key(secret_key, date_stamp, region), string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={signature}"
    )
    return headers


class S3Store:
    def __init__(self, cfg: S3Config, client: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self._client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=8.0))

    def _url(self, key: str) -> str:
        encoded = quote(key, safe="/-_.~")
        return f"{self.cfg.endpoint}/{self.cfg.bucket}/{encoded}"

    def _request(self, method: str, key: str, body: bytes = b"", content_type: str | None = None) -> httpx.Response:
        url = self._url(key)
        headers = signed_headers(
            method=method,
            url=url,
            access_key=self.cfg.access_key,
            secret_key=self.cfg.secret_key,
            region=self.cfg.region,
            body=body,
            content_type=content_type,
        )
        return self._client.request(method, url, headers=headers, content=body)

    def put(self, name: str, data: bytes, content_type: str) -> None:
        key = object_key(self.cfg, name)
        response = self._request("PUT", key, data, content_type)
        if response.status_code >= 300:
            raise RuntimeError(f"R2 put failed ({response.status_code}): {response.text[:300]}")

    def get(self, name: str) -> bytes | None:
        key = object_key(self.cfg, name)
        response = self._request("GET", key)
        if response.status_code == 404:
            return None
        if response.status_code >= 300:
            raise RuntimeError(f"R2 get failed ({response.status_code}): {response.text[:300]}")
        return response.content

    def delete(self, name: str) -> None:
        key = object_key(self.cfg, name)
        response = self._request("DELETE", key)
        if response.status_code not in (204, 200, 404) and response.status_code >= 300:
            raise RuntimeError(f"R2 delete failed ({response.status_code}): {response.text[:300]}")
