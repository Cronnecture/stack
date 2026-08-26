# Staging setup and standard release

Runbook **RB-13**.

One-time staging sandbox setup, then the daily **staging → smoke → production** release flow.

**Security note:** staging is a UX sandbox on the **same cluster** (shared registry, mail, CF tokens unless you override vault). Write-guards prevent staging from mutating prod clients; it is **not** a tenant isolation boundary.

## When to use

| Situation | Command |
|-----------|---------|
| First-time staging setup | Follow **One-time setup** below |
| Normal control-plane code change | `make release` |
| Staging only (no prod touch) | `make deploy-staging` |
| Production only (emergency) | `SKIP_STAGING=1 make release` or `make deploy-production` |
| Confirm before prod promote | `CONFIRM=1 make release` |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  make release                                               │
│    1. deploy-staging  →  platform-staging  :30081         │
│    2. smoke tests     →  health, maintenance, readiness   │
│    3. deploy-production → platform           :30080 (×2)  │
└─────────────────────────────────────────────────────────────┘

Staging                          Production
─────────────────────────        ─────────────────────────
namespace: platform-staging      namespace: platform
NodePort:  30081                 NodePort:  30080
replicas:  1                     replicas:  2
DB:        staging Supabase      DB:        production Supabase
host:      staging-ops.{zone}     host:      ops.{zone}
```

Staging shares the **production mail stack** and **container registry**. It never modifies client Traefik routes or the `platform` namespace until you promote.

Config lives under:

```
config/environments/
  production/group_vars/all/main.yml
  staging/group_vars/all/main.yml
  staging/group_vars/all/vault.yml    ← staging Supabase URI only
```

Production Cloudflare tokens and most vault secrets come from `config/inventory/group_vars/all/vault.yml`. Staging vault only overrides `vault_platform_database_url`.

---

## One-time setup

Complete these once before the first `make release`.

### 1. Staging Supabase project

**Current status (2026-08-26):** the previous `cronnecture-staging` project (`xsnstmwycerlibgmeuem`) is deleted. Recreate a new project before the next `make deploy-staging`. Dump: `/home/dev/backups/db-cleanup-2026-08-26/cronnecture-staging-postgres.sql.gz`.

See [supabase.md](../operations/supabase.md#staging-project) for full detail.

1. [Supabase dashboard](https://supabase.com/dashboard) → **New project** (e.g. `cronnecture-staging`).
2. Region: match production if possible (e.g. `eu-west-1` or `eu-central-1`).
3. Save the database password securely.
4. **Project Settings → Database → Connection string → URI**
5. Copy the **Transaction pooler** URI (port **6543**), append `?sslmode=require`.

Example shape (do not commit real passwords):

```yaml
vault_platform_database_url: "postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require"
```

**Port guide:**

| Port | Mode | Use for |
|------|------|---------|
| **6543** | Transaction pooler | Running control-plane API (staging + production) |
| **5432** | Session pooler / direct | Migrations, `psql`, SQL editor |

6. Apply schema once (optional but recommended):

   - **SQL Editor** → paste `services/control-plane/schema.sql` → Run  
   - Or: `psql "$SESSION_POOLER_URI?sslmode=require" -f services/control-plane/schema.sql`

   If skipped, SQLAlchemy creates tables on first pod start.

You do **not** need a separate leads project, mail PostgREST keys, or production data copy for staging.

### 2. Staging vault

On the control machine:

```bash
cd $FLEET_ROOT

cp config/environments/staging/group_vars/all/vault.yml.example \
   config/environments/staging/group_vars/all/vault.yml

ansible-vault edit config/environments/staging/group_vars/all/vault.yml
```

Set only:

```yaml
vault_platform_database_url: "postgresql://postgres....:6543/postgres?sslmode=require"
```

Encrypt if still plaintext:

```bash
ansible-vault encrypt config/environments/staging/group_vars/all/vault.yml
```

### 3. Deploy staging and verify

```bash
make deploy-staging
curl -sf http://127.0.0.1:30081/api/health/ready
curl -sf http://127.0.0.1:30081/api/platform/readiness | python3 -m json.tool
```

Success: `"checks":{"database":"ok"}` and `"ready": true`.

### 4. Staging DNS (optional but recommended)

In **Cloudflare DNS** for your platform zone:

| Type | Name | Target |
|------|------|--------|
| CNAME | `staging-ops` | `{tunnel-id}.cfargotunnel.com` (same tunnel as `ops`) |

Use **`staging-ops.{zone}`** (not `staging.ops.{zone}`). Cloudflare Universal SSL covers `*.cronnecture.com` only — nested names like `staging.ops` fail TLS handshake. Self-serve day-1 hosts use `{slug}.sites.cronnecture.com` under a **dedicated** Cloudflare zone for `sites.cronnecture.com` (so that zone’s Universal SSL covers `*.sites…`).

Tunnel ingress hostname is `control_plane_public_host` (`staging-ops.cronnecture.com` by default).

Without DNS, use NodePort locally: `http://127.0.0.1:30081`.

### 5. Mail reverse DNS (Hostinger)

Outbound SMTP reputation only — does not affect inbound mail or websites. See [mail.md](../operations/mail.md#reverse-dns-ptr-hostinger).

---

## Standard release (daily)

After one-time setup:

```bash
cd $FLEET_ROOT
make release
```

Script: `scripts/fleet/release-control-plane.sh`

Steps:

1. **Staging deploy** — build image, Ansible playbook with staging overlay
2. **Staging smoke** — `/api/health/live`, `/api/health/ready`, `/api/maintenance`, `/api/platform/readiness`
3. **Production deploy** — pre `make health`, rolling update (`maxSurge: 1`, `maxUnavailable: 0`)
4. **Production smoke** — same endpoints on port 30080

### Variants

```bash
CONFIRM=1 make release          # prompt before production step
SKIP_STAGING=1 make release     # skip staging (emergency)
make deploy-production          # production only, with health gates
make deploy-staging             # staging only
```

### Vault-only changes (no code)

Secrets are baked into k8s at deploy time. After editing vault:

```bash
make deploy-staging      # or make deploy-production
# If image tag unchanged, force pod reload:
sudo k3s kubectl -n platform rollout restart deployment/control-plane
sudo k3s kubectl -n platform-staging rollout restart deployment/control-plane
```

---

## Verification checklist

### Staging

```bash
curl -sf http://127.0.0.1:30081/api/health/ready
curl -sf https://staging-ops.cronnecture.com/api/health/ready
```

### Production

```bash
make health
curl -sf http://127.0.0.1:30080/api/health/ready
curl -sf https://ops.cronnecture.com/api/health/ready
sudo k3s kubectl -n platform get pods -l app=control-plane
sudo k3s kubectl -n platform rollout status deployment/control-plane
```

### Maintenance edge (after CF Worker setup)

```bash
curl -s http://127.0.0.1:30080/api/maintenance | python3 -m json.tool
# Expect: "layer": "cloudflare-worker", "worker_configured": true
```

---

## Rollback

```bash
# Undo last production rollout
sudo k3s kubectl -n platform rollout undo deployment/control-plane

# Redeploy known-good git commit
git checkout <sha> -- services/control-plane/
make deploy-production
```

Staging rollback does not affect production:

```bash
sudo k3s kubectl -n platform-staging rollout undo deployment/control-plane
```

---

## Rotate staging database password

1. Supabase → **Project Settings → Database → Reset database password**
2. `ansible-vault edit config/environments/staging/group_vars/all/vault.yml`
3. Update `vault_platform_database_url` (pooler **6543**)
4. `make deploy-staging`

Never paste database passwords in chat, tickets, or commit logs.

---

## Related

- [deployment.md](../operations/deployment.md) — overview and downtime matrix
- [supabase.md](../operations/supabase.md) — production + staging database setup
- [RB-04 Deploy control plane](deploy-control-plane.md) — playbook details, troubleshooting
- [RB-06 Cloudflare tokens](cloudflare-tokens.md) — mint scoped API tokens
- [maintenance.md](../operations/maintenance.md) — edge maintenance during deploys
- [mail.md](../operations/mail.md) — PTR, deliverability, external mail tests
