# Site previews (demos)

Public demo / preview sites for clients (or standalone demos before a full client) live on a **dedicated host**, not the marketing apex.

## URL shape

```
https://previews.cronnecture.com/previews/{UUIDv7}
```

Example: `https://previews.cronnecture.com/previews/01936c2a-…`

- Hostname: `previews.cronnecture.com` (Cloudflare proxied → `node-tunnel` → Traefik `:80`)
- Path: `/previews/{uuid}` (UUIDv7 assigned on create, same pattern as `portal_uuid`)
- Marketing `cronnecture.com` / `#pricing` etc. are **not** path-hijacked

## Auth (default)

| Mode | Status |
|------|--------|
| **public** (default) | Preferred for demos — no login; listed on the Focus View hub when live |
| `logto` | Traefik ForwardAuth → product Logto (same invite list as the customer portal). **No Cloudflare Access.** Hub listing is forced off. |
| `access` | Path-scoped Cloudflare Access on `/previews/{uuid}` (+ `/*`) using the **ops** allowlist (Authentik). Hub listing is forced off. Prefer `logto` for client demos. |

`PATCH /api/previews/{id}` with `{"auth_mode":"logto"}` (or `"access"`) gates that path and hides it from `GET /api/public/previews`. Teardown/purge removes the Access app and the Logto middleware.

## Fast path (60 seconds) — Ship preview

For founders who want “redo this site” without pasting the full [CLIENT-APP-REPO](client-app-repo.md) guide:

1. Open **Infrastructure** → **Fleet → Previews** (`/infrastructure/previews`) → **Ship preview**
2. Paste **source site URL** (e.g. `https://mysunnahshop.nl/`) + optional name/slug / `style_profile`
3. Template default: `vite-react-ts` (static → nginx :80). Optional: `static-vite` / `supabase-ready` / **`blank-diy`**
4. **Ship & deploy** — control plane (the **previews** platform system, hidden from CRM):
   - Ensures the `previews` system client (`status=platform`, namespace `previews`)
   - Creates a **new** private GitHub repo under the connected account
   - Injects **`.env.example`** (`VITE_APP_NAME`, `VITE_PREVIEW_URL`, plus template keys)
   - Injects coding rules: **`.cursor/rules/preview-infra.mdc`** + **`preview-design.mdc`** plus **`AGENTS.md`**
   - Seeds fleet Dockerfile + **`BRIEF.md`** / **`PREVIEW.md`** / **`DESIGN.md`** (AI-ready, not the ops dump)
   - Registers a `SitePreview` + backing `App` on the system client, then Kaniko-builds with `BASE_PATH=/previews/{uuid}`
5. Copy the **founder AI prompt** from the result panel → paste into your coding AI
6. Open the preview URL when the job finishes; push to `main` to auto-redeploy

Ops list is compact (name + status + relative time); details/actions open in a drawer. CRM client **Previews** tab redirects here. The `previews` slug is a **platform system** (seeded on control-plane startup, hidden from the Clients sidebar). Standalone ships attach there automatically; client-scoped ships stay on that customer.

The seeded brief + founder prompt **mandate Firecrawl** for source-site work (**scrape → classify branche → redesign per `DESIGN.md` → build → Firecrawl/visual verify**). Design system: **no boxes**, system fonts, photographic full-bleed heroes, **~20 named palettes** by branche (Agency Ember, Luxury Mono, Studio Magenta, Industrial Leaf, Cloud Sage, Ember Light, Ocean Teal, Slate Gold, Forest Lodge, Charcoal Volt, Sand Espresso, Editorial Ink, Auto Gunmetal, Wellness Grove, Legal Navy, Nightlife Signal, Nordic Ice, Craft Hearth, Civic Steel, Boutique Noir). Optional body fields `style_profile` + `branche` pre-seed BRIEF (and blank DIY); URL/name heuristics also hint when omitted. Agent must confirm from scrape. Cronnecture constraints stay short (Vite, `BASE_PATH`, no secrets, port 80) — see `REQUIREMENTS.md` / `INFRA.md` on blank DIY.

## Blank / DIY scaffold (empty starter)

For founders who will **fully style the page themselves** (no source-site redesign, no AI generate):

1. Open **Infrastructure** → **Fleet → Previews** → **New blank scaffold** (or Ship preview → template **Blank / DIY**)
2. Optional name/slug + optional `style_profile` / `branche` → **Create blank & deploy**
3. Control plane bootstraps a minimal Vite + React + TS repo with:
   - Almost-empty `src/App.tsx` (no Firecrawl stub copy — deploy classifies as **`live`**, not `scaffold`)
   - **`REQUIREMENTS.md`** + **`INFRA.md`** — hard contracts for Cronnecture (build → `dist/`, path prefix `/previews/{uuid}/`, `.fleet/Dockerfile` + nginx :80, health/probes, env, no privileged, push-to-redeploy)
   - **`DESIGN.md`** + **`AGENTS.md`** — same visual system as ship-preview (no boxes, system fonts, named palettes) + agent notes
   - Assigned style profile seeded into PREVIEW/AGENTS/founder prompt (override or name/branche heuristics)
   - Same fleet Dockerfile / nginx SPA config as other Vite ship templates
4. Clone the GitHub repo, style `src/` per `DESIGN.md`, push `main` (or Redeploy in ops)

```bash
curl -sS -X POST https://ops.cronnecture.com/api/previews/ship \
  -H "Authorization: Bearer $OPS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template":"blank-diy","name":"my-diy-site","style_profile":"nordic_ice","deploy":true}'
```

No `source_url` required for `blank-diy`. Response includes `url`, `html_url`, `founder_prompt` (DIY + DESIGN.md), `style_profile`, `mode: "blank-diy"`.

```bash
curl -sS -X POST "https://ops.cronnecture.com/api/clients/{id}/previews/ship" \
  -H "Authorization: Bearer $OPS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://mysunnahshop.nl/","template":"vite-react-ts","deploy":true}'
```

Override style (optional):

```bash
curl -sS -X POST https://ops.cronnecture.com/api/previews/ship \
  -H "Authorization: Bearer $OPS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://example-juwelier.nl/","style_profile":"luxury_atelier","branche":"jewelry","deploy":true}'
```

Standalone (no client):

```bash
curl -sS -X POST https://ops.cronnecture.com/api/previews/ship \
  -H "Authorization: Bearer $OPS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://example.com/","name":"demo","deploy":true}'
```

Response includes `url`, `html_url`, `founder_prompt`, `style_profile`, `branche`, `job_id`. Control plane does **not** scrape/redesign automatically — the coding AI does that from `BRIEF.md` + the founder prompt, using Firecrawl.

## Create from ops (existing repo / stub)

1. Open **Infrastructure** → **Fleet → Previews**
2. **New preview** → name
3. Source (any one):
   - **GitHub repository** — any repo from the connected GitHub account (`/api/github/repos`). Builds via Kaniko.
   - Leave empty for a **stub** smoke page
4. If GitHub is not connected, the repo picker shows **Settings → GitHub**
5. **Create & deploy** → job dock shows progress
6. Click a row for details → **Open** / **Redeploy** / **Take down** / **Delete**
   - **Take down** — stops workloads (Ingress/Deployment); row stays as `taken_down`
   - **Delete** — purges cluster resources and removes the DB record from the list

Standalone stub (no client):

```bash
curl -sS -X POST https://ops.cronnecture.com/api/previews \
  -H "Authorization: Bearer $OPS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Smoke demo","deploy":true}'
```

Client-scoped from a GitHub repo:

```bash
curl -sS -X POST "https://ops.cronnecture.com/api/clients/{id}/previews" \
  -H "Authorization: Bearer $OPS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme demo","github_repo":"owner/repo","deploy":true}'
```

Client-scoped from an existing app:

```bash
curl -sS -X POST "https://ops.cronnecture.com/api/clients/{id}/previews" \
  -H "Authorization: Bearer $OPS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme demo","app_id":12,"deploy":true}'
```

## Architecture (one-liner)

`previews.cronnecture.com` → node-tunnel → Traefik → `IngressRoute` `Host + PathPrefix(/previews/{uuid})` → Deployment in namespace `previews`.

```
Browser → CF (public) → node-tunnel → Traefik :80
       → IngressRoute in ns/previews (priority 100)
       → optional StripPrefix /previews/{uuid}  (Vite/static only)
       → preview Service → demo-banner nginx sidecar (HTML sub_filter)
       → site container
```

Every HTML page under `/previews/{uuid}/*` gets a subtle bottom-left **Demo Preview**
watermark (script from hub `/__cronnecture/demo-banner.js`, injected by the sidecar).
Control-plane attaches the sidecar on deploy and reconciles missing sidecars on startup.

GitHub preview Kaniko builds pass `BASE_PATH=/previews/{uuid}`: Vite uses `--base`, Next.js gets `basePath`/`assetPrefix` injected at build. Next/SSR previews keep the full path (no StripPrefix).

Hub page at `/` on the same host is a low-priority catch-all (`previews-hub`) —
a **Focus View** master-detail gallery from `GET /api/public/previews`
(same-origin; hub nginx proxies to the control plane). **Public feed is live-only**
(`status` in `live` / `ready` / `active`) — building, deploying, **scaffold**
(ship-bootstrap placeholder still waiting for a real redesign), failed, and
taken_down never appear. After each preview deploy, control-plane probes the
page for ship-stub markers (`Preview scaffold…`) and sets `scaffold` instead of
`live` when found so the public hub stays a gallery of finished demos. Ops
**Infrastructure → Previews** still lists scaffolds. Left: sticky index (name, live dot, relative time) —
**click to select**. Right: browser-frame stage with a stable iframe (screenshot
placeholder until load). Preview responses send
`Content-Security-Policy: frame-ancestors 'self' https://previews.cronnecture.com`
(Traefik `preview-embed` middleware + fleet nginx). Header search + Recent/Name sort.
Ops **Infrastructure → Previews** still shows building/down for management.
Unknown `/previews/{uuid}` paths are handled by a Traefik route at priority 10
(`previews-unknown`) and the hub nginx **302-redirects to `/`** (the gallery) —
never a bare 404 and never SPA-fallback that serves gallery HTML under the
preview path.

## API

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/previews` | List (`?client_id=` optional; `?include_taken_down=1` to show soft-stopped) |
| GET | `/api/public/previews` | Public Focus View feed — **live/ready/active only** and `gallery_visible=true` (name, url, status, `screenshot_url`, timestamps); no auth; excludes `scaffold` and live aliases. Filmstrip thumbs are live [thum.io](https://www.thum.io) screenshots; `screenshot_url` includes a `?v=` bust from `updated_at` so redesigns invalidate thum’s ~24h cache |
| POST | `/api/previews` | Create (+ optional `deploy`; accepts `app_id`, `github_repo`, `github_branch`, `image`, `gc_exempt`, `preview_uuid` to restore a known URL) |
| POST | `/api/previews/ship` | **Fast path**: `source_url` → bootstrap template repo + BRIEF → preview deploy; returns `founder_prompt` |
| POST | `/api/previews/classify-scaffolds` | Probe deployed previews; demote ship-bootstrap stubs to `scaffold` (hide from public gallery) |
| POST | `/api/previews/gc` | Nightly GC dry-run (`dry_run=1` default) or queue apply (`dry_run=0`) |
| GET | `/api/previews/{id}` | Detail + URL |
| PATCH | `/api/previews/{id}` | Update `gc_exempt` / `gallery_visible` / `notes` |
| POST | `/api/previews/{id}/deploy` | Redeploy / roll |
| POST | `/api/previews/{id}/promote-website` | Apex promote: Kaniko rebuild with empty `BASE_PATH` + platform leads `VITE_SUPABASE_*`, roll `cronnecture-website` (persist image in `platform_sites.yml`) |
| POST | `/api/previews/{id}/teardown` | Take down (remove cluster resources; keep DB row as `taken_down`) |
| DELETE | `/api/previews/{id}` | Delete / purge (teardown + remove DB row; `?purge=false` for soft take-down only) |
| GET/POST | `/api/clients/{id}/previews` | Client-scoped list / create |
| POST | `/api/clients/{id}/previews/ship` | Client-scoped fast path (same as `/api/previews/ship`) |
| POST | `/api/webhooks/github` | Push → matching apps **and** GitHub previews (rebuild) |

## Edge inventory

Declared in `cf_portals.yml` → `cf_public_sites` (with marketing hosts) and `platform_sites.yml` (`platform_previews_*`). Cloudflare sync creates DNS `previews` CNAME → tunnel. No Access app (public).

## Push-to-redeploy (GitHub)

GitHub-sourced previews share the same ops webhook as app auto-deploy:

```
https://ops.cronnecture.com/api/webhooks/github
```

On create (when `github_repo` is set), control-plane ensures a push hook on that repo (reuses the existing hook if the URL already matches). A push to `SitePreview.github_branch` enqueues `deploy_preview` with **`rebuild=true`** so Kaniko rebuilds with `BASE_PATH=/previews/{uuid}`.

- Matching is `github_repo` (case-insensitive) + exact branch; `taken_down` rows are ignored.
- App auto-deploy and preview redeploy can share one hook; the hook is removed only when **no** auto-deploy app and **no** active GitHub preview still need it.
- Webhook secret: Settings → Deploy → `github_webhook_secret` (auto-generated on first use).

## Nightly GC

Automation preset **Nightly preview GC (02:30 UTC)** → platform task `preview_gc`.

| Rule | Default | Setting key |
|------|---------|-------------|
| Purge `taken_down` rows older than N days | **7** | `preview_gc_taken_down_days` |
| Warn ops about stale **active** previews (no `updated_at` bump) | **14** days | `preview_gc_stale_days` |
| After warn, take down if still stale | **+3** days | `preview_gc_stale_grace_days` |

- Activity proxy: `updated_at` (bumped on create / redeploy / status changes). Redeploy clears `gc_warned_at`.
- Pin a demo: `PATCH /api/previews/{id}` with `{"gc_exempt": true}` (Autoklaver is auto-pinned by name).
- Hide a live alias from the public gallery (keep the URL serving): `PATCH /api/previews/{id}` with `{"gallery_visible": false}`. Autoklaver’s ship-preview UUID (`019fdbf4-…`) is hidden so only the emailed demo (`019faf42-…`) appears in Focus View.
- **Never** mutates marketing `cronnecture.com` / `www` — GC only touches `site_previews` + namespace `previews`.
- Dry-run: `POST /api/previews/gc?dry_run=1` · apply now: `POST /api/previews/gc?dry_run=0`

## Notes

- Stub previews (no image/app/repo) serve a small nginx HTML page for smoke tests.
- GitHub-sourced previews **always Kaniko-build** with `BASE_PATH=/previews/{uuid}` (never reuse an apex/client image — those use base `/` and break under PathPrefix).
  - **Vite / static nginx**: build with `vite --base=/previews/{uuid}/`, Traefik **StripPrefix** so the pod sees `/assets/...`.
  - **Next.js**: inject `basePath` + `assetPrefix` at build (embedded in the Dockerfile); Traefik does **not** strip (app expects the full path).
- **Redeploy** on a GitHub preview rebuilds by default (`POST /api/previews/{id}/deploy` with optional `{"rebuild":false}` to roll only).
- The previews hub at `/` is a low-priority catch-all with a live gallery; unknown `/previews/{uuid}` paths **302 to `/`**. Absolute `/_next` or `/assets` (or SPA links like `/diensten`) without the preview prefix still **404** on this host — if the app still navigates there, rebuild with `BASE_PATH` and set the router `basename` to `import.meta.env.BASE_URL` (Vite) / Next `basePath`.
- **Deep-link refresh** under `/previews/{uuid}/…` must stay on that preview: Traefik PathPrefix (priority ≥100) + nginx `try_files` (Vite) or Next `basePath` (no StripPrefix). If refresh shows the hub/gallery, the request left the `/previews/{uuid}` prefix (client absolute path) or the hub pod is serving a stale SPA ConfigMap (restart `previews-hub`).
- Do not print secrets; do not mutate unrelated clients when creating previews.
