# Supabase database integration

All fleet Postgres databases run in **Supabase**, not in the k3s cluster.

| Workload | Database | Connection |
|----------|----------|------------|
| Control plane — **production** | Supabase project | `vault_platform_database_url` in main vault |
| Control plane — **staging** | Deferred — recreate a new project | Empty `vault_platform_database_url` until a new project exists. Old dump: `/home/dev/backups/db-cleanup-2026-08-26/cronnecture-staging-postgres.sql.gz` |
| Identity (Authentik) | In-cluster `identity-postgres` DB `authentik` | Live host `identity-postgres` |
| Identity (Vaultwarden) | Cloud project `cronnecture-identity` | Session pooler `:5432` |
| Identity (Hanko) | In-cluster `identity-postgres` DB `hanko` (orphaned) | Retired 2026-08-26 |
| Client apps (deployed via ops UI) | Supabase (per app or shared project) | `DATABASE_URL` in app deploy env |

**Not on Supabase:** Passbolt CE (MariaDB) and Authentik Redis stay on-cluster in `identity` ns. Authentik Postgres is in-cluster `identity-postgres`. Vaultwarden uses project `cronnecture-identity`. Logto was retired 2026-08-26.

## Connection strings — which port?

| Port | Pooler mode | Use for |
|------|-------------|---------|
| **6543** | Transaction | **Running control-plane API** (staging + production, 1 or 2 replicas) |
| **5432** | Session / direct | Migrations, SQL editor, `psql`, one-off admin |

Always append `?sslmode=require` to URIs in vault if not present.

Example transaction pooler (production or staging):

```yaml
vault_platform_database_url: "postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require"
```

The region in the hostname (`eu-west-1`, `eu-central-1`, …) must match the project region shown in Supabase dashboard.

## Control plane setup (production)

1. Create a Supabase project (or use an existing org project).
2. **Project Settings → Database → Connection string → URI**
3. Prefer the **transaction pooler** (port **6543**) for the running API.
4. Append `?sslmode=require` if it is not already in the URI.
5. Add to encrypted vault:

```yaml
vault_platform_database_url: "postgresql://postgres.xxxxx:PASSWORD@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require"
```

6. Apply schema once (direct connection, port **5432**, or Supabase SQL editor):

```bash
psql "$DIRECT_DATABASE_URL" -f services/control-plane/schema.sql
```

7. Redeploy:

```bash
make control-plane
```

When `vault_platform_database_url` is set, Ansible **stops deploying** the in-cluster `postgres` Deployment/PVC. The control plane runs **2 replicas** in production with leader-elected background jobs.

## Staging project

**Deferred (2026-08-26):** the previous project `cronnecture-staging` (`xsnstmwycerlibgmeuem`) was deleted. Dump is at `/home/dev/backups/db-cleanup-2026-08-26/cronnecture-staging-postgres.sql.gz`. Recreate a new empty project and put its transaction-pooler URI in the staging vault before `make deploy-staging`.

Staging uses a **separate empty Supabase project** so schema experiments and bad deploys never touch production data.

**Full procedure:** [RB-13 Staging and release](../runbooks/staging-and-release.md)

Summary:

1. Create project (e.g. `cronnecture-staging`) in [Supabase dashboard](https://supabase.com/dashboard).
2. Copy **transaction pooler** URI (port **6543**), add `?sslmode=require`.
3. Save in encrypted staging vault only:

```bash
cp config/environments/staging/group_vars/all/vault.yml.example \
   config/environments/staging/group_vars/all/vault.yml
ansible-vault edit config/environments/staging/group_vars/all/vault.yml
```

```yaml
vault_platform_database_url: "postgresql://postgres.STAGING_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require"
```

4. Apply `services/control-plane/schema.sql` via SQL editor (recommended).
5. `make deploy-staging` and verify:

```bash
curl -sf http://127.0.0.1:30081/api/health/ready
```

**What staging does not need:**

| Item | Required? |
|------|-----------|
| Copy production data | No — empty DB |
| Separate leads / mail Supabase keys | No — inherits from main vault |
| Per-client Supabase projects | No — created later via ops UI |

**Password rotation:** Supabase → reset DB password → update staging vault → `make deploy-staging`. Never commit or paste passwords in chat.

## Backups

See [backup.md](backup.md). Daily etcd snapshots + fleet → R2 on the control node.

- **Control plane:** prefer provider daily backups (paid plans); PITR when budget allows.
- **`cronnecture-identity`:** PITR **deferred** until HA / more VPS budget (~€100/mo). Free tier has no automatic daily backups; Pro+ rolling dailies apply only if that project is on a paid plan. Passbolt is covered by fleet MariaDB dumps.

## Migrating from in-cluster Postgres

If the fleet already has data in the cluster postgres PVC:

1. Add `vault_platform_database_url` to vault (do not deploy yet).
2. Port-forward or exec into the old postgres pod and dump:

```bash
kubectl -n platform exec deploy/postgres -- pg_dump -U controlplane controlplane > controlplane.sql
```

3. Load into Supabase via direct URI (`psql` or SQL editor).
4. Set `vault_platform_database_url` and run `make control-plane`.
5. Verify `https://ops.cronnecture.com/api/health/live`, `/api/health`, and spot-check clients/apps in the UI.
6. Optionally delete legacy resources after a soak period:

```bash
kubectl -n platform delete deploy/postgres svc/postgres pvc/postgres-data
```

## Client apps

Operator checklist for repo layout, build-args, and `VITE_SUPABASE_*` / `DATABASE_URL` wiring: **[client-app-repo.md](../platform/client-app-repo.md)**.

Prefer **one isolated Supabase project per client** (auto-created when Management API credentials are configured).

### Auto-create (Management API)

Vault keys (mounted into the control-plane pod):

| Vault | Env |
|-------|-----|
| `vault_supabase_access_token` | `SUPABASE_ACCESS_TOKEN` |
| `vault_supabase_org_id` | `SUPABASE_ORG_ID` |
| `vault_supabase_region` | `SUPABASE_REGION` (default `eu-central-1`) |

Mint a personal access token at [supabase.com/dashboard/account/tokens](https://supabase.com/dashboard/account/tokens) with permission to create projects in the org. Verify with **Settings → Integrations → Test** (`POST /api/settings/test-supabase-mgmt`) or:

```bash
curl -sf -X POST http://127.0.0.1:30080/api/settings/test-supabase-mgmt
```

On wizard launch with pack **Site + Supabase** (or DB mode `supabase`) and empty credential fields, the `provision_client` job:

1. `POST /v1/projects` → name `client-{slug}`
2. Polls until `ACTIVE_HEALTHY`
3. Fetches API keys + builds pooler `DATABASE_URL`
4. Writes the client namespace secret and marks `client_databases` **ready**

Manual paste (URL + anon key) still works as a fallback when Management API is off or you want an existing project.

Apps bootstrapped through the ops UI may already declare `VITE_SUPABASE_*` or `DATABASE_URL`. During deploy, env is filled from the linked client database.

**Marketing / main site:** standalone previews (no `client_id`) and `POST /api/previews/{id}/promote-website` auto-fill empty `VITE_SUPABASE_*` from platform leads settings (`vault_supabase_leads_*`) at Kaniko build time. Persist the promoted image in `platform_sites.yml`.

The repo analyzer warns when Prisma or backend profiles are detected without `DATABASE_URL` — point those at Supabase before first deploy.

## Backups and HA

- **Backups**: Provider daily backups on paid plans; identity **PITR deferred** to HA scale-up ([RB-10](../runbooks/scale-to-ha.md)). No in-cluster Postgres CronJob for Supabase-hosted DBs. Passbolt MariaDB is dumped by `backup-fleet.sh`.
- **Control plane HA**: With an external DB, production already runs **2 control-plane replicas** (leader-elected jobs); the database is not tied to a single k3s node PVC.

## Local development

Copy `services/control-plane/.env.example` and set `DATABASE_URL` to your Supabase pooler URI.
