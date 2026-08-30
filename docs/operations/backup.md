# Backup and disaster recovery

What to back up, how automation handles it, and how to restore without adding nodes.

## Critical off-repo assets

Store these **outside Git** in a password manager or secure vault:

| Asset | Location | If lost |
|-------|----------|---------|
| Ansible vault password | `~/.ansible/vault_pass` | Cannot decrypt `vault.yml` |
| SSH private key | `~/.ssh/id_ed25519` | Cannot SSH to nodes |
| Supabase credentials | In encrypted vault + Supabase dashboard | DB access lost |
| Ops runner token | `/etc/cronnecture/ansible-runner.token` | Ops cannot run Ansible on host |
| Ops admin password | `/etc/cronnecture/ops-admin.password` | Cannot log into ops UI |
| R2 backup credentials | `/etc/cronnecture/backup-r2.env` | Cannot pull off-site backups |

### Off-box break-glass pack

Automated weekly (Sun 04:00 UTC) and on demand via `make break-glass` / ops **Off-box break-glass pack**.

The sealed tarball (secrets never committed to git) is synced to:

| Destination | Path |
|-------------|------|
| **R2** (primary) | `s3://cronnecture-fleet-backups/break-glass/latest/` |
| **Worker** (secondary) | `worker-general-01:/var/backups/cronnecture-break-glass/latest/` |
| Control local (convenience only) | `/var/backups/cronnecture-break-glass/latest/` |

Pack includes: `vault_pass`, encrypted `vault.yml` (**this is the off-laptop vault backup** — do not invent a second secrets store), SSH deploy key (+ fingerprint in checklist), `ansible-runner.token`, `ops-admin.password`, `backup-r2.env`, latest backup stamp pointer, inventory snapshot. See [RB-11](../runbooks/emergency-management.md#off-box-break-glass-pack). `config/.identity/` is a local DR fallback only and is not packed; restore those files from vault after laptop loss.

**Operator habit:** download `break-glass-pack.tar.gz` to an encrypted laptop / password manager once after each key rotation.

Verify backups quarterly: decrypt vault, SSH to each node, restore Supabase to a test project.

## Automated on the control node

The `fleet_ops` role installs cron jobs (via `make site` or `make fleet-ops`):

| Schedule | Job | Log |
|----------|-----|-----|
| Daily 03:00 UTC | k3s etcd snapshot | `/var/log/k3s-etcd-snapshot.log` |
| Daily 03:15 UTC | Fleet backup script | `/var/log/cronnecture-fleet-backup.log` |
| Every 15 min | Health check | `/var/log/cronnecture-fleet-health.log` |
| Weekly Mon 06:00 | Placement rebalance audit | `/var/log/cronnecture-fleet-rebalance.log` |
| Hourly | Cloudflare policy sync | `/var/log/cronnecture-cloudflare.log` |

Backups land in `/var/backups/cronnecture-fleet/<timestamp>/`:

- etcd snapshot (via `k3s etcd-snapshot save`)
- `cf_clients.yml` copy
- **operator books** (`/var/lib/cronnecture/books` → `operator-books/`) plus control-plane **`/data/client-documents`** tar
- **`emergency/`** bundle — `hosts.ini`, ingress routes, restore README ([RB-11](../runbooks/emergency-management.md))
- kubectl node/pod snapshots
- git HEAD reference

Legal/commercial PDFs also copy live to R2 prefix `operator-books/{legal,commercial,startup-invoices,client-docs}/`. Operator ledger: `operator-books/ledger.json`.

Manual run:

```bash
FLEET_ROOT=$PWD /usr/local/lib/cronnecture-fleet/backup-fleet.sh
```

## Cloudflare R2 off-site sync

**Registry (images):** bucket `cronnecture-fleet-registry` via `vault_registry_s3_*` — see [RB-12](../runbooks/registry-recovery.md) and `make r2-registry`.

**Fleet backups (bundles):** separate bucket (default `cronnecture-fleet-backups`) via `vault_backup_s3_*`. After each successful local backup, `sync-backup-r2.sh` uploads to:

`s3://<bucket>/fleet-backups/<YYYYMMDD-HHMMSS>/`

Setup (Ansible control host):

```bash
./bin/fleet-r2-backups          # create bucket + vault_backup_s3_* keys
make fleet-ops                  # /etc/cronnecture/backup-r2.env on k3s_server
make control-plane              # ops UI shows R2 status under Automations → Backups
```

Credentials on the control node: `/etc/cronnecture/backup-r2.env` (mode 600). Last sync marker: `/var/backups/cronnecture-fleet/.r2-last-sync`.

Ops UI: **Platform → Automations → Fleet backups → Cloudflare R2**.

## Supabase (control plane + identity DBs)

| Project | Workloads | Backups |
|---------|-----------|---------|
| Control plane (`vault_platform_database_url`) | Ops / clients registry | Prefer provider daily backups (paid plans). PITR when budget allows |
| **`cronnecture-identity`** (`vault_identity_database_*`) | Vaultwarden | **PITR deferred** until HA / more VPS budget (~€100/mo — not urgent). Free tier has **no** automatic daily backups; Pro+ includes rolling daily backups if the project is upgraded. Authentik is **not** on this project (in-cluster `identity-postgres`, dumped by `backup-fleet.sh`). |

- Control-plane schema: `services/control-plane/schema.sql`
- Re-register clients in the ops UI if DB is empty but cluster remains.
- **Logto** was retired 2026-08-26 (not this Supabase project) — see [identity.md](identity.md).

See [supabase.md](supabase.md) and [identity.md](identity.md). When scaling VPS/HA ([RB-10](../runbooks/scale-to-ha.md)), enable identity PITR (or equivalent) in the same wave.

### Identity protection (what actually runs today)

| Layer | Coverage |
|-------|----------|
| Fleet → R2 (`backup-fleet.sh`) | Passbolt MariaDB dump; emergency bundle; etcd snapshot |
| Break-glass (`make break-glass`) | Vault, SSH, R2 env, inventory → R2 + worker |
| Supabase `cronnecture-identity` | Provider backups only if plan includes them; **no PITR until HA scale-up** |
| Optional rollback dumps | `identity/*.sql.gz` only if `identity-postgres` STS still has replicas |

### Identity on-cluster dumps (fleet backup)

`backup-fleet.sh` (full) writes `identity/` into each bundle and syncs to R2:

| Artifact | Source |
|----------|--------|
| `identity/passbolt.sql.gz` | Passbolt MariaDB (always on-cluster; `mariadb-dump`) |
| `identity/SUPABASE.txt` | Marker when Postgres is external (Vaultwarden on `cronnecture-identity`; PITR deferred) |
| `identity/*.sql.gz` | Only if `identity-postgres` STS still has replicas (rollback path) |
| `gitea/gitea.sql.gz` | Gitea Postgres (in-ns `gitea-postgres` or Database_cluster DSN) |
| `gitea/gitea-data.tar.gz` | Git objects from `gitea-data` PVC (`/data`, RWX NFS) |

Gitea LFS/attachments already sit on R2 (`cronnecture-fleet-backups` prefix `gitea/`). See [gitea.md](gitea.md).

**Restore Passbolt MariaDB** (from a fleet backup bundle):

```bash
gunzip -c identity/passbolt.sql.gz | \
  kubectl -n identity exec -i deploy/passbolt-db -- mysql -upassbolt -p"$MYSQL_PASSWORD" passbolt
```

**Rollback identity Postgres to PVC:** clear `vault_identity_database_host`, `make identity` (recreates STS), restore dumps into `identity-postgres`, point apps back.

## etcd / k3s cluster state

Snapshots: `/var/lib/rancher/k3s/server/db/snapshots/`

Restore (on control node, **destructive** — test in staging first):

```bash
sudo systemctl stop k3s
sudo k3s server --cluster-reset --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<snapshot-file>
sudo systemctl start k3s
```

## Runtime registry

`cf_clients.yml` is regenerated by the ops API from Postgres. After DB restore, run:

```bash
make clients
```

Fleet container images live in the `fleet-registry` PVC on the control node **or** S3/R2 when configured. See [resilience.md](../architecture/resilience.md) and [runbooks/registry-recovery.md](../runbooks/registry-recovery.md).

## Full stack recovery

See [bootstrap.md](bootstrap.md). After `make site`, verify:

```bash
/usr/local/lib/cronnecture-fleet/health-check.sh
curl -sf http://127.0.0.1:30080/api/health
```

## Restore fire drill

Weekly **Sun 05:30 UTC** via:

- Host cron `cronnecture restore fire drill` (installed by `make fleet-ops`)
- Automation preset **Weekly restore fire drill** (`restore_drill`, enabled by default)

On demand after major ops:

```bash
make restore-drill
# or: sudo /usr/local/lib/cronnecture-fleet/restore-drill.sh
```

Proves the latest on-site stamp is restorable **without overwriting production**:

1. Latest stamp age + `manifest.txt`
2. Emergency bundle copied to a scratch dir — `hosts.ini` + `cf_clients.yml` parse
3. Newest k3s etcd snapshot present and non-trivial
4. Same stamp’s manifest downloadable from R2
5. In-cluster Postgres only: dump → scratch DB → drop (external Supabase = skipped; restore via provider backups/PITR when enabled)

| Log | Path |
|-----|------|
| Cron stdout/stderr | `/var/log/cronnecture-fleet-restore-drill.log` |
| Per-run JSONL | `/var/log/cronnecture-fleet/restore-drill.jsonl` |

See [RB-07](../runbooks/backup-restore.md#fire-drill-non-destructive).

## When you add nodes later

- Copy backup retention to object storage (S3/R2)
- Run etcd snapshots on each server once HA etcd is live
- Add edge LB VIP and update `k3s_tls_san` + `k3s_server_url`

## Runbook

Step-by-step restore: [runbooks/backup-restore.md](../runbooks/backup-restore.md)
