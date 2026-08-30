# Resilience & known vulnerabilities

Honest assessment of single-control-node risks, blast radius, and mitigation roadmap.

## Vulnerability register

| ID | Risk | Severity | Current state |
|----|------|----------|---------------|
| V-01 | Registry storage | **Medium** (was High) | **R2-backed** — bucket `cronnecture-fleet-registry`; registry pod is still single-replica on `pool=general` (`worker-general-01`) |
| V-02 | Management plane coupled to control node | **High** | Ansible, etcd, FLEET_ROOT, vault on same host |
| V-03 | Supabase hard dependency | **Medium** | Control plane CrashLoop if DB unreachable |
| V-04 | Single compute node | **High** | One `compute_general` worker (`worker-general-01`, Hetzner HEL1). Client connectors on every node. HTTP origin is Traefik ClusterIP `10.43.125.134`. |
| V-05 | Single k3s server (etcd) | **High** | No etcd quorum |

## V-01: Registry bottleneck

### What breaks

| Event | Impact |
|-------|--------|
| R2 bucket / credentials failure | Kaniko builds fail; pod restarts without cached image fail |
| Registry pod crash | Brief pull failures until pod restarts (images safe in R2) |
| Control node disk full | Slower k3s/etcd; registry no longer fills local PVC |

### What keeps working

- **Already-running pods** on compute nodes continue (image cached in containerd)
- Traffic via Traefik + Cloudflare tunnels unaffected until a pod must restart

### Blast radius

Cannot deploy, rebuild, or restart apps that need a fresh pull. All client namespaces share one registry.

### Mitigations

| Phase | Action | Status |
|-------|--------|--------|
| **Done** | R2-backed registry when `vault_registry_s3_*` set (PVC fallback otherwise) | ✅ Template-wired |
| **Now** | Daily backup + health check | ✅ Cron |
| **Now** | Off-site backup sync to R2 (`vault_backup_s3_*`, `.r2-last-sync`) | ✅ + restore fire drill |
| **Next** | Dedicated mail node (Stalwart off etcd) | ✅ `mail-01` |
| **Later** | External registry (GHCR) with `control_plane_private_registry` | Optional |

The registry pod is scheduled on `pool=general`, not the etcd host. Image blobs live in R2; losing the worker loses pulls until the pod reschedules.

#### R2 registry (production)

Setup script: `./bin/fleet-r2-registry` (see `scripts/cloudflare/setup-r2-registry.py`).

Vault keys:

```yaml
vault_registry_s3_access_key: "..."
vault_registry_s3_secret_key: "..."
vault_registry_s3_bucket: "cronnecture-fleet-registry"
vault_registry_s3_region: "auto"
vault_registry_s3_endpoint: "https://7165c7b6d905174f8050497c39e642ce.r2.cloudflarestorage.com"
```

Redeploy after changes:

```bash
make control-plane
```

When R2 keys are present, images persist in the bucket and the registry Deployment has no data PVC. Without those keys, storage is the `fleet-registry-data` PVC.

See [RB-12 Registry recovery](../runbooks/registry-recovery.md).

---

## V-02: Management plane asymmetry

### What breaks

| Event | Impact |
|-------|--------|
| Control node unreachable | No `make site`, no tunnel sync, no CF policy updates |
| FLEET_ROOT lost | Control-plane pod cannot run connector Ansible |

### What keeps working

- Kubernetes **data plane** on compute (existing pods, Traefik, cloudflared connectors **already installed**)
- Cloudflare edge (cached config; hourly cron stops)

### Blast radius

**Imperative GitOps gap:** declarative K8s state remains, but Ansible-driven reconciliation (tunnels, CF edge, new nodes) stops until control machine returns.

### Mitigations

| Phase | Action | Status |
|-------|--------|--------|
| **Now** | Clone repo + vault password on **laptop** or CI (secondary control) | Operator habit |
| **Now** | Emergency bundle in daily backup (`emergency/` subdirectory) | ✅ |
| **Now** | Off-box break-glass pack → R2 + worker (`make break-glass`) | ✅ |
| **Now** | [RB-11 Emergency management](../runbooks/emergency-management.md) — restore tunnels without ops UI | ✅ |
| **Now** | Weekly restore fire drill (`make restore-drill`) | ✅ |
| **Next** | Git remote always current; `hosts.ini` backed up off-node | Via break-glass + R2 |
| **Later** | Dedicated CI runner (GitHub Actions) with vault + SSH — not tied to k3s server | Pending |
| **Later** | HA control plane (3× server) — etcd survives one loss | Pending |

**Key insight:** decouple **execution** (where Ansible runs) from **storage** (git + vault backup). The k3s server does not have to be the only Ansible control machine.

---

## V-03: Supabase dependency

### What breaks

| Event | Impact |
|-------|--------|
| Supabase outage | Control plane pods CrashLoop; no UI, no new jobs |
| Lost `vault_platform_database_url` | Same — cannot start API |
| DB corrupted | Client/tunnel metadata wrong or empty |
| Heavy customer-portal stats traffic | `/api/stats` can saturate workers — mitigated by 2 uvicorn workers + `/api/health/live` probes |

### What keeps working

- **Running workloads** on compute (Deployments already applied)
- **Existing Traefik IngressRoutes** and Cloudflare tunnel connectors
- Public client sites **often stay up** during control plane outage

### Blast radius

User analysis overstates immediate traffic loss: existing routes persist. You lose **management** (deploy, expose, tunnel updates), not instant multi-tenant blackout — unless pods restart and need registry + control plane.

### Mitigations

| Phase | Action |
|-------|--------|
| **Now** | Control-plane Supabase: provider daily backups on paid plans; PITR when budget allows ([supabase.md](../operations/supabase.md)) |
| **Now** | Identity Supabase (`cronnecture-identity`): **no PITR** — accepted until HA scale; Passbolt MariaDB → fleet/R2; break-glass; provider daily backups only if plan includes them ([backup.md](../operations/backup.md), [identity.md](../operations/identity.md)) |
| **Now** | `cf_clients.yml` in daily backup — tunnel shape without DB |
| **Now** | Export `DATABASE_URL` to secure password manager (not just vault file) |
| **Now** | Emergency restore: [RB-11](../runbooks/emergency-management.md) |
| **Later (HA / 5–7 VPS)** | Enable PITR (or equivalent) on `cronnecture-identity` alongside compute/etcd scale-up ([RB-10](../runbooks/scale-to-ha.md)) |
| **Optional** | Read-only health endpoint that does not require DB (future) |
| **DR** | Keep `vault_platform_database_url` in offline break-glass doc |

Connector tokens live **encrypted in Postgres** — `cf_clients.yml` has tunnel IDs but not connector tokens. For full tunnel recovery without DB, use Cloudflare API to re-issue tokens or restore Supabase from provider backup/PITR when available.

---

## Priority roadmap

```
Priority 1 (before paying clients — see MVP-FIRST-CLIENTS.md)
├── External mail roundtrip + billing/portal rehearsal
├── Off-box break-glass pack (R2 + worker) + laptop download habit
└── Weekly restore fire drill (scratch emergency bundle + R2 manifest)

Priority 2 (done / leftover)
├── Dedicated mail node — ✅ mail-01 (Stalwart off etcd)
└── Registry pod still single-replica on the control node (R2-backed)

Priority 3 (5+ VPS / HA)
├── edge_lb + VIP
├── 3× k3s_server etcd quorum
└── Enable identity Supabase PITR on cronnecture-identity (or equivalent) — deferred cost ~€100/mo
```

Also: [first-clients.md](../business/first-clients.md).

## Monitoring

Health check warns on:

- Registry PVC disk usage > 80%
- Missing `cf_clients.yml`
- Control plane / platform pods unhealthy

Repair is host `incident-watchdog` (`make auto-heal`) plus leftover `/api/selfheal`. MAS is retired. See [mas-retired.md](../platform/mas-retired.md).

```bash
make health
```

## Related docs

- [overview.md](overview.md)
- [backup.md](../operations/backup.md)
- [runbooks/RB-11 Emergency management](../runbooks/emergency-management.md)
- [runbooks/RB-12 Registry recovery](../runbooks/registry-recovery.md)
- [runbooks/RB-10 Scale to HA](../runbooks/scale-to-ha.md)
