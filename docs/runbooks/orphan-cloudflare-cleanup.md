# Scheduled orphan Cloudflare cleanup

Runbook **RB-15**.

Weekly dry-run of orphan DNS / Access / tunnels, with an opt-in allowlisted apply. Never deletes `node-tunnel`, declared portals/SSH, or DNS in zone `cronnecture.eu`.

## Schedule

| Day (UTC) | Action | Default |
|-----------|--------|---------|
| Sunday 02:00 | Dry-run → `alerts@` (+ Webhooky if vault URL set) | **On** |
| Monday 03:00 | Apply candidates from Sunday evidence ∩ allowlist | **Off** |

Also: Automation preset **Weekly CF orphan dry-run** (`inventory_cleanup_report`).

## What gets reported

From `POST /api/inventory/cleanup?dry_run=true` / `preview_fleet_cleanup`:

- Orphan **tunnels** (client-* leftovers)
- Orphan **DNS** records
- Orphan **platform ingress routes** on `node-tunnel` (undeclared hostnames only)
- Orphan **Access** apps
- **skipped_protected** — items the sweeper will never touch

Evidence file: `/var/lib/cronnecture-orphan-cleanup/last-dry-run.json`

## Manual dry-run

```bash
make orphan-cleanup
# or:
sudo /usr/local/lib/cronnecture-fleet/cf-orphan-cleanup.sh --dry-run
```

## Enable apply

1. Review Sunday email / evidence JSON.
2. Edit allowlist:

```bash
sudoedit /etc/cronnecture/orphan-cleanup-allowlist.conf
# one hostname / tunnel name / Access domain per line
# or a single * to accept the full dry-run candidate set
```

3. Enable Monday cron (inventory/group vars or one-off play):

```yaml
fleet_ops_orphan_cleanup_apply_enabled: true
```

```bash
make fleet-ops
```

4. One-shot apply (still gated):

```bash
ORPHAN_APPLY=1 make orphan-cleanup
```

Apply refuses if evidence is missing/stale (>8 days) or allowlist is empty.

## Deploy

```bash
make fleet-ops          # host cron + script + allowlist stub
make control-plane      # Automation preset + platform task
# or: make release
```

## Verify

```bash
crontab -l | grep orphan
make orphan-cleanup
ls -l /var/lib/cronnecture-orphan-cleanup/last-dry-run.json
# Ops UI → Automation → Weekly CF orphan dry-run
```

## Rollback

- Disable dry-run cron: `fleet_ops_orphan_cleanup_enabled: false` + `make fleet-ops`
- Disable apply: `fleet_ops_orphan_cleanup_apply_enabled: false` (default)
- Toggle off Automation preset in Ops UI

## Related

- [overview.md](../operations/overview.md)
- [cloudflare.md](../operations/cloudflare.md)
- [freeze-list.md](../architecture/freeze-list.md) — do not delete zone `cronnecture.eu`
