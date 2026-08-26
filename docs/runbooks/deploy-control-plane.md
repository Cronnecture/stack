# Deploy control plane

Runbook **RB-04**.

Build and rollout changes to the ops API and dashboard.

## When to use

- Code changes in `services/control-plane/`
- Vault changes affecting control plane env (DB URL, CF tokens, GitHub OAuth, Leads keys)
- Template changes in `platform.yaml.j2`
- Replica count or resource limit adjustments

## Prerequisites

- `FLEET_ROOT` set on control machine
- Vault password available
- kubectl access on control node

## Procedure

### 1. Pre-check

```bash
cd $FLEET_ROOT
make health
curl -sf http://127.0.0.1:30080/api/health/live
curl -sf http://127.0.0.1:30080/api/health
```

### 2. Deploy

**Recommended** (standard release — staging smoke, then production):

```bash
make release
```

Production-only (skip staging):

```bash
make deploy-production
```

Or directly:

```bash
make control-plane
```

See [deployment.md](../operations/deployment.md) and [RB-13 Staging and release](staging-and-release.md) for the full staging → production workflow.

This playbook:

1. Builds Docker image from `services/control-plane/Dockerfile`
2. Templates manifest to `/var/lib/rancher/k3s/server/manifests/control-plane.yaml`
3. `kubectl set image` triggers a rolling update (new pod before old terminates)
4. Waits for rollout — production runs **2 replicas** with `maxSurge: 1`

### 3. Watch rollout

```bash
sudo k3s kubectl -n platform rollout status deployment/control-plane --timeout=120s
sudo k3s kubectl -n platform get pods -l app=control-plane
```

### 4. Verify API

```bash
curl -sf http://127.0.0.1:30080/api/health/live
curl -sf http://127.0.0.1:30080/api/health
curl -sf https://ops.cronnecture.com/api/health/live
```

UI: hard refresh dashboard shells under `static/dashboards/*.html` (cache buster e.g. `?v=2.1.0`). Customer hub: `static/customer-portal/`.

### Hot path (control node)

Code or UI iteration — skip apt, vault re-template, and agent registries:

```bash
make control-plane-hot
```

That syncs image inputs with tar, BuildKit-builds, imports into containerd only when the image id or tag changed, then rolls the deployment. It does **not** re-template k3s manifests — hostPaths (docs at `/home/dev/stack/docs`, tool overlay at `ansible/data`) stay as last applied.

Use full `make control-plane` for vault, manifest, docs mount, or first-time converge.

Details: [control-plane.md](../platform/control-plane.md#deployment).

### 5. Vault-only changes

If you only changed vault secrets (no code):

```bash
make control-plane
sudo k3s kubectl -n platform rollout restart deployment/control-plane
sleep 10
sudo k3s kubectl -n platform exec deploy/control-plane -c api -- env | grep -E 'DATABASE|CF_|SUPABASE'
```

Confirm new values loaded (do not log secrets in tickets).

## Local development (optional)

```bash
cd services/control-plane
cp .env.example .env   # set DATABASE_URL
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Rollback

### Previous image

If old image tag still on node:

```bash
sudo k3s kubectl -n platform rollout undo deployment/control-plane
```

### Git revert

```bash
git checkout HEAD~1 -- services/control-plane/
make control-plane
```

Database migrations are forward-compatible via SQLAlchemy `create_all` — test schema changes in staging Supabase first.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| CrashLoopBackOff | `kubectl logs deploy/control-plane -c api` — usually DB URL or missing vault key |
| Pods 1/2 Ready, stale dashboard | Probes must use `/api/health/live`; image needs `--workers 2` in Dockerfile |
| 2 replicas, jobs duplicate | Check leader lease `control-plane-leader` |
| Stale UI | Bump cache version in `static/index.html` (ops + portal) |
| Leads HTTP 500 | Missing `supabase_leads` import in `main.py` or vault keys |
| Leads empty / 403 | Service role key + rollout restart |

See [control-plane.md](../platform/control-plane.md), [RB-08](troubleshooting.md).

## Related

- [supabase.md](../operations/supabase.md)
- [RB-05 Onboard a client](onboard-client.md)
