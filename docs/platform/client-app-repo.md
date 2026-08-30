# Client app GitHub repo — deploy on Cronnecture

Operator guide for founders building a client site: what the repo must contain, how Kaniko builds it, and how Supabase / `DATABASE_URL` are wired.

Related: [RB-05 Onboard a client](../runbooks/onboard-client.md) · [supabase.md](../operations/supabase.md) · [control-plane.md](control-plane.md) · [overview.md](../operations/overview.md#client-app-image-roll) · [previews.md](previews.md)

---

## Fast path — preview from a source URL

**Do not paste this whole guide into a coding AI.** For “fully redo {site URL}” demos:

1. Ops **Infrastructure → Fleet → Previews** (`/infrastructure/previews`) → **Ship preview**
2. Paste the source URL → **Ship & deploy**
3. Copy the short **founder prompt** from the UI (also returned as `founder_prompt` from `POST /api/previews/ship`)
4. Coding AI reads `BRIEF.md` in the new repo — not this document

That path bootstraps `vite-react-ts` (or `static-vite` / `supabase-ready`), deploys to `https://previews.cronnecture.com/previews/{uuid}` with Kaniko `BASE_PATH`, and leaves secrets out of git. Details: [previews.md — Fast path](previews.md#fast-path-60-seconds--ship-preview).

For an **empty starter you style yourself**, use Ops **New blank scaffold** (`template=blank-diy`) — same Docker/nginx/`BASE_PATH` contract, plus `REQUIREMENTS.md` / `INFRA.md` in the repo. See [previews.md — Blank / DIY](previews.md#blank--diy-scaffold-empty-starter).

Use the sections below when wiring a **client production** app (from-repo / New site / Supabase / expose), not for the 60-second preview loop.

---

## Deploy path (what happens)

```
CRM Apps → from-repo / New site (bootstrap) / Rebuild & deploy
  → analyze_repo (rescan)
  → Kaniko Job in client-{slug} namespace
  → push to fleet-registry.platform.svc:5000/{ns}/{app}:{tag}
  → Deployment + Service (TCP probe on app.port)
  → optional auto-expose (Cloudflare tunnel + Traefik)
```

- **Rebuild & deploy** (`mode=rebuild`): rescan → Kaniko → roll out.
- **Roll image** (`mode=roll`): redeploy last recorded image; no rebuild.
- GitHub must be connected (OAuth or PAT) in ops Settings **only for platform sites and previews**. Customer deploys use a **per-client deploy key**, not the platform PAT.

---

## 1. Minimum repo layout

| Must exist | Why |
|------------|-----|
| At least one commit on the deploy branch (default `main`) | Empty repos cannot be scanned or built |
| `package.json` (for Node / Vite / Next stacks) | Stack detection, `npm run build` / `start` |
| Buildable app (`npm run build` for static; runnable server for APIs) | Kaniko runs the Dockerfile’s build/start |

| Strongly recommended | Why |
|----------------------|-----|
| `.env.example` (or `.env.sample` / `.env.template`) | Declares env keys the analyzer + autofill use |
| Lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, or `bun.lockb`) | Avoids `npm ci` failures |
| `.gitignore` including `.env`, `node_modules`, `dist` | Security scan fails if `.env` is committed |
| Dockerfile **or** accept fleet-generated `.fleet/Dockerfile` | Build still works without one; Vite SPAs get nginx |

**Dockerfile search order** (first match wins): `Dockerfile`, `docker/Dockerfile`, `deploy/Dockerfile`, `k8s/Dockerfile`, `.docker/Dockerfile`, then any `*Dockerfile`. Bootstrapped templates ship `.fleet/Dockerfile`.

**Never commit:** `.env`, `.env.local`, `.env.production`, keys/PEMs, `credentials.json`, vault YAML. The repo security scan marks these as **fail**.

---

## 2. Recommended stack (what works best today)

| Preference | Template / pack | Port | Notes |
|------------|-----------------|------|--------|
| **Best default** | `vite-react-ts` (pack `site`) | 80 | Static SPA → nginx; fleet Dockerfile + SPA `try_files` |
| Marketing / landing | `static-vite` | 80 | Minimal Vite, no React |
| Site + managed DB | `supabase-ready` (pack `site_supabase`) | 80 | Same as Vite + `VITE_SUPABASE_*` in `.env.example` |
| Blank / DIY preview | `blank-diy` (ship only) | 80 | Empty Vite shell + `REQUIREMENTS.md` / `INFRA.md`; no Firecrawl stub |
| Small API / webhooks | `node-api-stub` (pack `api`) | 3000 | Express; listen on `PORT` |
| Existing repo | CRM → Apps → **from-repo** | scanned | Analyzer generates/patches Dockerfile when needed |

**Go-live packs (CRM wizard)** vs app templates:

| Pack | Default DB | Typical first app |
|------|------------|-------------------|
| Site only | none | `vite-react-ts` / `static-vite` |
| Site + Supabase | Supabase (auto-create or paste) | `supabase-ready` |
| Site + billing | none | Vite site |
| Full | in-cluster Postgres | API or site + `DATABASE_URL` |

SSR (Next.js) and Node APIs are supported via generated Dockerfiles, but the **happy path** for client marketing/sites is **Vite → static nginx on port 80**.

---

## 3. Dockerfile / build requirements

### What Kaniko does

1. Shallow-clone `owner/repo` @ branch into `/workspace`.
2. If the app has a **generated** Dockerfile / extra files, write them (often `.fleet/Dockerfile` + `.fleet/nginx-spa.conf`).
3. Build with `--dockerfile=` + `--context=` (usually `.`).
4. Pass **build-args** only for frontend-prefixed keys that have values:
   - `VITE_*`, `NEXT_PUBLIC_*`, `REACT_APP_*`, `PUBLIC_*`
5. Push to private fleet registry; deploy that image.

Timeouts: job active deadline ~30m; wait ~15m.

### Fleet Vite Dockerfile (generated / bootstrapped)

Multi-stage pattern used by templates and analyzer:

- **Build:** `node:20-alpine` → install deps → `ARG`/`ENV` for `VITE_*` (etc.) → `npm run build` (or pnpm/yarn/bun).
- **Runtime:** `nginx:1.27-alpine` → copy `dist` (or Vite `outDir`) → SPA config → **EXPOSE 80**.

Your app must:

- Produce static output under `dist` (or set `outDir` in `vite.config.*` so the analyzer sees it).
- Use `npm run build` (or the PM equivalent) that exits 0.
- Prefer `base: '/'` in Vite (non-root `base` warns about asset/ingress paths).

### If you bring your own Dockerfile

- Include `EXPOSE <port>` matching the app’s listen port (TCP readiness/liveness probe uses `app.port`).
- For SPAs: nginx (or equivalent) must serve `try_files … /index.html` or the fleet will inject `.fleet/nginx-spa.conf`.
- Do **not** hardcode `ENV …PASSWORD/SECRET/TOKEN/KEY=…` — scanner fails; fleet may strip them.
- `npm ci` requires a lockfile; without one, fleet patches to `npm install`.
- Avoid `ADD http…` and `--privileged` (security **fail**).

### Node API stub shape

```
EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]   # or npm start
```

Listen on `process.env.PORT` (default 3000).

---

## 4. Env / database connection

### Two injection layers

| Layer | When | What |
|-------|------|------|
| **Build-args** | Kaniko | Non-empty `VITE_*` / `NEXT_PUBLIC_*` / `REACT_APP_*` / `PUBLIC_*` from app `env_json` after DB autofill |
| **Runtime env** | Deployment | Explicit env from `resolved_deploy_env` + **`envFrom`** secret `client-db-app` (when `attach_db=true` and client has a database) |

`attach_db` defaults to **true**. Set false only if the app must not receive the client DB secret.

### What lands in the client namespace secret (`client-db-app`)

**Supabase (auto-create or Management API sync):**

| Key | Purpose |
|-----|---------|
| `SUPABASE_URL` | `https://{ref}.supabase.co` |
| `SUPABASE_ANON_KEY` | Public anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only |
| `DATABASE_URL` | Transaction pooler `:6543` + `sslmode=require` |
| `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` | Split DSN fields |

**Manual Supabase connect:** same keys from pasted URL + anon (+ optional service role / DSN).

**In-cluster Postgres (Full pack):** `DATABASE_URL` (and related) for the namespace Postgres service.

### Autofill into app env keys (empty values only)

From `autofill_db_env` — only fills **empty** keys in the app’s env map:

| App env key pattern | Filled from | Frontend (`VITE_` / …) |
|---------------------|-------------|-------------------------|
| `*SUPABASE_URL` | `SUPABASE_URL` | yes |
| `*SUPABASE_ANON_KEY` / `*SUPABASE_PUBLISHABLE_KEY` / `*SUPABASE_KEY` | anon key | yes |
| `*SUPABASE_SERVICE_ROLE_KEY` | service role | **no** (never into frontend prefixes) |
| `*DATABASE_URL` / `*POSTGRES_URL` / `*POSTGRESQL_URL` | `DATABASE_URL` | **no** |

Empty keys are dropped at deploy so they do not override `envFrom` secret values.

### What the app must read

| Stack | Read at… | Keys |
|-------|----------|------|
| Vite SPA + Supabase JS | **Build time** (`import.meta.env`) | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` |
| Next | Build / public | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| Prisma / backend SQL | **Runtime** | `DATABASE_URL` (from env or `envFrom`) |
| Server Supabase admin | Runtime | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` — never `VITE_*` |

**Important for static Vite:** anon URL/key must be present as build-args **before** Kaniko `npm run build`. Ensure the client DB is **ready** and app env keys exist (from `.env.example` / template) so autofill can populate them. A rebuild after DB ready is required if the first build ran with empty Supabase vars.

### Local `.env.example` (do not commit secrets)

**Site only / Vite:**

```bash
VITE_APP_NAME=
VITE_API_URL=
```

**Supabase-ready:**

```bash
VITE_APP_NAME=
VITE_API_URL=
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

**Backend / Prisma:**

```bash
DATABASE_URL=
# optional for server-side Supabase:
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
PORT=3000
```

Locally: `cp .env.example .env` and fill from Supabase dashboard or ops (never commit `.env`).

---

## 5. Supabase-ready checklist (Site + Supabase)

1. **CRM pack** Site + Supabase (or Database = Supabase).
2. **Credentials:** leave blank for Management API auto-create (`client-{slug}`), **or** paste project URL + anon key.
   - Vault/Settings need `SUPABASE_ACCESS_TOKEN` + `SUPABASE_ORG_ID` (+ region) for auto-create.
3. Wait until workspace Database / DMS shows **ready** (provision polls up to ~10 minutes).
4. **App:** bootstrap `supabase-ready`, or add to an existing repo:
   - dependency `@supabase/supabase-js` (helps detection),
   - `.env.example` with `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`,
   - client init via `import.meta.env.VITE_SUPABASE_*`.
5. Keep **`attach_db` enabled** so `client-db-app` is mounted and autofill runs.
6. **Rebuild & deploy** after DB is ready so build-args bake the anon URL/key into the static bundle.
7. Use **anon** in the browser only; service role and `DATABASE_URL` stay server-side / secret.
8. Schema/migrations: apply in Supabase SQL editor or CLI against the project (fleet does not run Prisma migrate for you).

Manual fallback API shape is in [RB-05](../runbooks/onboard-client.md). Details: [supabase.md](../operations/supabase.md#client-apps).

---

## 6. Expose / domain after deploy

Prerequisites: client zone **active**, tunnel present.

| Setting | Behavior |
|---------|----------|
| `auto_expose_subdomain=www` | Routes `www.{domain}` **and** apex `{domain}` |
| `auto_expose_subdomain=@` | Apex only |
| Other subdomain | `{sub}.{domain}` only |
| Unset | Deploy succeeds; expose later via Apps → Expose |

Optional Cloudflare Access on the **site exposure** (Authentik allowlist) — separate from the customer portal, which is Authentik OIDC (`cp_oidc_session`).

If zone/tunnel is not ready at deploy time, the job logs *Skipping auto-expose* — re-expose from the UI when DNS is active.

Public traffic: Cloudflare → client tunnel → Traefik → Service → pod. Origin is not on the public internet.

---

## 7. Common failure modes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Scan / deploy: empty repo | No commits | Push code or use Bootstrap template |
| Branch not found | Wrong default branch | Set app branch to actual default (`main` / `master`) |
| Kaniko: `npm ci` failed | No lockfile | Commit lockfile or let fleet use `npm install` |
| Build: missing `VITE_SUPABASE_*` in browser | Built before DB ready / empty env | Confirm DB ready + env keys → **Rebuild & deploy** |
| Prisma / API can’t connect | No client DB or `attach_db=false` | Provision Supabase/cluster DB; enable attach; ensure `DATABASE_URL` in env or secret |
| Security fail: `.env` in repo | Secrets committed | Remove from git; keep `.env.example` only |
| SPA deep links 404 | No nginx `try_files` | Use fleet Dockerfile / `.fleet/nginx-spa.conf` |
| Port probe fails / CrashLoop | Listen port ≠ `app.port` / EXPOSE | Align listen, EXPOSE, and CRM port (80 static, 3000 Node) |
| Auto-expose skipped | Hub tenant had no client tunnel / zone | Day-1 hosts now publish on node-tunnel: `sites-{slug}.cronnecture.com` |
| 502 on hostname | Tunnel / Traefik / wrong backend | Connector install; check ingress; job logs |
| Monorepo wrong context | Nested `package.json` | Set build context / Dockerfile path in from-repo |
| SQLite warning | File DB in container | Migrate to client `DATABASE_URL` / Supabase |
| Job stuck / build timeout | Quota, registry, heavy build | `kubectl -n client-{slug} logs` on Kaniko job; [RB-12](../runbooks/registry-recovery.md) |

### Operator commands

```bash
# Deploy job
curl -sf http://127.0.0.1:30080/api/jobs/<job_id>

# Kaniko / app pods
sudo k3s kubectl -n client-{slug} get jobs,pods
sudo k3s kubectl -n client-{slug} logs job/build-<app>-<tag> -c kaniko

# DB secret keys present (values redacted in UI; raw only on-node)
sudo k3s kubectl -n client-{slug} get secret client-db-app -o jsonpath='{.data}' | jq 'keys'
```

CRM: Apps → job dock / Configure → deployment history; **Rebuild & deploy** vs **Roll image** ([overview.md](../operations/overview.md#client-app-image-roll)).

---

## Quick founder checklist

1. Prefer **Vite + React TS** (or bootstrap `supabase-ready` if using Site + Supabase).
2. Ship `package.json`, lockfile, `.env.example`, `.gitignore` (ignore `.env`).
3. No secrets in git; Dockerfile optional (fleet generates for Vite).
4. Onboard client with correct pack/DB; wait for Supabase **ready**.
5. Apps → from-repo or New site → deploy; confirm expose when zone is active.
6. After DB credentials exist, **Rebuild** once so `VITE_*` are baked in.
7. App code: frontend reads `VITE_SUPABASE_*`; backends read `DATABASE_URL` / service role at runtime.
