# Business go-live (KVK + VAT → platform SoT)

**Status 2026-08-27:** KVK **`42140905`**, legal name **Cronnecture**, BTW-id and omzetbelastingnummer are stored in encrypted platform settings (not git). Stripe `charges_enabled` / `payouts_enabled` are **true**. Live keys and webhook are in ops. VAT is **on** (21% NL B2B). Public Checkout stays **off**.

Keep **`self_serve_live_payments=false`**. VAT-on and `make business-go-live` do **not** open public `/start` cards unless you pass `--enable-live-gate`. Close deals via invoice / Tikkie + email. Customer Portal configuration is created via API (`ensure_billing_portal_configuration`).

## What the script does

```bash
make business-go-live KVK=42140905 VAT=NL005528822B26 OMZETBELASTING=322284338B01 LEGAL_NAME='Cronnecture'
# or
./bin/fleet-business-go-live --kvk 42140905 --vat NL005528822B26 --omzetbelasting 322284338B01 --legal-name 'Cronnecture'
./bin/fleet-business-go-live --status
./bin/fleet-business-go-live --dry-run --kvk … --vat … --omzetbelasting …
```

Do **not** pass `ENABLE_LIVE_GATE=1` unless the founder asks for public card Checkout.

Writes (encrypted platform settings — **not** git):

| Key | Purpose |
|-----|---------|
| `business_kvk` | 8-digit KVK |
| `business_vat` | NL BTW-id (`NL#########B##`) |
| `business_omzetbelastingnummer` | Omzetbelastingnummer (`#########B##`) |
| `business_legal_name` | Legal name |
| `business_proprietor_name` | Natural person on quote/invoice From block (default **S. J. Braad (Sven Braad)**) |
| `business_registered_address` | Optional registered address (fills legal PDF placeholders) |
| `business_privacy_email` | Optional privacy contact (defaults to support@) |
| `business_go_live_at` | ISO timestamp |
| `business_go_live_notes` | JSON checklist / gate reason |
| `self_serve_live_payments` | **Unchanged** unless `--enable-live-gate` |

After writing identity, the script **syncs the legal library** and **re-issues PDF packs** to existing clients (NoordDrive included) so Terms/Privacy/DPA show real KVK / BTW-id / omzetbelastingnummer. Public URLs: `https://client.cronnecture.com/legal/terms-of-service.pdf` (and siblings under `/legal/`). Sources: `services/control-plane/legal/*.md` → PDF via `app/legal_docs.py`.

**Have a Dutch advocaat review the pack before live charging.** Do not invent KVK/VAT — only run this script with real registration numbers.

## Honest limits (Stripe Dashboard)

This fleet **cannot** automate:

1. Flipping Dashboard into **Live** mode  
2. Creating live API keys / webhook signing secrets  
3. Creating **yearly** prices (10× monthly) — paste `price_…` into Settings `stripe_pack_prices` `{pack}_annual` after one Dashboard click  
4. Enabling Stripe Tax (optional). In-app Tax Rate `nl_btw_21` (21% exclusive NL) is created via API when VAT is on file  
5. Public `/start` Checkout (`self_serve_live_payments`)

Paste BTW-id in Stripe account public details. Referral amount-off coupons (no percent) stay a Dashboard click.

## Handshake (NoordDrive)

€39.99/mo + €79.99 setup. First payment bank/Tikkie. Stripe auto-charge from **2026-09-14** at handshake price `standard_handshake` — never Pilot €49.99. Frozen until that date: `ensure_handshake_auto_billing` may create a subscription with `trial_end` = stripe_start. `mark_handshake_settled` / CRM Settle already call that path.

## Verification

```bash
make business-go-live-status
curl -sf https://client.cronnecture.com/api/public/self-serve/status | jq '.checkout'
curl -sf https://client.cronnecture.com/api/public/legal | jq '.version'
```

Checkout mode must stay **contact** while `self_serve_live_payments=false`.

Related: [stripe-billing.md](../platform/stripe-billing.md) · [pricing.md](pricing.md) · [commercial-offer.md](commercial-offer.md) · [acquisition.md](acquisition.md) · [company-nl.md](company-nl.md)
