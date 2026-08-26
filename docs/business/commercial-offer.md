# Cronnecture — first-client commercial package

Founder-facing offer for early paying clients. Aligns with [stripe-billing.md](../platform/stripe-billing.md), [client-portal.md](../platform/client-portal.md), [backup.md](../operations/backup.md), [first-clients.md](first-clients.md), and Business **Terms of Service** / **Privacy Policy** (issued to each client’s portal Documents).

**Not a legal contract.** Legal text lives in Stripe + Business docs. **Current amounts** are in [pricing.md](pricing.md) (subject to change). This page is the commercial posture you can quote honestly.

---

## Package name (internal)

**Managed site** (CRM go-live ids unchanged: `site_only` / `site_supabase` / `site_billing` / `full`).

**Public names** (marketing only): **The website** → `site` / `site_only` · **The webshop** → `site_billing` · **The CMS** → `full`. Ops-only: **Website + CMS / CRM** → `site_supabase` (never a bare database).

Positioning matches marketing: managed websites / webshops / CMS-CRM — not generic shared hosting.

### Pricing (excl. BTW) — see [pricing.md](pricing.md)

| Mix | Pack id | Monthly | New build | Move |
|-----|---------|--------:|----------:|-----:|
| **Website** | `site` | **€49.99** | **€899** | **€0** |
| **Website + webshop** | `site_billing` | **€119.99** | **€1,699** | **€0** |
| **Website + CMS / CRM** | `site_supabase` | **€89.99** | **€4,149** | **€0** |
| **Website + webshop + CMS / CRM** | `full` | **€129.99** | **from €4,999** | **€0** |

Handshake (NoordDrive only): setup **€79.99** + monthly **€39.99**. Not a public SKU.

Above cheap shared hosting (€3–10); below agency hour-retainers (€500+). Quote **excl. 21% BTW** for NL B2B. Do not use a percent Stripe coupon. Full sheet: [pricing.md](pricing.md). Marketing: [cronnecture.com/pricing](https://cronnecture.com/pricing).

---

## What’s included

| Area | Included |
|------|----------|
| **Hosting** | Client namespace on the Cronnecture k3s fleet; containerized app (static / Node / Supabase-ready templates or customer repo) |
| **Edge & tunnel** | Cloudflare proxied DNS + dedicated `client-{slug}` tunnel; origin not exposed on the public internet |
| **Customer portal** | Invite-only hub at `https://client.cronnecture.com/client/portal/{uuid}` — account, billing/invoices, documents, status, support form |
| **Billing** | Stripe subscription (checkout / Customer Portal). **Pay-needed banners immediately** on failed/overdue payment; **site stays up for 90 days** unpaid, then maintenance + workloads scaled to 0 ([stripe-billing.md](../platform/stripe-billing.md)) |
| **Legal pack** | Versioned **PDFs** (Terms, Privacy, DPA, Cookie, AUP, Soft SLA, Refund) auto-issued into portal Documents at onboard; public `/legal/*.pdf` on the portal host; identity from `business-go-live` / platform SoT |
| **Backups / restore posture** | Daily fleet + etcd backups; off-site R2 sync; weekly non-destructive restore fire drill; operator break-glass pack (platform-level — not a per-client “download your VM” product) |
| **Support channel** | `support@cronnecture.com` and in-portal Support message form |
| **Monitoring (baseline)** | Platform health/watchdog + client status page (portal `/status`); edge protection via Cloudflare |

---

## Soft SLA (solo founder — honest)

This is a **best-effort service level**, not a contractual uptime guarantee. No 24/7 NOC, no fake “99.99%”, no SOC2/ISO claims unless separately certified.

| Target | Commitment |
|--------|------------|
| **Business hours** | Mon–Fri **09:00–18:00 Europe/Amsterdam** (CET/CEST), excluding public holidays in NL |
| **Normal requests** (questions, content deploys, non-urgent changes) | First response within **1 business day** |
| **Degraded / down** (site unreachable, tunnel/ingress failure, billing/portal login broken) | Best-effort **same business day** once reported; after-hours triage when the founder sees the alert — not a promised night/weekend desk |
| **Planned maintenance** | Prefer off-peak; short edge maintenance page when needed ([maintenance.md](../operations/maintenance.md)) |
| **Uptime** | Aim for high availability with Cloudflare + fleet backups; **no numerical SLA** until multi-node client ingress is in place (see MVP gap: single `compute_general`) |

Escalate via portal Support or `support@cronnecture.com`. Critical production issues: put **URGENT** in the subject and the client hostname.

---

## What’s not included / extras

Quote these separately (time & materials or a fixed add-on):

- Custom application development beyond deploy/configure of agreed stack
- Design / copywriting / SEO campaigns
- Multi-region HA, dedicated nodes, or second-compute guarantees (fleet is growing)
- 24/7 on-call, phone support, or dedicated Slack/Teams channel (unless agreed)
- Customer-owned AWS/GCP accounts or bring-your-own Kubernetes
- PCI / HIPAA / formal compliance attestations
- Guaranteed RPO/RTO numbers for *customer* app data (platform drills ≠ per-tenant restore SLA; Supabase client DBs use provider PITR when enabled)
- Unlimited redesigns or open-ended “agency retainer” scope

---

## Access-gated vs public site (recommendation)

| Surface | Default for paying clients | Notes |
|---------|---------------------------|--------|
| **Customer portal** | Always **Authentik OIDC** (invite-only; cookie `cp_logto_session`) | Never advertise as public. Access is **off** on `client.cronnecture.com` (`skip_access`) so Stripe return URLs do not 1043 |
| **Production marketing / shop hostname** | **Public** (Access **off**) | Buyers expect an open site; CF proxy + tunnel still protect the origin |
| **Staging, admin UIs, pre-launch** | **Access-gated** | Same pattern as the former rehearsal site on `cronnecture.eu` |

Former pilot `decinemaat` / `cronnecture.eu` was Access-gated for rehearsal (tenant deleted 2026-07-28, job `3795`) — **do not** treat that as the default for a public customer launch. Set exposure explicitly at go-live (CRM / Cloudflare).

---

## How a buyer starts (CTA path)

### A) Contact + invoice / Tikkie (preferred until live Stripe)

1. **Contact** — [cronnecture.com/#contact](https://cronnecture.com/#contact) or `support@cronnecture.com` (marketing primary CTA). Funnel: [acquisition.md](acquisition.md).
2. Agree pack + catalog price → send **invoice** or **Tikkie** (move setup is €0 / 12-month term; new builds are quoted).
3. Ops provisions tenant + portal + bootstrap site on **`{slug}.sites.cronnecture.com`** (or flat `sites-{slug}.cronnecture.com` until the dedicated sites zone is ready).
4. Buyer gets portal Access + welcome (billing / documents / support).
5. **Custom domain upgrade (optional)** — portal **Account → Connect custom domain** (or Support) → ops cutover ([RB-05](../runbooks/onboard-client.md)).

**Website care includes** platform subdomain hosting. **Custom domain is an upgrade** (ops-assisted cutover; not required on day 1).

**Public Stripe Checkout stays off** while `self_serve_live_payments=false`. `/start` shows contact UI only. After you flip that flag (KVK + `charges_enabled` are already true; VAT still deferred), optional path: `/start` → Stripe Checkout → webhook provision (`/api/public/self-serve/*`).

### B) Migrate / Business / Complete (same human path)

1. **Contact** — [cronnecture.com/#contact](https://cronnecture.com/#contact) or email `support@cronnecture.com` / `info@cronnecture.com`
2. **Scope reply** — founder confirms pack, domain, Access emails, public vs gated
3. **Provision** — CRM New client wizard → portal invite ([RB-05](../runbooks/onboard-client.md))
4. **Pay** — invoice / Tikkie (or Stripe Checkout / Customer Portal when live billing is enabled)
5. **Ongoing** — portal Documents (Terms/Privacy), Support form, status page

Do **not** invent `insights.*` or `portal.cronnecture.com` URLs. Canonical hub: `client.cronnecture.com/client/portal/{uuid}`.

**Ops copy-paste for checkout (manual path):** CRM → client → Billing → create checkout / copy pay link (requires Stripe keys + default price in Business → Settings).

---

## Billing posture (must match product)

Say this the same way every time:

- Payment problems → **pay-needed immediately** in ops + customer portal (loud CTAs).
- Site remains online during a **90-day** grace window of continuous non-payment.
- After 90 days unpaid → maintenance page + workloads suspended until paid.
- Platform tenant `cronnecture` is never billed/suspended.
- Public catalog: Website **€49.99** / Webshop **€119.99** / Portal **€129.99** per month excl. BTW. Handshake NoordDrive stays €39.99.

---

## Pilot / referral ask (email blurb)

Use after ~2–4 weeks of a stable pilot, or when asking for the first case study:

```
Subject: Quick ask — referral / short case note

Hi {Name},

Thanks again for running with Cronnecture on {site}. Glad things have been stable.

I’m keeping the early client circle small. Two asks if you’re happy with the setup:

1) If someone in your network needs a managed site/stack with clear ops and security-minded defaults, an intro to support@cronnecture.com (or me) would mean a lot.
2) If you’re open to it, a short quote (2–3 sentences) I can use as a case note — what you needed and how it’s going. No pressure; happy to draft something you can edit.

Either way, portal Support or this thread is the right channel for anything you need.

Thanks,
Sven
Cronnecture
```

---

## Founder checklist before quoting

- [ ] Business Terms + Privacy are the real text (not seed placeholders) and match what you say verbally
- [ ] Stripe prices match [pricing.md](pricing.md) public amounts; default price is Website €49.99 (`price_1U5rCpI1DriezaayXjS2SJHU`), never handshake
- [ ] Customer Portal activated in Stripe Live so manage/pay works
- [ ] Portal Access emails collected before invite
- [ ] Public vs Access decided for the **site** hostname
- [ ] Soft SLA above is what you promise (not more)
- [ ] Client understands pay-needed immediate / suspend at 90 days
- [ ] Setup stated explicitly excl. BTW (public move €0 / 12-month term; new build quoted; handshake €79.99)

---

## Related

- [pricing.md](pricing.md) — public catalog (no list/Pilot split)
- [lead-generation.md](lead-generation.md) — ICP / outreach plan (plan only)
- [first-clients.md](first-clients.md) — go-live DoD (item 10: written offer)
- [stripe-billing.md](../platform/stripe-billing.md) · [client-portal.md](../platform/client-portal.md) · [backup.md](../operations/backup.md)
- [RB-05 Onboard a client](../runbooks/onboard-client.md)
