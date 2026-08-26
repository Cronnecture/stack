# Backup and restore

Runbook **RB-07**.

Manual backup procedures and restore paths for fleet data.

## What gets backed up

### Automated (daily)

| Time (UTC) | Component | Location |
|------------|-----------|----------|
| 03:00 | etcd snapshot | `/var/lib/rancher/k3s/server/db/snapshots/` |
| 03:15 | Fleet bundle | `/var/backups/cronnecture-fleet/<timestamp>/` |

Fleet bundle includes:

- etcd snapshot copy
- `cf_clients.yml`
- kubectl node/pod snapshots
- git HEAD reference

Logs: `/var/log/cronnecture-fleet-backup.log`, `/var/log/k3s-etcd-snapshot.log`

### External (manual responsibility)

| Asset | Location |
|-------|----------|
| Ansible vault password | Password manager |
| SSH private key | Secure backup |
| Supabase | PITR in Supabase dashboard |
| Encrypted `vault.yml` | Git + offline copy |

## Manual backup

```bash
cd $FLEET_ROOT
make backup
# or:
/usr/local/lib/cronnecture-fleet/backup-fleet.sh
```

Verify:

```bash
ls -lt /var/backups/cronnecture-fleet/ | head
ls -lt /var/lib/rancher/k3s/server/db/snapshots/ | head
```

### Supabase

Enable **Point-in-Time Recovery** in Supabase project settings.

Schema reference: `services/control-plane/schema.sql`

Optional manual dump:

```bash
psql "$DIRECT_DATABASE_URL" -pg_dump controlplane > controlplane-$(date +%F).sql
```

## Restore scenarios

### A: Restore `cf_clients.yml` only

If file lost but DB intact:

```bash
# Ops API regenerates from Postgres on next client update, or:
make clients
```

### B: Restore Supabase (control plane DB)

1. Supabase dashboard → restore to point in time (or import SQL dump)
2. Verify schema matches `schema.sql`
3. `make control-plane`
4. `make clients`
5. Spot-check clients/apps in ops UI

### C: Restore etcd (cluster state)

**Destructive** — test in staging first.

On k3s **server** node:

```bash
sudo systemctl stop k3s
sudo k3s server \
  --cluster-reset \
  --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<snapshot-file>
sudo systemctl start k3s
sudo k3s kubectl get nodes
make site
```

After etcd restore:

- Reconcile drift with `make site`
- Verify platform pods
- Client apps may need re-deploy if registry PVC lost

### D: Restore fleet-registry images

PVC on control node — **not** in etcd backup.

If lost:

1. Re-trigger Kaniko builds from ops UI for each app
2. Or restore PVC from provider snapshot (if available)

### E: Full control machine loss

1. Fetch the **off-box break-glass pack** from R2 (`break-glass/latest/`) or `worker-general-01:/var/backups/cronnecture-break-glass/latest/` — see [RB-11](emergency-management.md#off-box-break-glass-pack)
2. Install `vault_pass` + SSH key; pull latest fleet backup stamp via `backup-r2.env`
3. Follow [bootstrap.md](../operations/bootstrap.md): restore `hosts.ini`, `make site`, Supabase PITR if needed

### Fire drill (non-destructive)

Scheduled **weekly Sunday 05:30 UTC** on the k3s server (host cron + Automation preset `restore_drill`). Scratch-only — never overwrites production.

```bash
make restore-drill   # on demand; same script as the weekly cron
make break-glass     # refresh off-box pack → R2 + worker (Sun 04:00 UTC)
```

| What | Where |
|------|--------|
| Cron job | `cronnecture restore fire drill` → `/usr/local/lib/cronnecture-fleet/restore-drill.sh` |
| Automation | Ops UI → Automation → **Weekly restore fire drill (Sun 05:30 UTC)** |
| Text log | `/var/log/cronnecture-fleet-restore-drill.log` |
| Results JSONL | `/var/log/cronnecture-fleet/restore-drill.jsonl` |
| Runbook meta | Fleet → Runbooks → Restore fire drill |

## Verification after restore

```bash
make health
curl -sf http://127.0.0.1:30080/api/health
curl -sf https://ops.cronnecture.com/api/health
sudo k3s kubectl -n platform get pods
# Test one client URL
```

## Retention

Default: local disk on control node. **Recommended:** copy `/var/backups/cronnecture-fleet/` to object storage (S3/R2) weekly.

Example (adjust credentials):

```bash
aws s3 sync /var/backups/cronnecture-fleet/ s3://your-bucket/cronnecture-fleet/
```

## Related

- [backup.md](../operations/backup.md)
- [bootstrap.md](../operations/bootstrap.md)
- [RB-09 Incident response](incident-response.md)
