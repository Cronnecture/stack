# Disaster recovery bootstrap

Replicate the Cronnecture fleet from this repository after total loss of the control machine or cluster.

## What this repo contains

| Layer | Path | Purpose |
|-------|------|---------|
| Stack root | `/home/dev/stack` | Operator Makefile, kubernetes, operator UI |
| Inventory | `ansible/config/inventory/` | Host groups, group_vars, encrypted vault |
| Playbooks | `ansible/playbooks/` | `site.yml` = full converge; `stack.yml` = operator root |
| Roles | `ansible/roles/` | Node + platform configuration |
| Policies | `ansible/config/policies/` | Cloudflare edge + placement |
| Services | `ansible/services/control-plane/` | Platform API + customer portal |
| Docs | `docs/` | Reference and runbooks |

## Prerequisites (off-repo backups)

Store these **outside** Git — losing them blocks recovery:

1. **Ansible vault password** — decrypts `config/inventory/group_vars/all/vault.yml`
2. **SSH private key** — `~/.ssh/id_ed25519` (injected into every node at bootstrap)
3. **Cloudflare bootstrap token** — only needed to re-mint API tokens (`scripts/cloudflare/cf-mint-tokens.py`)
4. **Supabase** — control plane and client app databases; connection strings in vault / deploy env (see [supabase.md](supabase.md))

## Fresh control machine setup

```bash
# 1. Clone (private GitHub repo recommended)
# Restore the operator root (Ansible lives at stack/ansible)
mkdir -p /home/dev/stack
# restore stack + ansible checkouts from backup / git
cd /home/dev/stack

# 2. Restore secrets
install -m 600 ~/.ansible/vault_pass   # from secure backup
install -m 600 ~/.ssh/id_ed25519       # from secure backup

# 3. Inventory
cp ansible/config/inventory/hosts.ini.example ansible/config/inventory/hosts.ini
# Edit with current VPS public IPs — leave no YOUR_* placeholders.
# make inventory-check   # refuse example copy / duplicate IPs / missing groups

# 4. Vault (pick one)
#   a) Restore encrypted vault.yml from git + vault password
#   b) New vault from template:
cp ansible/config/inventory/group_vars/all/vault.example.yml \
   ansible/config/inventory/group_vars/all/vault.yml
# Fill values, then: ansible-vault encrypt ansible/config/inventory/group_vars/all/vault.yml

# 5. Cloudflare tokens (if vault was lost/compromised)
python3 ansible/scripts/cloudflare/cf-mint-tokens.py
# Edit ansible/config/policies/cloudflare.yml — set cf_zone, allowed emails

# 6. Verify connectivity
export STACK_ROOT=/home/dev/stack
export FLEET_ROOT=/home/dev/stack/ansible
make ping
make check
```

## Full fleet convergence

```bash
export STACK_ROOT=/home/dev/stack
export FLEET_ROOT=/home/dev/stack/ansible

# Preferred: add VPS then full converge (placement + site.yml)
make add-node IP=1.2.3.4          # bootstrap → autoplace → site

# Or ordered full stack (same as site.yml) after inventory is ready:
make site

# site.yml imports (tags work): baseline, lb, cluster, siem, rancher,
# control_plane, cloudflare, clients, fleet_ops, monitoring, mail, identity, stack

# Step-by-step equivalents:
make baseline      # hardening + cloudflared on all nodes
make cluster       # k3s control plane + workers
make siem          # no-op while [siem] is empty (Wazuh retired)
make control-plane # ops dashboard + registry
make cloudflare    # edge policy + admin portals
make clients       # per-client tunnels (needs cf_clients.yml or API rebuild)
make fleet-ops     # backup/health cron + ansible-runner
make monitoring    # optional observability
make mail          # Stalwart (when mail hosts/role enabled)
```

## Control plane recovery

The ops API runs in the `platform` namespace on k3s. Inventory and playbooks execute on the host via `cronnecture-ansible-runner` (`:18765`). The ansible hostPath mount is off by default; client documents and read-only host logs remain as hostPath volumes.

```bash
make control-plane
```

Verify: https://control.cronnecture.com (see `ansible/config/policies/cloudflare.yml` → `cf_zone`).

**Runtime state:**

- **Postgres** — clients, apps, tunnels, GitHub tokens
- **`ansible/config/inventory/group_vars/all/cf_clients.yml`** — tunnel registry for Ansible client playbooks

If Postgres is empty, re-create clients in the ops UI. The API will rewrite `cf_clients.yml` and trigger connector playbooks.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FLEET_ROOT` | directory containing `ansible.cfg` | Repo root; hostPath mount for control-plane pod |

## GitHub publish checklist

Before pushing to GitHub:

- [ ] `config/inventory/hosts.ini` is **not** tracked (use `hosts.ini.example`)
- [ ] `cf_clients.yml` is **not** tracked (runtime)
- [ ] `vault.yml` is **ansible-vault encrypted** (safe to commit) OR gitignored with offline backup
- [ ] No `.env`, PEM keys, or `vault_pass` in the tree
- [ ] `config/policies/cloudflare.yml` has no live tokens (only zone name + email domains)
- [ ] Rotate any credentials that were ever committed in plaintext

## Quick validation after recovery

```bash
make health
/usr/local/lib/cronnecture-fleet/health-check.sh
curl -sf https://ops.YOUR_ZONE/api/health
```

See [backup.md](backup.md) for automated backups and etcd snapshots.

Expected: `{"status":"ok"}`

## Further reading

- [docs/README.md](../README.md) — documentation hub
- [runbooks/backup-restore.md](../runbooks/backup-restore.md) — restore procedures
- [runbooks/incident-response.md](../runbooks/incident-response.md) — outage checklist
