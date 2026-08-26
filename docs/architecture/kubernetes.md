# Kubernetes (k3s)

k3s is the cluster runtime: lightweight Kubernetes with embedded etcd on server nodes.

## Cluster overview

| Setting | Value |
|---------|-------|
| Distribution | k3s |
| Version | `k3s_version` in `group_vars/k3s_cluster.yml` |
| CNI | flannel `wireguard-native` (encrypted pod network) |
| Ingress | Traefik (bundled with k3s) |
| Secrets | Encrypted at rest (`--secrets-encryption`) |

## Nodes (current fleet)

```bash
sudo k3s kubectl get nodes -L pool,node-class,node-role.kubernetes.io/control-plane
```

| Node | Role | Labels (typical) |
|------|------|------------------|
| `cp-master-01` (`31.97.126.9`) | server | control-plane / etcd |
| `worker-general-01` (`135.181.58.45`) | agent | `pool=general` |
| `worker-general-02` (`72.60.32.178`) | agent | `pool=general` |

API server `:6443` is **not** exposed to the public internet — cluster peers only (`k3s_server.yml`).

## kubectl access

### On control node

```bash
sudo k3s kubectl get pods -A
```

### From workstation

```bash
ansible-playbook -i config/inventory/hosts.ini playbooks/fetch-kubeconfig.yml
export KUBECONFIG=~/.kube/k3s.yaml
kubectl get nodes
```

Helper script (cron/backup): `/usr/local/lib/cronnecture-fleet/lib/fleet-kubectl.sh`

## Manifest sources

Do **not** commit static YAML under `services/` for platform workloads. Edit Jinja templates and converge:

| Workload | Template |
|----------|----------|
| Platform (ops, registry) | `roles/control_plane/templates/platform.yaml.j2` |
| Client apps | `roles/k3s_client_app/templates/app.yml.j2` |
| etcd snapshot CronJob | `roles/fleet_ops/templates/` |

Rendered to: `/var/lib/rancher/k3s/server/manifests/` on server nodes.

Apply changes:

```bash
make control-plane    # platform namespace
make clients        # client tunnel connectors (Ansible, not pure K8s)
```

## Namespaces

### `platform`

| Resource | Replicas | Notes |
|----------|----------|-------|
| `api-edge` + JS APIs | 1 each | **`api-edge` owns NodePort 30080**. `api-data` is the only JS process with a DB URL |
| `control-plane` | 2 | FastAPI leftover + customer portal (ClusterIP `control-plane-legacy`); PDB; leader election; 2 uvicorn workers; requests `100m`/`256Mi`, limits `1` CPU / **`10Gi`** memory |
| `fleet-registry` | 1 | NodePort 30500; R2 when `vault_registry_s3_*` set, else PVC |
| `cronnecture-website` | 1 | Public marketing hostnames |
| `maintenance-page` | 1 | Billing/maintenance origin |
| `postgres` | 0 | Only without Supabase URL |

Control plane scheduling:

```yaml
nodeSelector:
  node-role.kubernetes.io/control-plane: "true"
```

Probes: liveness/startup `/api/health/live`; readiness `/api/health/ready` (DB).

### `mail`

| Resource | Replicas | Notes |
|----------|----------|-------|
| `stalwart` | 1 | Control-plane node; TCP probes + startupProbe; PVC for queue/data |

Apply: `make mail`

### `monitoring`

| Resource | Replicas | Notes |
|----------|----------|-------|
| `prometheus` | 1 | Scrapes node/cadvisor/kubelet/traefik/ksm; PVC `prometheus-data` |
| `alertmanager` | 1 | Email (+ optional Webhooky push); `hostNetwork` on control node for local webhook |
| `kube-state-metrics` | 1 | Deployment/Job/node condition signals |
| `node-exporter` | DaemonSet | One pod per node |

**No Grafana.** Apply: `make monitoring`. Day-2: [overview.md](../operations/overview.md) (Prometheus → Alertmanager section).

### `previews`

Demo sites at `https://previews.cronnecture.com/previews/{uuid}` — hub Deployment + per-UUID `pv-*` Deployments (app + demo-banner). Managed by control-plane; see [previews.md](../platform/previews.md).

### `client-{slug}` (per tenant)

Created by ops API:

| Resource | Purpose |
|----------|---------|
| `Namespace` | Isolation |
| `ResourceQuota` | CPU/memory/pod caps |
| `NetworkPolicy` | Same-ns unrestricted; kube-system + platform on `80`/`8080`/`3000`; UFW perimeter |
| `Deployment` + `Service` | Application pods |
| `IngressRoute` | Traefik hostname routing |
| `Job` | Kaniko image builds |

### `kube-system`

Traefik, CoreDNS, flannel, metrics-server (k3s defaults).

## Traefik ingress

Client traffic path:

```
Cloudflare → client tunnel → compute:80 → Traefik → IngressRoute → Service → Pod
```

Traefik dashboard (if enabled): `https://traefik.cronnecture.com` via admin portal.

Inspect routes:

```bash
sudo k3s kubectl -n client-{slug} get ingressroutes.traefik.io
```

## Networking

| Layer | Mechanism |
|-------|-----------|
| Node firewall | UFW — see [security.md](../operations/security.md) |
| Pod network | flannel wireguard-native between nodes |
| Service mesh | None (kube-proxy + Traefik) |
| NetworkPolicy | Per-client namespace |

Compute node publishes **80/443** for tunnel ingress backends.

## Storage

| Store | Namespace | Notes |
|-------|-----------|-------|
| **Cloudflare R2** | `platform` (via registry pod) | When `vault_registry_s3_*` complete — bucket `cronnecture-fleet-registry` |
| `fleet-registry-data` PVC | `platform` | Fallback when R2 vault keys are incomplete |
| `postgres-data` PVC | `platform` | Legacy DB only (if no Supabase) |

Verify registry mode:

```bash
sudo k3s kubectl -n platform get deploy fleet-registry -o yaml | grep REGISTRY_STORAGE
# Expect REGISTRY_STORAGE=s3 and bucket cronnecture-fleet-registry.
# Unauthenticated catalog returns 401 (Basic auth) — that still proves the NodePort is up.
curl -si http://127.0.0.1:30500/v2/ | head -20
```

Setup / recovery: [RB-12 Registry recovery](../runbooks/registry-recovery.md), `./bin/fleet-r2-registry`.

etcd data: `/var/lib/rancher/k3s/server/db/` on server node.

## Jobs & builds

Kaniko jobs run in client namespace:

```bash
sudo k3s kubectl -n client-{slug} get jobs
sudo k3s kubectl -n client-{slug} logs job/kaniko-build-{app}-{id}
```

Images push to: `fleet-registry.platform.svc.cluster.local:5000/{client}/{app}:tag`

## Upgrades

See [RB-03 Upgrade k3s](../runbooks/upgrade-k3s.md).

Pin version in `group_vars/k3s_cluster.yml`, then `make cluster`.

## etcd backup

Automated daily 03:00 UTC on control node. Snapshots:

```bash
ls -la /var/lib/rancher/k3s/server/db/snapshots/
```

Manual:

```bash
sudo k3s etcd-snapshot save --name manual-$(date +%Y%m%d)
```

Restore: [RB-07 Backup and restore](../runbooks/backup-restore.md).

## Useful commands

```bash
# All pods not Running
sudo k3s kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Control plane logs
sudo k3s kubectl -n platform logs deploy/control-plane -c api -f

# Describe scheduling failure
sudo k3s kubectl -n client-{slug} describe pod {pod-name}

# Resource usage (if metrics-server healthy)
sudo k3s kubectl top nodes
sudo k3s kubectl top pods -A
```

## Database

Production uses **Supabase** external to the cluster. In-cluster Postgres is not deployed when `vault_platform_database_url` is set.

See [supabase.md](../operations/supabase.md).

## Related docs

- [overview.md](overview.md)
- [control-plane.md](../platform/control-plane.md)
- [RB-02 Remove a node](../runbooks/remove-node.md)
- [RB-10 Scale to HA](../runbooks/scale-to-ha.md)
