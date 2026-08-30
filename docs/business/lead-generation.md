# Cronnecture Lead Generation Pipeline — Plan

**Status:** MVP + reply sync + **automated discovery** + **call-first Prospects UX** — **v2.5** (SMB filters + call-first IA)  
**Offer:** Managed Site Pilot — Standard / Business / Complete ([commercial-offer.md](commercial-offer.md))  
**Prices:** [pricing.md](pricing.md) (List €79.99 / €119.99 / €159.99; Pilot €49.99 / €89.99 / €129.99 excl. BTW)  
**Operator:** solo founder (Sven), NL business hours Mon–Fri 09:00–18:00 Europe/Amsterdam

---

## Grounding in what exists today

| Surface | Current state | Role in this plan |
|--------|----------------|-------------------|
| **Inbound leads** | Supabase `contact_leads` via Business → Leads + CRM → Pipeline | Keep as **inbound** store; extend schema for outbound prospects |
| **Convert → wizard** | `POST /api/leads/convert` prefills name/slug/email → New client wizard | End of funnel only (Qualified → Converted) |
| **Client model** | `contact_email`; status kanban includes `lead` / `prospect` | Paying tenants — not the prospect CRM |
| **Mail** | Stalwart + Business Mail; platform SMTP (`send_email`); `info@` / `support@` / `noreply@` / `alerts@` | Outreach From: **`info@`** (human); never `noreply@` or `alerts@` |
| **Maps / prospecting** | **Automated discovery** (Overpass/OSM default; Google Places optional) → prospects `new`/`researched` | Human still Approves before send; **SMB ICP filters** drop hotels/chains/enterprises |
| **Phone** | Prospect phone + **Call list** + call-first modal (primary workflow) | Email Approve & send remains secondary |

**Opinionated posture:** build a **prospect pipeline** that feeds the existing convert→wizard path. Do not bolt cold outreach onto `Client` rows until someone pays / is provisioned.

**Primary acquisition engine (2026-08):** inbound brand + **contact/email** + invoice/Tikkie + warm `contact_leads` nurture — see [acquisition.md](acquisition.md). Public Stripe Checkout stays off. Cold research/call-first remains secondary capacity, not the default growth bet.

---

## Locked defaults (solo founder, Apeldoorn)

All former open questions that blocked v1 are decided here. Change deliberately, not casually.

| Topic | Default |
|-------|---------|
| **Language** | **NL** for T0/T1/T2. **EN** only when the company site is EN-only (or they reply in EN). |
| **Daily caps** | Max **10** reviewed outbound emails/day; max **15** call attempts/day. |
| **Sales From** | `Sven Braad <info@cronnecture.com>` — not `noreply@`, not `alerts@`. |
| **T0 A-leads** | **Call-first** (or call same day as Email #1); phone before long email sequences when a published business number exists. |
| **Pack minimum** | **Site-only OK** for first clients. Upsell +billing / Full when they already take payments or need a DB. |
| **Vertical** | **All NL SMB with a site** — no exclusive niche. Prefer local services, retail, and professional firms; deprioritize pure agencies. |
| **Decision maker** | Prefer owner / directeur; **office manager OK** if they own the website budget. |
| **Data store** | New **`prospects`** table (or equivalent), separate from `clients`; keep `contact_leads` for inbound. |
| **Time split** | ~**40%** inbound / referrals / warm; ~**60%** cold research + outreach (calendar hours, not lead count). |
| **Case study** | Mention past pilots **vaguely** until a paying client agrees to a quote ([commercial-offer.md](commercial-offer.md) referral blurb). |
| **Price anchor** | Quote Pilot first (€49.99 Standard) with list strikethrough; Stripe default = dedicated Pilot `price_…` (not 30% of list). |
| **AVG note** | Soft: document legitimate-interest + opt-out before first cold batch of 20+; lawyer review **recommended before scaling**, not a blocker for 5–10 manual T0 calls. |

---

## 1. Ideal Client Profile (ICP)

### Who buys Managed Site Pilot

SMB / micro-SME that **owns a public website or small webshop**, wants it **stable, secure, and off their plate**, and can pay a **recurring managed fee** (list ~€79.99–€159.99/mo excl. BTW; Pilot €49.99–€129.99 while acquiring first clients) — not an agency redesign retainer.

### Explicit fit: old or outdated websites

**Primary pain/fit for outreach:** companies whose site looks **dated, neglected, or insecure** — even if the business itself is healthy.

| Signal (research checklist) | Why it fits |
|-----------------------------|-------------|
| Design / UX looks **5–10+ years** old; non-mobile layout | Embarrassment + lost trust; open to “we’ll host and harden” or migrate |
| Broken layout, mixed content, expired cert, “Not secure” | Security / ops pain Cronnecture names honestly |
| Ancient WordPress / Joomla / Flash-era remnants / “Under construction” | Cheap hosting + no owner; managed care is an easy story |
| Contact page still works but **nobody updates** content | Owner fatigue — recurring fee beats another rebuild pitch |
| Site on **€3–10 shared hosting**, slow or occasionally hacked | Clear upgrade path without selling a €5k redesign first |
| Local Apeldoorn/Gelderland business with a weak Google presence via old site | Geo trust + visible problem |

**Outreach rule:** when you have a *human* observation about age/quality/security, use `{observatie}` / `{observatie_blok}` — never scrape junk (`titel «…»`, generator meta) and never “I help companies grow online” fluff. Empty observation → omit the sentence; company name already personalizes the opener.

**Still in ICP if the site is modern** but ops pain is clear (exposed admin, no backups, agency bottleneck, need portal/billing). Outdated sites are the **preferred** cold-mail hook, not the only buyers.

### Firmographics

| Dimension | Sweet spot | Stretch | Hard no (early) |
|-----------|------------|---------|-----------------|
| **Size** | 1–25 employees; owner/ops decides | 25–50 with a clear “website owner” | Enterprise procurement, RFPs |
| **Legal form** | BV / eenmanszaak / VOF with public site | Stichting with real ops site | Pure holding / dormant KvK shells |
| **Revenue proxy** | Pays for tools already; or outdated site but busy shop/phone | DIY WordPress that “mostly works” | No digital presence and no intent in 90 days |
| **Decision maker** | Owner, directeur, or office manager with budget | Marketing lead with budget | Junior “webmaster” with no € |
| **Stack fit** | Static / WordPress / small Node / needs portal+billing later | Custom app → Site+Supabase / Full | Heavy SAP/ERP hosting, PCI/HIPAA day-1 |
| **Budget fit** | Comfortable at Pilot **€49.99–€129.99/mo** (list €79.99–€159.99) excl. BTW | Needs setup waive | Only compares to Hostinger €3 and will not move |

### Tech / ops pain (what the email must name)

1. **Outdated or neglected site** (primary cold hook)
2. Site on cheap shared hosting — slow, hacked, or “nobody knows the login”
3. Origin / admin exposed; no Cloudflare / tunnel mindset
4. No customer portal, invoices, or Terms/Privacy in one place
5. Agency dependency for every DNS/SSL/deploy change
6. Want **one Dutch-reachable operator** in business hours — not a ticket black hole

### Offer match (quote honestly)

- Included: managed hosting, CF edge + tunnel, portal, Stripe (per pack), legal pack, backups posture, soft SLA — [commercial-offer.md](commercial-offer.md)
- Prices: [pricing.md](pricing.md)
- Not included: redesign/SEO campaigns, 24/7 phone, multi-region HA, compliance attestations

### Exclusions (score to D or discard)

- Agencies / freelancers who **resell hosting** (channel conflict unless referral)
- Competitors (hosting, MSPs, big cloud)
- Pure B2C consumer, schools without budget, political parties
- Companies with **no website and no intent** to launch one in 90 days
- Anyone asking for SOC2/HIPAA/PCI as day-1 requirement
- International HQ with NL branch only as a mailbox (unless local decision maker)
- Prospects who only want a **full redesign** with no managed-hosting interest (refer out or nurture)

### Geo tiers

| Tier | Geography | Priority | Cadence |
|------|-----------|----------|---------|
| **T0** | Apeldoorn (+ immediate neighbors: Deventer, Zutphen, Epe, Voorst) | Highest | Research + **call-first** when phone exists |
| **T1** | Gelderland | High | Same playbook; call A/B with phone |
| **T2** | Rest of NL | Medium | Email-first; call only A-rated |
| **T3** | BE / DE / EN-speaking EU | Later | After NL pipeline is full |

**Why:** solo founder capacity + local trust. “Ik zit in Apeldoorn” beats generic EU SaaS cold mail.

---

## 2. Data sources (legal / ethical / automation honesty)

### Allowed for MVP (manual or light-assisted + discovery)

| Source | What you take | Automation | Compliance note |
|--------|---------------|------------|-----------------|
| **OpenStreetMap / Overpass** | Name, city, phone, **website** (where tagged) | **Automated** discovery job (default, no API key) | Public OSM data; polite User-Agent; capped creates/run |
| **Google Places API** (optional) | Name, phone, website, locality | Automated when `google_places_api_key` / `vault_google_places_api_key` set | Licensed API + ToS; not HTML scraping |
| **Public company website** | Domain, contact email, phone, city, **outdated-site signals** | Light homepage fetch for `{site_observatie}` heuristics + manual browse | Prefer published `info@` / `contact@` |
| **Google Maps / search (manual)** | Name, address, phone, website link | Still useful for spot checks | No scraping bots |
| **KvK / OpenKvK / Handelsregister** | Legal name, vestigingsadres, SBI | Manual or licensed API later | Firmographics, not spam lists |
| **Local directories** | Name, sector, sometimes web | Manual | Public business data |
| **LinkedIn (manual)** | Decision-maker name/title | Browser only | No scrapers; store carefully |
| **Inbound** (`cronnecture.com/#contact`) | Warm leads | Already automated | Jump the queue |
| **Referrals / network** | Warm intros | Manual | Best conversion |

### Automated discovery (what is / isn’t auto)

| Automated | Still human |
|-----------|-------------|
| Query Apeldoorn (T0) then Gelderland (T1) **SMB** businesses **with a website** | Research quality / decision-maker name |
| **ICP reject:** hotels, national chains, franchises, enterprise/gov name+domain patterns | Rating A–D |
| Dedupe by domain/phone vs prospects, client zones, suppression domains | Call outcomes; convert → wizard |
| Create prospect `source=discovery_osm` or `discovery_places`, stage `new` or `researched` | **Approve & send** every email (caps + kill switch) — secondary to calling |
| Draft `{site_observatie}` + fit notes + address (no scrape junk / title / generator) | Choosing who to call first |
| Enrich public **phone** / role email / address from homepage + contact page | |
| Nightly preset **03:15 UTC** + CRM **Discover** | |

**Does not:** auto-send cold email; buy lists; scrape LinkedIn; invent emails; ingest hotels/chains as ICP.

**Run:** CRM → Prospects → **Discover** / **Dry-run**, or `POST /api/prospects/discovery/run`, or automation `prospect_discovery`.  
**CRM UX (call-first):** compact list (Phone / Call-first / Discovery / New / Replied) + **Call list** primary CTA. Click row → **client profile modal** with Call + script elevated; email Approve & send collapsed as secondary.  
**Enrich:** `POST /api/prospects/{id}/enrich` (also auto on first open when profile is thin). Soft/public sources only.  
**Review API (optional):** `GET /api/prospects/discovery/new` still works; UI uses the main list + discovery badge/filter.  
**Key missing:** discovery still works via Overpass; clear hint points to Settings → Integrations → Google Places / vault `vault_google_places_api_key`.

### Do not do

- Bulk scrape Maps HTML without licensed API + ToS-compliant use
- Buy email dumps or scraped LinkedIn CSVs
- Harvest personal Gmail/Hotmail for cold sequences
- Fire high volume from a cold IP overnight
- Auto-send from discovery (Approve gate stays)

### NL / AVG framing (practical, not legal advice)

1. **Legitimate interest** for B2B contact about a relevant service; clear identity; easy opt-out; minimal data
2. Prefer **role mailboxes** when cold
3. **Suppression list** (bounce, stop, DNC)
4. Retention e.g. 12 months inactive → delete/anonymize
5. Privacy Policy must cover prospecting if phone/email live in ops CRM
6. Calling published business numbers is normal; **don’t record** by default

**Automation limit:** MVP enrichment is **operator + checklist**, not an AI scraper farm.

---

## 3. Pipeline stages

```
New → Researched → Rated → Contacted → Replied → Qualified → Converted
         ↓           ↓          ↓
      (Discard)   (Nurture)  (Unsubscribed / Do-not-contact)
```

| Stage | Definition | Exit criteria |
|-------|------------|---------------|
| **New** | Captured with company name + domain or phone | Research checklist |
| **Researched** | Website opened; city/tier; **outdated-site notes**; contacts | Ready to score |
| **Rated** | Score + grade A–D | A/B → outreach; C → nurture; D → discard |
| **Contacted** | ≥1 outbound email **or** call logged | Wait / follow-up |
| **Replied** | Human reply | Interested / not now / no |
| **Qualified** | Budget (Pilot ~€49.99+ / list €79.99+) + need + timeline + pack lean; soft SLA understood | Scope reply + wizard |
| **Converted** | Convert → wizard → provision started | Leaves prospect pipeline |

**Side states:** `Unsubscribed`, `Do-not-contact`, `Wrong fit`, `Nurture (90d)`.

Inbound: never force cold-research delays.

---

## 4. Rating model

Score **0–100**, then grade.

| Dimension | Weight | 0 | 5 | 10 |
|-----------|--------|---|---|-----|
| **Geo fit** | 20% | Outside NL / unknown | NL (T2) | T0 Apeldoorn / T1 Gelderland |
| **Site / product fit** | 25% | No site, no plan | Live but modern DIY | Live site/shop **or clear outdated-site upgrade** matching packs |
| **Pain clarity** | 20% | Looks fine / enterprise IT | Mild friction | **Outdated/insecure/neglected** or clear hosting/ops pain |
| **Reachability** | 15% | No email/phone | Email **or** phone | Business email **and** phone |
| **Decision proximity** | 10% | Unknown | Named manager | Owner / directeur / office manager with budget |
| **Commercial realism** | 10% | Hostinger-only mindset | SMB that pays for tools | Already pays hosting/agency **or** busy business with shamefully old site |

**Grade thresholds:**

| Grade | Score | Action |
|-------|-------|--------|
| **A** | ≥ 75 | Sequence + call (T0: call-first) within 2 business days |
| **B** | 60–74 | Email sequence; call if T0/T1 |
| **C** | 40–59 | Nurture / monthly batch |
| **D** | &lt; 40 | Discard or DNC |

**Hard overrides → D:** competitor; no NL presence; compliance-only; explicit no-sales; agency reseller without referral intent.

---

## 5. Outreach

### Channel rules

- **Email:** NL-first; human-sounding; personalize on **outdated/security** observation
- **Phone:** published business number; T0 A = call-first
- **No LinkedIn blast automation**

### Email tone

- From: `Sven Braad <info@cronnecture.com>`
- **Human, warm, short** (~80–120 words first touch); no HTML marketing templates
- Plain language: site veilig / bereikbaar / niet zelf knutselen — **not** Cloudflare, tunnels, Stripe feature dumps
- Optional `{observatie}` (human only: age, mobile, SSL, “oud ogende site”) — omit if empty/ugly
- Soft CTA: kort gesprek / bel even
- Opt-out natural: `Liever geen mail meer? Antwoord met stop, dan schrap ik je.`

**Tokens:** `{aanhef}` `{voornaam}` `{bedrijf}` / `{bedrijfsnaam}` `{plaats}` `{observatie}` `{observatie_blok}` `{site_observatie}` (sanitized) `{pijn}` `{jouw_naam}` `{prijs}` `{domein}`

Defaults live in `services/control-plane/app/prospect_service.py` → `DEFAULT_TEMPLATES` (synced to DB on control-plane boot).

Example good first-touch (NL) — rendered:

```
Onderwerp: Korte vraag over de site van Banketbakkerij Maassen

Hoi,

Ik zag de website van Banketbakkerij Maassen en dacht: even kort mailen vanuit Apeldoorn.
Jullie site oogt wat gedateerd.

Ik help mkb’ers om hun site veilig te houden en bereikbaar te laten blijven —
zonder dat jullie zelf aan hosting hoeven te knutselen.
Desgewenst vanaf ongeveer €49,99 per maand excl. BTW.

Als dat iets is waar jullie mee zitten, bel of mail ik graag even.
Past het niet, zeg het gerust — dan laat ik het rusten.

Groet,
Sven
Cronnecture · info@cronnecture.com

Liever geen mail meer? Antwoord met stop, dan schrap ik je.
```

Price optional / light (“ongeveer €49,99”); don’t lead with a brochure. Operator may tighten `{observatie}` before send — never paste discovery `titel «…»`.

### Cadence (A/B only)

| Step | Day | Channel | Rule |
|------|-----|---------|------|
| 0 / 1 | 0 | **Call #1** (T0 A with phone) **or** Email #1 | Call-first for T0 A; else email |
| 2 | 0–1 | Email #1 if call was first | Personalized; review gate |
| 3 | 3–4 | Call attempt | If not reached yet |
| 4 | 7 | Email #2 | New angle (security / portal / old hosting) |
| 5 | 10–12 | Call #2 | T0/T1 A |
| 6 | 14–16 | Email #3 (breakup) | Close dossier politely |

**Stop rules:** stop keyword; hard bounce; no interest; convert started; breakup with no reply → Nurture or close.

### Phone opener (NL)

> Hoi, Sven van Cronnecture in Apeldoorn. Ik bel kort over jullie website — geen pitch van vijf minuten. {observatie} Ik help mkb’ers om hun site veilig en bereikbaar te houden, zonder zelf aan hosting te knutselen — vanaf ongeveer €49,99 per maand excl. BTW. Is {naam} de juiste persoon voor de website?

If yes → soft SLA honesty + pack options → email summary + Stripe when ready.

**Call list UX:** today’s A/B with phone, sorted call-first → T0 → T1 → T2; `tel:` link; NL opener on page; outcomes: Reached / VM / No answer / Wrong number / Interested / Nurture / DNC. Prospects list shows phone column + Call-first filter.

---

## 6. System design

### Where data lives

| Data | Store | Why |
|------|-------|-----|
| **Prospects** | New `prospects` table | Separate from k8s `Client` until convert |
| **Inbound** | Existing `contact_leads` | Untouched |
| **Stages, score, grade, outdated-site notes** | Prospect columns | Pipeline + rating |
| **Phone, email, domain, city, geo_tier** | Prospect fields | Call list |
| **Templates + send log** | Ops DB / Supabase | Audit + stop rules |
| **Suppression** | Dedicated table | Shared |
| **Paying tenant** | `clients` via wizard | After Qualified |

### Mail path

```
CRM/Business “Approve & send”
  → render text (tokens filled)
  → platform SMTP → Stalwart
  → From info@
  → log real SMTP Message-ID, template_id, prospect_id
  → replies land in info@ (Business Mail)
  → leader poller (every ~3 min) matches inbound → stage replied
```

### Reply → stage sync (automated)

Control-plane leader polls `info@` over IMAP (`BODY.PEEK`, does not mark read / does not auto-send).

| Priority | Match | Notes |
|----------|--------|--------|
| 1 | `In-Reply-To` / `References` ↔ `prospect_email_logs.message_id` | Primary; requires Approve & send after this feature |
| 2 | Exact `From` ↔ `contact_email` or sent `to_email` | Only if prospect has ≥1 sent log; not terminal stages |
| 3 | `From` domain ↔ `prospect.domain` | Only when **exactly one** contacted candidate; free-mail domains skipped |

Skipped: platform addresses (`info@` / `noreply@` / …), auto-replies (`Auto-Submitted`, OOO subjects), already-processed IMAP UIDs.  
On match: stage → `replied` (CRM badge / Needs attention). Body `stop` → `unsubscribed` + suppression. Never sends mail.

**Verify with a test reply**

1. Approve & send a prospect email from CRM → Prospects (note `message_id` in the send response).
2. From that recipient mailbox, reply to the message (so `In-Reply-To` is set).
3. Wait ≤3 minutes, or `POST /api/prospects/reply-poll` (ops Bearer).
4. Confirm prospect stage is `replied`, row highlights under CRM → Prospects, nav badge increments.
5. Optional: `GET /api/prospects/reply-poll` for last poll stats.

### Human review gates

1. Stage = Rated; grade ∈ {A,B}
2. Required: email, non-empty `{site_observatie}`, opt-out line
3. Approve per message; daily caps
4. Global kill switch
5. First 20 sends: founder-only; watch bounces

### Convert path

Qualified → Convert → wizard → packs + [pricing.md](pricing.md) → RB-05 → Stripe checkout / portal.

---

## 7. MVP vs later

### MVP

1. Prospect fields + stages + A–D (incl. outdated-site notes)
2. Manual add / CSV paste
3. Research checklist + rating form
4. Email templates (3) + approve-to-send via Stalwart
5. Call list + outcomes + `tel:`
6. Suppression + caps
7. Inbound convert unchanged
8. Docs: this plan + [pricing.md](pricing.md) + short AVG processing note

### Later

- KvK enrichment; richer Places query verticals
- AI polish of `{site_observatie}` (human still approves)
- Capped sequencer (still human-reviewed sends)
- T3 geo; deliverability relay if needed ([mail.md](../operations/mail.md))

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Deliverability | Caps, warm-up, human review; relay if needed |
| AVG / cold email | Role emails, opt-out, T0 call bias, no scraped personal lists |
| Brand | Honest soft SLA; no spammy HTML |
| Price shoppers | Qualify on Pilot €49.99+ / list €79.99+; don’t compete with €3 hosting |
| Capacity | Caps; A-priority calling; breakup email |
| Prospect vs Client confusion | Separate `prospects` until convert |

---

## 9. Remaining open questions (short)

Almost everything is locked. Only ask if something changes:

1. **Lawyer before cold email batch &gt;20?** Recommended yes; optional for first handful of T0 calls.
2. **Annual billing** offered at Pilot launch, or monthly-only until 5+ clients?
3. **Fair-use hour rate** (€89.99/uur suggested) — confirm when first out-of-scope tweak is quoted.

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-07-29 | Initial plan; open questions on price/language/caps/etc. |
| v2 | 2026-07-29 | Outdated-site ICP; locked solo-founder defaults; pricing → [pricing.md](pricing.md) |
| v2.1 | 2026-07-29 | MVP shipped: `prospects` table, CRM UI, 3 NL templates, approve-to-send, call list, convert bridge |
| v2.2 | 2026-07-29 | Reply→stage sync: poll `info@`, match Message-ID / From / domain, CRM replied badge |
| v2.3 | 2026-07-29 | Automated discovery: Overpass/OSM (+ optional Places), dedupe, site heuristics, CRM Run discovery + nightly job — **no** auto-send |
| v2.4 | 2026-07-30 | Prospects: single compact list + profile modal; homepage/contact enrich for phone/email; advance stage API — still **no** auto-send |
| v2.5 | 2026-08-02 | **Call-first IA** (Call list primary, email demoted); **SMB ICP filters** (no hotels/chains/enterprises); richer profile (address, fit notes, site quality); tickets triage upgrade |

Discovery fills the SMB pipeline; **calling is the primary action**; humans still Approve every outbound email.
