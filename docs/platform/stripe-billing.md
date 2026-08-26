# Stripe billing — failsafe pay-needed + 90-day suspend

Per-client subscriptions via Stripe. Keys live in **ops → Business / Settings → Billing** (encrypted platform settings), not in git or Ansible vaults.

**Live check (2026-08-21):** ops has `sk_live_` + webhook `https://ops.cronnecture.com/api/webhooks/stripe` (`we_1U5oabI1DriezaayH38kd3qR`). Stripe account **Cronnecture** `acct_1ThxGgI1Driezaay` (NL, EUR). `charges_enabled` and `payouts_enabled` are **on**. KVK `42140905` is on file; VAT is deferred. `self_serve_live_payments` stays **false** — do not flip it with `make business-go-live` (that script also requires a VAT id). Policy: pay-needed **immediately**; site suspend only after **90 days** unpaid. **Customer Portal:** `create_billing_portal_link` creates/reuses a live `billing_portal` configuration if none exists, so ops/portal “manage / pay” no longer depends on a Dashboard Activate click.

## Policy (locked)

| Condition | Ops / customer UI | Public site |
|-----------|-------------------|-------------|
| Payment failed, `past_due`, `unpaid`, incomplete checkout, open failed invoice | **Pay-needed immediately** (loud banners + pay CTAs) | Stays online |
| Continuous non-payment ≥ **90 days** (`billing_past_due_since`) | Suspend eligible | Maintenance page + workloads scaled to 0 |
| Paid / subscription `active` again | Clear banners | Restore tunnel + resume workloads |
| Platform client `cronnecture` | Never billed / never suspended | N/A |

`billing_past_due_since` is the earliest of: first `invoice.payment_failed`, Stripe open-invoice `due_date`/`created`, or when status entered `past_due`/`unpaid`/`incomplete`.

## Flow

1. **Checkout / Customer Portal** — ops copies a pay link or opens the client’s Stripe portal; customer pays on Stripe-hosted pages.
2. **Webhooks** (`POST https://ops.{zone}/api/webhooks/stripe`) update DB idempotently (`stripe_webhook_events`).
3. **Scheduler** (automation: *Stripe billing reconcile every 30 min*) pulls Stripe → DB if a webhook was missed, then applies warn vs 90-day suspend.
4. **Suspend** routes the client’s tunnel hostnames to the maintenance Worker (or Traefik overlay fallback) and scales app deployments to 0.
5. **Restore** on `invoice.paid` / healthy subscription: rebuild tunnel, clear maintenance, resume workloads.

## Self-serve Website checkout

**Default public path (pre-KVK):** contact / email → invoice or Tikkie → ops provision. See [acquisition.md](../business/acquisition.md).

Optional self-serve path (only when `self_serve_live_payments=true`):

1. Buyer opens **`https://client.cronnecture.com/start`** (also `/api/public/start` on ops — Access-bypassed API).
2. Form (company, slug, portal email + Terms clickwrap) → `POST /api/public/self-serve/signup` → Stripe Checkout **subscription + required setup**.
3. On `checkout.session.completed` with `metadata.self_serve=true`: auto-create client + portal Access + **legal PDF pack** (Terms/Privacy/DPA/…) + platform-subdomain site — TLS-safe `sites-{slug}.cronnecture.com` until a dedicated CF zone for `sites.cronnecture.com` exists (then `{slug}.sites.cronnecture.com`) — + notify founder. Public PDFs: `https://client.cronnecture.com/legal/*.pdf` — see [overview.md](../legal/overview.md).
4. Success URL polls `/api/public/self-serve/session/{id}` → customer portal (Manage billing).
5. **Custom domain upgrade:** portal `POST …/api/domain-request` stores `custom_domain_request` (pending) + support ticket; CRM shows a **Domain request** attention chip; ops adds the customer zone via [RB-05](../runbooks/onboard-client.md). Day-1 signup never requires a custom domain.

While the live-payments flag is **false**, `/start` and the signup API return **contact** mode (no public Checkout — including test keys).

### KVK / VAT gate (live payments)

**Keep `self_serve_live_payments=false` until you intentionally open public card checkout.** KVK and `charges_enabled` are already true. VAT is still deferred. Do not invent a VAT number. Live keys alone are not enough.

| Setting | Default | Meaning |
|---------|---------|---------|
| `self_serve_enabled` | true | Public `/start` page on/off |
| `self_serve_live_payments` | **false** | When false, public Checkout is blocked (contact / invoice / Tikkie). When true, requires `sk_live_…` |
| `self_serve_max_tenants` | 8 | Concurrent self-serve tenant cap |
| `self_serve_sites_suffix` | `sites.cronnecture.com` | Day-1 suffix; host is `sites-{slug}.cronnecture.com` (apex Universal SSL) until `self_serve_sites_zone_id` is set, then `{slug}.sites…` |
| `self_serve_sites_zone_id` | (auto) | Cloudflare zone id for nested `*.sites…` TLS — requires dashboard “Add site” or token with `zone.create` |

Do **not** invent VAT numbers or enable live charging before registration. Contact / invoice / Tikkie remain the default close path.

### Recording KVK / VAT (Aug 18 go-live)

```bash
make business-go-live KVK=……… VAT=NL……… LEGAL_NAME='…'
make business-go-live-status
```

Stores registration ids in platform settings and sets `self_serve_live_payments=true` **only when** a `sk_live_` key is already configured. Stripe Dashboard live-mode clicks stay manual — see [go-live.md](../business/go-live.md).

## Stripe Dashboard setup (required)

In [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks):

1. **Endpoint URL:** `https://ops.cronnecture.com/api/webhooks/stripe`  
   (or your platform zone’s ops host)
2. **Events to send:**
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
   - `invoice.paid`
3. Copy the **Signing secret** (`whsec_…`) into ops → **Settings → Billing → Webhook signing secret**.
4. Add the **Secret key** (`sk_live_…` or `sk_test_…`) and optional **Default price ID** (`price_…`).
5. Live catalog is the public page (no list/Pilot split). Leave `stripe_pilot_coupon_id` empty. Do **not** use `PILOT30PACKS`.
6. Enable **Customer Portal** so ops/portal “manage / pay” sessions work. Stripe MCP cannot create this object. In [Dashboard → Settings → Billing → Customer portal](https://dashboard.stripe.com/acct_1ThxGgI1Driezaay/settings/billing/portal) (Live mode):
   1. Click **Activate** / **Save** to create the default live configuration.
   2. Turn **on**: invoice history, payment-method update, customer update (email, address, name, tax ID).
   3. Subscription cancel: **at period end** only.
   4. Leave **subscription plan switching off** (or limit it to public Website / Webshop / Portal prices). Do **not** let customers switch onto or off the NoordDrive handshake price `price_1U4SVFI1DriezaayQ4Q3XNQu`.
   5. Default return URL: `https://client.cronnecture.com`.
   6. Privacy / Terms: `https://client.cronnecture.com/legal/privacy-policy.pdf` and `https://client.cronnecture.com/legal/terms-of-service.pdf`.

Public mixes (EUR excl. BTW): Website €49.99 + €899 build · Webshop €119.99 + €1,699 · Portal from €4,999 + €129.99/mo. Moves €0 (12-month term). Handshake €39.99/mo + €79.99 setup is not public. See [pricing.md](../business/pricing.md).

### If keys are missing

Do **not** invent secrets. The operator must provide:

| Setting | Where |
|---------|--------|
| `stripe_secret_key` | Stripe Dashboard → Developers → API keys |
| `stripe_webhook_secret` | Webhook endpoint signing secret after creating the endpoint above |
| `stripe_default_price` (optional) | Product catalog → default pay-link price. Live default is **Website €49.99** (`price_1U5rCpI1DriezaayXjS2SJHU`), never handshake |
| `stripe_pilot_coupon_id` | Leave **empty**. Old coupon `PILOT30PACKS` must not be used |
| `stripe_pilot_promo_code` | Display/manual code if you still allow promo entry |
| `stripe_pack_prices` | JSON map of pack → `price_…` (see live table below) |
| `stripe_addon_prices` | JSON one-time prices: move website, builds, domain, extra hour, handshake setup |

**Live catalog (2026-08-21, `acct_1ThxGgI1Driezaay`):**

| Product | Care / mo | Build | Move |
|---------|----------:|------:|-----:|
| Website | €49.99 `price_1U5rCpI1DriezaayXjS2SJHU` | €899 `price_1U5wEAI1Driezaay1sdtNEEf` | €0 `price_1U5wEAI1DriezaayhykpUbQR` |
| Webshop (add-on) | €70 `price_1U6oG7I1Driezaay7lRaaQVE` | €800 `price_1U6oG7I1Driezaayc0NcJl2d` | €0 `price_1U5wEMI1Driezaay73Cgvr5s` |
| CMS / CRM (add-on) | €40 `price_1U5rCrI1DriezaayyYMzAhTv` | €3,250 `price_1U5wEPI1DriezaayCgPmBXag` | €0 `price_1U5wEPI1DriezaayjvEo8ASn` |
| Website + webshop | €119.99 `price_1U6oFxI1DriezaayK1swMVhd` | €1,699 `price_1U6oFxI1DriezaayMGOs98kM` | €0 `price_1U5wEAI1Driezaayr3up1ncp` |
| Website + CMS / CRM | €89.99 `price_1U5rCxI1Driezaay93kQQnjs` | €4,149 `price_1U5wEMI1DriezaayBlR6da31` | €0 `price_1U5wEMI1DriezaayKV9RQAIb` |
| Website + webshop + CMS / CRM | €129.99 `price_1U5rD0I1Driezaay23Ku4W8m` | from €4,999 `price_1U5wEAI1DriezaayeN8ut3vZ` | €0 `price_1U5wEMI1Driezaaya4L7RWAR` |
| Extras | — | domain €49.99 `price_1U5rD2I1DriezaaybstSgPP7` · hour €90 `price_1U5wEeI1DriezaayFeF06KmV` · 2.5h €225 / 5h €400 / 10h €750 | — |
| Handshake (NoordDrive) | €39.99 `price_1U4SVFI1DriezaayQ4Q3XNQu` | setup €79.99 `price_1U5rD3I1Driezaayd8ogGl7s` | — |

Tax codes: Website Hosting `txcd_10701100` on website mixes / extras / handshake. SaaS business `txcd_10103001` on Webshop and CMS/CRM modules. Archived leftovers stay archived.

**Sandbox leftovers** (`sk_test_` only, in `packs.yml` `stripe_test_prices`): old Standard/Business/Complete list+Pilot IDs. Do not paste those into live Settings.

## Ops APIs

| Endpoint | Purpose |
|----------|---------|
| `GET /api/clients/{id}/billing` | Status + `payment_needed`, `past_due_days`, grace fields |
| `POST /api/clients/{id}/billing/checkout` | Client pay / checkout link |
| `POST /api/clients/{id}/billing/portal` | Stripe Customer Portal session |
| `POST /api/clients/{id}/billing/refresh` | Pull one subscription from Stripe |
| `POST /api/billing/reconcile?dry_run=true` | Sync + evaluate gates without suspending |
| `POST /api/billing/reconcile` | Queue `billing_enforce` platform task |
| `POST /api/webhooks/stripe` | Stripe → control-plane |
| `GET /api/public/self-serve/status` | Public Pilot availability / waitlist gate |
| `POST /api/public/self-serve/signup` | Public signup → Checkout (or waitlist) |
| `GET /api/public/self-serve/session/{id}` | Success-page poll → portal URL |

## Related

- [maintenance.md](../operations/maintenance.md) — edge maintenance Worker used for billing holds
- [client-portal.md](client-portal.md) — customer hub billing UI
- [pricing.md](../business/pricing.md) · [commercial-offer.md](../business/commercial-offer.md) — KVK/VAT unlock ~2026-08-18
