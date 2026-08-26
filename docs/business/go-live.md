# Business go-live (KVK + VAT → platform SoT + Stripe live gate)

**Status 2026-08-19:** KVK **`42140905`** and legal name **Cronnecture** are on file. VAT is **deferred** (not required yet). Stripe `charges_enabled` / `payouts_enabled` are **true**. Live keys and webhook are in ops. Public Checkout stays **off**.  
Keep **`self_serve_live_payments=false`**. Do **not** run the full go-live script — it would flip self-serve because `sk_live_` is already configured, and it also requires a VAT id we do not have. `/start` shows contact / invoice guidance. Close deals via invoice / Tikkie + email. Activate Customer Portal in the Stripe Dashboard (see [stripe-billing.md](../platform/stripe-billing.md)) so ops/portal manage/pay works.

## What the script does

```bash
make business-go-live KVK=12345678 VAT=NL123456789B01 LEGAL_NAME='Cronnecture'
# or
./bin/fleet-business-go-live --kvk 12345678 --vat NL123456789B01 --legal-name 'Cronnecture'
./bin/fleet-business-go-live --status
./bin/fleet-business-go-live --dry-run --kvk … --vat …
```

Writes (encrypted platform settings — **not** git):

| Key | Purpose |
|-----|---------|
| `business_kvk` | 8-digit KVK |
| `business_vat` | NL BTW id (`NL#########B##`) |
| `business_legal_name` | Legal name |
| `business_proprietor_name` | Natural person on quote/invoice From block (default **S. J. Braad (Sven Braad)**) |
| `business_registered_address` | Optional registered address (fills legal PDF placeholders) |
| `business_privacy_email` | Optional privacy contact (defaults to support@) |
| `business_go_live_at` | ISO timestamp |
| `business_go_live_notes` | JSON checklist / gate reason |
| `self_serve_live_payments` | Set **`true` only when** Settings already has `sk_live_…` |

After writing identity, the script **syncs the legal library** and **re-issues PDF packs** to existing clients so Terms/Privacy/DPA show real KVK/VAT (not placeholders). Public URLs: `https://client.cronnecture.com/legal/terms-of-service.pdf` (and siblings under `/legal/`). Sources: `services/control-plane/legal/*.md` → PDF via `app/legal_docs.py`.

**Have a Dutch advocaat review the pack before live charging.** Do not invent KVK/VAT — only run this script with real registration numbers.

## Honest limits (Stripe Dashboard)

This fleet **cannot** automate:

1. Flipping Dashboard into **Live** mode  
2. Creating live API keys / webhook signing secrets  
3. Enabling Customer Portal in Live mode (required click — no API config exists yet)  
4. Adding a VAT id we do not have  

Live keys, identity verification, and the 2026-08-19 catalog already exist. Confirm `sk_live_…` + live `whsec_…` in Settings, activate Customer Portal, then leave `self_serve_live_payments=false` until you want public card Checkout.

## Verification

```bash
make business-go-live-status
curl -sf https://client.cronnecture.com/api/public/self-serve/status | jq '.checkout'
```

**Acquisition scale switch:** `self_serve_live_payments=true` is what turns public `/start` into real Checkout. KVK and `charges_enabled` are already true; VAT is still deferred. Flip the flag only when you want public cards. Funnel + weekly rhythm: [acquisition.md](acquisition.md). Ops panel: CRM → Acquisition.

Related: [stripe-billing.md](../platform/stripe-billing.md) · [pricing.md](pricing.md) · [commercial-offer.md](commercial-offer.md) · [acquisition.md](acquisition.md)
