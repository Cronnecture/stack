from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from cronnecture_agent.contract import books as books_mod
from cronnecture_agent.contract.books import empty_ledger, is_ledger, ledger_score, load_file, save_file, save_ledger
from cronnecture_agent.contract.s3compat import S3Config, S3Store, load_s3_config, signed_headers


class _Infra:
    core = None


class MemoryR2(httpx.BaseTransport):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        key = path.split("/", 2)[-1] if path.count("/") >= 2 else path.lstrip("/")
        if request.method == "PUT":
            self.objects[key] = request.content
            return httpx.Response(200)
        if request.method == "GET":
            if key not in self.objects:
                return httpx.Response(404, text="not found")
            return httpx.Response(200, content=self.objects[key])
        if request.method == "DELETE":
            self.objects.pop(key, None)
            return httpx.Response(204)
        return httpx.Response(405)


class BooksTests(unittest.TestCase):
    def test_empty_ledger_shape(self):
        state = empty_ledger()
        self.assertTrue(is_ledger(state))
        self.assertEqual(ledger_score(state), 0)

    def test_richer_ledger_wins(self):
        empty = empty_ledger()
        rich = empty_ledger()
        rich["entries"] = [{"id": "1"}]
        rich["invoices"] = [{"id": "a"}, {"id": "b"}]
        rich["account"]["balance"] = 10
        self.assertGreater(ledger_score(rich), ledger_score(empty))

    def test_load_s3_config_ignores_backup_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / "backup-r2.env"
            env.write_text(
                "AWS_ACCESS_KEY_ID=ak\n"
                "AWS_SECRET_ACCESS_KEY=sk\n"
                "AWS_DEFAULT_REGION=auto\n"
                "BUCKET=cronnecture-fleet-backups\n"
                "ENDPOINT=https://example.r2.cloudflarestorage.com\n"
                "PREFIX=fleet-backups\n",
                encoding="utf-8",
            )
            patched = {
                "BOOKS_S3_ENV_FILE": str(env),
                "BOOKS_S3_PREFIX": "operator-books",
            }
            with patch.dict(os.environ, patched, clear=False):
                for key in (
                    "BOOKS_S3_ACCESS_KEY",
                    "AWS_ACCESS_KEY_ID",
                    "BOOKS_S3_BUCKET",
                    "BOOKS_S3_ENDPOINT",
                    "AWS_SECRET_ACCESS_KEY",
                ):
                    os.environ.pop(key, None)
                cfg = load_s3_config()
        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertEqual(cfg.bucket, "cronnecture-fleet-backups")
        self.assertEqual(cfg.prefix, "operator-books")

    def test_signed_headers_are_stable(self):
        headers = signed_headers(
            method="PUT",
            url="https://example.r2.cloudflarestorage.com/bucket/operator-books/ledger.json",
            access_key="AKIA",
            secret_key="secret",
            region="auto",
            body=b"{}",
            content_type="application/json",
            now=dt.datetime(2026, 8, 25, 21, 0, 0, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(headers["x-amz-date"], "20260825T210000Z")
        self.assertTrue(headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIA/20260825/auto/s3/aws4_request"))
        self.assertIn("Signature=", headers["authorization"])

    def test_books_round_trip_disk_and_r2(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = MemoryR2()
            store = S3Store(
                S3Config(
                    access_key="ak",
                    secret_key="sk",
                    bucket="cronnecture-fleet-backups",
                    endpoint="https://example.r2.cloudflarestorage.com",
                    region="auto",
                    prefix="operator-books",
                ),
                client=httpx.Client(transport=transport),
            )
            with (
                patch.object(books_mod, "FILES_DIR", Path(tmp)),
                patch.object(books_mod, "_offsite", lambda: store),
                patch.object(books_mod, "_ledger_cache", None),
            ):
                state = empty_ledger()
                state["account"]["balance"] = 595.7
                state["account"]["asOf"] = "2026-08-25"
                state["invoices"] = [{"id": "inv1", "fileId": "pdf1"}]
                save_ledger(_Infra(), state)
                loaded = json.loads((Path(tmp) / "ledger.json").read_text(encoding="utf-8"))
                self.assertEqual(loaded["account"]["balance"], 595.7)
                self.assertIn(b"595.7", transport.objects["operator-books/ledger.json"])
                save_file("pdf1", b"%PDF-1.4 test", "cursor.pdf", "application/pdf")
                hit = load_file("pdf1")
                self.assertIsNotNone(hit)
                assert hit is not None
                self.assertTrue(hit[0].startswith(b"%PDF"))
                self.assertEqual(hit[1], "cursor.pdf")
                (Path(tmp) / "files" / "pdf1").unlink()
                (Path(tmp) / "files" / "pdf1.meta").unlink()
                restored = load_file("pdf1")
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertTrue(restored[0].startswith(b"%PDF"))
                self.assertTrue((Path(tmp) / "files" / "pdf1").exists())


if __name__ == "__main__":
    unittest.main()
