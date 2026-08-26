# Maintenance mode — Cloudflare edge

Client-facing maintenance is handled at **Cloudflare**, not on the fleet. Traffic never reaches Traefik or your compute nodes while maintenance is ON.

## Architecture

```
Visitor → Cloudflare (proxied DNS)
            ↓
     Tunnel ingress → Maintenance Worker (503 HTML)
            ✗  (fleet not contacted)

Ops / webmail / customer portal host → node-tunnel → control-plane  (always bypassed)
Marketing apex (cronnecture.com / www) → node-tunnel rewrite when ON
Client site hostnames → that client's tunnel rewrite when ON
```

| Component | Role |
|-----------|------|
| **Maintenance Worker** | Serves branded 503 HTML from KV state |
| **KV namespace** | `state` = `{ enabled, message }` — updated by ops UI; per-host billing keys `host:{hostname}` |
| **Client tunnel ingress** | Each client public hostname routed to Worker URL while ON |
| **Platform / node-tunnel** | Marketing `cf_public_sites` hosts also rewritten while ON |
| **Traefik overlay** | Optional fallback only (`MAINTENANCE_TRAEFIK_FALLBACK=true`) |

## One-time setup

### 1. Mint Workers token (if not already)

```bash
make cf-mint ARGS="--zone cronnecture.com"
# Creates vault_cf_workers_token with Scripts + KV permissions
```

### 2. Deploy the Worker

```bash
python3 scripts/cloudflare/deploy-maintenance-worker.py
# or: make cloudflare   (includes Worker deploy when token is set)
```

The script prints a KV namespace id. Add to vault:

```yaml
vault_cf_maintenance_kv_namespace_id: "<namespace-id-from-script>"
```

Enable the workers.dev subdomain for the Worker if Cloudflare returns error **1042**.

### 3. Redeploy control plane

```bash
make deploy-production
# or hot path on the control node — see RB-04 / DEPLOYMENT.md
```

Verify in ops UI → **Home → Maintenance mode** — status should show **Cloudflare edge** (not "Worker not configured").

## Daily use

### Manual toggle

Ops UI → **Home** or **Automations → Cluster maintenance**

- Toggle switch → enables/disables maintenance for covered public hostnames
- Edit visitor message → saved to KV (no Worker redeploy needed)
- **Re-sync edge** → re-applies tunnel ingress if drift detected
- **Preview** → `GET /api/maintenance/preview`

### What is covered when ON

| Covered | Source |
|---------|--------|
| Active client exposure hostnames | Client tunnels |
| Marketing public sites (`cronnecture.com`, `www`, `cronnecture.nl`, `www.cronnecture.nl`, …) | `cf_public_sites` / `platform_sites.yml` via `public_site_hostnames` → **node-tunnel** |
| Origins for restore | Persisted in `platform_settings` key `maintenance_platform_origins` |

### Bypass (never maintenance)

Typical bypass set (see live `GET /api/maintenance` → `bypass_hosts`):

- `ops.{zone}`, `staging-ops.{zone}`, `webmail.{zone}`
- `client.{zone}` (shared customer-portal host)
- Control-plane public host / ingress backend host
- SSH / non-public admin portals from `cf_portals.yml`

### Auto maintenance (fleet jobs)

These jobs automatically enable maintenance for their duration (ops/webmail stay up):

- `control_plane`, `restart_control_plane`, `site`, `cluster`, `upgrade`, `k3s`, `bootstrap`, `platform_refresh`, …

During platform upgrades, prefer **`make release`** (staging first) or **`make deploy-production`** — see [deployment.md](deployment.md) and [RB-13](../runbooks/staging-and-release.md).

### API

```bash
curl -s https://ops.cronnecture.com/api/maintenance | python3 -m json.tool
curl -X PATCH https://ops.cronnecture.com/api/maintenance \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true, "message": "Upgrading platform.\n\nBack in 15 minutes."}'
curl -X POST https://ops.cronnecture.com/api/maintenance/sync
curl -s https://ops.cronnecture.com/api/maintenance/preview | python3 -m json.tool
```

## How it works (implementation)

When maintenance is **enabled**:

1. Control plane writes `{ enabled: true, message }` to Workers KV
2. For each active **client** tunnel, public hostnames get ingress to  
   `https://cronnecture-maintenance.<account>.workers.dev` with  
   `originRequest.httpHostHeader` = Worker host (required for correct Worker routing)
3. **Platform marketing hosts** on **node-tunnel** are rewritten the same way; prior origins saved for restore
4. Worker reads KV and returns **503** HTML (`Scheduled maintenance`)

When **disabled**:

1. KV updated to `{ enabled: false }`
2. Client tunnels restored via reconcile / saved ingress
3. Platform marketing hosts restored from `maintenance_platform_origins`

### Drift protection

Fleet reconcile and per-client tunnel rebuilds used to undo maintenance. After:

- `rebuild_tunnel_for_client` — if cluster maintenance is ON, that client’s maintenance ingress is **re-applied**
- `reconcile_all_clients_cloudflare` — platform marketing maintenance is **re-applied** when ON

Code: `app/client_service.py`, `app/cf_maintenance.py`, `app/maintenance_service.py`, `app/system_resources.py`.

## Traefik fallback (optional)

By default Traefik overlay is **disabled** when Cloudflare edge is configured.

```yaml
maintenance_traefik_fallback: true
# or env MAINTENANCE_TRAEFIK_FALLBACK=true
```

Use only for hostnames that bypass Cloudflare (direct IP access).

## Files

| Path | Purpose |
|------|---------|
| `workers/maintenance/worker.js` | Edge Worker script |
| `scripts/cloudflare/deploy-maintenance-worker.py` | Deploy Worker + KV |
| `services/control-plane/app/cf_maintenance.py` | Tunnel + KV sync (+ httpHostHeader, platform origins) |
| `services/control-plane/app/maintenance_service.py` | UI/API orchestration, covers + bypass |
| `services/control-plane/app/system_resources.py` | `public_site_hostnames` |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| UI shows "Worker not configured" | Run deploy script; add KV namespace id to vault; redeploy control plane |
| Marketing site still live while ON | Confirm hostname is in `public_hostnames`; **Re-sync edge**; check node-tunnel ingress + Worker `httpHostHeader` |
| Client site still live | **Re-sync edge**; check client tunnel exposures; confirm not in bypass |
| Worker **1042** / empty | Enable workers.dev subdomain; redeploy Worker |
| Generic 403/404 from Worker | KV `enabled` false, missing `httpHostHeader`, or wrong Worker host |
| Ops UI unreachable | node-tunnel / Access issue — not maintenance |
| Maint undone after CF reconcile | Ensure build includes post-reconcile re-apply (see Drift protection) |

## Billing holds (per-client)

After **90 days** of non-payment, billing enforcement routes that client’s tunnel hostnames to this same Worker (KV key `host:{hostname}`) and scales workloads to 0. Other clients stay live. See [stripe-billing.md](../platform/stripe-billing.md).

Redeploy the Worker after pulling Worker script changes:

```bash
python3 scripts/cloudflare/deploy-maintenance-worker.py
```

## Related

- [cloudflare.md](cloudflare.md) — tunnels and DNS
- [control-plane.md](../platform/control-plane.md) — ops planes and APIs
- [stripe-billing.md](../platform/stripe-billing.md) — pay-needed + 90-day suspend
- [deployment.md](deployment.md) — safe deploy workflow with auto-maintenance
