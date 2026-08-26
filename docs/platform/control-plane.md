# Control plane (ops dashboard)

Python FastAPI leftover plus the customer portal. Day-to-day ops UI is the JS platform API ([platform-api.md](../architecture/platform-api.md)): seven TSX sites behind `api-edge` on NodePort **30080**.

**URL:** `https://ops.cronnecture.com`  
**UI version (cache buster):** shared across leftover dashboard shells in `static/dashboards/*.html` — currently **`?v=2.1.0`** (hard-refresh after deploys)  
**API title version:** `0.34.0` (`app/main.py`)  
**Bookkeeping:** [company-nl.md](../business/company-nl.md) — deprecated; use Moneybird + Stripe client billing  

**Namespace:** `platform` (staging: `platform-staging` → NodePort `30081` / `staging-ops.cronnecture.com`)  
**Edge:** JS `api-edge` owns NodePort `30080`. Python is ClusterIP `control-plane-legacy` for unported APIs + `/client/portal/{uuid}`. Catalog-owned `/api/*` on Python return **501 `js_owned`** so ClusterIP cannot split-brain.  
**Resources (Python prod + staging):** requests `100m` CPU / `256Mi` memory · limits `1` CPU / **`10Gi`** memory (template: `roles/control_plane/templates/platform/_deployment.j2`)

## Components

| Piece | Location | Role |
|-------|----------|------|
| API + UI | `services/control-plane/` | FastAPI; `static/dashboards/*` planes; `static/customer-portal/` hub |
| Manifest | `roles/control_plane/templates/platform.yaml.j2` | k3s deployment |
| Database | Supabase (`vault_platform_database_url`) | Clients, apps, jobs, tunnels, portals, billing |
| Image registry | `fleet-registry` in `platform` | Kaniko push `:5000`; **R2 when `vault_registry_s3_*` set**, else PVC |
| Ansible runner | Host systemd `cronnecture-ansible-runner` `:18765` | Inventory/playbooks/vault on host — ansible hostPath off by default |
| Ops admin login | `/login` + session cookie **or** `OPS_API_TOKEN` | Required for admin `/api/*` in addition to Cloudflare Access |

## Architecture

```
Browser → Cloudflare Access → node-tunnel → :30080
       → api-edge (JS)
       → ClusterIP JS APIs  and/or  control-plane-legacy (FastAPI, 2 replicas)
       → Supabase (Postgres) via api-data / Python
       → Kubernetes API (in-cluster SA)
       → Cloudflare API (tunnel/DNS/Access)
       → host ansible-runner :18765
```

### Leader election

Background job sweeper runs on **one** replica only:

- K8s Lease: `control-plane-leader` in `platform`
- Implementation: `app/leader.py`
- On startup: `recover_interrupted_jobs()` marks stale jobs failed
- Job enqueue uses Postgres advisory locks (`app/resilience.py`)

### Pod health

| Probe | Path | Notes |
|-------|------|-------|
| Liveness / startup | `/api/health/live` | Lightweight — no DB |
| Readiness | `/api/health/ready` | DB must respond (503 when degraded) |
| Full health | `/api/health` | DB + Stalwart + mail storage label |

Deployment: **2 uvicorn workers**, JSON logs, **X-Request-Id**. Resource requests `256Mi` / limits **`10Gi`** memory (raise the limit if cgroup OOM kills appear in `dmesg` / Wazuh — that is pod pressure, not host exhaustion).

### Resilience modules

| Module | Purpose |
|--------|---------|
| `resilience.py` | Retries/timeouts for CF, Supabase, K8s |
| `oauth_store.py` | OAuth states in DB (not in-memory) |
| `leader.py` | Fail-closed leader election |
| `system_resources.py` | Desired platform hostnames from `cf_portals.yml` + public sites |
| `inventory_service.py` | Fleet Cloudflare inventory + cleanup |
| `maintenance_service.py` / `cf_maintenance.py` | Cluster maintenance at Cloudflare edge |

## Ops UI planes

Entry: Welcome chooser → plane shells (`dashboard_registry.py`).

### Global nav (IA)

| Group | Items |
|-------|--------|
| **Home** | Overview · Observability |
| **Fleet** | Topology · Cluster · **Nodes** · **Self-heal** · Previews |
| **Workspaces** | CRM · Client Databases · Business |
| **Security** | Security HQ |
| **Operate** | Automation |
| **Platform** | Settings (incl. **Users / Access** — ops team, passwords, CF allowlists, client portal access; see [operator-access.md](../operations/operator-access.md)) |

### Plane shells

| Plane | Path | Purpose |
|-------|------|---------|
| Welcome | `/welcome` | Home / observability entry |
| Infrastructure | `/infrastructure` | Topology constellation, cluster, **node add/remove**, **self-heal** |
| Security | `/security` | Wazuh SIEM HQ, detections, portal sync |
| Business | `/business` | Billing, cash flow, platform documents (mail inbox → `/webmail`) |
| Automation | `/automation` | Schedules, fleet backups / R2 status, cluster maintenance |
| Settings | `/settings` | Platform config, integrations, **Access / Team** ([operator-access.md](../operations/operator-access.md)) |
| CRM | `/crm` | Clients, apps, routes, portal, billing per tenant |
| DMS | `/dms` | Client databases inventory, schema ER diagrams, stale cluster-row cleanup |

### Infrastructure subpages (slimmed)

| Page | Path | Notes |
|------|------|--------|
| **Topology** | `/infrastructure/topology` | Live 3D constellation from `/api/architecture` (`universe.layout.positions3d` + geo on hosts). Click → detail; hubs drill. |
| Cluster | `/infrastructure/cluster` | Platform stack, Traefik, leader; CF orphan sweep action |
| **Nodes** | `/infrastructure/nodes` | Register/bootstrap VPS + cordon/drain/remove |
| **Self-heal** | `/infrastructure/selfheal` | Status hero, KPI rates, Detect→Heal→Verify flow, policy chips, action timeline |
| Previews | `/infrastructure/previews` | Demo sites on `previews.cronnecture.com` |

Removed from operator chrome (APIs unchanged): **Quick Ops** (legacy `/quickops*` → Self-heal; runbooks stay on cron/CLI), **Capacity**, **Edge** overview/tunnels/routes/DNS, **Client workloads** — redirect to Topology or Cluster. Edge inventory surfaces via topology click-through; orphan sweep on Cluster (and CF edge detail). Also merged earlier: Worker pools → Nodes; Control plane / Platform services → Cluster.

**Topology API note:** Universe diagram nodes (esp. `k8s-node`) may include `details.provider` / `dc` / `city` / `geo_label` from inventory + fleet geo. `layout.positions3d` is the authoritative orbital layout for the 3D view.

Hard refresh after deploy uses `static/dashboards/*.html` cache busters (currently `?v=2.1.0`).

### Add a compute node from ops

VPS purchase stays external (no Hostinger/Hetzner API in vault). Once the IP exists:

1. Open **Fleet → Nodes** (`/infrastructure/nodes`)
2. Fill **Register & bootstrap node**: public IP, SSH user (usually `root`), one-time SSH password, role (`general` for second ingress worker, or `auto`)
3. Submit → job type `fleet_add_node` runs `scripts/fleet/add-node.sh` on the ansible control host (same as `make add-node` / `bin/fleet-add-node`)
4. Watch progress in the **job dock** (bootstrap → register → converge; ~15–30 min)
5. Refresh Nodes — host appears in inventory; Cluster / Topology update after cache invalidate

API: `POST /api/fleet/nodes` `{ ip, user, password, node_class }` → `{ job_id }`. Password is never stored in job payload.

Post-add reminder: if SSH Access hostnames need the new name, run **`make cloudflare`** (CLI). Site converge inside add-node usually covers client tunnels.

CLI equivalent: [RB-01](../runbooks/add-node.md).

## CRM — portfolio vs manage workspace

**Portfolio** (`/crm`, `/crm/portfolio`) and **manage workspace** (`/crm?client={id}&manage=1`) are **mutually exclusive**. Showing both stacks the portfolio bulk bar over the client Overview/Apps/… tabs (garbled labels).

| Mode | UI root | How to open |
|------|---------|-------------|
| Portfolio | `#crm-enterprise-root` | CRM plane boot / “← Back to CRM portfolio” |
| Manage | `#client-panel` | **Manage** button, sidebar client click, or `?client=&manage=1` |

Implementation: `static/planes/crm/enterprise.js` (`showEnterprise`), `static/app.js` (`crmPortfolioExclusive`, `selectClient`). APIs: `/api/crm/overview`, `/api/crm/pipeline`, `/api/crm/clients/{id}`, `/api/clients/{id}`.

### Attention chips & readiness

- Health score + chips (`Failed job`, `Access empty`, …): `app/client_health.py`
- Setup checklist steps: `client_to_dict` → `readiness` in `app/client_service.py`
- Portal step is **done** only when `client_portals.status = active` (run `POST /api/clients/{id}/portal/provision` if stuck pending)
- Dismissed/orphaned jobs: `POST /api/jobs/{id}/dismiss` (optional `{"retry": true}`) sets `jobs.status=dismissed` and clears the Failed-job chip; retry enqueues a fresh job when the type is retryable
- Needs action / Failed-job chips only surface **actionable** failures (`app/job_attention.py`): still `failed`, not superseded by a later success of the same/related edge family (`cloudflare` / `clients` / `client_connector` / `edge_sync` / `platform_refresh` / legacy `new_client_edge`), not older than 14 days, and (for edge sync) related Access/inventory check still unhealthy. Home load and `POST /api/jobs/dismiss-resolved` auto-clear resolved rows (covers CLI `make cloudflare` / `make clients` after a failed edge sync)

### Wizard defaults (2026-07)

- Default zone mode: **client domain (custom)**
- Platform apex (`cronnecture.com`) is owned by the platform Cronnecture client — second clients cannot claim `zone_mode=platform` when taken (`/api/platform-zone` → `taken`)

## Customer portal

Canonical hub: `https://client.cronnecture.com/client/portal/{uuid}`. See [client-portal.md](client-portal.md).

- Account, billing, documents, status, support
- Ops: CRM → client → **Portal**
- **Do not advertise** `insights.*` (legacy 302 only if DNS left behind)
- API: `POST /api/clients/{id}/portal/provision`, `PATCH /api/clients/{id}/portal`

## Cluster maintenance

Edge maintenance (Worker + tunnel rewrite) covers **client hostnames and marketing public sites** (`cronnecture.com`, `www`). Ops / webmail / customer-portal host stay bypassed. Full detail: [maintenance.md](../operations/maintenance.md).

## Fleet Cloudflare inventory

Ops → Infrastructure / inventory APIs: “what exists in Cloudflare vs what the fleet uses?”

### Classification

| Status | Meaning |
|--------|---------|
| **in_use** | Client route in Postgres **or** platform portal in `cf_portals.yml` **with** active tunnel ingress |
| **system** | Only the `node-tunnel` object itself |
| **orphan** | Exists in CF but not declared or routed |
| **stale** | Was desired; drifted |
| **unmanaged** | Non-fleet naming (rare) |

Source of truth for platform portals: `config/inventory/group_vars/all/cf_portals.yml`.

### API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/inventory` | Full snapshot |
| POST | `/api/inventory/sync` | Reconcile all active clients + refresh |
| POST | `/api/inventory/cleanup` | Remove orphans (`?dry_run=true` preview); **never** deletes `node-tunnel`, declared portals, or `cronnecture.eu` zone DNS |

Per-client Access (still available):

| Method | Path |
|--------|------|
| GET | `/api/cloudflare/access/inventory` |
| POST | `/api/cloudflare/access/cleanup` |
| GET | `/api/clients/{id}/access/inventory` |
| POST | `/api/clients/{id}/access/sync` |

Full-fleet reconcile: `POST /api/cloudflare/reconcile`

## Database schema

Applied on startup via SQLAlchemy + `schema.sql` (high level):

| Table | Purpose |
|-------|---------|
| `clients` | Tenant slug, namespace, status, `portal_uuid`, billing fields |
| `client_zones` | Custom domains, CF zone IDs, NS delegation |
| `client_tunnels` | Per-client tunnel ID + encrypted connector token |
| `apps` / `exposures` | Workloads + hostname routes / Access |
| `site_previews` | Demo sites at `previews.{zone}/previews/{uuid}` |
| `client_portals` | Portal Access emails, hub JSON |
| `client_documents` | Customer portal DMS files |
| `fleet_registry_snapshots` | cf_clients tunnel registry |
| `jobs` | Async work queue |
| `oauth_states` | GitHub OAuth CSRF |
| `stripe_webhook_events` | Idempotent billing webhooks |

See [supabase.md](../operations/supabase.md).

## API reference (selected)

### Health & fleet

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health/live` | Probe-safe liveness |
| GET | `/api/health/ready` | Readiness (database) |
| GET | `/api/health` | DB + Stalwart + mail storage |
| GET | `/api/platform/readiness` | Launch checklist (auth required) |
| GET | `/api/fleet/cf-clients-registry` | cf_clients JSON |
| GET | `/api/fleet/cf-clients-registry.yaml` | YAML export for Ansible |
| GET | `/api/fleet-info` | Fleet summary (`image_tag`, zone, ingress) |

### Clients

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/clients` | List / create (`slug`, `name`) → assigns `portal_uuid` |
| GET/PATCH/DELETE | `/api/clients/{id}` | Read/update/delete (`?dry_run=true` on DELETE) |
| POST | `/api/clients/{id}/zones` | Add domain zone |
| POST | `/api/clients/{id}/connector/install` | Install cloudflared connector |
| POST | `/api/clients/{id}/apps`… | Create / deploy / expose (see code routers) |

Billing: [stripe-billing.md](stripe-billing.md). Delete teardown: [RB-14](../runbooks/delete-client.md).

### Background jobs

| Type | Actions |
|------|---------|
| `create_client` | Namespace, quota, network policy, tunnel, cf_clients registry |
| `delete_client` | Ordered teardown (Stripe, portal, CF, k8s, docs, mail…) |
| `deploy_app` | Kaniko → registry → Deployment |
| `delete_app` / `expose_app` | App + Traefik / DNS |
| `zone_poll` | NS delegation |
| `install_connector` | Ansible on compute |
| `billing_enforce` | Pay-needed / 90-day suspend |
| `provision_client` | Durable wizard stages (portal Access, database, zone, docs, billing, …) |

| `maintenance_sync` | Apply/restore Cloudflare edge maintenance |
| `fleet_converge` / `platform_task` | Fleet recipes from Automation / CLI |

## Deployment

Preferred:

```bash
export FLEET_ROOT=$PWD
make release                 # staging → smoke → production
# or: make deploy-production
# or: make control-plane
```

**Hot path on the control node** (code/UI only — skips apt, vault re-template, agent registries, and manifest hostPaths):

```bash
make control-plane-hot
```

Manual equivalent (same image tag + `imagePullPolicy: IfNotPresent` requires restart):

```bash
SRC=$FLEET_ROOT/services/control-plane
DST=/opt/control-plane
sudo tar -C "$SRC" --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' -cf - . \
  | sudo tar -C "$DST" -xf -
cd "$DST"
sudo DOCKER_BUILDKIT=1 docker build -t control-plane:latest .
TMP=/tmp/cp-img-$$.tar
sudo docker save control-plane:latest -o "$TMP"
sudo k3s ctr images import "$TMP" && sudo rm -f "$TMP"
sudo k3s kubectl -n platform rollout restart deploy/control-plane
sudo k3s kubectl -n platform rollout status deploy/control-plane --timeout=180s
```

Bump `?v=` cache busters in `static/dashboards/*.html` when shipping UI changes, then hard-refresh the browser.

Verify:

```bash
curl -sf http://127.0.0.1:30080/api/health/live
curl -sf http://127.0.0.1:30080/api/health/ready
make health
kubectl -n platform get pods -l app=control-plane
```

## Configuration (environment)

| Env var | Source |
|---------|--------|
| `DATABASE_URL` | `vault_platform_database_url` |
| `CF_*` tokens | vault |
| `SUPABASE_ACCESS_TOKEN` / `SUPABASE_ORG_ID` / `SUPABASE_REGION` | vault — Management API for per-client project auto-create |
| `SUPABASE_LEADS_*` | vault — ops Leads inbox |
| `INGRESS_BACKEND_HOST` | first `compute_general` host |
| `GITHUB_CLIENT_ID/SECRET` | vault / Settings |
| `TOKEN_ENCRYPTION_KEY` | Fernet |
| `CLIENT_PORTAL_HOST` | `client.cronnecture.com` |
| `PORTAL_DEV_EMAILS` | Always merged into portal Access |
| `HOST_IP` / `ANSIBLE_RUNNER_*` | Host runner |
| `OPS_ADMIN_PASSWORD` | `/etc/cronnecture/ops-admin.password` |

Stripe keys live in **Business → Settings → Billing** (encrypted platform settings), not git.

**Client databases:** pack `site_supabase` / DB mode `supabase` auto-creates an isolated Supabase project via the Management API when `SUPABASE_ACCESS_TOKEN` + `SUPABASE_ORG_ID` are set (vault or Settings → Integrations). Credentials land in `client_databases` and the client namespace secret; DMS at `/dms` inventories them (platform `cronnecture` excluded). Without Management API, the wizard requires a pasted URL + anon key.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Jobs stuck pending | Leader lease; only one replica sweeps; check UniqueViolation left job `running` — recover/dismiss |
| Connector install fails | `systemctl status cronnecture-ansible-runner`; pod → `HOST_IP:18765` |
| Dashboard flaky | `/api/health/live` + 2 replicas/workers |
| CRM tabs garbled / overlapping | Portfolio + manage stacked — hard refresh to current `?v=` (e.g. `≥2.1.0`); open via Manage only |
| Pod OOMKilled / Wazuh “system out of memory” | Almost always **memcg** (container limit), not host RAM — check `dmesg` for `CONSTRAINT_MEMCG` + `platform/control-plane`; limits are **`10Gi`** (see [RB-08](../runbooks/troubleshooting.md#control-plane-oom--wazuh-memory-alert)) |
| Portal checklist “working…” forever | `POST /api/clients/{id}/portal/provision` until `status=active` |
| Inventory false “system” | Only `node-tunnel` is system; hostnames must match `cf_portals` + ingress |
| Build fails | `kubectl -n client-{slug} logs job/kaniko-*` |
| Maintenance ON but marketing still live | See [maintenance.md](../operations/maintenance.md) — node-tunnel covers + `httpHostHeader` |

See [RB-04](../runbooks/deploy-control-plane.md), [RB-08](../runbooks/troubleshooting.md).

## Related docs

- [client-app-repo.md](client-app-repo.md) — client GitHub deploy requirements
- [first-clients.md](../business/first-clients.md)
- [client-portal.md](client-portal.md)
- [maintenance.md](../operations/maintenance.md)
- [cloudflare.md](../operations/cloudflare.md)
- [stripe-billing.md](stripe-billing.md)
- [RB-05](../runbooks/onboard-client.md) · [RB-14](../runbooks/delete-client.md)
