# Scale to high availability

Runbook **RB-10**.

Roadmap for multi-server etcd, edge load balancing, and compute redundancy.

## Current state vs target

| Tier | Current | HA target |
|------|---------|-----------|
| `k3s_server` | 1 node | 3 nodes (etcd quorum). **Never add a second server** (1→2 is split-brain). |
| `compute_general` | 2 nodes (HEL1 + FRA) | 2+ (Phase 1 done) |
| `edge_lb` | none | 2 nodes + VIP |
| `siem` | empty (retired) | leave empty |

Compute is already redundant. The remaining SPOF is the single etcd member. This runbook is for the next VPS spend.

## Phase 1: Second compute node (done)

**Goal:** Client workload redundancy + ingress spread. Live: `worker-general-01` (HEL1) + `worker-general-02` (FRA).

1. Provision VPS
2. Add node (either runs now, or the pending inbox picks it up within 2 minutes):

```bash
make add-node IP=<new-ip> CLASS=general
# or queue it:
make pending-node IP=<new-ip> CLASS=general PROVIDER=hetzner REGION=hel1
```

3. Verify scheduling:

```bash
sudo k3s kubectl get nodes -L pool
sudo k3s kubectl get pods -A -o wide
```

4. Traefik runs on all `compute_general` workers (ServiceLB `enablelb=true`)
5. Client tunnels originate at Traefik ClusterIP (`cf_client_ingress_backend`, live `10.43.125.134:80`). A `127.0.0.1:80` origin 502s — Traefik does not listen on the host. Every `cloudflared` replica can reach the ClusterIP.
6. Install connectors on every general worker (`make clients` / connector playbook), then:

```bash
make cloudflare && make clients
```

7. Confirm Traefik EXTERNAL-IP lists both workers and connectors are active on each:

```bash
sudo k3s kubectl get svc -n kube-system traefik -o wide
# Per live client tunnel unit on each compute_general host, e.g.:
ansible -i config/inventory/hosts.ini compute_general -a 'systemctl is-active "cloudflared-client-*"'
```

**Placement tip:** Run `make rebalance` weekly.

## Phase 2: Edge load balancer (5+ nodes)

**Goal:** Single VIP for API `:6443` and HTTP `:80/443`.

### Prerequisites

- 2+ VPSes for `[edge_lb]`
- Free VIP on same L2 network (provider floating IP or keepalived VRRP)
- Update DNS/firewall for public ingress

### Configuration

Edit `config/inventory/group_vars/edge_lb.yml`:

```yaml
lb_vip: "203.0.113.100"
lb_ingress_backend_group: compute_general
```

Edit `config/inventory/group_vars/k3s_cluster.yml`:

```yaml
k3s_tls_san:
  - "203.0.113.100"
  - "k3s.example.com"
k3s_server_url: "https://203.0.113.100:6443"
```

Add hosts:

```ini
[edge_lb]
203.0.113.10
203.0.113.11
```

```bash
make add-node IP=203.0.113.10 CLASS=lb
make add-node IP=203.0.113.11 CLASS=lb
make site
```

HAProxy health-checks backends; keepalived holds VIP.

## Phase 3: HA control plane (7+ nodes)

**Goal:** 3-server etcd quorum survives one server loss.

### Rules

- Always **odd** number of servers: 1, 3, or 5
- Never expand 1→2 servers (split brain) — go 1→3
- Upgrade one server at a time ([RB-03](upgrade-k3s.md))

### Procedure (1 → 3)

1. Add two new VPSes as servers:

```bash
make add-node IP=<ip2> CLASS=server
make add-node IP=<ip3> CLASS=server
```

2. First server remains primary; new servers join via `k3s_server_url`
3. If using edge VIP, agents join through VIP URL
4. Verify etcd members:

```bash
sudo k3s kubectl get nodes -l node-role.kubernetes.io/control-plane
sudo k3s etcd-snapshot save --name post-ha-test
```

5. Platform pods (control-plane, registry) stay on control-plane nodes — scheduler spreads if multiple labeled

### etcd backups with HA

- Snapshot from **any** server (shared etcd)
- Keep cron on one designated server
- Copy snapshots off-node

## Phase 4: SIEM redundancy (optional, 10+ nodes)

- Second `[siem]` manager
- Wazuh cluster configuration (manual beyond single-manager defaults)
- Update `cf_portals.yml` backend if dashboard moves

## Phase 5: Object storage for backups

When multi-node:

```bash
# Extend backup-fleet.sh or cron to sync:
aws s3 sync /var/backups/cronnecture-fleet/ s3://bucket/cronnecture-fleet/
```

## Identity DB recovery (same budget wave as HA)

When spending on more VPS / HA (typically 5–7 nodes), also upgrade identity DR:

- [ ] Enable **PITR** (or equivalent continuous recovery) on Supabase project **`cronnecture-identity`** — Authentik / Hanko / Vaultwarden  
- Until then: Passbolt MariaDB rides fleet backup → R2; break-glass pack; provider daily backups only if the project plan includes them (Free has none). PITR is **not** an urgent pre-HA TODO — see [backup.md](../operations/backup.md), [identity.md](../operations/identity.md), [roadmap.md](../architecture/roadmap.md)

## Verification checklist (post-HA)

- [ ] 3 servers Ready, etcd healthy
- [ ] Agent join via VIP URL works for new nodes
- [ ] Client sites load through edge LB
- [ ] Ops UI accessible
- [ ] Simulate server failure: stop one k3s server — cluster survives
- [ ] Simulate compute failure: cordon one worker — pods reschedule
- [ ] `make health` passes
- [ ] Backups run and off-site copy verified
- [ ] Identity Supabase PITR (or equivalent) enabled on `cronnecture-identity`

## What not to automate

- Promoting compute → control plane (drain workloads first)
- Reducing server count (etcd member remove is delicate)
- VIP DNS cutover (plan maintenance window)

Use `make rebalance` for recommendations; apply tier promotions manually.

## Related

- [overview.md](../architecture/overview.md)
- [inventory.md](../architecture/inventory.md)
- [RB-01 Add a node](add-node.md)
- [RB-02 Remove a node](remove-node.md)
- [RB-07 Backup and restore](backup-restore.md)
