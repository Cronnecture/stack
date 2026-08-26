# Identity & secrets platform

Top-tier self-hosted identity, password management, secret sharing, CIAM, and authorization — without replacing **Cloudflare Access SSH**.

## Hard rules

| Path | Auth |
|------|------|
| `ssh-*.cronnecture.com` | Cloudflare Access → **Authentik only** (password + TOTP) → **SSH CA** short-lived cert (`cloudflared access ssh`). Keep `type=ssh` — never password SSH. No email OTP. |
| Web admin UIs | Cloudflare Access → **Authentik OIDC only** (MFA). No email OTP on ops/passbolt/wazuh/id-admin/webmail. |
| Public IdP / CIAM / vault | No Access (OIDC + Bitwarden clients) |

Do **not** remove Cloudflare SSH CA or convert SSH Access apps to self-hosted/password SSH. See `config/inventory/group_vars/all/cf_ssh.yml` and `roles/cloudflare_mgmt/tasks/ssh_access.yml`.

## Wired architecture (2026-08-12)

```
Internet
   │
   ├─ Cloudflare Access (web + ssh-*) ──► Authentik OIDC only (no email OTP)
   │         │
   │         ├─ ops / staging-ops / passbolt / wazuh / id-admin / webmail / …
   │         └─ ssh-*.cronnecture.com  (type=ssh) ──► SSH CA short-lived cert
   │
   ├─ client.cronnecture.com (Access off) ──► Logto product SSO (invite-only)
   │
   └─ Public (no Access) ──► auth (Authentik) / id (Logto) / passkeys (Hanko) / vault (Vaultwarden)
                                      │
                                      ▼
                               k3s NodePorts (identity ns) + Cerbos ClusterIP

Databases:
  Authentik / Hanko / Vaultwarden → Supabase project cronnecture-identity (session pooler :5432)
  Logto → on-cluster logto-postgres (Node/pg + Supabase Supavisor is unreliable)
  Passbolt → on-cluster MariaDB (CE is MySQL-only)
  Authentik Redis → on-cluster identity-redis

Mail path: Authentik + Passbolt + Logto → Stalwart (mail ns) submission **:587** as `noreply@cronnecture.com` (not :25 — external relay denied)
Logto public CIAM: social **Google only** (+ username/password + Logto TOTP MFA). No “Sign in with Authentik” on product SIE.
Authentik = admin/ops edge IdP (CF Access for ops/ssh/passbolt/id-admin/…); OIDC app `logto-ciam` kept unused for future enterprise, not on public SIE.
Traditional app **Cronnecture customer portal** for product OIDC
MFA: Authentik TOTP for ops; Logto admin + default tenant MFA Mandatory (TOTP) for product
```

## Components

| Service | URL | Exposure | Role |
|---------|-----|----------|------|
| **Vaultwarden** | `https://vault.cronnecture.com` | **No Cloudflare Access** (`skip_access`) | Ops password vault (Bitwarden clients); use **Send** for one-time secrets |
| **Passbolt** | `https://passbolt.cronnecture.com` | Access → Authentik | Team credential sharing + audit |
| **Authentik** | `https://auth.cronnecture.com` | Public | Admin/ops edge IdP (**2026.8.0**) for CF Access (not Logto product social). **1 replica** — Supabase session pooler is 15 clients; a second server exhausts it. |
| **Logto** | `https://id.cronnecture.com` | Public | Product CIAM — Google (+ password/MFA); no Authentik button. **2 replicas** behind ClusterIP; `logto-postgres` stays 1× PVC. |
| **Logto Admin** | `https://id-admin.cronnecture.com` | Access → Authentik | Logto console |
| **Hanko** | `https://passkeys.cronnecture.com` | Public | Passkey / WebAuthn API (image pinned `v2.7.0`; not wired to the customer portal). **2 replicas**. |
| **Cerbos** | `identity/cerbos:3592` | ClusterIP | Fine-grained AuthZ (ops policies shipped). **2 replicas**, required anti-affinity. |

Logto, Hanko, and Cerbos run **2 replicas** (one per general worker). Traefik → ClusterIP load-balances ready endpoints. Authentik stays **1 replica** until the Supabase session pooler is larger than 15. Operator steps to finish failsafe (hosted Redis, dedicated Logto DB, raise pooler, laptop clone): [RB-16](../runbooks/identity-failsafe.md).

**Removed:** Password Pusher — use Vaultwarden Send.

## Deploy

```bash
make identity          # k3s manifests → identity namespace
make cloudflare        # DNS + Access apps + public tunnel routes + Authentik-only IdP pin
# Idempotent wire (also invoked by make cloudflare):
./scripts/cloudflare/cf-wire-authentik-idp.py --verify
```

Secrets in **vault** (`vault_authentik_*`, `vault_logto_*`, `vault_identity_*`). `config/.identity/` is gitignored **DR fallback only** — every identity bootstrap reader must prefer `vault_*` and only then a file under `config/.identity/`. Do not git-add `.identity/`. Bootstrap dump `BOOTSTRAP-CREDENTIALS.txt` is historical, not SoT.

### Off-laptop copy of encrypted `vault.yml`

Do **not** invent a second secrets store. Encrypted `config/inventory/group_vars/all/vault.yml` is already in the **break-glass pack** (R2 + worker), which is the off-laptop backup:

| Destination | How |
|-------------|-----|
| Cloudflare R2 | `s3://cronnecture-fleet-backups/break-glass/latest/` via `make break-glass` (weekly cron) |
| Worker disk | `worker-general-01:/var/backups/cronnecture-break-glass/latest/` |
| Operator habit | Download `break-glass-pack.tar.gz` to an encrypted laptop / password manager after key rotation |

Details: [backup.md](backup.md#off-box-break-glass-pack). Vault password (`~/.ansible/vault_pass`) is in the same pack — without it the encrypted file is useless. `config/.identity/` is **not** in the pack; restore identity file fallbacks from vault after a laptop loss.

## Databases (Supabase cutover)

| Data store | Where | Notes |
|------------|-------|--------|
| Authentik | Supabase `cronnecture-identity` DB `authentik` | Migrated from PVC; Redis still on-cluster |
| Hanko | Supabase DB `hanko` | Migrated |
| Vaultwarden | Supabase DB `vaultwarden` | Migrated; attachments PVC unchanged |
| Logto | **On-cluster** `logto-postgres` | Supabase Supavisor returns `ENOIDENTIFIER` for Logto/Node; dedicated PVC |
| Passbolt | On-cluster MariaDB | CE is MySQL/MariaDB only — not Postgres |
| Redis | On-cluster `identity-redis` | Not Supabase |

Vault keys: `vault_identity_database_host/user/password/port/sslmode` (+ `vault_identity_supabase_project_ref`).  
Connection: session pooler `aws-0-eu-central-1.pooler.supabase.com:5432` with user `postgres.<ref>` (except Logto).

### Identity data protection (current vs later)

| Layer | What | Status |
|-------|------|--------|
| Fleet → R2 | Passbolt MariaDB dump (`identity/passbolt.sql.gz`) + emergency bundle | **Now** — `backup-fleet.sh` |
| Break-glass | Vault pass, vault.yml, SSH key, R2 env, inventory → R2 + worker | **Now** — `make break-glass` |
| Supabase `cronnecture-identity` | Authentik / Hanko / Vaultwarden | **No fleet `pg_dump`**. Provider **daily backups** only if the project is on a paid plan that includes them (Free has none). **PITR deferred** (~€100/mo) until HA / more VPS budget — see [RB-10](../runbooks/scale-to-ha.md) |
| Logto | On-cluster `logto-postgres` PVC | Re-seedable; not in fleet identity dump today |

Accepted for current scale: survive without identity PITR. When adding VPS / HA (5–7 nodes), enable PITR (or equivalent) on `cronnecture-identity` in the same step — [backup.md](backup.md), [roadmap.md](../architecture/roadmap.md).

**Rollback to full in-cluster Postgres:** clear `vault_identity_database_host`, `make identity`, restore `pg_dump`s into `identity-postgres`, scale STS back to 1.

## Bootstrap state (2026-08-12)

| Item | State |
|------|--------|
| Authentik version | **2026.5.6** on Supabase; MFA **forced on next login** (TOTP enroll) |
| Authentik SMTP | Stalwart `noreply@` — send test OK |
| Passbolt SMTP | Stalwart **:587** + `noreply@` (same secret). `:25` denies external relay — was the “Controleer je mailbox!” stall. |
| Authentik OIDC `cloudflare-access` | **LIVE** for CF Access (`vault_authentik_cf_oidc_*`; fallback `.identity/authentik_cloudflare_oidc.env`) |
| Authentik OIDC `logto-ciam` | Exists unused (future enterprise); **not** on Logto public SIE |
| Cloudflare Access ← Authentik | **LIVE** on web + ssh-* (no email OTP). Customer portal is Logto, not Access |
| Vaultwarden | Supabase DB; signups off; **`skip_access`**; prelogin/password **200** |
| Passbolt | Access → Authentik; **browser extension + recovery kit still required** |
| Logto | On-cluster `logto-postgres`; admin `sven`; MFA Mandatory TOTP; SMTP + **Google** on public SIE (Authentik social off SIE); Traditional app **Cronnecture customer portal** → CP `LOGTO_*` |
| Hanko | Healthy on Supabase; RP id `cronnecture.com` |
| Cerbos | Healthy; CP mounts `CERBOS_URL`/`CERBOS_ENABLED=1` (ops API mirror; fail-closed on destructive; OPS_API_TOKEN + superadmin skip) |
| SSH Access | `type=ssh` + SSH CA; Authentik MFA only |
| Ops password login | Off by default — Access email bridges ([operator-access.md](operator-access.md)) |

### Login paths

| Goal | Flow |
|------|------|
| Ops / staging-ops | **CF Access → Authentik → TOTP → ops dashboard** (no second password; session from Access email) |
| Passbolt / id-admin / webmail / wazuh | **CF Access → Authentik → password → TOTP** |
| Authentik admin | `https://auth.cronnecture.com` → password → TOTP enroll |
| Logto Admin | Access → Authentik → **`https://id-admin.cronnecture.com`** → Logto `sven` (+ TOTP). Do not use bare `id.cronnecture.com` / `/unknown-session`. |
| Logto CIAM (apps) | Start from the **app** (portal **Sign in** → `/api/auth/logto/login`), not bare `https://id.cronnecture.com/` (that redirects to `/unknown-session` by design). Public social **Google only** (+ password/MFA); callback `https://id.cronnecture.com/callback/google`. Authentik is **not** a product login button. |
| Vaultwarden / Bitwarden apps | `https://vault.cronnecture.com` only (no CF Access) |
| SSH | `cloudflared access ssh` → **CF Access → Authentik → TOTP** → **SSH CA** cert |
| Ops recovery (Authentik down) | SSH + `OPS_API_TOKEN`, or `OPS_PASSWORD_LOGIN=1` + per-user password |

### Phone Authenticator enrollment (Authentik)

1. Open e.g. `https://ops.cronnecture.com` → choose **Authentik**  
2. Or open `https://auth.cronnecture.com` directly  
3. Username `akadmin` (or email), bootstrap password from `BOOTSTRAP-CREDENTIALS.txt`  
4. When prompted **Configure Authenticator**, scan QR with phone (Google Authenticator / Aegis / 1Password)  
5. Enter 6-digit code — required on every later login  
6. Change password after first successful MFA login  

Logto admin (`sven`): same idea inside Logto Admin Console → MFA / security (policy already **Mandatory** TOTP).

### Bitwarden app (Vaultwarden)

Native Bitwarden clients cannot complete Cloudflare Access challenges → **`skip_access: true`** on `vault.cronnecture.com`.

1. Bitwarden → **Logging in on a self-hosted server**  
2. **Server URL:** `https://vault.cronnecture.com` (no path, no Custom environment unless required)  
3. Email + master from `BOOTSTRAP-CREDENTIALS.txt` / `vaultwarden_owner_password`

### Remaining manual steps

1. **Scan TOTP** on Authentik (`akadmin`) with phone (forced on next login) — **required once**  
2. **Passbolt** — open setup URL in BOOTSTRAP (or recovery URL below); finish browser extension + **save recovery kit** (cannot be done headless). SMTP is Stalwart `:587`/`noreply@`; if UI says “Controleer je mailbox!” check spam for `noreply@cronnecture.com`, or admin alternate:
   ```bash
   # On worker / passbolt pod — prints a one-time recover URL (no email required):
   ./bin/cake passbolt recover_user -c -u svenbraad.work@gmail.com
   ./bin/cake passbolt send_test_email --recipient=svenbraad.work@gmail.com
   ```
3. **Vaultwarden** — change master password after login (account intact on Supabase)  
4. **Logto admin** — open `https://id-admin.cronnecture.com` (Access → Authentik) → sign in as `sven` → **enroll TOTP** if not already (MFA Mandatory). Password in `vault_logto_admin_password` (fallback `config/.identity/logto_admin_password`).  
5. **Prefer vault** for bootstrap passwords; keep `.identity/` files as local DR fallback only. Do not commit them.  
6. **Google → Logto** — connector is wired. **Do not rotate** the Google client secret unless an operator explicitly requests it (rotation is deferred). Confirm Console redirect URI below.  
7. **Revoke** any chat-pasted CF bootstrap tokens (if not already)  

**Logto (done):** admin `sven`; connectors `smtp-stalwart` + `google` on public SIE; `authentik-oidc` connector row may remain but **not** on default SIE; MFA Mandatory on admin + default; Traditional app **Cronnecture customer portal** registered; CP OIDC bridge `/api/auth/logto/*` + portal **Sign in** button.

**Later (with HA / more VPS — not urgent):** enable Supabase **PITR** on `cronnecture-identity` (or equivalent continuous recovery) when scaling per [RB-10](../runbooks/scale-to-ha.md). Do **not** enable paid PITR until that budget step.

### Google OIDC → Logto (wired)

**Cost:** Standard [Sign in with Google](https://developers.google.com/identity/sign-in/web/sign-in) / OAuth for consumer Google accounts is **free** — Google does **not** charge per login.

**Status:** Connector `google` (`google-universal`) is the only social on the default tenant sign-in experience. Secrets in `vault_logto_google_client_id` / `vault_logto_google_client_secret` (fallback `config/.identity/logto_google_oauth.env`).

**Google Cloud Console (confirm / fix):**
1. Authorized JavaScript origins: `https://id.cronnecture.com`  
2. Authorized redirect URIs: **`https://id.cronnecture.com/callback/google`**  
3. **Do not rotate** the Google client secret unless an operator explicitly requests it (rotation is deferred). If rotation is later approved, update vault + `.identity/logto_google_oauth.env` + Logto connector config — never commit the secret.

Scaffold reference: [logto-google-connector.json](examples/logto-google-connector.json).

### Customer portal / Logto CIAM

- **Edge (existing clients):** Cloudflare Access on `client.*/client/portal/*` stays **Authentik-only** allowlists (unchanged for autoklaver etc.).  
- **Product SSO (wired):** Logto Traditional app **Cronnecture customer portal** at `https://id.cronnecture.com`; CP env `LOGTO_ENDPOINT` / `LOGTO_APP_ID` / `LOGTO_APP_SECRET` from vault (`vault_logto_*`; fallback `config/.identity/logto_portal_app_*`).  
- **Bridge:** `GET /api/auth/logto/login` → Logto → `GET /api/auth/logto/callback` → `cp_logto_session` cookie; portal APIs accept Access email **or** Logto session email (allowlist still enforced). Portal UI **Sign in** when Logto is configured.  
- **Future client apps:** use Logto SDK against `https://id.cronnecture.com` with a dedicated Application (or reuse this Traditional app’s redirect URIs). Short guide: [client-portal.md](../platform/client-portal.md#logto-product-sso).  

## Ops notes

| Item | Detail |
|------|--------|
| Namespace | `identity` |
| Manifests | `/var/lib/rancher/k3s/server/manifests/identity-stack.yaml` (+ cerbos) |
| Role | `roles/identity_stack` |
| Authentik image pin | `identity_authentik_image` → `2026.8.0` |
| OIDC for CF | `vault_authentik_cf_oidc_*` (fallback `config/.identity/authentik_cloudflare_oidc.env`) |
| OIDC for Logto (unused on public SIE) | `vault_authentik_logto_oidc_*` (fallback `config/.identity/authentik_logto_oidc.env`) |
| Team domain | `curly-frog-441a.cloudflareaccess.com` |
| CF wire script | `scripts/cloudflare/cf-wire-authentik-idp.py` |
| CF notes | `scripts/cloudflare/cf-authentik-access-notes.md` |

```bash
sudo kubectl -n identity get pods,svc
curl -sf http://127.0.0.1:30113/-/health/ready/
curl -sf http://127.0.0.1:30113/api/v3/admin/version/ -H "Authorization: Bearer $AUTHENTIK_API_TOKEN"
curl -sf -o /dev/null -w '%{http_code}\n' -X POST https://vault.cronnecture.com/identity/accounts/prelogin/password \
  -H 'Content-Type: application/json' -d '{"email":"svenbraad.work@gmail.com"}'
```

`kubectl logs/exec` to worker pods needs apiserver → kubelet `:10250`. That path is peer-only (UFW). If exec hangs or returns kubelet EOF, check leftover `fleet-input-guard` DROP rules on the worker (`iptables -S INPUT | grep 10250`) — `baseline.yml` removes them.
