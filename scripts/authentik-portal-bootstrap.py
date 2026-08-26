#!/usr/bin/env python3
"""Idempotent Authentik cutover: ops vs client-portal isolation + NoordDrive user.

Creates:
  groups  cronnecture-ops / cronnecture-portal-noorddriveautos
  flow    cronnecture-portal-authentication (password, no MFA, no email verify)
  OIDC    cronnecture-client-portal  (client.cronnecture.com password + code)
  OIDC    noorddriveautos-site       (apex site gate)
  policies so CF Access requires ops, client hub requires the portal group,
  and the NoordDrive site allows ops OR that portal group
  user    Noorddriveautos@gmail.com  (portal group only)

Ops users (akadmin today) stay on the default MFA flow via Cloudflare Access.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AK = os.environ.get("AUTHENTIK_URL", "https://auth.cronnecture.com").rstrip("/")
TOKEN_PATHS = [
    Path("/home/dev/stack/ansible/config/.identity/authentik_api_token"),
]
PORTAL_EMAIL = os.environ.get("NOORDDRIVE_EMAIL", "Noorddriveautos@gmail.com")
PORTAL_PASSWORD = os.environ.get("NOORDDRIVE_PASSWORD", "")
OUT_ENV = Path("/home/dev/stack/ansible/config/.identity/authentik_portal_oidc.env")

IDENT_STAGE = "cb480a9a-5de2-4fe6-8cba-806060b73687"
PASSWORD_STAGE = "598060cf-dddf-463d-ae7c-137ff5b102a6"
LOGIN_STAGE = "5ca27b34-261d-4f13-8927-ec57e8d0f948"
AUTHZ_IMPLICIT = "bc087adb-504c-4f83-8faa-6d294e4ce75a"
INVALIDATION = "3acc3837-3878-4506-b555-a52e8508f35d"
SIGNING_KEY = "63ce6c33-9235-4f1a-91cc-f9022490dd61"
SCOPE_OPENID = "0d614943-aa48-402f-b6c7-15a30216fa2f"
SCOPE_EMAIL = "c0981bae-f837-4b0e-b4b0-5c8a43f372b2"
SCOPE_PROFILE = "30224d1e-68ed-4881-981c-7d0ddf35a959"
SCOPE_OFFLINE = "0eacb593-a303-4776-9e52-37d4d4700937"


def _token() -> str:
    env = (os.environ.get("AUTHENTIK_API_TOKEN") or "").strip()
    if env:
        return env
    for path in TOKEN_PATHS:
        if path.is_file():
            return path.read_text().strip()
    raise SystemExit("AUTHENTIK_API_TOKEN missing")


def api(method: str, path: str, body: dict | None = None):
    url = f"{AK}{path}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "cronnecture-authentik-bootstrap/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"detail": raw[:500]}
        if exc.code >= 400:
            print(f"{method} {path} -> {exc.code} {parsed}", file=sys.stderr)
        return exc.code, parsed


def list_results(path: str, **params):
    qs = urllib.parse.urlencode({"page_size": 100, **params})
    code, body = api("GET", f"{path}?{qs}")
    if code >= 400:
        raise SystemExit(f"list failed {path}: {body}")
    return body.get("results") or []


def get_or_create(kind: str, list_path: str, create_path: str, match: str, payload: dict, key="name"):
    for row in list_results(list_path, search=match):
        if str(row.get(key) or "") == match:
            print(f"exists {kind} {match} pk={row.get('pk')}")
            return row
    code, body = api("POST", create_path, payload)
    if code >= 400:
        raise SystemExit(f"create {kind} {match} failed: {body}")
    print(f"created {kind} {match} pk={body.get('pk')}")
    return body


def ensure_group(name: str) -> dict:
    return get_or_create("group", "/api/v3/core/groups/", "/api/v3/core/groups/", name, {"name": name, "is_superuser": False})


def add_user_to_group(group: dict, user_pk: int) -> None:
    users = list(group.get("users") or [])
    if user_pk in users:
        return
    users.append(user_pk)
    code, body = api("PATCH", f"/api/v3/core/groups/{group['pk']}/", {"users": users})
    if code >= 400:
        raise SystemExit(f"add user {user_pk} to {group.get('name')} failed: {body}")
    group["users"] = users
    print(f"added user {user_pk} to {group.get('name')}")


def ensure_flow() -> dict:
    slug = "cronnecture-portal-authentication"
    for row in list_results("/api/v3/flows/instances/", search=slug):
        if row.get("slug") == slug:
            print(f"exists flow {slug}")
            return row
    code, body = api(
        "POST",
        "/api/v3/flows/instances/",
        {
            "name": "Client portal login",
            "title": "Sign in",
            "slug": slug,
            "designation": "authentication",
            "authentication": "require_unauthenticated",
            "policy_engine_mode": "any",
            "layout": "stacked",
            "denied_action": "message_continue",
            "compatibility_mode": False,
        },
    )
    if code >= 400:
        raise SystemExit(f"create flow failed: {body}")
    print(f"created flow {slug}")
    return body


def ensure_flow_stages(flow: dict) -> None:
    existing = list_results("/api/v3/flows/bindings/", target=flow["pk"])
    have = {b.get("stage") for b in existing}
    for order, stage in ((10, IDENT_STAGE), (20, PASSWORD_STAGE), (100, LOGIN_STAGE)):
        if stage in have:
            continue
        code, body = api(
            "POST",
            "/api/v3/flows/bindings/",
            {
                "target": flow["pk"],
                "stage": stage,
                "order": order,
                "evaluate_on_plan": False,
                "re_evaluate_policies": True,
                "policy_engine_mode": "any",
                "invalid_response_action": "retry",
            },
        )
        if code >= 400:
            raise SystemExit(f"bind stage {stage} failed: {body}")
        print(f"bound stage {stage} order={order}")


def ensure_groups_mapping() -> str:
    name = "Cronnecture groups"
    for row in list_results("/api/v3/propertymappings/provider/scope/", search=name):
        if row.get("name") == name:
            return row["pk"]
    expression = (
        "groups = [g.name for g in request.user.ak_groups.all()]\n"
        "ops = 'cronnecture-ops' in groups\n"
        "tenants = [g.removeprefix('cronnecture-portal-') for g in groups if g.startswith('cronnecture-portal-')]\n"
        "return {\n"
        "    'groups': groups,\n"
        "    'cronnecture_plane': 'ops' if ops else 'portal',\n"
        "    'cronnecture_tenant': tenants[0] if tenants else '',\n"
        "}\n"
    )
    code, body = api(
        "POST",
        "/api/v3/propertymappings/provider/scope/",
        {
            "name": name,
            "scope_name": "groups",
            "description": "Cronnecture plane + tenant groups",
            "expression": expression,
        },
    )
    if code >= 400:
        raise SystemExit(f"scope mapping failed: {body}")
    print("created groups mapping")
    return body["pk"]


def ensure_provider(*, name: str, flow_pk: str, redirects: list[str], groups_map: str) -> dict:
    mappings = [SCOPE_OPENID, SCOPE_EMAIL, SCOPE_PROFILE, SCOPE_OFFLINE, groups_map]
    payload = {
        "name": name,
        "authentication_flow": flow_pk,
        "authorization_flow": AUTHZ_IMPLICIT,
        "invalidation_flow": INVALIDATION,
        "client_type": "confidential",
        "grant_types": [
            "authorization_code",
            "refresh_token",
            "password",
            "client_credentials",
        ],
        "include_claims_in_id_token": True,
        "signing_key": SIGNING_KEY,
        "redirect_uris": [{"matching_mode": "strict", "url": url} for url in redirects],
        "sub_mode": "user_email",
        "issuer_mode": "per_provider",
        "property_mappings": mappings,
        "access_code_validity": "minutes=1",
        "access_token_validity": "hours=1",
        "refresh_token_validity": "days=30",
    }
    for row in list_results("/api/v3/providers/oauth2/", search=name):
        if row.get("name") == name:
            code, body = api("PATCH", f"/api/v3/providers/oauth2/{row['pk']}/", payload)
            if code >= 400:
                raise SystemExit(f"patch provider {name} failed: {body}")
            print(f"updated provider {name} pk={row['pk']}")
            return body if body.get("pk") else {**row, **payload, "pk": row["pk"]}
    code, body = api("POST", "/api/v3/providers/oauth2/", payload)
    if code >= 400:
        raise SystemExit(f"create provider {name} failed: {body}")
    print(f"created provider {name} pk={body.get('pk')}")
    return body


def ensure_application(*, name: str, slug: str, provider_pk: int, launch: str, hide: bool) -> dict:
    payload = {
        "name": name,
        "slug": slug,
        "provider": provider_pk,
        "policy_engine_mode": "any",
        "meta_launch_url": launch,
        "meta_hide": hide,
        "open_in_new_tab": False,
        "group": "Cronnecture",
    }
    for row in list_results("/api/v3/core/applications/", search=slug, superuser_full_list="true"):
        if row.get("slug") == slug:
            code, body = api("PATCH", f"/api/v3/core/applications/{row['pk']}/", payload)
            if code >= 400:
                raise SystemExit(f"patch app {slug} failed: {body}")
            print(f"updated app {slug}")
            return body if body.get("pk") else row
    code, body = api("POST", "/api/v3/core/applications/", payload)
    if code >= 400:
        raise SystemExit(f"create app {slug} failed: {body}")
    print(f"created app {slug}")
    return body


def ensure_policy(name: str, expression: str) -> dict:
    for row in list_results("/api/v3/policies/expression/", search=name):
        if row.get("name") == name:
            if (row.get("expression") or "").strip() != expression.strip():
                code, body = api(
                    "PATCH",
                    f"/api/v3/policies/expression/{row['pk']}/",
                    {"expression": expression},
                )
                if code >= 400:
                    raise SystemExit(f"update policy {name} failed: {body}")
                print(f"updated policy {name}")
                row["expression"] = expression
            return row
    code, body = api(
        "POST",
        "/api/v3/policies/expression/",
        {"name": name, "execution_logging": True, "expression": expression},
    )
    if code >= 400:
        raise SystemExit(f"create policy {name} failed: {body}")
    print(f"created policy {name}")
    return body


def bind_policy(policy_pk: str, target_pk: str) -> None:
    for row in list_results("/api/v3/policies/bindings/", target=target_pk):
        if row.get("policy") == policy_pk:
            return
    code, body = api(
        "POST",
        "/api/v3/policies/bindings/",
        {
            "policy": policy_pk,
            "target": target_pk,
            "order": 0,
            "enabled": True,
            "timeout": 30,
            "failure_result": False,
            "negate": False,
        },
    )
    if code >= 400:
        raise SystemExit(f"bind policy failed: {body}")
    print(f"bound policy {policy_pk} -> {target_pk}")


def unbind_policy(policy_pk: str, target_pk: str) -> None:
    for row in list_results("/api/v3/policies/bindings/", target=target_pk):
        if row.get("policy") != policy_pk:
            continue
        code, body = api("DELETE", f"/api/v3/policies/bindings/{row['pk']}/")
        if code >= 400:
            raise SystemExit(f"unbind {policy_pk} from {target_pk} failed: {body}")
        print(f"unbound policy {policy_pk} from {target_pk}")


def bind_group(group_pk: str, target_pk: str, order: int = 10) -> None:
    for row in list_results("/api/v3/policies/bindings/", target=target_pk):
        if row.get("group") == group_pk:
            return
    code, body = api(
        "POST",
        "/api/v3/policies/bindings/",
        {
            "group": group_pk,
            "target": target_pk,
            "order": order,
            "enabled": True,
            "timeout": 30,
            "failure_result": False,
        },
    )
    if code >= 400:
        raise SystemExit(f"bind group failed: {body}")
    print(f"bound group {group_pk} -> {target_pk}")


def cleanup_empty_bindings(target_pk: str) -> None:
    for row in list_results("/api/v3/policies/bindings/", target=target_pk):
        if row.get("policy") or row.get("group") or row.get("user"):
            continue
        code, body = api("DELETE", f"/api/v3/policies/bindings/{row['pk']}/")
        if code >= 400:
            print(f"skip empty binding {row.get('pk')}: {body}")
            continue
        print(f"deleted empty binding {row.get('pk')} on {target_pk}")


def set_engine_mode(app: dict, mode: str = "any") -> None:
    if app.get("policy_engine_mode") == mode:
        return
    slug = app["slug"]
    code, body = api("PATCH", f"/api/v3/core/applications/{slug}/", {"policy_engine_mode": mode})
    if code >= 400:
        raise SystemExit(f"set engine mode {slug} failed: {body}")
    print(f"set {slug} policy_engine_mode={mode}")


def ensure_user(ops_group: dict, portal_group: dict) -> dict:
    email = PORTAL_EMAIL
    username = email.lower()
    existing = None
    for row in list_results("/api/v3/core/users/", search=username):
        if (row.get("username") or "").lower() == username or (row.get("email") or "").lower() == username:
            existing = row
            break
    payload = {
        "username": username,
        "name": "NoordDrive Autos",
        "email": email,
        "is_active": True,
        "type": "internal",
        "path": "users",
        "attributes": {
            "goauthentik.io/user/confirmed": True,
        },
    }
    if existing:
        code, body = api("PATCH", f"/api/v3/core/users/{existing['pk']}/", payload)
        if code >= 400:
            raise SystemExit(f"patch user failed: {body}")
        user = body if body.get("pk") else existing
        print(f"updated user {username} pk={user.get('pk')}")
    else:
        code, body = api("POST", "/api/v3/core/users/", payload)
        if code >= 400:
            raise SystemExit(f"create user failed: {body}")
        user = body
        print(f"created user {username} pk={user.get('pk')}")
    if PORTAL_PASSWORD:
        code, body = api(
            "POST",
            f"/api/v3/core/users/{user['pk']}/set_password/",
            {"password": PORTAL_PASSWORD},
        )
        if code >= 400:
            raise SystemExit(f"set_password failed: {body}")
        print("set password (no email sent)")
    add_user_to_group(portal_group, int(user["pk"]))
    ops_users = set(ops_group.get("users") or [])
    if int(user["pk"]) in ops_users:
        ops_users.discard(int(user["pk"]))
        api("PATCH", f"/api/v3/core/groups/{ops_group['pk']}/", {"users": sorted(ops_users)})
        print("removed portal user from cronnecture-ops")
    return user


def write_env(portal: dict, site: dict) -> None:
    lines = [
        f"AUTHENTIK_URL={AK}",
        f"AUTHENTIK_PORTAL_ISSUER={AK}/application/o/cronnecture-client-portal/",
        f"AUTHENTIK_PORTAL_CLIENT_ID={portal.get('client_id')}",
        f"AUTHENTIK_PORTAL_CLIENT_SECRET={portal.get('client_secret')}",
        f"AUTHENTIK_SITE_ISSUER={AK}/application/o/noorddriveautos-site/",
        f"AUTHENTIK_SITE_CLIENT_ID={site.get('client_id')}",
        f"AUTHENTIK_SITE_CLIENT_SECRET={site.get('client_secret')}",
        "AUTHENTIK_INTERNAL_URL=http://authentik.identity.svc.cluster.local:9000",
    ]
    OUT_ENV.parent.mkdir(parents=True, exist_ok=True)
    OUT_ENV.write_text("\n".join(lines) + "\n")
    os.chmod(OUT_ENV, 0o600)
    print(f"wrote {OUT_ENV}")


def main() -> None:
    if not PORTAL_PASSWORD:
        raise SystemExit("NOORDDRIVE_PASSWORD is required")
    ops = ensure_group("cronnecture-ops")
    portal_group = ensure_group("cronnecture-portal-noorddriveautos")
    # Current operator (akadmin / svenbraad.work@gmail.com) stays on control plane.
    for row in list_results("/api/v3/core/users/", search="akadmin"):
        if row.get("username") == "akadmin":
            add_user_to_group(ops, int(row["pk"]))
    flow = ensure_flow()
    ensure_flow_stages(flow)
    groups_map = ensure_groups_mapping()
    portal_provider = ensure_provider(
        name="Cronnecture client portal",
        flow_pk=flow["pk"],
        redirects=[
            "https://client.cronnecture.com/api/auth/oidc/callback",
            "https://client.cronnecture.com/api/auth/logto/callback",
        ],
        groups_map=groups_map,
    )
    site_provider = ensure_provider(
        name="NoordDrive site",
        flow_pk=flow["pk"],
        redirects=["https://noorddriveautos.com/oauth2/callback"],
        groups_map=groups_map,
    )
    portal_app = ensure_application(
        name="Cronnecture client portal",
        slug="cronnecture-client-portal",
        provider_pk=int(portal_provider["pk"]),
        launch="https://client.cronnecture.com/",
        hide=False,
    )
    site_app = ensure_application(
        name="NoordDrive site",
        slug="noorddriveautos-site",
        provider_pk=int(site_provider["pk"]),
        launch="https://noorddriveautos.com/",
        hide=False,
    )
    ops_policy = ensure_policy(
        "require-cronnecture-ops",
        'return ak_is_group_member(request.user, name="cronnecture-ops")\n',
    )
    portal_policy = ensure_policy(
        "require-cronnecture-portal",
        "return any(g.name.startswith('cronnecture-portal-') for g in request.user.ak_groups.all())\n",
    )
    site_policy = ensure_policy(
        "require-noorddriveautos-site",
        (
            "return (\n"
            '    ak_is_group_member(request.user, name="cronnecture-ops")\n'
            '    or ak_is_group_member(request.user, name="cronnecture-portal-noorddriveautos")\n'
            ")\n"
        ),
    )
    cf_apps = [
        row
        for row in list_results("/api/v3/core/applications/", search="cloudflare-access", superuser_full_list="true")
        if row.get("slug") == "cloudflare-access"
    ]
    if not cf_apps:
        raise SystemExit("Cloudflare Access application missing")
    bind_policy(ops_policy["pk"], cf_apps[0]["pk"])
    bind_policy(portal_policy["pk"], portal_app["pk"])
    unbind_policy(portal_policy["pk"], site_app["pk"])
    bind_policy(site_policy["pk"], site_app["pk"])
    set_engine_mode(site_app, "any")
    set_engine_mode(portal_app, "any")
    cleanup_empty_bindings(site_app["pk"])
    cleanup_empty_bindings(portal_app["pk"])
    bind_group(ops["pk"], site_app["pk"], order=10)
    bind_group(portal_group["pk"], site_app["pk"], order=11)
    bind_group(portal_group["pk"], portal_app["pk"], order=10)
    bind_group(ops["pk"], cf_apps[0]["pk"], order=10)
    ensure_user(ops, portal_group)
    # Refresh providers so client_secret is present for env file.
    portal_full = api("GET", f"/api/v3/providers/oauth2/{portal_provider['pk']}/")[1]
    site_full = api("GET", f"/api/v3/providers/oauth2/{site_provider['pk']}/")[1]
    write_env(portal_full, site_full)
    print("ok")


if __name__ == "__main__":
    main()
