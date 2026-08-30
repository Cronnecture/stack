# Add a node

Runbook **RB-01**.

Bootstrap a fresh VPS and join it to the fleet.

## Prerequisites

- Root SSH access to new VPS (password for first bootstrap)
- `~/.ssh/id_ed25519` on control machine
- `~/.ansible/vault_pass` present
- Inventory file: `config/inventory/hosts.ini`

## Decision: auto vs explicit class

| Class | Inventory group | Use when |
|-------|-----------------|----------|
| `auto` (default) | Placement engine decides | Normal expansion |
| `server` | `k3s_server` | Only when going **1→3** etcd. Never add a second server. |
| `general` | `compute_general` | Need more app capacity (Hetzner is the primary compute node) |
| `mail` | `mail` | Extra Stalwart node. A/MX/SPF publish on `make cloudflare` |
| `db` | `db` | Database_cluster. After Ready postgres: `make site` points Gitea DSN at it |
| `lb` | `edge_lb` | HAProxy/VIP tier |

Policy thresholds: `config/policies/placement.yml`

## Procedure

### Option A: Ops dashboard (preferred)

1. Buy/provision the VPS externally (SSH reachable on port 22).
2. Open `https://ops.cronnecture.com/infrastructure/nodes`
3. **Register & bootstrap node** — IP, SSH user, one-time password, role (`general` / `auto` / …); optional **Provider** + **Region / DC** (e.g. Hetzner `hel1`, Hostinger `fra`) for the welcome globe
4. Confirm the `fleet_add_node` job in the job dock finishes (~15–30 min)

Same backend as the CLI (`POST /api/fleet/nodes` → `add-node.sh` via ansible-runner). Optional body fields: `provider`, `region`.

### Option B: Pending inbox (auto when the VPS exists)

Drop a YAML file; the control-node cron (`*/2`) runs `add-node.sh` for you.

```bash
cd $FLEET_ROOT
make pending-node IP=203.0.113.50 CLASS=general PROVIDER=hetzner REGION=hel1
# with one-time SSH password (written 0600, not committed):
PENDING_PASSWORD='…' make pending-node IP=203.0.113.50 CLASS=general
```

Or copy `config/inventory/pending-nodes/node.yml.example` to `203.0.113.50.yml`.
Already-registered IPs are archived to `processed/` and never re-bootstrapped.

### Option C: Makefile (runs now)

```bash
cd $FLEET_ROOT
make add-node IP=203.0.113.50
# or explicit class + geo:
make add-node IP=203.0.113.50 CLASS=general PROVIDER=hetzner REGION=hel1
```

### Option D: Script directly

```bash
./scripts/fleet/add-node.sh 203.0.113.50
FLEET_PROVIDER=hostinger FLEET_REGION=fra ./scripts/fleet/add-node.sh 203.0.113.50 mail
# or: bin/fleet-add-node 203.0.113.50 general
```

### What happens

1. **Bootstrap** (`bootstrap.yml`) — packages, SSH key, UFW, cloudflared, fail2ban
2. **Placement** — `place-node.py` assigns group (if `auto`)
3. **Inventory update** — IP added under `[group]` with file lock (`fleet_provider` / `fleet_region` when set)
4. **Full converge** — `site.yml` (k3s join, CF edge/SSH Access, clients, fleet_ops, monitoring, mail)
5. **Finish onboard** — wait until the hostname is Ready, sync live `hosts.ini` for the JS fleet API, run `rebalance.sh --apply` (pool moves only; never auto-promotes a control-plane). For `compute_general`, also `sync-local-images.sh` so dashboard / client-portal (`imagePullPolicy: Never`) exist on the new worker, then reconverge Gitea (HPA max + anti-affinity). For `mail`, `mail_dns.yml` publishes A/MX/SPF (`mail.cronnecture.com` + `mail-NN`). Extra mail boxes are DNS/send capacity — do not run a second Stalwart replica on the same RocksDB. For `db`, Gitea DSN migrate is dry-run until postgres in ns `db` is Ready.

Duration: ~15–30 minutes.

## Verification

```bash
ansible -i config/inventory/hosts.ini <IP> -m ping
sudo k3s kubectl get nodes -o wide
make health
```

For compute nodes:

```bash
systemctl status cloudflared
sudo k3s kubectl get pods -A -o wide | grep <IP-hostname>
make sync-local-images HOST=<new-hostname>   # onboard already does this
```

For k3s_server:

```bash
sudo k3s kubectl get nodes -l node-role.kubernetes.io/control-plane
```

## Post-add (compute node)

If this is an **additional** `compute_general` ingress worker:

- Tunnel origin stays `127.0.0.1` (`group_vars/all/ingress.yml`) — no pin to inventory `[0]`
- `site.yml` already ran `cloudflare` + `clients`; re-run `make cloudflare && make clients` only if that import failed

Run placement audit:

```bash
make rebalance
```

## Rollback

If join failed mid-way:

1. Remove IP from `hosts.ini`
2. On failed node:

```bash
/usr/local/bin/k3s-agent-uninstall.sh   # or k3s-uninstall.sh if server
# reset firewall if needed
```

3. Re-run `make site` from control machine

If node joined but wrong group: move IP in inventory, re-run `make site` (do not run two k3s servers without planning — see RB-10).

## Related

- [inventory.md](../architecture/inventory.md)
- [RB-02 Remove a node](remove-node.md)
- [RB-10 Scale to HA](scale-to-ha.md)
