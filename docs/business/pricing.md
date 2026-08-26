# Cronnecture — price profile

**Status (2026-08-21):** Public page and live Stripe catalog match the marketing site. No list/Pilot split. Handshake NoordDrive unchanged.  
**Currency:** EUR. Amounts **excl. 21% BTW**.  
**Offer:** Website / webshop / CMS-CRM mixes — see [commercial-offer.md](commercial-offer.md).  
**Lead-gen alignment:** [lead-generation.md](lead-generation.md).  
**Stripe SoT:** `config/policies/packs.yml` + live products on `acct_1ThxGgI1Driezaay`. Do not use a percent coupon.

This is the usable quote sheet for Stripe catalog (list) prices and founder conversations. Not a legal price list; Terms + Stripe Catalog win at checkout.

**Public ↔ internal map** (marketing names only; CRM pack ids stay stable):

| Public name | Mix | Stripe / ops pack id |
|-------------|-----|----------------------|
| **The website** | website | `site` (go-live: `site_only`) |
| **The webshop** | website + webshop | `site_billing` |
| **The CMS** | website + webshop + CMS/CRM | `full` |
| *(ops only)* | website + CMS/CRM | `site_supabase` |

---

## Positioning (one sentence)

Above cheap shared hosting (€3–10) and commodity “WordPress hosting” (€5–35); below agency retainers that sell hours (€200–500+/mo). Cronnecture sells **managed platform + Dutch business-hours care** — not plugin updates alone.

---

## Public products (excl. BTW)

Match [cronnecture.com/pricing](https://cronnecture.com/pricing). No list/Pilot split on the public page.

| Mix | Ops pack | Monthly care | New build | Move (already have one) |
|-----|----------|-------------:|----------:|------------------------:|
| **Website** | `site` / `standard` | **€49.99** | **€899** | **€0** (12-month term) |
| **Website + webshop** (The webshop) | `site_billing` / `business` | **€119.99** | **€1,699** | **€0** (12-month term) |
| **Website + CMS / CRM** | `site_supabase` | **€89.99** | **€4,149** | **€0** (12-month term) |
| **Website + webshop + CMS / CRM** (Portal) | `full` / `complete` | **€129.99** | **from €4,999** | **€0** (audit first) |

Modules (add onto website): **Webshop** +€70/mo · build €800 · move €0. **CMS / CRM** +€40/mo · build €3,250 · move €0. A database is never sold alone — it comes with the CMS/CRM so you can manage it.

Handshake (NoordDrive only, not public): setup **€79.99** + monthly **€39.99**.

**Annual option (optional later):** 10× monthly (≈2 months free) paid upfront — do **not** lead with this until KVK and charges are on.

**Minimum pack for first clients:** Website is OK. Prefer **Website + webshop** when they already take card payments elsewhere.

**Cold outreach:** if you mention price at all, keep it light — “vanaf ongeveer €49,99/maand”. Do not lead with strikethrough or tech stack. Templates: `prospect_service.py` → `DEFAULT_TEMPLATES` / [lead-generation.md](lead-generation.md) §5.

**Marketing:** public page lists The website / The webshop / The CMS at the amounts above ([cronnecture.com/pricing](https://cronnecture.com/pricing)).

**Public CTA (pre-KVK):** [cronnecture.com/#contact](https://cronnecture.com/#contact) or `support@cronnecture.com` → invoice / Tikkie → ops provision. **Custom domain is an upgrade** — request from the customer portal (or contact); ops completes cutover via [RB-05](../runbooks/onboard-client.md).

**Optional self-serve after you choose to take public cards:** [client.cronnecture.com/start](https://client.cronnecture.com/start) → Stripe Checkout when `self_serve_live_payments=true` (still **false** on 2026-08-19). KVK and Stripe charges are already enabled. Do not invent VAT numbers. Do not run `make business-go-live` just to flip the flag.

---

## Setup / onboarding (one-time, excl. BTW)

| Item | Pack id | Amount | When to use |
|------|---------|-------:|-------------|
| **Move your website** | `setup_standard` | **€0** | They already have a site. 12-month term. No rebuild. |
| **Connect own domain** | `domain` | **€49.99** | One-time NS cutover (portal request). Live Stripe SKU on **Extras**. |

Quote setup **separately** from the subscription. Handshake setup (€79.99) is NoordDrive only — not the public move price.

---

## Optional builds (one-time, excl. BTW)

| Item | Pack id | Amount | When to use |
|------|---------|-------:|-------------|
| **Website — build** | `website` | **€899** | Design & build a site, then monthly website care |
| **Website + webshop — build** | `webshop` | **€1,699** | Shop design and checkout |
| **Website + CMS / CRM — build** | `website_database` | **€4,149** | Site plus CMS/CRM (never a bare database) |
| **Portal — build (from)** | `cms` | **€4,999** | Custom portal after intake |
| **Webshop — add-on build** | `payments` | **€800** | Add a shop onto an existing website |
| **CMS / CRM — add-on build** | `database` | **€3,250** | Add a CMS/CRM onto an existing website |
| **Hours small / medium / large** | `hours_*` | **€225 / €400 / €750** | 2.5h / 5h / 10h prepaid |
| **Extra hour** | `extra_hour` | **€90** | Quoted work beyond monthly care |

---

---

## What NOT to charge for (or include in the monthly)

| Include in monthly (no line item) | Quote separately / never “unlimited” |
|-----------------------------------|--------------------------------------|
| Routine deploys of the **agreed** stack | Custom feature development |
| Portal invite, Access email changes (reasonable) | Design / copy / SEO campaigns |
| Soft SLA responses in business hours | 24/7 on-call, Slack channel, phone desk |
| Platform backup / restore *posture* (fleet drills) | Guaranteed per-tenant RPO/RTO; customer-owned cloud accounts |
| Pay-needed banners + 90-day grace (as documented) | Multi-region HA / dedicated node |
| Terms + Privacy issued to portal Documents | PCI / HIPAA / SOC2 attestations |
| Short status / “is it down?” checks | Open-ended agency retainer hours |

**Fair-use content tweaks:** up to ~30 minutes/month of trivial text/image swaps on the live site if the founder can do them without a project — beyond that, time & materials (suggest **€89.99/uur**) or a fixed mini-quote.

---

## BTW / invoicing note (NL B2B)

- List and Stripe catalog prices as **excl. 21% BTW** for Dutch B2B (standaardtarief).
- Invoice shows excl. + BTW + incl. where applicable.
- EU B2B outside NL: may be reverse-charge / 0% with valid VAT ID — confirm with bookkeeping; do not invent VAT rules in sales copy.
- Say verbally: *“€49,99 per maand exclusief BTW”* so nobody thinks Hostinger-level all-in pricing.
- **Registration gate:** KVK + legal name are on file. VAT is deferred. Stripe `charges_enabled` is true. Ops already has `sk_live_` in Settings. Keep `self_serve_live_payments=false` until you want public card Checkout.

---

## How to talk about price vs the market

| Buyer compares to… | Typical range | Your line |
|--------------------|---------------|-----------|
| Shared / cheap WP hosting | €3–35/mo | “That’s self-serve hosting. We run the site on a managed fleet with a portal and a real person in Apeldoorn business hours.” |
| NL website-onderhoud MKB | ~€30–65/mo rational; €39–99 care packs | “Same ballpark as serious onderhoud, plus portal and billing care — not only plugin updates.” |
| Bureau retainer with hours | €100–300+/mo; €500+ agency | “We’re not selling a bag of design hours. Scope is managed site ops; big changes are quoted.” |
| DIY edge / workers | ~$5+ infra | “Infra is cheap; reliability, onboarding, billing, and someone who answers mail is the product.” |

---

## Cost floor (founder sanity check — not customer-facing)

Rough variable cost to serve one light Standard tenant (order of magnitude):

| Cost | Approx. |
|------|---------|
| Edge / tunnel share | low single-digit €–USD on a shared account |
| Compute share on k3s | amortised fleet |
| Client database (if CMS/CRM / `site_supabase` or `full`) | provider Pro floor → keep the CMS/CRM delta |
| Stripe fees | % of charge (customer pays subscription; fees are COGS) |
| Founder time | soft SLA — the real constraint |

Website €49.99 leaves little room after COGS for support time. Do not race monthly care toward €29.

---

## Stripe setup checklist

- [x] Live catalog rebuilt 2026-08-18: Website / Webshop / CMS-CRM modules + mixes. Tax codes Website Hosting + SaaS business.
- [x] One-time SKUs aligned 2026-08-21 to the marketing site (€899 / €1,699 / from €4,999; moves €0). Handshake unchanged.
- [x] Handshake NoordDrive kept at €39.99/mo + €79.99 setup (not a public SKU).
- [x] Ops Settings pointed at live `price_…` IDs (`stripe_pack_prices` / `stripe_addon_prices`). Default price is Website €49.99, not handshake.
- [x] KVK on file (`42140905`); legal name Cronnecture
- [ ] VAT deferred (not required now)
- [x] Stripe `charges_enabled` / `payouts_enabled` (2026-08-19)
- [ ] Customer Portal live configuration (Dashboard activate — see [stripe-billing.md](../platform/stripe-billing.md))
- [ ] `self_serve_live_payments=true` only when you want public card Checkout
- [ ] Quote language matches [commercial-offer.md](commercial-offer.md) soft SLA (no fake 99.99%)

**Ops:** Settings → Billing stores pack `price_…` JSON. Live IDs are also in `config/policies/packs.yml` (`stripe_live_prices`). Sandbox leftovers stay under `stripe_test_prices` for `sk_test_`.

---

## Research sources (comparables)

NL / EU signals used for this profile (fetched mid-2026 research):

| Source | Signal |
|--------|--------|
| [GraphicGenie — website onderhoud kosten](https://www.graphicgenie.nl/blog/wat-kost-website-onderhoud-per-maand) | Hosting-only €10–20; cheap all-in €20–30; Hosting Compleet €34,50; freelance €40–80; bureau basic €100–200; premium €199–500+ |
| [Jorijn — WordPress onderhoud](https://jorijn.com/nl/blog/wordpress-onderhoud-kosten/) | Rational MKB band **€30–65**; &lt;€25 = automation; &gt;€100 often = hours/SLA |
| [No Limit Design — onderhoud 2026](https://nolimitdesign.nl/inspiratiehub/website-onderhoud-bespaar-kosten-met-slim-onderhoud/) | Freelancer/bureau basic often €50–150; mid €150–300; complex €300–600+ |
| [Artworqs onderhoudspakketten](https://www.artworqs.nl/onderhoudspakketten/) | Care packs **€39 / €59 / €99** incl. hosting |
| [FlowTogether — beheer](https://www.flowtogether.nl/blog/wat-kost-een-maatwerk-website-eenmalig-bouwen-maandelijks-beheer.html) | Hour-bundled beheer **€99 / €199 / €299** |
| [Next Win — website laten maken](https://next-win.nl/kenniscentrum/wat-kost-een-website-laten-maken/) | Hosting €5–25; onderhoud €25–150; build €2.5k–7.5k typical MKB |
| [Bosman ICT — migratie](https://www.bosmanictservices.nl/website-laten-maken-kosten/) | Migration often €200–€2.000+; MKB build €2k–7.5k |
| [SoftwareKiezer WP hosting 2026](https://softwarekiezer.nl/kenniscentrum/wordpress-hosting-vergelijken-2026-9-beste-providers-prijzen) | Shared promo €3–10; managed premium (Kinsta/WP Engine class) ~€27–64+ |

---

## Change log

| Date | Note |
|------|------|
| 2026-07-29 | Initial profile treated €79–€159 as Pilot |
| 2026-07-29 | Reframe: €79–€159 = **list**; Pilot = **40% off** + Stripe `PILOT40`; marketing strikethrough |
| 2026-07-29 | **.99 prices** + Pilot **≈50%** (`PILOT50`); public Standard / Business / Complete; onboard €139.99 → €79.99; drop public migration SKU |
| 2026-08-13 | Website/webshop Pilot €199.99 / €299.99 (list €399.99 / €599.99); setup required on `/start`; pack coupon does not apply to build add-ons |
| 2026-08-13 | Pilot **30% off** (`PILOT30PACKS`); Standard/Business/Complete €55.99 / €83.99 / €111.99; setup €97.99; website/webshop €279.99 / €419.99 |
| 2026-08-13 | Charm **9,99** grid: Pilot €49.99 / €89.99 / €129.99 (€30 off list); setup €99.99; domain €49.99; hourly €89.99. Stop using percent coupon for quoted amounts. |
| 2026-08-18 | Public page becomes the catalog. Website / webshop / CMS-CRM mixes. No list/Pilot split. Handshake stays €39.99 + €79.99. |
| 2026-08-19 | Stripe charges/payouts on. `/start` copy matches public catalog (€49.99 / move €0). Customer Portal still needs a Dashboard activate. |
| 2026-08-21 | Webshop mix €119.99/mo + €1,699 build. Add-on module €70/mo + €800. Portal unchanged. |
