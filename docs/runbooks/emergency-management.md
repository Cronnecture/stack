# Emergency management (control node down)

Runbook **RB-11**.

Operate the fleet when the primary control node is unreachable but compute and Cloudflare still work.

## When to use

- Control node (`k3s_server`) dead or unreachable
- Ops UI down but client sites may still be serving traffic
- You have a **secondary machine** with repo clone, vault password, and SSH key

## What still works without control node

| Component | Status |
|-----------|--------|
| Running client pods on compute | ✅ Continue |
| Traefik routes already applied | ✅ Continue |
| cloudflared connectors on compute | ✅ Continue (until token rotation needed) |
| Cloudflare edge | ✅ Cached |
| New deploys / builds | ❌ |
| Ops UI / API | ❌ |
| `make site` / Ansible | ❌ From dead host only |

## Prerequisites (prepare before disaster)

1. **Git clone** on laptop: `git clone <repo> ~/stack` — set `STACK_ROOT=~/stack` and `FLEET_ROOT=~/stack/ansible`. Keep vault password + SSH key on that machine so `make` is not tied to `cp-master-01`.
2. **Offline copies:** `~/.ansible/vault_pass`, `~/.ssh/id_ed25519`
3. **Latest backup** from `/var/backups/cronnecture-fleet/` (synced off-node)
4. **`hosts.ini`** — copy from backup `emergency/hosts.ini` or reconstruct IPs

### Off-box break-glass pack

If the control node is gone, do **not** depend on its local disk. Use the sealed pack:

| Where | Path |
|-------|------|
| Cloudflare R2 | `s3://cronnecture-fleet-backups/break-glass/latest/break-glass-pack.tar.gz` |
| First compute worker | `/var/backups/cronnecture-break-glass/latest/break-glass-pack.tar.gz` on `worker-general-01` |

Refresh: `make break-glass` (weekly cron Sun 04:00 UTC). Checklist-only object: `CHECKLIST.txt` beside the tarball (paths + SSH fingerprint; no secret values).

**What is inside the tarball** (under `secrets/` — never commit):

| File | Restores |
|------|----------|
| `vault_pass` | Ansible vault password → `~/.ansible/vault_pass` |
| `vault.yml` | Encrypted inventory secrets |
| `id_ed25519` (+ `.pub`) | SSH deploy key (fingerprint in checklist) |
| `ansible-runner.token` | Ops host-runner token → `/etc/cronnecture/` |
| `ops-admin.password` | Ops UI admin password |
| `backup-r2.env` | R2 S3 access for fleet backup pull |

`pointers/LATEST_BACKUP.txt` records the newest fleet backup stamp and R2 prefix.

**Fetch from R2** (any machine that already has `backup-r2.env`, or via Cloudflare R2 dashboard):

```bash
source /path/to/backup-r2.env   # or use dashboard download once
aws s3 cp "s3://${BUCKET}/break-glass/latest/break-glass-pack.tar.gz" . \
  --endpoint-url "${ENDPOINT}"
mkdir -p ~/cronnecture-break-glass && chmod 700 ~/cronnecture-break-glass
tar -xzf break-glass-pack.tar.gz -C ~/cronnecture-break-glass
# then install vault_pass + id_ed25519 as in CHECKLIST.txt
```

**Manual step:** after each SSH/vault/R2 key rotation, also download the pack to an encrypted laptop.

## Procedure A: Restore client tunnels only

Use when compute is healthy but connectors or CF ingress drifted.

### 1. Restore runtime files

```bash
export FLEET_ROOT=~/cronnecture-fleet-emergency
BACKUP=/path/to/latest-backup   # e.g. from S3 or manual copy

cp "${BACKUP}/cf_clients.yml" \
   "${FLEET_ROOT}/config/inventory/group_vars/all/cf_clients.yml"

cp "${BACKUP}/emergency/hosts.ini" \
   "${FLEET_ROOT}/config/inventory/hosts.ini"
```

If `emergency/hosts.ini` missing, edit `hosts.ini` manually with known IPs.

### 2. Sync tunnels (no ops UI required)

```bash
cd $FLEET_ROOT
ansible-playbook -i config/inventory/hosts.ini playbooks/client.yml
```

This applies tunnel ingress + DNS from `cf_clients.yml`.

### 3. Verify

```bash
# On compute node via SSH
systemctl status cloudflared
curl -I https://www.clientdomain.com
```

## Procedure B: Cloudflare edge only

If tunnels OK but WAF/Access drifted:

```bash
cd $FLEET_ROOT
ansible-playbook -i config/inventory/hosts.ini playbooks/cloudflare.yml
```

Requires vault decryption on secondary machine.

## Procedure C: Full cluster rebuild

Control node lost entirely → follow [bootstrap.md](../operations/bootstrap.md):

1. New or reprovisioned VPS as control
2. Restore vault, SSH key, `hosts.ini`
3. Restore Supabase from PITR if DB affected
4. Restore `cf_clients.yml` from backup
5. `make site`
6. `make clients`

## Connector token gap

`cf_clients.yml` contains tunnel IDs and exposure metadata — **not** connector install tokens (those are in Supabase, encrypted).

If connectors were wiped and DB unavailable:

1. Restore Supabase PITR, **or**
2. Cloudflare Zero Trust dashboard → Tunnels → re-create connector token per tunnel → install manually on compute, **or**
3. Wait for control plane recovery and re-run client create job (if DB intact)

## Procedure D: Promote laptop to permanent control

```bash
export FLEET_ROOT=~/cronnecture-fleet-emergency
cd $FLEET_ROOT
make ping
make health   # may fail until cluster reachable
make clients
make cloudflare
```

Update DNS/SSH habits — any machine with vault + SSH + kubeconfig can be control.

## Verification checklist

- [ ] `ansible -i config/inventory/hosts.ini compute_general -m ping`
- [ ] Client HTTPS URLs respond
- [ ] `cloudflared` active on compute
- [ ] Wazuh dashboard reachable (independent path)

## Related

- [resilience.md](../architecture/resilience.md)
- [backup.md](../operations/backup.md) — break-glass + restore fire drill
- [RB-07 Backup and restore](backup-restore.md)
- [RB-09 Incident response](incident-response.md)
