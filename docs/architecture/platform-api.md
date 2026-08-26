# JS platform API

Source: `services/platform-api/`. Catalog: `config/policies/api-catalog.yml`.

Each catalog API is a **separate image** (`platform-api-<name>:cutover`) and
Deployment. They talk over ClusterIP. `api-data` is the only process with a
database URL. JS `api-edge` owns NodePort **30080**. Ops is seven TSX sites that
share `@cronnecture/ops-theme` but ship as separate images: home, clients, fleet
(previews/backups/registry), jobs, mail, business, admin. Old plane prefixes
(`/infrastructure`, `/business`, `/security`, `/settings`) redirect into those
sites. Python is ClusterIP `control-plane-legacy` for unported APIs, webmail,
and the customer portal.

Manifests are generated from the catalog (`npm run render-manifests`). Do not
hand-edit `deploy/cutover.yaml`.

JS-owned: public legal/handshake/checkout/contact, Stripe webhooks (HMAC +
raw body through edge), tenant billing, CRM `GET/POST /api/clients` and
`PATCH /api/clients/:id` (create also ensures `client-{slug}` namespace,
quota, isolation netpol, and the control-plane secrets RoleBinding), jobs,
settle, runner, mail list, fleet inventory/operations plus live k8s Ready.
Fleet re-reads host `hosts.ini` (mounted from `/var/lib/cronnecture/inventory`)
so a new VPS shows up without rebuilding the image.

Host `cronnecture-job-worker` claims pending `fleet_*` jobs and runs the
scripts. JS `POST /api/fleet/nodes` writes a 0600 password file under
`/var/lib/cronnecture/pending-passwords` and enqueues `fleet_add_node`.
Operations and remove also enqueue host jobs.

Still Python: leftover `/api/selfheal` (watchdog + event log), client delete, billing GET/checkout/reconcile, GitHub OAuth callback
(not repo bootstrap), mail send/IMAP/create, previews, portal Authentik OIDC, leftover
dashboard HTML. GitHub/Kaniko deploy and tunnel expose are JS (`api-ops`).
Python `JsCatalogGuardMiddleware` returns 501 `js_owned` for catalog-owned
routes so a direct ClusterIP hit cannot dual-write.
`/crm` redirects to the TSX clients workspace.
Ops auth (`/api/auth/me`, login, access-login, logout) is JS and issues the
same `ops_admin_session` cookie as Python. Authentik customer SSO stays Python (`authentik_oidc.py`).

Rollback:

```bash
services/platform-api/deploy/cutover.sh rollback
```

## Handshake money

NoordDriveAutos is not Pilot. Setup €79.99 + month €39.99 via bank transfer;
Stripe €39.99 from 2026-09-14. Public checkout ignores `amount_cents`.

## Mail

Identity freeze: `docs/operations/mail-freeze.md`. `api-mail` reads mailbox
metadata from `api-data`. It is not a second mail store.
