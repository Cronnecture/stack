# Inventory & configuration

How hosts, groups, variables, and policies are organized.

> **Note:** This document describes the **Ansible inventory** (VPS hosts and group_vars).  
> For **Cloudflare resource inventory** in the ops UI (tunnels, DNS, Access apps), see [control-plane.md](../platform/control-plane.md#fleet-cloudflare-inventory) and [cloudflare.md](../operations/cloudflare.md#fleet-cloudflare-inventory-ops-ui).

## Inventory file

Path: `config/inventory/hosts.ini` (**not committed** — gitignored).  
Template: `hosts.ini.example` (tracked). **Never copy the example over live inventory.**

Hourly `playbooks/cloudflare.yml` (cron `cronnecture cloudflare sync`) templates
tunnel origins from `ansible_host`. If that file still has `YOUR_*` placeholders,
Cloudflare will PUT `YOUR_COMPUTE_GENERAL_IP` / `YOUR_K3S_SERVER_IP` as origins
and the apex 502s even though the real origin is healthy.

Fail-closed guards:

- `make inventory-check` — placeholders, duplicate IPs, missing groups
- `playbooks/inventory_guard.yml` — imported by `cloudflare.yml` (and SSH
  playbooks) before any tunnel PUT, DNS publish, or remote SSH
- Hourly cron runs `scripts/lib/inventory_guard.py --mode publish` then
  `playbooks/cloudflare.yml` (not `automation/`)
- **Node registry** (Postgres + `/etc/cronnecture/node-registry.json`):
  seeded from live `hosts.ini` (never committed). Cloudflare portal backends
  prefer healthy registry IPs when `hosts.ini` still has `YOUR_*`. Seed from
  Manage → Infrastructure → Fleet. Heartbeat cron on the master refreshes the
  JSON cache. Registry overlay still fail-closed if no healthy IP exists.

Use **canonical hostnames** with `ansible_host` for the public IP. Optional
`fleet_provider` / `fleet_region` pin the ops welcome globe (provider DC):

```
cp-master-01 ansible_host=31.97.126.9 fleet_provider=hostinger fleet_region=fra
worker-general-01 ansible_host=135.181.58.45 fleet_provider=hetzner fleet_region=hel1
worker-general-02 ansible_host=72.60.32.178 fleet_provider=hostinger fleet_region=fra
```

Common regions: Hetzner `hel1` / `fsn1` / `nbg1`; Hostinger `fra` / `ams` / `lon`.
Set at bootstrap via Ops **Fleet → Nodes** or `make add-node IP=… PROVIDER=hetzner REGION=hel1`.

The `fleet_identity` role (via `make baseline`) sets the OS hostname to match inventory so k3s node names align with ops diagrams. After renaming, remove legacy node objects once: `kubectl delete node <old-name>`.

```
[k3s_server]          → control plane nodes
[compute_general]     → default worker pool
[compute_cpu]         → CPU-optimized pool (tainted)
[compute_memory]      → memory-optimized pool (tainted)
[edge_lb]             → HAProxy + keepalived
[siem]                → Wazuh managers
[new_nodes]           → staging for bootstrap only
```

Aggregate groups:

- `k3s_agent:children` — all compute pools
- `k3s_cluster:children` — servers + agents

## Group variables

| Path | Scope |
|------|-------|
| `group_vars/all/main.yml` | Every host — hardening, fleet root, ingress backends |
| `group_vars/all/vault.yml` | Encrypted secrets (ansible-vault) |
| `group_vars/all/vault.example.yml` | Template for new vaults |
| `group_vars/all/cf_portals.yml` | Platform portals + public sites (`ops`, `client`, `webmail`, marketing…) |
| `group_vars/all/platform_sites.yml` | Marketing + previews hostnames (`platform_previews_*`); `platform_client_portal_hostname` |
| `group_vars/all/cf_clients.yml` | Runtime client tunnel registry (API-generated; **Postgres is source of truth**) |
| `group_vars/k3s_cluster.yml` | k3s version, flannel, control plane toggle |
| `group_vars/k3s_server.yml` | Control-plane labels, firewall |
| `group_vars/compute_general.yml` | Pool label, ingress ports 80/443 |
| `group_vars/compute_cpu.yml` | Taints, CPU pool label |
| `group_vars/compute_memory.yml` | Taints, memory pool label |
| `group_vars/edge_lb.yml` | VIP, HAProxy backends |
| `group_vars/siem.yml` | Wazuh-specific settings |

## Key variables

### k3s (`k3s_cluster.yml`)

| Variable | Purpose |
|----------|---------|
| `k3s_version` | Pin cluster version |
| `k3s_flannel_backend` | `wireguard-native` for encrypted pod network (matches live `k3s.service`) |
| `k3s_write_kubeconfig_mode` | Admin kubeconfig mode (`0600` root-only; `fleet-kubectl.sh` sudo-escalates for cron) |
| `k3s_server_url` | Agent/secondary server join URL (auto: primary IP or VIP) |
| `k3s_tls_san` | Extra TLS SANs when using edge VIP |
| `control_plane_enabled` | Deploy ops dashboard |
| `rancher_enabled` | Deploy Rancher (default false) |

### Fleet ops (`all/main.yml`)

| Variable | Purpose |
|----------|---------|
| `fleet_root` | Repo path (`FLEET_ROOT` env or ansible.cfg dir) |
| `fleet_ops_enabled` | Install backup/health cron |
| `control_plane_replicas` | 2 when Supabase URL set, else 1 |
| `cf_client_ingress_backend` | Tunnel origin (Traefik ClusterIP; **never** `127.0.0.1`) |

### Edge LB (`edge_lb.yml`)

| Variable | Purpose |
|----------|---------|
| `lb_vip` | Virtual IP for HAProxy/keepalived (empty until edge tier deployed) |
| `lb_ingress_backend_group` | Inventory group for HTTP(S) backends |

## Policies

| File | Used by |
|------|---------|
| `config/policies/placement.yml` | `autoplace.py`, `rebalance.sh` |
| `config/policies/cloudflare.yml` | `cloudflare.yml` playbook |

### Placement tiers (summary)

| Tier | Fleet size | Target count |
|------|------------|--------------|
| `k3s_server` | ≥1 | 1; ≥7 → 3 |
| `siem` | ≥3 | 1; ≥10 → 2 |
| `edge_lb` | ≥5 | 1; ≥8 → 2 |

Compute pool selection: memory-heavy → `compute_memory`; many vCPUs → `compute_cpu`; else `compute_general`.

## Vault secrets

Edit: `ansible-vault edit config/inventory/group_vars/all/vault.yml`

| Key | Purpose |
|-----|---------|
| `vault_cf_*` | Cloudflare API tokens |
| `vault_platform_database_url` | Supabase for control plane |
| `vault_supabase_access_token` | Supabase Management API PAT (auto-create per-client projects) |
| `vault_supabase_org_id` | Supabase organization id/slug for project create |
| `vault_supabase_region` | Default region (e.g. `eu-central-1`) |
| `vault_supabase_leads_*` | Ops dashboard Leads inbox |
| `vault_supabase_platform_service_key` | PostgREST for mail filter rules (optional; falls back to SQLAlchemy) |
| `vault_control_plane_token_key` | Fernet key for GitHub tokens in DB |
| `vault_wazuh_*` | SIEM passwords |
| `vault_github_client_id/secret` | GitHub OAuth for ops UI |
| `vault_google_places_api_key` | Optional Places API for prospect discovery (else Overpass/OSM) |
| `vault_registry_s3_*` | R2/S3 backend for `fleet-registry` (PVC fallback if unset) |

Password file: `~/.ansible/vault_pass` (see `ansible.cfg`).

## SSH access

- User: `root` (`all/main.yml`)
- Key: `~/.ssh/id_ed25519.pub` injected on bootstrap
- Control machine: often `ansible_connection=local` for primary server

## Adding a custom compute pool

1. Add `[compute_gpu]` to `hosts.ini`
2. List under `[k3s_agent:children]`
3. Create `group_vars/compute_gpu.yml`:

```yaml
k3s_node_labels:
  pool: gpu
  node-class: compute
k3s_node_taints:
  - "pool=gpu:NoSchedule"
firewall_public_tcp_ports: []
```

4. Schedule workloads: `nodeSelector: {pool: gpu}` + matching tolerations.

## Related docs

- [config-sources.md](config-sources.md) — SoT matrix, including `config/policies/fleet-operations.yml`
- [RB-01 Add a node](../runbooks/add-node.md)
- [security.md](../operations/security.md)
- [overview.md](overview.md)
