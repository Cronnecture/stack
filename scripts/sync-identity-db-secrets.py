#!/usr/bin/env python3
"""Pin identity-secrets to the databases the live pods actually use.

Stack YAML reads these keys. Applying it must not retarget Authentik or
Vaultwarden onto empty in-cluster Postgres. Logto is retired; its DSN key
is left untouched when the Logto deploy is gone.

Never prints secret values.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys


def kubectl(*args: str, input: bytes | None = None) -> bytes:
    return subprocess.check_output(["kubectl", *args], input=input)


def deploy_env(namespace: str, name: str) -> dict[str, str]:
    raw = json.loads(
        kubectl("-n", namespace, "get", "deploy", name, "-o", "json").decode()
    )
    out: dict[str, str] = {}
    for env in raw["spec"]["template"]["spec"]["containers"][0].get("env") or []:
        if "value" in env and env["value"] is not None:
            out[env["name"]] = env["value"]
    return out


def pod_printenv(namespace: str, deploy: str, var: str) -> str:
    return (
        kubectl(
            "-n",
            namespace,
            "exec",
            f"deploy/{deploy}",
            "--",
            "printenv",
            var,
        )
        .decode()
        .strip()
    )


def patch_secret(data: dict[str, str]) -> None:
    encoded = {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}
    body = json.dumps({"data": encoded})
    kubectl(
        "-n",
        "identity",
        "patch",
        "secret",
        "identity-secrets",
        "--type",
        "merge",
        "-p",
        body,
    )


def host_of_dsn(dsn: str) -> str:
    try:
        return dsn.split("@", 1)[1].split("/", 1)[0]
    except Exception:
        return "unparsed"


def deploy_exists(namespace: str, name: str) -> bool:
    try:
        kubectl("-n", namespace, "get", "deploy", name)
        return True
    except subprocess.CalledProcessError:
        return False


def optional_printenv(namespace: str, deploy: str, var: str) -> str:
    if not deploy_exists(namespace, deploy):
        return ""
    try:
        return pod_printenv(namespace, deploy, var)
    except subprocess.CalledProcessError:
        return ""


def main() -> int:
    kubectl("get", "secret", "identity-secrets", "-n", "identity")

    vault = deploy_env("identity", "vaultwarden")
    auth = deploy_env("identity", "authentik-server")
    logto_dsn = optional_printenv("identity", "logto", "DB_URL")

    vault_dsn = vault.get("DATABASE_URL") or pod_printenv("identity", "vaultwarden", "DATABASE_URL")
    auth_host = auth.get("AUTHENTIK_POSTGRESQL__HOST") or pod_printenv(
        "identity", "authentik-server", "AUTHENTIK_POSTGRESQL__HOST"
    )
    auth_port = auth.get("AUTHENTIK_POSTGRESQL__PORT") or "5432"
    auth_user = auth.get("AUTHENTIK_POSTGRESQL__USER") or pod_printenv(
        "identity", "authentik-server", "AUTHENTIK_POSTGRESQL__USER"
    )
    auth_password = auth.get("AUTHENTIK_POSTGRESQL__PASSWORD") or pod_printenv(
        "identity", "authentik-server", "AUTHENTIK_POSTGRESQL__PASSWORD"
    )
    auth_ssl = auth.get("AUTHENTIK_POSTGRESQL__SSLMODE") or "require"

    if not vault_dsn or not auth_host or not auth_password:
        raise SystemExit("could not read live Authentik/Vaultwarden database settings from running pods")

    data = {
        "postgres-dsn-vaultwarden": vault_dsn,
        "authentik-postgres-host": auth_host,
        "authentik-postgres-port": str(auth_port),
        "authentik-postgres-user": auth_user,
        "authentik-postgres-password": auth_password,
        "authentik-postgres-sslmode": auth_ssl,
    }
    if logto_dsn:
        data["postgres-dsn-logto"] = logto_dsn
    patch_secret(data)
    print("identity-secrets pinned to live databases:")
    print(f"  vaultwarden -> {host_of_dsn(vault_dsn)}")
    print(f"  logto       -> {host_of_dsn(logto_dsn) if logto_dsn else 'retired (left existing secret key)'}")
    print(f"  authentik   -> {auth_host}:{auth_port} sslmode={auth_ssl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
