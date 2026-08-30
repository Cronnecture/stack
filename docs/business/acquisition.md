# Acquisition engine (solo founder)

**Primary bet:** inbound brand on [cronnecture.com](https://cronnecture.com/) → **contact / email** (`#contact` or `support@cronnecture.com`) → invoice (or Tikkie in ops/email only) → warm `contact_leads` nurture in ops CRM. No public Stripe Checkout (`self_serve_live_payments` stays false); no cold-email blasts, no ad spend, no fake social proof.

**Public marketing tone:** restore brand hero (“Infrastructure that stays secure.” / NL equivalent). Public prices are the catalog (Website €49.99 / Webshop €119.99 / Portal €129.99) — no list/Pilot strikethrough. Do **not** put Tikkie or “startup until registered” language on the public site.

**Ops panel:** [CRM → Inbound](https://ops.cronnecture.com/crm/pipeline) (unified leads inbox + acquisition checklist; aliases `/crm/acquisition`, `/business/leads`). API: `GET /api/crm/acquisition`, `GET /api/crm/pipeline`.

---

## Funnel

```
cronnecture.com (brand + Contact CTA)
        │
        ├─ primary → #contact / mailto:support@  → contact_leads
        │                 → ops email (poller ~2 min)
        │                 → CRM Inbound pipeline → Prospects / Convert
        │                 → invoice or Tikkie → provision
        │
        └─ /start (optional deep-link) → contact / waitlist UI
              (Stripe Checkout only when self_serve_live_payments=true)
```

**Keep `self_serve_live_payments=false` until you want public card Checkout.** KVK, BTW-id, and Stripe `charges_enabled` are already true. Live keys are in ops. Public marketing must not push Stripe Checkout yet.

---

## Go-live flip (optional self-serve after KVK)

1. Register KVK/VAT/omzetbelastingnummer; run `make business-go-live KVK=… VAT=… OMZETBELASTING=… LEGAL_NAME=…` — see [go-live.md](go-live.md). That script does **not** open public Checkout.
2. In Stripe Dashboard: confirm live keys + webhook `whsec` + Customer Portal activated. Catalog prices already match cronnecture.com (do not reuse `PILOT30PACKS`).
3. Paste `sk_live_…` + live webhook secret into ops **Settings → Billing**.
4. Set **`self_serve_live_payments=true`** only when ready to offer public card Checkout.
5. Verify: `curl -sf https://client.cronnecture.com/api/public/self-serve/status | jq '.checkout'`
6. Optionally re-enable marketing CTAs to `/start` — default stays contact/inbound until then.

Until that flip, close deals with **invoice / Tikkie** and human email.

---

## Weekly rhythm (founder)

Until public Checkout is intentionally opened:

1. Open **CRM → Acquisition** — clear new inbound within 24h (promote or convert).
2. Reply to every contact form / `support@` lead personally (`info@` or `support@`).
3. Share one honest NL touch (referral / local network) — point people to `#contact` or `support@`.
4. Send invoice or Tikkie; provision after payment clears.
5. Leave `self_serve_live_payments=false` — do not enable live Stripe on the public face.

After KVK (optional):

1. Flip live payments (above) if you want self-serve Checkout as a second path.
2. Same inbound SLA; invoice / Tikkie remain valid for migrate / Complete / custom deals.
3. Optional: light call-first on T0 A prospects only ([lead-generation.md](lead-generation.md)) — still human-approved email.

---

## Surfaces

| Surface | Role |
|---------|------|
| Marketing site | Brand + **primary CTA contact / email** |
| `/start` | Contact / waitlist until live payments; Checkout only when flag on |
| `contact_leads` | Warm inbound store (Supabase) |
| Leads notify poller | Emails `ops_notify_email` on new rows (**To:** `info@cronnecture.com`) |
| CRM → Pipeline | Act on inbound |
| CRM → Acquisition | Checklist + weekly + status |
| Prospects / Call list | Secondary outbound (not the primary engine) |

---

## Marketing promote

Site source: GitHub `Bolt2841/cronnecture`. Apex roll via preview **Promote website** (`POST /api/previews/{id}/promote-website`) — persists image in `platform_sites.yml`. Serves `cronnecture.com` (EN) and `cronnecture.nl` (NL). See [previews.md](../platform/previews.md).

Related: [pricing.md](pricing.md) · [commercial-offer.md](commercial-offer.md) · [lead-generation.md](lead-generation.md) · [stripe-billing.md](../platform/stripe-billing.md) · [overview.md](../legal/overview.md)
