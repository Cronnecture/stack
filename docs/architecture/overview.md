# Architecture

How the Cronnecture fleet is designed, how traffic flows, and how components interact.

Current as of **26 August 2026**. Live cluster: k3s `v1.35.4+k3s1`, 1 server + 2 general workers.

## Design goals

- **Horizontal scale**: add VPSes to inventory groups; placement policy assigns tiers.
- **Zero trust**: default-deny firewall, Cloudflare Access on admin UIs, isolated client tunnels.
- **GitOps-friendly**: Ansible + policy files; runtime registry for client tunnels.
- **Multi-tenant ops**: control plane manages many clients from one dashboard.

## High-level topology

```
                         Internet
                             │
                    ┌────────▼────────┐
                    │   Cloudflare    │
                    │  DNS · WAF ·    │
                    │  Access · TLS   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    node-tunnel         client tunnels      client zones
    (every node)        (per client)        (public sites)
         │                   │                   │
         ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│  k3s_server    │  │ compute_general│  │ compute_general│
│  31.97.126.9   │  │ 135.181.58.45  │  │ 72.60.32.178   │
│  Hostinger FRA │  │  Hetzner HEL1  │  │  Hostinger FRA │
│  cp-master-01  │  │ worker-gen-01  │  │ worker-gen-02  │
│                │  │                │  │                │
│ · etcd + API   │  │ · k3s agent    │  │ · k3s agent    │
│ · Ansible      │  │ · client pods  │  │ · client pods  │
│ · operator UI  │  │ · identity     │  │ · identity     │
│ · platform APIs│  │ · registry/web │  │ · cloudflared  │
│ · mail 25/587  │  │ · cloudflared  │  │                │
└────────────────┘  └────────────────┘  └────────────────┘
         Traefik ClusterIP 10.43.125.134:80 (HTTP origin for all tunnels)
```

WAN is default-deny. The only public origin ports are **mail 25/587** on the control node (`mail.cronnecture.com` A record). All HTTP is Cloudflare tunnel → Traefik ClusterIP — **not** host `:80` and **not** NodePort `30080` (that NodePort was closed).

### Target HA topology (when scaled)

At 5+ nodes: add `[edge_lb]` with keepalived VIP. At 7+ nodes: 3× `[k3s_server]` for etcd quorum (never 1→2). See [RB-10 Scale to HA](../runbooks/scale-to-ha.md).

## Node classes

| Group | Purpose | Current |
|-------|---------|---------|
| `k3s_server` | Control plane, embedded etcd, platform APIs, operator UI, Stalwart | 1 host (`cp-master-01`) |
| `compute_general` | Default workloads, identity, registry, client apps, connectors | 2 hosts |
| `compute_cpu` / `compute_memory` | Tainted specialized pools | empty |
| `edge_lb` | HAProxy + keepalived VIP | empty |
| `siem` | Wazuh managers | empty (retired) |

Placement policy: `ansible/config/policies/placement.yml`. Engine: `ansible/scripts/fleet/autoplace.py`.

## Kubernetes layout

Canonical root is `/home/dev/stack`. Ansible lives in `ansible/` (`FLEET_ROOT`). Operator YAML lives in `kubernetes/`. Do not overwrite the live k3s addon `manifests/control-plane.yaml` with `kubernetes/control-plane.yaml` by hand.

### Control plane node (`k3s_server`)

Runs k3s **server** (API + etcd). Platform addon: `ansible/roles/control_plane/templates/platform.yaml.j2` → `/var/lib/rancher/k3s/server/manifests/control-plane.yaml`. Operator UI/API: `kubernetes/control-plane.yaml` (namespace `cronnecture-system`). Mail/identity keep-set: `kubernetes/mail.yaml` + `kubernetes/identity*.yaml`.

### Namespace: `cronnecture-system` (canonical operator)

| Workload | Replicas | Notes |
|----------|----------|-------|
| `dashboard` | 2 | Next.js control portal at **https://control.cronnecture.com**. Pinned to `cp-master-01`. Source: github.com/Cronnecture/cronnecture-control-portal |
| `agent-core` | 1 | Fleet/cluster catalog API on `/api` of the same host. `GET /api/fleet/shell` + sliced ListResult reads; `POST /api/jobs` `{type,target,payload}` |

`ops.cronnecture.com` and `stack.cronnecture.com` **redirect the UI** here. Product APIs, webmail, webhooks, status, and the customer portal stay on `platform`.

### Namespace: `platform`

| Workload | Replicas | Notes |
|----------|----------|-------|
| `api-edge` + JS APIs | catalog | Catalog in `ansible/config/policies/api-catalog.yml`. Service **`control-plane` is ClusterIP → `api-edge`** (2 replicas). `api-data` is the only JS process with a DB URL. See [platform-api.md](platform-api.md) |
| `control-plane` | 3 | FastAPI leftover APIs + customer-portal middleware (ClusterIP `control-plane-legacy`); Supabase DB; memory limit **`10Gi`** (request `256Mi`) |
| `fleet-registry` | 1 | On `pool=general` (`worker-general-01`). NodePort **30500**. **R2** (`REGISTRY_STORAGE=s3`, bucket `cronnecture-fleet-registry`) |
| `cronnecture-website` | 1 | Marketing: `cronnecture.com` / `www` (EN), `cronnecture.nl` / `www` (NL) via Traefik. On `pool=general` |
| `maintenance-page` | 1 | Fallback origin for edge maintenance / billing hold |
| `postgres` | 0 | Only if no `vault_platform_database_url` (not deployed) |

JS APIs (all ClusterIP, pinned to the control-plane node): `api-edge`, `api-data`, `api-public`, `api-tenant`, `api-ops`, `api-auth`, `api-fleet`, `api-mail`, plus ops TSX sites `api-ops-ui` / `api-ops-crm` / `api-ops-fleet` / `api-ops-jobs` / `api-ops-mail` / `api-ops-business` / `api-ops-admin`.

Host process on `k3s_server` (not a pod): **`cronnecture-job-worker`** claims `fleet_*` jobs. **`cronnecture-ansible-runner`** (`:18765`) runs allowlisted playbooks. Repair is host **`incident-watchdog`** (cron every 5 min, `FLEET_AUTOHEAL=1`; `make auto-heal`) plus leftover `/api/selfheal`. There is no MAS / Jarvis control loop.

`platform-staging` is **not currently deployed**.

### Other namespaces

| Namespace | What runs |
|-----------|-----------|
| `mail` | Stalwart (1 replica on the control node; **hostPorts 25/587**) |
| `identity` | Vaultwarden, Passbolt, Authentik (1), Cerbos (2) on `pool=general`. **Logto and Hanko deleted 2026-08-26.** See [identity.md](../operations/identity.md). **SSH stays Cloudflare Access SSH CA** |
| `cronnecture-intelligence` | Overlay: master-orchestrator, cloudflare-manager, credential-manager, monitoring-system. Auto-heal / auto-scale **off** |
| `previews` | Demo hub + per-UUID `pv-*` sites on `previews.cronnecture.com` |
| `client-{slug}` | Per-tenant apps (live example: `client-noorddriveautos`) |
| `monitoring` | Prometheus + Alertmanager + kube-state-metrics + 3/3 node-exporters. Applied 2026-08-26 (`make monitoring`). No Grafana. |

Control plane pods use leader election (K8s Lease) for the background job sweeper.

### Namespace: `client-{slug}` (per tenant)

Created by ops API for each client:

| Resource | Purpose |
|----------|---------|
| `Namespace` | Isolation boundary |
| `ResourceQuota` | CPU/memory/pod limits |
| `NetworkPolicy` | Same-ns unrestricted; kube-system + platform only on app ports `80`/`8080`/`3000`; egress HTTPS/DNS/Postgres + registry `:5000`. UFW is the host perimeter |
| `Deployment` + `Service` | Each app (and optional `site-gate` / `site-logto` for product SSO) |
| `IngressRoute` | Traefik routes per hostname |
| `Job` | Kaniko image builds |

## Traffic flows

### Admin: operator UI

```
Browser → Cloudflare Access (control.cronnecture.com)
       → node-tunnel → Traefik ClusterIP
       → dashboard (UI)  /  agent-core (/api)
       → ClusterIP JS APIs / control-plane-legacy as needed

ops.cronnecture.com  →  301 UI to control (APIs / webmail / portal stay)
stack.cronnecture.com → 301 to control
```

JS still owns catalog APIs: auth cookie, CRM writes, GitHub/Kaniko deploy, tunnel expose, jobs, fleet, mail list, public legal/handshake/contact, Stripe webhook HMAC. Python still owns customer portal + Authentik OIDC (`logto_oidc.py`), delete-client, billing GET/checkout, mail send/IMAP, GitHub OAuth callback, previews, self-heal events. GitHub OAuth callback bypasses Access (`/api/github/callback` on `ops.cronnecture.com`).

### Client: customer portal

```
Browser → client.cronnecture.com (Cloudflare Access off — skip_access)
       → node-tunnel → Traefik ClusterIP (Host client.cronnecture.com)
       → Next.js client-portal (pages)
       → GET /portal + POST /portal/actions on control-plane-legacy
       → Authentik OIDC → cp_logto_session (cookie name is historical)
```

Canonical URL is **https://client.cronnecture.com/** (tenant from the Authentik session). Legacy `/client/portal/{uuid}` redirects here. See [client-portal.md](../platform/client-portal.md).

### Client public site

```
Browser → Cloudflare (client zone, proxied)
       → client-{slug} tunnel
       → Traefik ClusterIP :80  (not host :80)
       → IngressRoute in client-{slug} namespace
       → app Service → pod
```

### Site previews (demos)

```
Browser → Cloudflare (previews.cronnecture.com, public)
       → node-tunnel → Traefik ClusterIP :80
       → IngressRoute PathPrefix /previews/{uuid} (+ StripPrefix)
       → Deployment in namespace previews
```

See [previews.md](../platform/previews.md). Marketing apex is never path-routed for demos.

### Image build & deploy

```
Ops UI → POST /api/clients/.../apps → Job (deploy_app)
      → Kaniko Job in client namespace
      → push to fleet-registry.platform.svc:5000  (R2-backed)
      → Deployment updated → Traefik route (if exposed)
```

### SIEM auto-block (retired)

Wazuh is **not running**. `[siem]` is empty. Policy keys `cf_autoblock_*` remain in `ansible/config/policies/cloudflare.yml` but have no manager to fire them. See [siem-retired.md](../operations/siem-retired.md).

## Data stores

| Store | Location | Contents |
|-------|----------|----------|
| Supabase Postgres | External | Clients, apps, jobs, tunnels, GitHub tokens |
| etcd | k3s server | Cluster state |
| fleet-registry | `pool=general` worker | Built images → **R2** (`vault_registry_s3_*`); PVC fallback if unset |
| `cf_clients.yml` | repo (runtime) | Tunnel registry for Ansible (Postgres is source of truth) |
| Vault | encrypted file `ansible/config/inventory/group_vars/all/vault.yml` | CF tokens, DB URLs, identity secrets |

## Ansible convergence order

`make site` runs (tagged imports — use `--tags` / `--skip-tags`):

1. **baseline** — packages, hardening, cloudflared on all nodes
2. **loadbalancer** — edge_lb (no-op if empty)
3. **cluster** — k3s server + agents
4. **siem** — no-op while `[siem]` is empty (Wazuh retired)
5. **rancher** — optional (`rancher_enabled: false`)
6. **control_plane** — build image, deploy platform + registry
7. **cloudflare** — edge policy + admin portals + SSH Access hostnames
8. **client** — sync client tunnels from `cf_clients.yml`
9. **fleet_ops** — backup/health cron + ansible-runner unit
10. **monitoring** — node exporters + Prometheus + Alertmanager (live as of 2026-08-26)
11. **mail** — Stalwart mail stack
12. **identity** — Vaultwarden, Passbolt, Authentik, Cerbos (Logto and Hanko retired)
13. **stack** — keep-set mail/identity YAML, overlay, operator UI, tunnel origins, close leftover HTTP NodePorts (`ansible/playbooks/stack.yml`)

After `make add-node IP=…` (bootstrap → placement → inventory), the same `site.yml` path runs automatically.

## Scaling behavior

| Workloads | Scheduling |
|-----------|------------|
| Client apps | No nodeSelector → any untainted worker |
| JS APIs + Python control-plane + operator UI | `nodeSelector: node-role.kubernetes.io/control-plane: "true"` (or hostname `cp-master-01`) |
| Identity, marketing site, registry | `nodeSelector: pool=general` |
| Multiple replicas | kube-scheduler spreads when multiple workers exist (Cerbos already 2×; Authentik stays 1×) |

Ingress backend for tunnels: Traefik ClusterIP (`cf_client_ingress_backend` in `ansible/config/inventory/group_vars/all/ingress.yml`). Host `:80` is not the origin. Client connectors run on every node so Cloudflare can fail over.

## Related docs

- [repository.md](repository.md) — stack folder layout
- [inventory.md](inventory.md) — groups and variables
- [kubernetes.md](kubernetes.md) — manifests and kubectl
- [platform-api.md](platform-api.md) — JS API catalog
- [control-plane.md](../platform/control-plane.md) — leftover FastAPI / CRM internals
- [security.md](../operations/security.md) — hardening details
- [resilience.md](resilience.md) — SPOFs and mitigation roadmap
- [first-clients.md](../business/first-clients.md) — go-live checklist
