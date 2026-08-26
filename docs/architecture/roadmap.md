# Cronnecture Platform Roadmap

Locked priorities as of **2026-07-26**.  
**First paying clients:** see [first-clients.md](../business/first-clients.md) (definition of done + ordered next steps).  
**Long-horizon ops UI:** [control-plane-roadmap.md](control-plane-roadmap.md).

## Phase 0 — Mail ✅

- [x] Stalwart mail server on k3s (`make mail`)
- [x] Mail admin workspace — Manage → Mail (`ops.{zone}/#/mail`); webmail at `/webmail` + `webmail.{zone}`
- [x] `webmail.{zone}` Access portal (redirects to ops Mail)
- [x] Cloudflare DNS sync for **MX / SPF / DMARC** (API path exists)
- [x] **Publish DKIM TXT** — selectors `202607r` (RSA) + `202607e` (Ed25519) live as of 2026-07-26 evening; see [mail.md](../operations/mail.md)
- [x] PTR for mail IP → `mail.{zone}` (Hostinger; verified public PTR)
- [x] Bootstrap platform SMTP (`POST /api/mail/bootstrap-smtp`)
- [x] PostgREST mail rules (`vault_supabase_platform_service_key`)
- [x] **Verify external send/receive** (Gmail ↔ `info@cronnecture.com`) — closed 2026-07-26; see [first-clients.md](../business/first-clients.md)

## Phase 0.5 — Infrastructure polish ✅

- [x] Unified service error mapping, readiness probes, JSON logging, cf_clients Postgres registry
- [x] Mail checks in `make health`
- [x] Customer portal on `client.cronnecture.com` (Logto; Access off); no `insights.*` product

## Phase 1 — Business layer (mostly done)

- [x] Stripe keys + webhook secret in Business → Settings (readiness green)
- [x] Pay-needed banners + **90-day** suspend → maintenance ([stripe-billing.md](../platform/stripe-billing.md))
- [x] Launch checklist (`/api/platform/readiness`)
- [x] CRM documents + customer portal billing/docs sections
- [x] Delete-client ordered teardown + dry-run ([RB-14](../runbooks/delete-client.md))
- [x] End-to-end rehearsal: throwaway client → portal → checkout → delete (do **not** delete production pilots casually) — **2026-08-07** `mvp-probe-20260807` (Stripe **test** mode): portal UUID + Access, checkout link `cs_test_…`, paid sub €39.99 via PILOT50, webhook `customer.subscription.created` → `billing_status=active`, delete job `8423` completed; stale `v1.ext.cattle.io` APIService removed so ns finalized
- [ ] Enable push-to-deploy on production apps when desired (optional)

## Phase 1.5 — Safe deploys ✅

- [x] Staging (`platform-staging`, `make deploy-staging`, `staging-ops.{zone}`)
- [x] Zero-downtime production rolling deploy
- [x] Production 2-replica control-plane
- [x] Cloudflare edge maintenance (Worker + KV)
- [x] `make release` flow
- [ ] Second compute node for client ingress HA ([RB-10](../runbooks/scale-to-ha.md)) — **MVP risk** (blocked on adding VPS capacity)
- [ ] HA control plane / edge at ≥5–7 nodes via placement policy ([resilience.md](resilience.md) V-04/V-05) — needs more hosts
- [ ] Identity Supabase **PITR** on `cronnecture-identity` (or equivalent) — **deferred** with HA / more VPS budget (~€100/mo; not urgent; current survival = Passbolt dumps + fleet→R2 + break-glass + provider daily backups if plan includes them). See [identity.md](../operations/identity.md), [backup.md](../operations/backup.md)
- [ ] Control-plane monolith split (further router/service peel beyond current strangler) — deferred; freeze list in [freeze-list.md](freeze-list.md)

## Phase 2 — Alerting (before scale)

- [x] Choose channels (email floor via notify-ops + Alertmanager; Slack-compatible Webhooky when `vault_slack_webhook_url` set)
- [x] Alert rules: disk / NotReady / backup+R2 stale / health+watchdog / deploy+converge failure (`make monitoring`)
- [ ] Notification preferences per operator

## Phase 3 — Client productization

- [ ] Client onboarding templates (static site + Supabase + mail)
- [ ] Auto-provision mailbox on client create (optional)
- [ ] Public status pages defaults per client (portal `/status` already exists)
- [ ] Portal performance / traffic KPIs polish (hub, not `insights.*`)

## Phase 4 — Trust & hardening

- [x] Weekly restore fire drill (scheduled) — `restore_drill` + `make restore-drill`; off-box break-glass pack on R2/worker
- [ ] SLO targets on Observability / Welcome

## Quick commands

```bash
make release               # staging → smoke → production
make health
make mail-smoke
curl -s -H "Authorization: Bearer $OPS_TOKEN" \
  http://127.0.0.1:30080/api/platform/readiness | python3 -m json.tool
```

Docs: [first-clients.md](../business/first-clients.md) · [deployment.md](../operations/deployment.md) · [mail.md](../operations/mail.md) · [stripe-billing.md](../platform/stripe-billing.md)
