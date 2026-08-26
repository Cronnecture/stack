# Safe deployments — staging sandbox + zero-downtime production

Build and test changes without touching live client traffic, then promote to production with rolling updates.

**Step-by-step runbook:** [RB-13 Staging and release](../runbooks/staging-and-release.md)  
**Staging database:** [supabase.md](supabase.md#staging-project)  
**Mail / PTR (Hostinger):** [mail.md](mail.md)

## The problem

Running `make control-plane` on a live fleet used to:

- Restart the **only** control-plane pod before the new one was ready (API blip)
- Deploy directly to production with no sandbox
- Use `rollout restart`, which ignores rolling-update strategy

Client apps on Traefik may stay up, but the ops API, webmail, and deploy pipeline all blink offline during platform upgrades.

## The solution

| Layer | What it does |
|-------|----------------|
| **Staging environment** | Separate k8s namespace (`platform-staging`), NodePort 30081, own Supabase project |
| **Zero-downtime rollout** | `maxSurge: 1`, `maxUnavailable: 0` — new pod starts before old terminates |
| **Production replicas** | 2 pods in production (requires Supabase **transaction pooler**, port 6543) |
| **Immutable image tags** | `control-plane:<git-sha>` instead of only `:latest` |
| **Release script** | `make release` — staging smoke, then production with health gates |

## Daily workflow

### Standard release (recommended)

```bash
make release
```

This runs:

1. **Staging deploy** — builds image, deploys to `platform-staging` (NodePort 30081)
2. **Staging smoke** — `/api/health/ready`, maintenance API, platform readiness
3. **Production deploy** — zero-downtime rolling update on `platform` (NodePort 30080)
4. **Production smoke** — same checks on port 30080

Production is never touched until staging passes smoke tests.

**Prerequisite:** one-time staging setup ([RB-13](../runbooks/staging-and-release.md)) — Supabase project, staging vault, optional DNS.

```bash
# Emergency production-only (skip staging)
SKIP_STAGING=1 make release

# Prompt before production promote
CONFIRM=1 make release
```

### Manual steps (same flow, split)

```bash
make deploy-staging        # sandbox only — NodePort 30081
make deploy-production     # production only — health gates, zero-downtime
make control-plane         # production playbook without deploy script gates
```

Staging shares the production mail stack and container registry. It never modifies the `platform` namespace or client Traefik routes.

Production deploy:

1. Runs `make health` first — aborts if fleet is unhealthy
2. Builds image tagged with current git SHA
3. `kubectl set image` triggers a **rolling** update (not restart)
4. Waits for `/api/health/ready` on NodePort 30080

Client websites stay online. Auto-maintenance during fleet jobs shows the maintenance page on **client hostnames at the Cloudflare edge** — ops and webmail stay reachable. See [maintenance.md](maintenance.md).

### Full stack changes (mail, cluster, etc.)

Use staging for control-plane code. For infrastructure playbooks (`make mail`, `make site`):

- Schedule a maintenance window, **or**
- Enable maintenance mode in ops → Home before running
- Mail (Stalwart) still uses `Recreate` strategy — brief SMTP gap on `make mail`

See [mail.md](mail.md) for PTR and deliverability.

## Environment layout

```
config/environments/
  production/group_vars/all/main.yml   ← 2 replicas, platform namespace, :30080
  staging/group_vars/all/main.yml      ← 1 replica, platform-staging, :30081
  staging/group_vars/all/vault.yml     ← staging Supabase URI only (encrypted)
```

Scripts:

| Script | Purpose |
|--------|---------|
| `scripts/fleet/release-control-plane.sh` | `make release` |
| `scripts/fleet/deploy-control-plane.sh` | `make deploy-staging` / `make deploy-production` |

## Requirements

| Setting | Production | Staging |
|---------|------------|---------|
| Supabase | Transaction pooler URI (port **6543**) | Separate project, same pooler port |
| DNS | `ops.{zone}`, `webmail.{zone}` | `staging-ops.{zone}` → tunnel |
| NodePort | 30080 | 30081 |

## Rollback

```bash
# Undo last production rollout
sudo k3s kubectl -n platform rollout undo deployment/control-plane

# Or redeploy previous git commit
git checkout <sha> -- services/control-plane/
make deploy-production
```

## What still causes downtime

| Operation | Impact | Mitigation |
|-----------|--------|------------|
| `make release` / `make deploy-production` | **None** on client sites (rolling, 2 replicas) | Default for code changes |
| `make mail` | Brief SMTP/IMAP gap | Schedule off-peak; maintenance mode — [mail.md](mail.md) |
| `make site` | Cumulative | Never on live fleet; staging + targeted playbooks |
| `make cluster` | k3s API restart | Use `upgrade.yml` rolling playbook |
| Single compute node | Worker loss = client outage | Add 2nd compute node (RB-10) |

## Related

- [runbooks/staging-and-release.md](../runbooks/staging-and-release.md) — **primary runbook**
- [runbooks/deploy-control-plane.md](../runbooks/deploy-control-plane.md)
- [runbooks/cloudflare-tokens.md](../runbooks/cloudflare-tokens.md)
- [runbooks/scale-to-ha.md](../runbooks/scale-to-ha.md)
- [supabase.md](supabase.md)
- [mail.md](mail.md)
- [maintenance.md](maintenance.md)
- [resilience.md](../architecture/resilience.md)
