# Identity & secrets platform

Top-tier self-hosted identity, password management, secret sharing, CIAM, and authorization — without replacing **Cloudflare Access SSH**.

## Hard rules

| Path | Auth |
|------|------|
| `ssh-*.cronnecture.com` | Cloudflare Access → **Authentik only** (password + TOTP) → **SSH CA** short-lived cert (`cloudflared access ssh`). Keep `type=ssh` — never password SSH. No email OTP. |
| Web admin UIs | Cloudflare Access → **Authentik OIDC only** (MFA). No email OTP on ops/passbolt/wazuh/id-admin/webmail. |
| Public IdP / CIAM / vault | No Access (OIDC + Bitwarden clients) |

Do **not** remove Cloudflare SSH CA or convert SSH Access apps to self-hosted/password SSH. See `config/inventory/group_vars/all/cf_ssh.yml` and `roles/cloudflare_mgmt/tasks/ssh_access.yml`.

## Wired architecture (2026-08-26)

```
Internet
   │
   ├─ Cloudflare Access (web + ssh-*) ──► Authentik OIDC only (no email OTP)
   │         │
   │         ├─ ops / control / passbolt / webmail / id-admin leftovers / …
   │         └─ ssh-*.cronnecture.com  (type=ssh) ──► SSH CA short-lived cert
   │
   ├─ client.cronnecture.com (Access off) ──► Authentik product OIDC (invite-only)
   │         cookie cp_oidc_session (cp_logto_session still accepted)
   │
   └─ Public (no Access) ──► auth (Authentik) / vault (Vaultwarden)
                                      │
                                      ▼
                               identity ns ClusterIP + Cerbos

Databases:
  Authentik → in-cluster identity-postgres
  Vaultwarden → Supabase project cronnecture-identity (session pooler :5432)
  Passbolt → on-cluster MariaDB (CE is MySQL-only)
  Authentik Redis → on-cluster identity-redis

Mail path: Authentik + Passbolt → Stalwart (mail ns) submission **:587** as `noreply@cronnecture.com`
Logto cluster objects were **deleted 2026-08-26**. Product SSO is Authentik. Cookie / env names still say logto.
Authentik = admin/ops edge IdP (CF Access) **and** customer portal OIDC.
MFA: Authentik TOTP for ops and product.
```

## Components

| Service | URL | Exposure | Role |
|---------|-----|----------|------|
| **Vaultwarden** | `https://vault.cronnecture.com` | **No Cloudflare Access** (`skip_access`) | Ops password vault (Bitwarden clients); use **Send** for one-time secrets |
| **Passbolt** | `https://passbolt.cronnecture.com` | Access → Authentik | Team credential sharing + audit |
| **Authentik** | `https://auth.cronnecture.com` | Public | Admin/ops edge IdP **and** customer-portal OIDC (**2026.8.0**). **1 replica** on in-cluster `identity-postgres`. |
| **Logto** | — | **Retired 2026-08-26** | Cluster objects deleted. `authentik_oidc.py` is the portal SSO client. Historical aliases: cookie `cp_logto_session`, path `/api/auth/logto/login`. |
| **Logto Admin** | `https://id-admin.cronnecture.com` | leftover DNS | Do not treat as live product SSO. |
| **Hanko** | — | **Retired 2026-08-26** | Cluster objects deleted. Orphan DB `hanko` may remain on identity-postgres until a PVC rebuild. |
| **Cerbos** | `identity/cerbos:3592` | ClusterIP | Fine-grained AuthZ (ops policies shipped). **2 replicas**, required anti-affinity. |

Logto and Hanko are retired. Cerbos runs **2 replicas**. Authentik stays **1 replica**. Operator failsafe: [RB-16](../runbooks/identity-failsafe.md).

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
| Authentik | In-cluster `identity-postgres` DB `authentik` | Migrated off Supabase 2026-08-26 |
| **Hanko** | In-cluster `identity-postgres` — **database dropped 2026-08-27** (dump in `/home/dev/backups/db-cleanup-2026-08-26`) | Retired 2026-08-26; cluster objects deleted |
| Vaultwarden | Supabase DB `vaultwarden` | Attachments PVC unchanged |
| Logto | **Deleted 2026-08-26** | Do not restore without a dedicated cutover |
| Passbolt | On-cluster MariaDB | CE is MySQL/MariaDB only — not Postgres |
| Redis | On-cluster `identity-redis` | Not Supabase |

Vault keys: `vault_identity_database_host/user/password/port/sslmode` (+ `vault_identity_supabase_project_ref`) for Vaultwarden. Authentik uses in-cluster `identity-postgres`.

### Identity data protection (current vs later)

| Layer | What | Status |
|-------|------|--------|
| Fleet → R2 | Passbolt MariaDB dump (`identity/passbolt.sql.gz`) + emergency bundle | **Now** — `backup-fleet.sh` |
| Break-glass | Vault pass, vault.yml, SSH key, R2 env, inventory → R2 + worker | **Now** — `make break-glass` |
| Supabase `cronnecture-identity` | Vaultwarden only | **No fleet `pg_dump`**. Provider **daily backups** only if the project is on a paid plan. **PITR deferred**. |
| Authentik | In-cluster `identity-postgres` PVC | **Required** `pg_dump authentik` in `backup-fleet.sh` when the STS has replicas |
| Hanko | Orphan DB on identity-postgres | Retired 2026-08-26; dump is best-effort if the DB still exists |
| Logto | Retired | — |

Accepted for current scale: survive without identity PITR. When adding VPS / HA (5–7 nodes), enable PITR (or equivalent) on `cronnecture-identity` in the same step — [backup.md](backup.md), [roadmap.md](../architecture/roadmap.md).

**Rollback to full in-cluster Postgres:** clear `vault_identity_database_host`, `make identity`, restore `pg_dump`s into `identity-postgres`, scale STS back to 1.

## Bootstrap state (2026-08-12)

| Item | State |
|------|--------|
| Authentik version | **2026.8.0** on in-cluster Postgres; MFA **forced on next login** (TOTP enroll) |
| Authentik SMTP | Stalwart `noreply@` — send test OK |
| Passbolt SMTP | Stalwart **:587** + `noreply@` (same secret). `:25` denies external relay — was the “Controleer je mailbox!” stall. |
| Authentik OIDC `cloudflare-access` | **LIVE** for CF Access (`vault_authentik_cf_oidc_*`; fallback `.identity/authentik_cloudflare_oidc.env`) |
| Authentik OIDC `logto-ciam` | Exists unused (future enterprise); **not** on Logto public SIE |
| Cloudflare Access ← Authentik | **LIVE** on web + ssh-* (no email OTP). Customer portal is Authentik OIDC (`cp_oidc_session`), not Access |
| Vaultwarden | Supabase DB; signups off; **`skip_access`**; prelogin/password **200** |
| Passbolt | Access → Authentik; **browser extension + recovery kit still required** |
| Logto | **Retired 2026-08-26** | Cluster objects gone; names linger in code |
| Hanko | **Retired 2026-08-26** | Cluster objects deleted; do not send customers to `passkeys.cronnecture.com` |
| Cerbos | Healthy; CP mounts `CERBOS_URL`/`CERBOS_ENABLED=1` (ops API mirror; fail-closed on destructive; OPS_API_TOKEN + superadmin skip) |
| SSH Access | `type=ssh` + SSH CA; Authentik MFA only |
| Ops password login | Off by default — Access email bridges ([operator-access.md](operator-access.md)) |

### Login paths

| Goal | Flow |
|------|------|
| Ops / staging-ops | **CF Access → Authentik → TOTP → ops dashboard** (no second password; session from Access email) |
| Passbolt / webmail | **CF Access → Authentik → password → TOTP** |
| Authentik admin | `https://auth.cronnecture.com` → password → TOTP enroll |
| Product portal | `https://client.cronnecture.com` → Authentik OIDC (`/api/auth/oidc/login`) → `cp_oidc_session` |
| Logto Admin / `id.cronnecture.com` | **Retired** — do not send customers here |
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

Logto is gone. Portal OIDC lives in `authentik_oidc.py` (`AUTHENTIK_PORTAL_*`). Canonical login is `/api/auth/oidc/login` (cookie `cp_oidc_session`; `cp_logto_session` is still accepted).

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
4. **Prefer vault** for bootstrap passwords; keep `.identity/` files as local DR fallback only. Do not commit them.  
5. **Google → Authentik** — social login is on the Authentik portal application. **Do not rotate** the Google client secret unless an operator explicitly requests it.  
7. **Revoke** any chat-pasted CF bootstrap tokens (if not already)  

Product SSO is Authentik (`authentik_oidc.py`). Canonical bridge: `/api/auth/oidc/login` → `/api/auth/oidc/callback` with cookie `cp_oidc_session`. `/api/auth/logto/*` and `cp_logto_session` remain aliases.

**Later (with HA / more VPS — not urgent):** enable Supabase **PITR** on `cronnecture-identity` (or equivalent continuous recovery) when scaling per [RB-10](../runbooks/scale-to-ha.md). Do **not** enable paid PITR until that budget step.

### Google OIDC / Logto CIAM (retired 2026-08-26)

Logto is gone. Do **not** point Google OAuth or new client apps at `id.cronnecture.com`. Product SSO is Authentik at `auth.cronnecture.com`. Canonical bridge: `/api/auth/oidc/login` → `/api/auth/oidc/callback` with cookie `cp_oidc_session`. `/api/auth/logto/login` and `cp_logto_session` remain aliases.

Customer hub: `client.cronnecture.com` (Access off, invite-only). NoordDrive shop is public (no site-gate). Cookie `_site_logto` is frozen.  

## Ops notes

| Item | Detail |
|------|--------|
| Namespace | `identity` |
| Manifests | `/var/lib/rancher/k3s/server/manifests/identity-stack.yaml` (+ cerbos) |
| Role | `roles/identity_stack` |
| Authentik image pin | `identity_authentik_image` → `2026.8.0` |
| OIDC for CF | `vault_authentik_cf_oidc_*` (fallback `config/.identity/authentik_cloudflare_oidc.env`) |
| OIDC leftover `logto-ciam` (unused) | `vault_authentik_logto_oidc_*` — not product SSO |
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
