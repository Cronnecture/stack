# Legal pack (GDPR + Dutch law templates → PDF)

Operational legal documents for Cronnecture (Dutch sole-trader / BV-bound SaaS hosting).  
**Not a substitute for advocaat advice** — review before scaling live card charging.

Current on-disk pack: **v2026.08.27.1** (published **2026-08-27**, **effective immediately**, notice waived so public PDFs match VAT-on invoices).  
Public `/legal/*.pdf` and `/start` clickwrap serve this pack as **Current**. Prior pack **v2026.08.19.1** is archived.

## Versioning + prior notice

Each published pack has:

| Field | Meaning |
|-------|---------|
| `version` | Pack id (e.g. `2026.08.10.3`) |
| `published_at` | When the pack was issued / attached |
| `effective_at` | When it becomes binding (`>= published_at`) |
| `notice_days` | Default **14** for material ToS/Privacy changes (configurable in `version.json`) |
| `change_summary` | Short note for portal banner / email |

Flow:

1. Edit `services/control-plane/legal/*.md` and bump `version.json`.
2. Keep the previous pack under `legal/archive/{old-version}/` so clickwrap can keep serving it during the notice window.
3. Publish: `POST /api/business/legal/publish` (or deploy — `ensure_legal_library` seeds versions) → store PDFs → issue to all clients (**keeps previous versions**) → in-portal notice + email when SMTP is configured.
4. Until `effective_at`, portal shows **Current** (in force) and **Upcoming** (accepted/notice). After that, the new pack becomes Current and the old one moves to **Previous**.

## Documents

| Slug | Title | Public PDF |
|------|-------|------------|
| `terms-of-service` | Terms of Service | `/legal/terms-of-service.pdf` (effective) |
| `privacy-policy` | Privacy Policy | `/legal/privacy-policy.pdf` |
| `data-processing-agreement` | DPA | `/legal/data-processing-agreement.pdf` |
| `cookie-policy` | Cookie Policy | `/legal/cookie-policy.pdf` |
| `acceptable-use-policy` | Acceptable Use Policy | `/legal/acceptable-use-policy.pdf` |
| `service-description` | Service Description / Soft SLA | `/legal/service-description.pdf` |
| `refund-cancellation-policy` | Refund & Cancellation Policy | `/legal/refund-cancellation-policy.pdf` |

Upcoming (during notice): `/legal/{slug}/upcoming.pdf`.  
Host: `https://client.cronnecture.com`. Catalog: `GET /api/public/legal`.

Clickwrap on `/start` links to Terms + Privacy **effective** PDFs; keep those slugs stable.

## Portal UX

Documents → grouped sections:

- **Current (effective)** — in force now  
- **Upcoming** — published with prior notice, not yet effective  
- **Previous** — superseded versions kept for records  

Banner / Documents callout: “Updated Terms effective DATE — view changes”. View/Download remain PDF.

## Source → PDF

- Markdown templates: `services/control-plane/legal/*.md` + `version.json`
- Archives: `services/control-plane/legal/archive/{version}/`
- Renderer: `services/control-plane/app/legal_docs.py` (fpdf2 + markdown)
- Fonts: `services/control-plane/legal/fonts/DejaVuSans*.ttf`
- Issued to clients as **application/pdf** on create / self-serve / provision / publish (`issue_legal_pack_to_client`, `keep_previous=True`)
- Ops: `GET /api/business/legal/versions`, `POST /api/business/legal/publish`

## Identity (no placeholders)

Filled from platform settings when present (`make business-go-live`):

| Macro / field | Setting |
|---------------|---------|
| `LEGAL_NAME` / brand | `business_legal_name` (else **Cronnecture**) |
| `PROPRIETOR_NAME` | `business_proprietor_name` (else **S. J. Braad (Sven Braad)**) |
| `KVK` | `business_kvk` — **row omitted if empty** |
| `VAT` / BTW-id | `business_vat` — **row omitted if empty** |
| `OMZETBELASTINGNUMMER` | `business_omzetbelastingnummer` — **row omitted if empty** |
| `REGISTERED_ADDRESS` | `business_registered_address` — omitted if empty |
| Support / privacy | `ops_notify_email` / `business_privacy_email` (else `support@cronnecture.com`) |

Customer PDFs must not show `[pending…]`, Jinja `{{ }}`, or invented KVK/VAT.  
Do not narrate “pending registration” or “payment unlocks after KVK” in customer-facing docs — omit unset identity rows cleanly.

## Commercial posture in the pack

Production-grade hosting terms: invoices from Cronnecture’s own system; Stripe collects card/SEPA; 21% NL BTW; reverse-charge for qualifying EU B2B; soft SLA; 90-day payment-required window; versioned notice. Orders start through contact, email, or `/start`. The pack describes the live service only.

## Public vs internal

Public legal PDFs use **processor categories** (CDN/security, cloud hosting, database, payment processor, AI tools when used). Internal fleet inventory stays in ops docs — not in ToS/Privacy.

Soft SLA and 90-day pay-needed/suspend match [commercial-offer.md](../business/commercial-offer.md) / [stripe-billing.md](../platform/stripe-billing.md).

## Related

[go-live.md](../business/go-live.md) · [acquisition.md](../business/acquisition.md) · [client-portal.md](../platform/client-portal.md) · [backup.md](../operations/backup.md) · [security.md](../operations/security.md)
