# Delete a client

Runbook **RB-14**.

Complete teardown of a customer workspace (CRM client) — Stripe, Supabase/DB, Cloudflare, Kubernetes, portal, mail, monitoring.

## Prerequisites

- Ops UI: `https://ops.cronnecture.com`
- Confirm the client is a **test / decommissioned** tenant (not production revenue)
- **Never** delete platform client `cronnecture` (API refuses)

## Prefer dry-run first

```bash
# From a control-plane pod, or via ops API with Access session:
curl -sf -X DELETE "https://ops.cronnecture.com/api/clients/<id>?dry_run=true"
```

Or in CRM → client → **Delete client**: the UI loads the dry-run plan into the confirm dialog before enqueueing work.

Dry-run lists every step and target (hostnames, tunnel name, Stripe IDs, Supabase ref, document dir, mailboxes) **without mutating anything**.

## How ops triggers delete

1. CRM → select client → **Delete client**
2. Review dry-run checklist in the confirm dialog
3. Confirm → API enqueues background job `delete_client` (HTTP returns immediately with `job_id`)
4. Watch job log / Activity center until `completed` (or `failed` with step errors)

API (destructive):

```http
DELETE /api/clients/{id}
→ { "job_id": N, "status": "deleting" }
```

## Ordered teardown checklist

| # | Step | What is removed |
|---|------|-----------------|
| 1 | `guard_platform` | Refuse slug/`status=platform` cronnecture |
| 2 | `inventory` | Snapshot hostnames, tunnel, Stripe, Supabase for the job log |
| 3 | `maintenance` | Clear per-host maintenance Worker KV + Traefik billing overlay |
| 4 | `stripe` | Cancel subscription; delete/archive customer if safe; clear local billing fields |
| 5 | `suspend_workloads` | Scale app deployments to 0 |
| 6 | `apps_cluster` | Delete app Deployments/Services in `client-{slug}` |
| 7 | `portal` | Customer-portal Access path apps, legacy insights Access, portal ingress, `ClientPortal` |
| 8 | `database` | Supabase project **or** cluster Postgres; k8s secrets `client-db` / `client-db-app`; `ClientDatabase` |
| 9 | `documents` | `ClientDocument` rows + files under `CLIENT_DOCUMENTS_DIR/{id}` |
| 10 | `mail` | Client-linked mailboxes/domains only (**not** platform `cronnecture.com` mail) |
| 11 | `uptime` | `uptime_checks` rows for that client / hostnames |
| 12 | `cloudflare` | Connector stop; tunnel ingress clear; tunnel CNAMEs; Access `client-{slug}-*`; delete tunnel `client-{slug}`; rewrite DNS in client + platform zones |
| 13 | `k8s_namespace` | Delete namespace `client-{slug}` |
| 14 | `jobs` | Cancel other active jobs for this client |
| 15 | `database_rows` | Delete Client (+ apps, exposures, zones, tunnel) |
| 16 | `cf_clients_registry` | Rewrite `cf_clients` without this slug |

Step order in code: `DELETE_CLIENT_STEPS` in `client_service.py` (jobs → database_rows → registry).

Code entrypoint: `app.client_service.delete_client_resources` (job runner: `app.jobs._run_delete_client` → `enqueue_delete_client`).

## Failure handling

- Steps are **idempotent** — safe to re-run while the client row still exists (`status=failed` after a partial run).
- Soft warnings (e.g. connector already gone) are logged; hard failures (Stripe subscription still active, Access/DNS/tunnel errors, namespace delete) mark the job **failed** with `payload_json.teardown.failures`.
- Job log lists each step; Activity center shows `delete_client`.

## What this covers that used to be missing

- Stripe cancel + customer archive + local billing clear
- Supabase project teardown on full client delete
- Document files on disk
- Maintenance Worker KV / billing overlay clear
- Uptime history purge
- Client-specific mail teardown (platform mail untouched)
- Platform client delete block
- Dry-run preview (`?dry_run=true`)
- Structured per-step success/failure in the job payload

## Verify

```bash
# Client gone from API
curl -sf https://ops.cronnecture.com/api/clients | jq '.[] | select(.slug=="<slug>")'

# Namespace gone
kubectl get ns client-<slug>   # NotFound

# Tunnel gone
# Cloudflare Zero Trust → Tunnels: no client-<slug>
```

## Rollback

Deletion is **not** reversible from the ops UI. Restore from fleet backup (RB-07) only if the client must be resurrected; Stripe/Supabase/CF objects are already torn down.
