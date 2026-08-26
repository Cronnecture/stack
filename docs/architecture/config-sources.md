# Config sources of truth

Normative map for Cronnecture fleet configuration. Cleanup and ops changes must edit the **SoT** column — derived artifacts are regenerated, not hand-authored (except emergencies documented in runbooks).

See also: [freeze-list.md](freeze-list.md), [inventory.md](inventory.md), [supabase.md](../operations/supabase.md), [cloudflare.md](../operations/cloudflare.md).

## SoT matrix

| Concern | Source of truth | Repo / runtime artifact | Notes |
|---------|-----------------|-------------------------|-------|
| Clients, billing, portals, apps, tunnels metadata | **Postgres (Supabase)** | Control-plane API / DB | Never “fix” live clients by editing YAML alone |
| Host topology (SSH, groups, classes) | **`config/inventory/hosts.ini`** (gitignored live file) | `hosts.ini.example` is the template only | Overlay: `config/environments/{production,staging}/hosts.ini`. `make inventory-check` + `playbooks/inventory_guard.yml` refuse `YOUR_*` before CF PUT / SSH |
| Cloudflare origin IPs (platform portals) | **Postgres `fleet_nodes`** + `/etc/cronnecture/node-registry.json` | Seeded from live `hosts.ini`; never committed | Prefer registry IPs when healthy; still fail-closed on `YOUR_*` if registry empty |
| Platform Access portals + public marketing hosts | **`cf_portals.yml`** | `config/inventory/group_vars/all/cf_portals.yml` (committed) | Freeze zone — Access bypass paths are contract |
| Secrets | **`vault.yml`** (ansible-vault) | `config/inventory/group_vars/all/vault.yml` encrypted; `vault.example.yml` committed | Identity bootstrap lives in vault (`vault_authentik_*`, `vault_logto_*`, `vault_identity_*`). `config/.identity/` is **fallback only**, never committed |
| Client tunnel export for `make clients` | **Derived** from Postgres | `cf_clients.yml` (gitignored) via ansible-runner allowlisted write | Rewrite with `write_cf_clients_registry` / inventory sync — do not hand-edit as SoT |
| Control-plane deploy knobs | **`config/environments/{production,staging}/`** | Namespace, NodePort, replicas, public host | Staging must never share prod namespace/NodePort |
| Placement / edge / fleet ops catalog | **`config/policies/`** | `cloudflare.yml`, `placement.yml`, **`fleet-operations.yml`**, **`packs.yml`** | Low churn. Job catalog + runner allowlists are one file — do not duplicate paths in Python. Pack list is YAML so adding a pack is not a code change |
| Runner allowlist | **`config/policies/fleet-operations.yml`** → `runner.*` | `ansible-runner.py` and `test_runner_allowlist.py` load this file | Do not expand `write_paths`. Read/script prefixes must match the committed list |
| Encrypted `vault.yml` off-laptop | **Break-glass pack** (already includes vault.yml) | R2 + worker via `make break-glass` — [backup.md](../operations/backup.md) | Not a second secrets store. `config/.identity/` stays local DR fallback |

## DATABASE_URL pooler policy (documented once)

Multi-replica control-plane must use Supabase **transaction** pooler (`*.pooler.supabase.com:6543`), not session pooler (`:5432`).

**Both layers rewrite the same intent** (keep in sync; characterization: `scripts/test_pooler_rewrite.py`):

| Layer | Location | Rule |
|-------|----------|------|
| Jinja (deploy-time) | `roles/control_plane/templates/platform.yaml.j2` | `replace('.pooler.supabase.com:5432/', '.pooler.supabase.com:6543/')` into Secret `DATABASE_URL` |
| Python (runtime) | `services/control-plane/app/config.py` → `_prefer_supabase_transaction_pooler` | Replace `pooler.supabase.com:5432` → `:6543` when reading `DATABASE_URL` |

**Left alone:** direct `db.*.supabase.co:5432` (migrations / psql) and in-cluster `postgres:5432`.

Do **not** invent a third runtime rewriter or shared library inside the pod for this — dual documentation + characterization tests are the contract until a deliberate single-helper change lands.

## Operator edit guide

| I need to… | Edit |
|------------|------|
| Add/change a VPS | `hosts.ini` (+ peer firewall via baseline) |
| Change ops/webmail/client Access portal | `cf_portals.yml` then `make cloudflare` (freeze window) |
| Change Stripe/CF/DB secrets | `ansible-vault edit …/vault.yml` |
| Change client tunnels/exposures | Ops UI / API (Postgres) → registry rewrite → `make clients` if needed |
| Change CP replicas / staging NodePort | `config/environments/...` group_vars |
| Run playbooks against staging overlay | `make … ENV=staging` |

## Explicit non-goals (this doc)

- Migrating vault to external secret manager / SOPS
- Expanding ansible-runner filesystem powers
- Treating `cf_clients.yml` as authoritative over Postgres
