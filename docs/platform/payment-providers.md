# Client PSP connect (Mollie / Stripe Connect)

Clients connect **their own** Mollie or Stripe accounts in the customer portal, then ops (or the client) links a connected account to specific apps. This is **not** Cronnecture platform billing and does **not** enable public Checkout (`self_serve_live_payments` stays off until you ask for public cards).

## URLs

| Surface | URL |
|---------|-----|
| Unified inbound leads | https://ops.cronnecture.com/crm/pipeline (alias: `/business/leads`, `/crm/acquisition`) |
| Client portal Payments | `https://client.cronnecture.com/client/portal/{uuid}/payments` |
| **Client checkout (end-customers)** | `https://client.cronnecture.com/pay/{client-slug}` |
| Ops client → Portal tab | CRM → client → Portal → **Client PSP** + **Client checkout branding** |
| Platform keys | Ops → Settings → Integrations → **Client PSP** |

## Client checkout storefront

Hosted on the existing `client.cronnecture.com` tunnel (no extra DNS): public `/pay/{slug}` + `/api/public/checkout/{slug}*`.

- **Who pays:** the client’s end-customers (not Cronnecture Pilot billing).
- **Who receives:** the client’s connected Stripe Connect account or Mollie org (linked under Payments).
- **Branding:** logo, colors, business name, support email, headline/subtext, product defaults, success/cancel URLs, field visibility — editable in the **client portal → Payments → Checkout branding**, and also by ops under CRM → Portal → **Client checkout branding**.
- **Preview without PSP:** page renders branded; Pay CTA shows **Connect PSP to go live** until a connected/live account is available (and optionally linked to an app).
- **Live:** `POST /api/public/checkout/{slug}/session` creates a Stripe Checkout Session (`Stripe-Account` header) or Mollie payment and redirects the buyer.

Logo files live under the client-documents volume (`{client_id}/checkout/logo.*`). Settings are stored in `client_portals.extensions_json.checkout` (no secrets).

## Keys to add in Ops Settings → Integrations

| Setting key | Purpose |
|-------------|---------|
| `stripe_connect_secret_key` | Stripe platform secret for Connect Account Links (optional; falls back to billing `stripe_secret_key`) |
| `stripe_connect_webhook_secret` | Webhook signing for connected-account events (optional until webhooks wired) |

**Stripe Connect prerequisite:** a platform `sk_test_` / `sk_live_` key is not enough. Enable Connect in the Stripe Dashboard ([Connect](https://dashboard.stripe.com/connect)) for that mode, or Start Stripe Connect returns an actionable JSON error (`stripe_connect_not_enabled`) instead of a bare 502.
| `mollie_client_id` | Mollie OAuth app client ID |
| `mollie_client_secret` | Mollie OAuth app client secret |
| `mollie_partner_api_key` | Optional partner/org key for status probes without full OAuth |
| `mollie_redirect_uri` | Default `https://ops.cronnecture.com/api/psp/mollie/callback` |

No secrets belong in git — enter them only in the encrypted Settings store.

## Client how-to

1. Open **Payments** in the customer portal.
2. Click **Connect Stripe** or **Connect Mollie** (buttons enable when platform keys are set).
3. Complete KVK / identity onboarding at the PSP.
4. Return to Payments → **Refresh** until status is `connected` / `live`.
5. Under **Link to apps**, pick an app + connected account → **Link**.

## Ops app-link flow

1. CRM → client → **Portal** → Client PSP panel.
2. Or start onboarding from ops (**Start Stripe Connect** / **Start Mollie**).
3. **Link to app**: select app + PSP account → stores `STRIPE_CONNECTED_ACCOUNT_ID` or `MOLLIE_ORG_ID` (+ `PSP_PROVIDER`, `PSP_STATUS`) on the app `env_json` for deploy awareness. Tokens stay Fernet-encrypted on `client_psp_accounts`.

## Data model

- `client_psp_accounts` — per-client provider row (status, external id, encrypted tokens)
- `app_psp_links` — app ↔ PSP account (purpose: `payments`)

## Safety

- Do **not** set `self_serve_live_payments=true` for this feature.
- Platform Stripe subscription billing (`stripe_secret_key` under Billing) remains separate.
