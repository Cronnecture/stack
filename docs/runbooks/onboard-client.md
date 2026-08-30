# Onboard a client

Runbook **RB-05**.

End-to-end procedure for adding a new tenant via the **CRM New client wizard** (and optional durable provision job).

**Self-serve Website (no wizard):** buyers use [client.cronnecture.com/start](https://client.cronnecture.com/start). While `self_serve_live_payments` is **false** (default), `/start` is contact / invoice only. See [stripe-billing.md — Self-serve](../platform/stripe-billing.md#self-serve-website-checkout). Do not open public cards unless the founder asks.

**Custom domain upgrade (self-serve):** CRM portfolio shows a **Domain request** chip when the customer submits **Connect custom domain** in the portal. Add their domain under Workspace → Domains (same NS cutover as below), expose the app on the new hostname, leave the platform subdomain as fallback until cutover is confirmed. Use this runbook also for migrations and non-self-serve packs.

## Prerequisites

- Ops UI: `https://ops.cronnecture.com` → **CRM**
- Cloudflare API tokens in vault
- At least one `compute_general` node Ready
- GitHub connected (optional, for first app / New site)
- Stripe default price set (optional, for Site + billing / Full packs)

## Overview

```
Wizard (name/slug + Access emails + pack)
  → POST /api/clients  (namespace + portal_uuid + portal_url + legal docs)
  → POST /api/clients/{id}/provision  (durable job stages)
  → zone_poll → tunnel + connector + portal Access
  → optional app / checkout
  → CRM checklist + Open workspace
```

Customer hub URL is always:

`https://client.cronnecture.com/client/portal/{uuid}`

(Do **not** invent `insights.*` hostnames.)

## Step 1: New client wizard

1. **CRM → Portfolio → + New client** (or empty-state CTA).
2. Enter **name** + **slug** (`a-z0-9-`, becomes `client-{slug}`).
3. Choose a **go-live pack** (sets the default database mode; override in the Database radios):
   - Site only → **no database**
   - Site + Supabase → **Supabase** (auto-creates a project when Management API is configured; otherwise paste URL + anon key)
   - Site + billing → **no database**
   - Full → **in-cluster PostgreSQL**
4. Confirm or override **Database** (Supabase / in-cluster / none). Pack default is shown as a hint.
   - **Managed Supabase:** leave credential fields blank — the provision job creates `client-{slug}` via the Management API, waits until ready, and stores URL/keys in `client_databases` + the client namespace secret.
   - **Manual connect:** paste project URL + anon key (optional service role / DSN).
5. Enter **≥1 Portal Access email** (Cloudflare OTP).  
   Skipping requires the explicit “skip with warn” checkbox — portal login will fail until emails are set.
6. Optional: auto-issue Terms/Privacy (default on), create Stripe checkout link.
7. Domain: default is **client domain (custom)**. Platform apex (`*.cronnecture.com` zone ownership) is disabled when already taken by the platform client (`/api/platform-zone` → `taken`). Prefer a real customer domain for production tenants.
8. Optional first app (template or GitHub repo).
9. **Launch** — create returns `portal_uuid` + `portal_url`; durable `provision_client` job owns DB/zone/docs/billing (wizard polls DB status).

**Database ownership:** the provision job is the single writer for `client_databases` on create. Workspace → Database still supports day-2 provision/connect/delete. **Client Databases (DMS)** at `/dms` inventories customer DBs (platform `cronnecture` excluded); use **Refresh** after create, and **Clear inventory** only for stale cluster rows whose k8s resources are already gone.

**Create API always assigns** `portal_uuid` and returns `portal_url`.

Monitor:

```bash
curl -sf http://127.0.0.1:30080/api/jobs/<job_id>
sudo k3s kubectl get ns | grep client-
```

**UI note:** Portfolio and manage workspace are exclusive — use **Manage** (or sidebar) to open a client; do not expect the table and Overview tabs on screen at once. See [control-plane.md](../platform/control-plane.md#crm--portfolio-vs-manage-workspace).

## Step 2: DNS / nameservers

If the zone is pending:

1. Use **Copy nameservers** in the wizard (or Domains tab).
2. Update the registrar.
3. Click **I updated registrar — refresh** (or Domains → Refresh).
4. When status is `active`, tunnel `client-{slug}` + connector (if enabled) + portal Access are ensured by `zone_poll`.

## Step 3: Portal Access & invite

1. Workspace → **Portal** — confirm Access emails (CRM shows an **Access empty** chip when missing).
2. If portal status is still **pending**, run **Provision** (checklist or `POST /api/clients/{id}/portal/provision`) until status is **active**.
3. **Open portal** is blocked until at least one email is set.
4. **Invite teammate** adds an email + sends onboarding mail with the portal URL.
5. Status page is **on by default** for new clients (Status tab / Billing status-page toggle).

## Step 4: Billing

Policy: **pay-needed immediately**; site suspend only after **90 days** unpaid.

1. Billing tab (or wizard checkout) → create checkout / link subscription / refresh.
2. Customer hub → Billing → **Manage billing** (Stripe Customer Portal) when payment is needed.

## Step 5: Day-2 — Grant their GitHub repo (not the platform PAT)

Do **not** attach `Bolt2841/…` or NoordDrive’s repo. Each customer App binds **one** `owner/repo` they own.

1. Control portal → client → **Release → Grant GitHub repo**. Paste their `org/repo` (leave empty until they have a real repo).
2. Copy the **deploy key** (read-only) and **webhook secret**.
3. On GitHub, for **that repo only**:
   - **Settings → Deploy keys → Add deploy key** (write access off). Paste the public key. Title: `Cronnecture {slug}`.
   - **Settings → Webhooks → Add webhook**. Payload URL: `https://ops.cronnecture.com/api/webhooks/github` (paste in GitHub; POST only — a browser GET is 405, not a missing route). Content type: `application/json`. Secret: the **per-client** secret (never Settings → Deploy `github_webhook_secret`). Events: **Just the push event**.
4. Toggle **Auto-deploy** on after the hook is saved. A push to the bound branch ships **this** tenant only. Unknown repos return 404 and do not enqueue a build.
5. Next step (not this box): a GitHub App **installation** on the client org, so clone uses an installation token instead of a deploy key.

Ops-built sites (no repo) stay “Cronnecture is building your site.” The customer hub can **Connect Git** with the same deploy-key path. NoordDrive stays locked. Public Checkout stays off. Do not AddNode from the hub.

Capacity: 4 live tenants on one general worker.

## Step 6: Day-2 — New site & health

- Apps → **New site** (name + subdomain + template) → deploy + expose job.
- Templates: `vite-react-ts`, `static-vite`, `node-api-stub`, `supabase-ready`.
- CRM portfolio shows **health score (0–100)** and attention chips (`past_due`, pending NS, Access empty, failed jobs).
- Kanban: Lead · Provisioning · Live · Attention · Suspended.
- Bulk actions: reconcile CF, connector install, refresh billing, suspend.

## Step 6: Verification checklist

| Check | How |
|-------|-----|
| Namespace | `kubectl -n client-{slug} get all` |
| Portal UUID | CRM detail / create response `portal_url` |
| Access emails | Portal tab non-empty; customer OTP works |
| Zone active | Domains tab / wizard progress |
| Database | Pack/radio match; DMS `/dms` shows row when provisioned; workspace → Database |
| Billing | CRM chips + customer pay-needed UI |
| Delete dry-run | Settings → Delete → structured modal (`DELETE ?dry_run=true`) |

## Suspend / delete

- **Suspend:** scales workloads to 0.
- **Delete:** dry-run preview (grouped steps) → type slug → enqueue `delete_client` job (see [RB-14](delete-client.md)).

## Common issues

| Issue | Resolution |
|-------|------------|
| Portal OTP fails | Access emails empty — invite or Portal tab |
| Zone stuck pending | Registrar NS + refresh |
| Half-provisioned after tab close | Open workspace; retry `POST …/provision/retry?resume_from=zone` |
| Accidental in-cluster DB on Site only | Pack default is now **none**; confirm Database radios before Launch |
| Supabase pack without creds | Needs Management API (`vault_supabase_access_token` + `vault_supabase_org_id`) **or** paste URL + anon; otherwise the job fails clearly |
| DMS empty after create | Click **Refresh** on Client Databases; platform client is intentionally hidden |
| Build fails | Job dock / Dockerfile / registry |
| 502 on site | Connector / Traefik / ingress backend |

## API sketch

```bash
# Create (portal uuid + optional emails + legal docs)
curl -X POST http://127.0.0.1:30080/api/clients \
  -H 'Content-Type: application/json' \
  -d '{"slug":"acme","name":"Acme","access_emails":["ops@acme.com"],"issue_legal_docs":true}'

# Durable provision (database mode: none | cluster | supabase)
# Managed Supabase (no credentials) when Management API is configured:
curl -X POST http://127.0.0.1:30080/api/clients/<id>/provision \
  -H 'Content-Type: application/json' \
  -d '{"pack":"site_supabase","access_emails":["ops@acme.com"],"zone_mode":"skip","database":"supabase"}'

# Manual Supabase connect:
curl -X POST http://127.0.0.1:30080/api/clients/<id>/provision \
  -H 'Content-Type: application/json' \
  -d '{"pack":"site_supabase","access_emails":["ops@acme.com"],"zone_mode":"skip","database":"supabase","supabase":{"supabase_url":"https://xxxx.supabase.co","anon_key":"…"}}'

# Dry-run delete
curl -X DELETE 'http://127.0.0.1:30080/api/clients/<id>?dry_run=true'
```

## Related

- [client-app-repo.md](../platform/client-app-repo.md) — GitHub repo layout, Dockerfile, Supabase env for clean deploy
- [client-portal.md](../platform/client-portal.md) · [stripe-billing.md](../platform/stripe-billing.md) · [RB-14](delete-client.md) · [first-clients.md](../business/first-clients.md)
