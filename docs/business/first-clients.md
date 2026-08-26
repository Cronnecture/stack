# MVP / first paying clients

**Canonical go-live plan** for Cronnecture: verified baseline → gaps → ordered actions → definition of done.

**Verified:** 2026-08-22 (docs mount `stack/docs`, identity off master, two general workers). Prior passes 2026-08-11 / 2026-07-28 / 2026-07-26.  
Long-horizon UI: [control-plane-roadmap.md](../architecture/control-plane-roadmap.md). Product phases: [roadmap.md](../architecture/roadmap.md).

---

## 1. Current verified baseline

### Fleet

| Fact | Verified value |
|------|----------------|
| k3s | `v1.35.4+k3s1` — `cp-master-01`, `worker-general-01`, `worker-general-02` (all Ready) |
| Inventory | 1× `k3s_server`, 2× `compute_general`; `[siem]` empty (Wazuh retired); `edge_lb` / `compute_cpu` / `compute_memory` empty |
| Control plane | `platform` ns, **2/2** Ready, image `control-plane:5332744-2693f09fb3d7`, UI cache buster **`?v=2.1.0`**, API **`0.34.0`**, memory limit **`10Gi`** (request `256Mi`), rollout `maxSurge:1` / `maxUnavailable:0` |
| Staging | `platform-staging` 1/1 + NodePort **30081**; image `control-plane:6eb44ac-1bf77eeb92e1`; memory limit **`10Gi`**; `https://staging-ops.cronnecture.com` (Access) |
| Monitoring | `monitoring` ns: Prometheus + Alertmanager + kube-state-metrics + node-exporter DaemonSet (3/3); **no Grafana** |
| Registry | NodePort **30500**, storage **S3/R2** bucket `cronnecture-fleet-registry` (Basic auth required) |
| Backups | Daily etcd + fleet; R2 sync to `s3://cronnecture-fleet-backups/fleet-backups/…`; restore drill **passed** (2026-07-28); break-glass on R2 `break-glass/latest/` + worker |
| SIEM | Retired. `72.60.32.178` is `worker-general-02`. |

### Platform endpoints (DNS)

| Hostname | Public DNS | Notes |
|----------|------------|--------|
| `ops.cronnecture.com` | Proxied (CF anycast) | Access → ops planes + `/login` |
| `client.cronnecture.com` | Proxied | Path-scoped Access per portal UUID |
| `staging-ops.cronnecture.com` | Proxied | Access |
| `webmail.cronnecture.com` | Proxied | Access → webmail SPA (also `ops…/webmail`) |
| `cronnecture.com` / `www` | Proxied | Marketing → Traefik → `cronnecture-website` |
| `wazuh.cronnecture.com` | Proxied | Access |
| `mail.cronnecture.com` | **A → `31.97.126.9`** | SMTP entry (not tunnel) |
| `traefik.cronnecture.com` | **none** | `traefik_dashboard_enabled: false` |
| `rancher.cronnecture.com` | **none** | `rancher_enabled: false` (cattle-* pods may still linger) |
| `insights.*` / `portal.cronnecture.com` | **none** | Not a product URL |

### Mail

| Fact | Verified |
|------|----------|
| Stack | Stalwart `mail` ns, `hostPort` **25/587** on control node; UFW allows 25/587 |
| MX | `10 mail.cronnecture.com.` |
| PTR | `31.97.126.9` → `mail.cronnecture.com.` |
| SPF | `v=spf1 ip4:31.97.126.9 mx a:mail.cronnecture.com -all` |
| DMARC | `p=quarantine` |
| DKIM | **Published** — selectors **`202607r`** (RSA, canonical) + `202607e` (Ed25519); dig `@1.1.1.1` shows `v=DKIM1`; deliverability `ok: true` |
| Local caveat | Host **exim4** also listens on `127.0.0.1:25`; use public IP / pod for Stalwart checks |
| Gmail roundtrip | **Done (user confirmed 2026-07-26)** — Gmail ↔ `info@cronnecture.com` |

### Billing & pilot tenant

| Fact | Verified |
|------|----------|
| Platform readiness | Required **3/3** OK (`mail_server`, `smtp`, `registry`); Stripe + webhook secrets **ok** (optional); `auto_deploy` = 0 apps |
| Policy | Pay-needed **immediately**; site suspend only after **90 days** unpaid ([stripe-billing.md](../platform/stripe-billing.md)) |
| Pilot | **Historical** — rehearsal tenant `decinemaat` was **intentionally deleted** 2026-07-28 (job `3795`). No current live pilot. Empty CF zone `cronnecture.eu` may remain for reuse (do not delete as cleanup). |
| Portal Access (historical) | Was non-empty for the deleted pilot (`svenbraad.work@gmail.com`, `svenbraad@gmail.com`) — do not treat as a live allowlist |
| Pilot site (historical) | Was `https://cronnecture.eu` Access-gated for rehearsal; public paying clients need Access off |

### Planes (ops UI)

Welcome, Infrastructure (Fleet: Topology · Cluster · Nodes · **Self-heal** · Previews), Security, Business (mail/billing/docs), Automation, Settings, CRM, DMS — [control-plane.md](../platform/control-plane.md). Legacy Quick Ops → `/infrastructure/selfheal`.

### Already done (foundation)

- [x] 3-node fleet + Cloudflare edge (`node-tunnel` + per-client tunnels)
- [x] Control plane 2 replicas + staging + `make release`
- [x] Customer hub on **`client.cronnecture.com`** (not `insights.*`)
- [x] CRM lifecycle + delete dry-run ([RB-14](../runbooks/delete-client.md))
- [x] Stripe keys/webhook in readiness; pay-needed + 90-day suspend code path
- [x] Mail stack + Business Mail + `webmail.*` Access portal
- [x] R2 registry + R2 fleet-backup sync (marker fresh)
- [x] Marketing site via Traefik / `cf_public_sites`

---

## 2. Gaps / risks before first paying clients

| Pri | Gap | Why it matters | Evidence / notes |
|-----|-----|----------------|------------------|
| ~~P0~~ | ~~DKIM TXT missing~~ | — | **Closed 2026-07-26** — `202607r` / `202607e` published; see §6 |
| ~~P0~~ | ~~Gmail human roundtrip~~ | — | **Closed 2026-07-26** — user confirmed Gmail ↔ `info@` |
| **P0** | **Single compute ingress** | All client Traefik/sites on `worker-general-01` | V-04 [resilience.md](../architecture/resilience.md) — **tunnel origin now `127.0.0.1` (replica-ready); still need 2nd VPS** |
| ~~P0~~ | ~~Go-live rehearsal on throwaway~~ | — | **Closed 2026-07-26** — `mvp-probe-20260726` dry-run + delete job **completed** |
| ~~P1~~ | ~~Stripe enforcement drill~~ | — | **Closed 2026-07-26** — webhook ledger + dry-run reconcile + safe past_due UI observation (no site suspend); live Stripe `invoice.payment_failed` on real sub still optional |
| ~~P1~~ | ~~Portal Access allowlists~~ | — | **Closed 2026-07-26** — user set emails; API `access_emails` non-empty for `decinemaat` |
| ~~P1~~ | ~~Support / legal baseline~~ | — | **Closed** — Terms/Privacy in Business + issued to pilot Documents; marketing `/terms` `/privacy` **200**; support `support@cronnecture.com`; portal footer Terms/Privacy live |
| ~~P1~~ | ~~No push operator alerting~~ | — | **Closed** — `notify-ops.sh` on health/backup/watchdog → `info@` + `svenbraad.work@gmail.com` |
| ~~**P2**~~ | ~~Off-box vault/SSH clone~~ | — | **Closed 2026-07-26** — break-glass pack on R2 + `worker-general-01`; see §6 |
| **P2** | Single k3s server / etcd | Accept for MVP; break-glass [RB-11](../runbooks/emergency-management.md) |
| **P2** | Push-to-deploy off | Optional for first clients |
| **P2** | Rancher leftovers | `cattle-*` pods without portal DNS — cleanup later; do not advertise `rancher.*` |

### Explicit unknowns

- Stripe Dashboard webhook **delivery history** UI (DB ledger has events; Dashboard not opened here)
- Wazuh agent coverage / recent auto-block activity
- Whether first paying client site should be public (former pilot `cronnecture.eu` was Access-gated for rehearsal)

---

## 3. Ordered next actions (checkable)

1. [x] **Publish + verify DKIM** — `make mail-dns`; selectors `202607r` (RSA) + `202607e`; dig `@1.1.1.1` → `v=DKIM1`; deliverability `ok`.
2. [x] **Mail deliverability proof** — Internal + Port25: SPF/DKIM/iprev **pass**. **User confirmed:** Gmail ↔ `info@cronnecture.com`.
3. [x] **Throwaway client rehearsal** — `mvp-probe-20260726` (create/delete, no checkout). **Money path 2026-08-07:** `mvp-probe-20260807` → portal Access → Stripe **test** checkout link → paid €39.99 (PILOT50) → webhook → `billing_status=active` → delete job `8423` **completed**; throwaway cleaned (see §6a).
4. [x] **Billing failsafe drill** — Webhook ledger then had `customer.subscription.updated` (decinemaat active) + smoke `invoice.payment_failed`; dry-run reconcile `ok` (1 client, no suspend). Safe past_due observation (DB only, `past_due_since=now`): ops CRM billing + Business finance + customer-portal payload showed pay-needed / Manage billing (`can_manage_billing` + `pay_now`); site stayed `active`, `billing_maintenance_active=false`, no suspend. Reverted (Stripe dry-run sync also restores `active`). **Did not** suspend `decinemaat` during the drill.
5. [x] **Portal polish for humans** — Support `support@cronnecture.com` + pilot welcome blurb; Terms/Privacy in Business docs + issued on (then-live) pilot Documents; marketing `/terms` `/privacy` **200**; Access emails non-empty for that pilot; Stripe Customer Portal session URL OK. Footer Terms/Privacy links staged in `static/customer-portal` (ship on next `make release`).
6. [x] **Minimum alerting** — `notify-ops.sh` wired into health/backup/watchdog; cron `FLEET_NOTIFY_TO=info@cronnecture.com,svenbraad.work@gmail.com`; probe delivered to both.
7. [ ] **Second `compute_general`** — **Blocked on VPS** (no Hostinger/Hetzner API in vault). Tunnel ingress code is replica-HA ready (`127.0.0.1`). After purchase: Ops **Fleet → Nodes** (role `general`) or `make add-node IP=… CLASS=general`, then confirm `make cloudflare && make clients` if needed.
8. [x] **Off-box break-glass** — Pack stamp `20260726-222042` → R2 `break-glass/latest/` + `worker-general-01:/var/backups/cronnecture-break-glass/latest/`; weekly cron Sun 04:00 UTC; `make break-glass`.
9. [x] **Restore fire drill** — **passed** 2026-07-26 (6/6): stamp `20260726-031501`, emergency scratch restore, etcd snapshot, R2 manifest; DB skipped (Supabase PITR). Weekly Sun 05:30 UTC via host cron + Automation `restore_drill`; logs `/var/log/cronnecture-fleet-restore-drill.log` + `…/restore-drill.jsonl`; `make restore-drill`.
10. [x] **Portal footer legal links** — shipped via `make control-plane` 2026-07-26 (Terms/Privacy in customer-portal footer). Optional remaining: enable auto-deploy per app.

---

## 4. Definition of done — “MVP ready”

All must be true:

| # | Criterion | How to prove |
|---|-----------|--------------|
| 1 | Platform readiness required items green | `GET /api/platform/readiness` → `required_ok == required_total` |
| 2 | DKIM published + inbound/outbound mail pass spam filters once | Dig + Gmail roundtrip logged |
| 3 | Customer portal opens for **customer** email via Access OTP | Login on `client.cronnecture.com/client/portal/{uuid}` |
| 4 | Stripe checkout + webhook updates `billing_status` | Live or test mode with real webhook hits — **proved 2026-08-07** on `mvp-probe-20260807` (test mode; see §6a) |
| 5 | Pay-needed UI on failure; site stays up until 90 days | Ops + customer portal banners |
| 6 | Public site hostname serves app (Access policy intentional) | Browser / curl through Cloudflare |
| 7 | Delete dry-run lists Stripe/CF/k8s/portal/docs | `DELETE …?dry_run=true` or CRM dialog |
| 8 | Backup local **and** R2 sync marker fresh (&lt;48h) | `/var/backups/cronnecture-fleet/` + `.r2-last-sync` |
| 9 | Operator knows break-glass | [RB-11](../runbooks/emergency-management.md) + R2/worker pack + laptop download habit |
| 10 | Written offer: support path, SLA expectations (even if soft) | [commercial-offer.md](commercial-offer.md) + Business Terms/Privacy + portal Support |

**Not required for first client:** multi-server etcd, edge LB, Grafana product, Insights hostnames, full CONTROL_PLANE_ROADMAP phases, second compute (required before **volume**, not the absolute first tenant if risk accepted).

---

## 5. Platform vs client (do not confuse)

| Layer | Hosts / URLs | Audience |
|-------|--------------|----------|
| **Platform ops** | `ops.cronnecture.com` | Operators (Access + `/login`) |
| **Platform mail UI** | `ops…/webmail` + `webmail.cronnecture.com` | Operators |
| **Customer hub** | `client.cronnecture.com/client/portal/{uuid}` | Clients (Logto invite-only; Access off) |
| **Client sites** | Client zones → `client-{slug}` tunnel → Traefik | Public or Access per exposure |
| **SIEM** | `wazuh.cronnecture.com` | Operators |
| **Not a product** | `insights.*`, `portal.cronnecture.com`, `traefik.*` / `rancher.*` (disabled) | Absent or non-product |

---

## 6. Execution log — 2026-07-26 (MVP pass, no 2nd compute)

| Step | Result | Evidence / blocker |
|------|--------|--------------------|
| 1 DKIM | **done** | `make mail-dns`; dig `202607r._domainkey` + `202607e._domainkey`; MailDomain.dkim_selector=`202607r` |
| 2 Mail roundtrip | **done** | Port25 SPF/DKIM/iprev pass; **user confirmed** Gmail ↔ `info@cronnecture.com` |
| 3 Throwaway client | **done** | `mvp-probe-20260726` → delete job completed; ns briefly stuck Terminating on stale `ext.cattle.io` discovery (Rancher leftover) then finalized; `decinemaat` left untouched that day (deleted later — job `3795`, 2026-07-28) |
| 4 Stripe drill | **done** (safe) | Ledger: `customer.subscription.updated` + smoke `invoice.payment_failed`; dry-run reconcile ok; temporary DB `past_due` showed pay-needed in CRM/Business/customer portal payloads + Manage billing actions; reverted; site never maintenance |
| 5 Portal polish | **done** | Access emails API non-empty; support + welcome; Terms/Privacy on pilot Documents + marketing URLs; Stripe portal session OK; footer Terms/Privacy shipped (`make control-plane`) |
| 6 Alerting | **done** | notify → `info@cronnecture.com` + `svenbraad.work@gmail.com`; see [overview.md](../operations/overview.md) |
| 7 2nd compute | **skipped** | per instructions — **what's next when ready** |
| 8 Off-box break-glass | **done** | R2 `s3://cronnecture-fleet-backups/break-glass/latest/` + worker path; SSH fp `SHA256:KUMXpY2YGfB/TuyA4nNPwx4DHx5wbSYBg2T2vinVfvA`; secrets not in git |
| 9 Restore fire drill | **passed** | `make restore-drill` — onsite stamp, emergency inventory/registry, etcd snap, R2 manifest; see `/var/log/cronnecture-fleet/restore-drill.jsonl` |

### What's next

1. **Second `compute_general`** when ready (resilience / volume) — only remaining MVP-ordered infra gap intentionally skipped. After purchase: `make add-node IP=… CLASS=general` then `make cloudflare && make clients`.
2. **Manual:** download `break-glass-pack.tar.gz` once to encrypted laptop / password manager (refresh: `make break-glass`; weekly Sun 04:00 UTC).
3. **Decision:** first paying client site public vs Access-gated (former pilot `cronnecture.eu` was Access-gated for rehearsal).
4. Optional: enable **Deploy on push** per app (CRM → Apps → Configure). Use **Rebuild & deploy** / **Roll image** on the Apps tab for manual rolls.

### Client management upgrade (2026-07-27)

Shipped in control-plane: durable `provision_client` job, CRM health score + attention chips + kanban, Access-email gate on create, structured delete dry-run modal, go-live packs, New site CTA, portal invite, support tickets lite, app catalog packs (`static-vite`, `node-api-stub`, `supabase-ready`). See [RB-05](../runbooks/onboard-client.md).

### 6a. Money-path rehearsal — 2026-08-07 (Stripe test mode)

Full throwaway that the 2026-07-26 probe skipped (checkout/webhook):

| Step | Result | Evidence |
|------|--------|----------|
| Create `mvp-probe-20260807` | **pass** | client id `21`, portal `019fdc60-791f-701b-a874-cb79ae992f4b`, ns `client-mvp-probe-20260807` |
| Portal provision + Access | **pass** | portal status `active`; edge `302` → Cloudflare Access OTP for UUID path |
| Checkout link (test) | **pass** | `POST …/billing/checkout` → `checkout.stripe.com` `cs_test_…`, Pilot `PILOT50` auto-applied |
| Pay + webhook → `billing_status` | **pass** | Test sub `sub_1U1ngk…` invoice **€39.99** paid; ledger `customer.subscription.created` processed; CRM billing `active` / `payment_needed=false` / gates ok |
| Dry-run delete | **pass** | Listed Stripe sub+customer, portal UUID/Access, ns, CF tunnel name |
| Delete job | **pass** | job `8423` **completed**; Stripe sub canceled + customer deleted; CRM row gone |
| Namespace finalize | **pass** (after fix) | Stuck `Terminating` on stale Rancher `v1.ext.cattle.io` APIService (`ServiceNotFound`); deleted that APIService → ns **NotFound** |

**Ops note:** platform Stripe secret is `sk_test_…` (“Cronnecture sandbox”). No live charges. Remaining clients after cleanup: `autoklaver` only. Unit gates: `test_billing_gates.py` 7/7 + `test_delete_client_checklist.py` ok.

---

## Related

- [roadmap.md](../architecture/roadmap.md) · [control-plane-roadmap.md](../architecture/control-plane-roadmap.md)  
- [commercial-offer.md](commercial-offer.md) · [client-portal.md](../platform/client-portal.md) · [stripe-billing.md](../platform/stripe-billing.md) · [mail.md](../operations/mail.md)  
- [resilience.md](../architecture/resilience.md) · [RB-05](../runbooks/onboard-client.md) · [RB-14](../runbooks/delete-client.md)
