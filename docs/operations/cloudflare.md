# Cloudflare integration

Cloudflare is the edge layer: DNS, TLS, WAF, rate limits, Zero Trust Access, and tunnels.

## Configuration files

| File | Purpose |
|------|---------|
| `config/policies/cloudflare.yml` | Zone settings, WAF, rate limits, Access emails |
| `config/inventory/group_vars/all/cf_portals.yml` | Admin portal tunnel routes |
| `config/inventory/group_vars/all/cf_clients.yml` | **Runtime** client tunnel registry (API-generated) |
| `config/inventory/group_vars/all/vault.yml` | API tokens (encrypted) |

## Token model

Mint once with bootstrap token:

```bash
echo 'BOOTSTRAP_TOKEN' > ~/.cf_bootstrap && chmod 600 ~/.cf_bootstrap
make cf-mint ARGS="--zone cronnecture.com"
# or: ./scripts/cloudflare/cf-mint-tokens.py --zone cronnecture.com
```

| Vault key | Used for |
|-----------|----------|
| `vault_cf_dns_token` | DNS record management |
| `vault_cf_tunnel_token` | Tunnel create/configure |
| `vault_cf_access_token` | Zero Trust Access apps |
| `vault_cf_waf_token` | WAF, rate limits, zone settings |
| `vault_cf_zone_id` | Platform zone ID |

Bootstrap token is **revoked** after minting. See [RB-06](../runbooks/cloudflare-tokens.md).

## Apply edge policy

```bash
make cloudflare
# ansible-playbook -i config/inventory/hosts.ini playbooks/cloudflare.yml
```

Runs on control machine (`localhost` limit). Idempotent — safe to cron hourly.

### What gets applied

From `config/policies/cloudflare.yml`:

- Zone settings: HTTPS, TLS 1.2+, security level high, brotli
- Bot Fight Mode **off** (Free cannot skip BFM per-host; breaks Bitwarden/Vaultwarden apps)
- Rate limit: global abuse brake (300 req / 10s)
- WAF custom rules: **skip** verified crawlers (`cf.client.bot`, so Googlebot is not challenged), **skip** `vault.cronnecture.com` (BIC / security level / rate-limit / managed), then block scanner paths, bad methods, high threat score. Same custom ruleset is published to extra marketing zones (`cronnecture.nl`) when the WAF token can write them.
- Access allowed emails/domains
- Auto-block rule pruning (24h TTL)

From `cf_portals.yml`:

- Tunnel ingress on `node-tunnel` (every node runs cloudflared)
- Proxied DNS CNAME per portal
- Cloudflare Access app per portal

**Maintenance Worker** (client sites): deployed by `make cloudflare` or `deploy-maintenance-worker.py`. See [maintenance.md](maintenance.md).

## Admin / platform portals

Defined in `cf_portals.yml` (`cf_admin_portals` + `cf_public_sites`):

| Portal | URL | Backend | Access |
|--------|-----|---------|--------|
| Client Control Plane | `ops.cronnecture.com` | k3s_server:30080 | CF Access → **Authentik only** (emails from `ops_users`) → ops session + RBAC — [operator-access.md](operator-access.md) |
| Cronnecture Control | `control.cronnecture.com` | k3s_server:30080 | CF Access → **Authentik only** (ops). Do not skip_access. |
| Gitea | `git.cronnecture.com` | Traefik → gitea.git:3000 | **`skip_access` + `purge_access_apps`** — Authentik OIDC inside Gitea (same IdP as client hub). Not Cloudflare Access. |
| Staging Control Plane | `staging-ops.cronnecture.com` | k3s_server:30081 | Same as ops (when staging enabled) |
| Cronnecture Mail | `webmail.cronnecture.com` | k3s_server:30080 | CF Access → Authentik → webmail SPA (`/webmail`) |
| Client customer portal | `client.cronnecture.com` | k3s_server:30080 | **`skip_access` + `purge_access_apps`** — Logto gates hub (no host/path Access; avoids Error 1043) |
| Vaultwarden | `vault.cronnecture.com` | k3s_server:30110 | **`skip_access` + `purge_access_apps`** — public; Bitwarden apps need no Access cookie |
| Traefik dashboard | `traefik.cronnecture.com` | k3s_server:9000 | when enabled |
| Rancher | `rancher.cronnecture.com` | k3s_server:443 | when enabled |
| Marketing site | `cronnecture.com`, `www`, `cronnecture.nl`, `www.cronnecture.nl` | compute_general:80 (Traefik) | public |
| Site previews | `previews.cronnecture.com` | compute_general:80 (Traefik → ns/previews) | public hub; individual demos may be **Logto**-gated (no CF Access) — see [previews.md](../platform/previews.md) |

`cf_extra_zones` in `config/policies/cloudflare.yml` lists marketing zones besides `cf_zone`. Hourly sync publishes proxied apex/`www` CNAMEs to `node-tunnel` when that zone exists **in this Cloudflare account**. If the domain’s nameservers are Cloudflare but the zone lives in another account, DNS is skipped (playbook stays green) until the zone is added or transferred. Tunnel ingress and Traefik Host rules are still declared so the site works the moment DNS is in this account.

Ops Access bypass paths (no CF session):

- `/api/github/callback`, `/api/webhooks/*`, `/status/*`, `/api/public/*`

Allowed operator emails: `cf_access_allowed_emails` in `cloudflare.yml`.

**Not product DNS:** `insights.*`, `portal.cronnecture.com` — do not recreate.

## Client platform sites (day-1 hostname)

Public pattern (locked): **`https://sites-{slug}.cronnecture.com`**

Staging: **`https://preview-{slug}.cronnecture.com`**

Both are one-label hosts under the apex, so Free-plan Universal SSL (`*.cronnecture.com`) covers them. They are **not** `{slug}.sites.cronnecture.com` until a dedicated `sites.cronnecture.com` Cloudflare zone exists.

Path: visitor → Cloudflare (proxied CNAME on the apex) → **node-tunnel** (`*.cronnecture.com` catch-all, no Access) → Traefik ClusterIP → IngressRoute `Host()` in `client-{slug}`.

Custom domains (NoordDrive `noorddriveautos.com`, future customer zones) stay on **client-{slug}** tunnels. Do not put `sites-*` on those tunnels.

Control-plane upserts the per-slug CNAME. Ansible `make cloudflare` keeps the wildcard tunnel rule (`skip_dns` so a `*` record is not published).

**Ingress order:** Cloudflare Tunnel is first-match. `*.cronnecture.com` must sit **after** every exact hostname, especially `ssh-cp` / `ssh-mail-01` / `ssh-worker-general`. If the wildcard is first, Access still mints a short-lived SSH cert, then the session is sent to Traefik HTTP and fails. `make cloudflare` sorts wildcards last.

**SSH origins:** `ssh://<inventory ansible_host>:22` so any `node-tunnel` connector can dial the peer. Never `ssh://127.0.0.1:22` on a shared tunnel.

## Node tunnel (`node-tunnel`)

Every fleet node runs `cloudflared` (baseline role):

- Connects outbound to Cloudflare
- No inbound ports required for admin UIs
- Ingress routes defined by cloudflare playbook

## Client tunnels

Each client gets a **dedicated** tunnel `client-{slug}`:

1. Ops API creates tunnel via CF API
2. Token stored encrypted in Postgres
3. `cf_clients.yml` updated atomically
4. Ansible `client.yml` installs connector on compute node
5. Ingress points to `cf_client_ingress_backend` (live Traefik ClusterIP `10.43.125.134:80` — **not** `127.0.0.1`; a loopback origin 502s. See `group_vars/all/ingress.yml`)

Sync manually:

```bash
make clients
```

## DNS for client zones

When a client adds a zone in the ops UI:

1. CF zone created (or linked)
2. Nameservers returned — client updates registrar
3. `zone_poll` job checks delegation
4. Exposures create proxied CNAMEs → client tunnel

### Per-client reconciliation

The control plane treats Postgres as **source of truth** and prunes stale Cloudflare state on every tunnel rebuild:

| Resource | Behavior |
|----------|----------|
| Tunnel ingress | Replaced entirely with active routes (+ 404 catch-all) |
| DNS CNAME | Upsert desired hostnames; **delete** other CNAMEs pointing to this client's tunnel |
| Access apps | Upsert/remove per route; **delete** `client-{slug}-*` apps for domains no longer routed |
| Traefik IngressRoute | **Replace** host rules (no merge); delete route when app has no exposures |

Triggers: route delete, app delete, **Apply tunnel**, portal changes, and leader sweeper (~every 30 min).

Manual full-fleet reconcile:

```bash
curl -X POST https://ops.cronnecture.com/api/cloudflare/reconcile
```

Or per client: **Routes → Apply tunnel** in the ops UI.

## Fleet Cloudflare inventory (ops UI)

Ops dashboard → **Platform → Inventory** (API: `GET /api/inventory`).

Compares **live Cloudflare state** against **desired fleet state**:

| Desired source | Covers |
|----------------|--------|
| Postgres (`clients`, `exposures`, `client_portals`) | Client tunnels, routes, DNS, Access apps |
| `cf_portals.yml` (mounted at `/ansible/...`) | Platform portals on `node-tunnel` |

### Status labels

| Status | Meaning |
|--------|---------|
| **in_use** | Declared in fleet config **and** actively routed (client DB or platform ingress) |
| **system** | The `node-tunnel` tunnel object only — not every hostname on it |
| **orphan** | Leftover DNS, Access app, or client tunnel with no fleet owner |
| **stale** | Drift (e.g. portal in cf_portals but missing from tunnel ingress) |

**Important:** Hostnames like `argocd`, `k3s`, or manual SSH Access apps are **not** protected unless listed in `cf_portals.yml`. Use **Cleanup stale** to remove unused records.

### Actions

| Button / API | Effect |
|--------------|--------|
| Refresh | `GET /api/inventory` |
| Sync all | `POST /api/inventory/sync` — reconcile all clients |
| Cleanup stale | `POST /api/inventory/cleanup` — delete orphans; prune extra `node-tunnel` ingress rules; stop orphan connectors before tunnel delete (`?dry_run=true` for preview) |

Declared platform hostnames come only from `cf_portals.yml` (see table above). Inventory cleanup will not protect ad-hoc CF apps.

### Scheduled orphan cleanup

| When | What |
|------|------|
| **Sun 02:00 UTC** | Dry-run report → `alerts@` (+ Webhooky). Host cron + Automation `inventory_cleanup_report`. |
| **Mon 03:00 UTC** | Apply — **disabled by default**; needs allowlist + Sunday evidence. |

Protections (always): `node-tunnel`, declared portals/SSH, empty/reuse zone `cronnecture.eu`. See [overview.md](overview.md#scheduled-cf-orphan-cleanup-dns--access--tunnels).

See [control-plane.md](../platform/control-plane.md) for inventory APIs. Customer hub paths: [client-portal.md](../platform/client-portal.md).

## GitHub OAuth for ops UI

```bash
./scripts/cloudflare/bootstrap/configure-github-oauth.sh
```

Sets GitHub OAuth app callback to `https://ops.{cf_zone}/api/github/callback`. Credentials in vault.

## Editing policy

1. Edit `config/policies/cloudflare.yml` or `cf_portals.yml`
2. `make cloudflare`
3. Verify in CF dashboard or curl portal URL

## Troubleshooting

| Issue | Check |
|-------|-------|
| Portal 502 | Tunnel connector on backend node: `systemctl status cloudflared` |
| Access loop | Email not in `cf_access_allowed_emails` |
| Client site down | `cf_clients.yml`, connector on compute, Traefik ingress |
| WAF false positive | Temporarily lower rule in dashboard; tune expression in policy |
| Token 403 | Re-mint tokens; verify vault decrypted |

See [RB-06](../runbooks/cloudflare-tokens.md), [RB-08](../runbooks/troubleshooting.md).

## Related docs

- [maintenance.md](maintenance.md)
- [security.md](security.md)
- [control-plane.md](../platform/control-plane.md)
- [siem.md](siem-retired.md)
