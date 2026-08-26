# Ops Access & Team RBAC

Control who can reach **ops.cronnecture.com**, what they can do inside the dashboard, and (from the same surface) who can open **client portals / Access-gated domains**.

**URL:** [https://ops.cronnecture.com/settings/access](https://ops.cronnecture.com/settings/access)  
**Staging:** [https://staging-ops.cronnecture.com/settings/access](https://staging-ops.cronnecture.com/settings/access)  
**API:** `/api/ops-users` (overview: `GET /api/ops-users/overview`)  
**Superadmin (break-glass):** `svenbraad.work@gmail.com` — always seeded, never removable / demotable / deactivatable via UI or API.

## Login path (production)

1. Browser hits `ops.cronnecture.com` (or `staging-ops…`).
2. **Cloudflare Access → Authentik** (password + TOTP). Email OTP / one-time PIN is **not** offered on ops / admin portals.
3. Control plane reads `Cf-Access-Authenticated-User-Email`, maps it to an active `ops_users` row, and issues the ops session cookie — **no second password form**.
4. RBAC permissions apply as before.

Staging behaves the same.

**Machine auth:** `Authorization: Bearer $OPS_API_TOKEN` (or `X-Ops-Api-Token`) — unchanged for scripts / ansible-runner.

### Optional password break-glass

Set `OPS_PASSWORD_LOGIN=1` on the control-plane Deployment (ansible var `ops_password_login: "1"`) to show `/login` password again. Default is `"0"` (Access bridge only).

## Recovery if Authentik / Access is down

| Path | How |
|------|-----|
| **API / automation** | SSH to control node → use `OPS_API_TOKEN` from vault / k8s secret `control-plane-cf` against NodePort `30080` / `30081` with `Host: ops…` |
| **Re-enable password UI** | Set `ops_password_login: "1"`, `make control-plane` (or staging), then `/login` with per-user hash |
| **Set / reset password** | With API token: `POST /api/ops-users/{id}/password`; or DB/`ensure_superadmin` seed from legacy `OPS_ADMIN_PASSWORD` |
| **Access allowlist** | Superadmin email always stays on the ops Access policy payload even if sync partially fails |

Do **not** put Vaultwarden (`vault.*`) behind Access — Bitwarden clients need `skip_access`.

## How to add an employee or contractor

1. Sign in to ops (Access → Authentik → land in dashboard).
2. Open **Settings → Users / Access**.
3. Enter their **work email**, choose a **role** (default **Read-only**), optionally tweak permission toggles.
4. Password is optional (only needed if `OPS_PASSWORD_LOGIN=1`).
5. Control-plane syncs the active email list to the Cloudflare Access allow policy for `ops.cronnecture.com` (and `staging-ops` when present).
6. They complete Cloudflare Access with Authentik using that email and land in ops with their RBAC role.

Disable, enable, remove, and sync Access from the same page (except protected superadmin).

## Users / Access UI (control plane)

| Section | What it shows / does |
|---------|----------------------|
| **KPIs** | Active ops users, client counts |
| **Ops Cloudflare Access** | Desired emails from Postgres vs live edge allow policy; **Sync ops Access** |
| **Invite / create** | Email, role, permissions; optional password for break-glass mode |
| **Ops team** | List: email, role, permissions summary, active/disabled, last login; edit role/perms; disable/delete |
| **Client domain access** | Per client: portal Access emails (Authentik IdP at edge; optional Logto product Sign in); gated app hosts |

## API surface

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/auth/me` | Session (auto-bridges from Access email when password login off) |
| `POST` | `/api/auth/access-login` | Explicit Access → ops session |
| `GET` | `/api/auth/login-options` | UI: password form vs Access bridge |
| `POST` | `/api/auth/login` | Password login (only when `OPS_PASSWORD_LOGIN=1`) |
| `GET` | `/api/ops-users` | List users + role/permission catalog |
| `GET` | `/api/ops-users/overview` | Unified ops + CF edge + client access oversight |
| `GET` | `/api/ops-users/access-edge` | Desired vs live ops Access emails |
| `POST` | `/api/ops-users` | Create user |
| `PATCH` | `/api/ops-users/{id}` | Role, permissions, active, display name |
| `DELETE` | `/api/ops-users/{id}` | Remove user + Access sync |
| `POST` | `/api/ops-users/{id}/password` | Admin set/reset (break-glass) — audited |
| `POST` | `/api/ops-users/sync-access` | Push active emails to ops (+ staging-ops) Access |
| `PATCH` | `/api/ops-users/clients/{id}/portal-access` | Set client portal Access emails + CF sync |

## Layers

1. **Cloudflare Access** — Authentik-only IdP on ops / staging-ops / admin portals + `ssh-*` (`make cloudflare` runs `cf-wire-authentik-idp.py`). Email allowlist synced from active `ops_users` (always includes superadmin).
2. **Ops session** — cookie issued from Access email → `ops_users` (default). Optional password when `OPS_PASSWORD_LOGIN=1`.
3. **`ops_users` RBAC** — active user + permission on API; nav planes hidden when unauthorized.
4. **`OPS_API_TOKEN`** — machine callers; full access (not a human login).

If Cloudflare sync fails, the superadmin email remains on the allowlist payload (fail-open for break-glass only). Other users are fail-closed (must be active in DB).

## Roles

| Role | Intent |
|------|--------|
| **Superadmin** | Break-glass only (`svenbraad.work@gmail.com`). Full access. |
| **Admin** | Full in-app permissions (including Users & Access). |
| **Operator** | Fleet (incl. Self-heal), CRM, DMS, mail, automation, security. |
| **Sales** | CRM, prospects/leads, mail, billing. |
| **Read-only** | Least-privilege view: fleet, CRM, prospects, mail, security, automation, DMS. **No** billing, settings/secrets, users admin, or self-heal. Mutations blocked. **Default for new users.** |

Per-permission overrides can refine a role when needed.

## Client domain access

- **Customer portal:** Authentik OIDC at `auth.cronnecture.com` (invite-only; cookie still `cp_logto_session`, login path still `/api/auth/logto/login`). Cloudflare Access is **off** on `client.cronnecture.com` (`skip_access` + `purge_access_apps`).
- **App domains:** exposures with `cf_access_enabled` — oversight on Users / Access; edit allowlists in CRM → client → Access.
- Dev emails always merged via `PORTAL_DEV_EMAILS` for portals.
- **Vaultwarden** stays `skip_access` (Bitwarden clients).

## Ansible baseline

`config/policies/cloudflare.yml` → `cf_access_allowed_emails` reads `vault_cf_access_allowed_emails` (empty committed default). Keep the break-glass operator email in **vault** so a recreate cannot lock Sven out. Ops/staging-ops policies are also maintained live from the dashboard (**Sync ops Access**).

See also: [identity.md](identity.md), `scripts/cloudflare/cf-wire-authentik-idp.py`.
