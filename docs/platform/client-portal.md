# Client customer portal

Logto-gated customer hub at:

`https://client.cronnecture.com/`

Tenant is selected from the Logto session (`cp_logto_session`), not from the URL. `portal_uuid` is still stored on the client row. Legacy `https://client.cronnecture.com/client/portal/{portal_uuid}` **302s** to `/`.

The UI is the Next.js app [Cronnecture/client-portal](https://github.com/Cronnecture/client-portal). Backend contract: `GET /portal` (PortalSnapshot) and `POST /portal/actions`. See that repo’s `docs/INTEGRATION.md`.

## What clients see

Lightweight shell (`static/customer-portal/`) — **account / business only** (no website builder, Deploy, or AI site tools):

| Section | Content |
|---------|---------|
| Overview | Account health, billing snapshot, domain/site summary, jump links |
| Account | Profile, teammate Access invites, status-page toggle, custom-domain upgrade |
| Billing & invoices | Plan status, recent Stripe invoices, pay / Customer Portal link |
| Payments | Connect Mollie / Stripe for apps + **checkout branding** (logo, colors, product defaults, success/cancel URLs) with live preview |
| Documents | Issued **PDF** legal pack + files — grouped **Current / Upcoming / Previous**, with prior-notice banner; **View** (in-portal PDF viewer) and **Download** |
| Status | Modular uptime dashboard (KPIs, donut, trends, incidents) |
| Support | Contact paths + in-portal message form |
| Site traffic | Compact KPIs on Overview (requests, availability, top countries) |

**End-customer checkout (public):** `https://client.cronnecture.com/pay/{client-slug}` — branded page for the client’s buyers via their connected PSP. See [payment-providers.md](payment-providers.md).

**UX note (2026-08):** Light soft-UI shell — navy sidebar, off-white main, **Plus Jakarta Sans** display + **DM Sans** body. Dense layout with pack entitlement strip, locked upgrade previews (no fake metrics), denser billing/invoices, Payments (PSP + checkout branding on Business+), and Complete managed-database packaging. Portal HTML/APIs require **Logto** (`cp_logto_session`); Cloudflare Access is not used on this hub. Checkout cancel returns to `/?billing=cancelled` on the portal path (trailing slash). Stripe Customer Portal returns to `/billing/`.

**Self-serve in portal:** custom domain request · teammate allowlist invites · uptime page toggle · **pack checkout / prorated upgrade** · optional setup/website/webshop when Stripe one-time prices are configured.

### Account as source of truth

1. Ops **must** set a client account email when creating a portal (CRM create wizard / Manage).
2. That email is allowlisted. Give the client **their portal URL** — not a bare `id.cronnecture.com` link.
3. Unauthenticated visit → Logto sign-in (that **is** account setup: password or Google for the invited email). Strangers cannot enter; they see a clear “not invited” page.
4. After Logto, they land **in** the portal. Control plane persists **account ↔ portal** (`Client.contact_email` + `Client.logto_sub`).
5. Subscription, pack, and add-ons stay on the **Client** row + Stripe Customer linked to that email.
6. Active pack → Billing shows **Upgrade** (current pack locked). Upgrades call Stripe subscription update with proration (pay-the-difference), not a full new-customer Checkout. Downgrades → contact / period-end messaging.

**Not in the client portal:** website builder, Deploy, AI site generation, previews, sandbox probes, or publish — those stay on **ops CRM** (`ops.cronnecture.com`).

This is **not** the old Insights extension marketplace. Do not advertise `insights.*` hostnames to clients.

## Access control

- **Logto** (Google + password/TOTP) at `id.cronnecture.com` — **required** before portal HTML/APIs
- Domain: `client.cronnecture.com` (Cloudflare Access **off** — `skip_access: true` + `purge_access_apps: true`; legacy path Access apps are stripped)
- Path: `/client/portal/{portal_uuid}` (+ APIs under that prefix)
- Unauthenticated HTML → `302` to `/api/auth/logto/login` → Logto → callback sets `cp_logto_session` and binds `logto_sub` when the email is invited
- After Logto, control plane checks email against the client allowlist (`portal_email_allowed`). Not invited → `/auth/not-invited` (not a raw OIDC error)
- `GET /api/auth/home` routes a signed-in account to **their** portal (stub for a future marketing-site login)
- Client emails: ops UI → **Settings → Users / Access** (client domain section) or CRM → client → **Portal** / Access tab / **Invite teammate**
- Clients can also invite teammates under Account → Access emails (`POST .../api/access-emails` with optional `send_invite`)
- Unified oversight + write: `GET /api/ops-users/overview`, `PATCH /api/ops-users/clients/{id}/portal-access`
- Dev access always merged via `PORTAL_DEV_EMAILS`
- Legacy path-scoped Access apps (`client-{slug}-customer-portal`) are removed on portal sync — **do not** put Authentik in front of this hub

Ops/admin hosts stay on **CF Access → Authentik**. See [operator-access.md](../operations/operator-access.md).

## Logto product SSO

| Piece | Detail |
|-------|--------|
| Logto app | Traditional web **Cronnecture customer portal** |
| Endpoint | `https://id.cronnecture.com` |
| CP env | `LOGTO_ENDPOINT` / `LOGTO_APP_ID` / `LOGTO_APP_SECRET` |
| Login | `GET https://client.cronnecture.com/api/auth/logto/login?return_to=…&portal_uuid=…` |
| Callback | `GET https://client.cronnecture.com/api/auth/logto/callback` |
| Home (stub) | `GET https://client.cronnecture.com/api/auth/home` → their portal |
| Not invited | `GET https://client.cronnecture.com/auth/not-invited` |
| Session | HttpOnly cookie `cp_logto_session` |
| Account link | `clients.contact_email` + `clients.logto_sub` |
| Gate | Invite-only: portal SPA + APIs require a valid Logto session email on the allowlist. **No public self-serve signup.** |

### Wiring a future client app (Logto SDK)

1. Logto Admin → Applications → create **SPA** or **Traditional** app (or reuse redirect URIs on the portal app).  
2. Set redirect URI(s) to your app callback (e.g. `https://app.example.com/callback`).  
3. In the app: Logto endpoint `https://id.cronnecture.com`, client id (+ secret for Traditional).  
4. Request scopes `openid profile email`; map `email` to your allowlist / tenant membership.  
5. Public Logto SIE uses **Google** (+ password/MFA) — not Authentik. Ops/edge portals stay **CF Access → Authentik**. 

SDK docs: [Logto quick starts](https://docs.logto.io/quick-starts). Fleet secrets: `vault_logto_*` (fallback `config/.identity/logto_portal_app_*`).

## Architecture

```
Internet → client.cronnecture.com (no Access on host)
  → node-tunnel → k3s_server:30080 (cf_portals.yml)
  → control-plane CustomerPortalMiddleware
       → no cp_logto_session: 302 → Logto sign-in (invited setup)
       → session + allowlist: bind logto_sub, portal HTML/APIs
       → session, not invited: 302 → /auth/not-invited
```

APIs (portal-scoped, no ops token):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `.../api/summary` | Account summary + profile |
| `PATCH` | `.../api/profile` | Client-safe profile update (validated) |
| `GET` | `.../api/billing` | Billing + invoices + pay link |
| `GET` | `.../api/documents` | Document metadata + `view_url` / `download_url`; legal docs grouped as `legal.current` / `upcoming` / `previous` + `notice` |
| `GET` | `.../api/documents/{id}/view` | Inline PDF (in-portal viewer; no forced download) |
| `GET` | `.../api/documents/{id}/download` | PDF / file download (`Content-Disposition: attachment`) |
| Public | `/legal/{slug}.pdf`, `/api/public/legal` | Latest Terms/Privacy/DPA/… PDFs (identity from platform SoT) |
| `GET` | `.../api/status` | Rich uptime payload (charts, incidents) |
| `GET` | `.../api/stats` | Compact visitor KPIs |
| `POST` | `.../api/support` | Support message to hub support email |
| `POST` | `.../api/domain-request` | Custom domain upgrade request |
| `GET/POST/DELETE` | `.../api/access-emails` | Manage portal Access OTP emails (`send_invite` on POST) |
| `PATCH` | `.../api/status-page` | Enable/disable status page |
| `GET/PATCH` | `.../api/checkout` | Checkout branding settings + readiness |
| `POST/DELETE` | `.../api/checkout/logo` | Upload / clear checkout logo |

Retired under the client portal (404): `.../api/site-builder*`. Website builder remains available to ops via `/api/clients/{id}/site-builder*`.

Legacy `/deploy` portal paths **302** to Overview.

Legacy insights hostnames are **not** on client tunnels or in `cf_clients` inventory. Do not list `insights.*` anywhere clients or CRM can see.

## Ops API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/clients` | Creates client + `portal_uuid` / `portal_url` |
| `POST` | `/api/clients/{id}/portal/provision` | Create/refresh Access; sets portal `status=active` |
| `PATCH` | `/api/clients/{id}/portal` | Update access emails |
| `POST` | `/api/clients/{id}/portal/invite` | Add Access email + optional onboarding mail |
| `GET/POST/DELETE` | `/api/clients/{id}/documents…` | CRM document management |
| `* ` | `/api/clients/{id}/site-builder…` | Ops AI site builder (not exposed to clients) |

CRM setup checklist marks **Customer portal** done only when portal status is `active`. If the chip stays on **Provision** / pending, call provision (or use the checklist action). Do not leave rows at `pending` after the portal UUID + allowlist are configured.

## Vault / env

```yaml
control_plane_portal_dev_emails: "svenbraad.work@gmail.com"
platform_client_portal_hostname: client.cronnecture.com
CLIENT_PORTAL_HOST: client.cronnecture.com
PORTAL_DEV_EMAILS: "…"
# Ops AI site builder (CRM) — not client portal
vault_openrouter_api_key: ""  # → Secret/env OPENROUTER_API_KEY; also setting openrouter_api_key
vault_firecrawl_api_key: ""   # → Secret/env FIRECRAWL_API_KEY; also setting firecrawl_api_key
```

Platform DNS/tunnel: `cf_portals.yml` entry `Client customer portal` (`skip_access: true` — Logto gates the hub in the control plane).

## Deprecations

- Platform `insights.cronnecture.com` removed (ops has Insights in Security HQ).
- Client portal **Deploy / website builder** removed (ops CRM retains site-builder tools).
- Live marketing site (`cronnecture.com`, checked 2026-07-26) has **no** `insights.*` / `portal.cronnecture.com` links. Do not reintroduce them.
