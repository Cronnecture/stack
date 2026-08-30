# Gitea (in-cluster git)

HTTPS-only Gitea for **new** tenant repos. GitHub-bound apps stay on GitHub.

## URL and login

| | |
|--|--|
| Public | https://git.cronnecture.com (**no** Cloudflare Access — Authentik OIDC, same IdP as the client hub) |
| In-cluster (Kaniko) | `http://gitea.git.svc.cluster.local:3000` |
| Admin user | `gitadmin` — password `vault_gitea_admin_password` in encrypted `ansible/config/inventory/group_vars/all/vault.yml` (also `ansible/config/.gitea/`, gitignored) |
| Clients | Per-org accounts (`{slug}/site`). Not the admin user. Hub create-repo does not need GitHub Settings. |

```bash
ansible-vault view config/inventory/group_vars/all/vault.yml | grep vault_gitea_
```

Do **not** open host `:22` for git. Gitea SSH is disabled. IMAP 993 stays closed.

## Topology (load-balanced HTTP, RWX git objects)

Cloudflare tunnel → Traefik ClusterIP `10.43.125.134:80` → IngressRoute `Host(git.cronnecture.com)` → Service `gitea.git:3000` (no session affinity; sessions in Postgres). Readiness `/api/healthz` (includes DB ping) + PDB `minAvailable: 1` so Traefik does not send to a not-ready replica.

| Workload | Replicas | Where | Notes |
|----------|----------|-------|--------|
| `gitea` Deployment | HPA min **2** / max **2–4** | `pool=general` | Max tracks Ready `compute_general` count (ceiling 4). Required hostname anti-affinity when ≥2 general workers; `ScheduleAnyway` on one node so pods do not go Pending. |
| `gitea-postgres` STS | **1** until `[db]` | `worker-general-01` | Metadata. Scales to **0** after a Ready Database_cluster postgres exists. |
| `gitea-data` PVC | **RWX** 8Gi (`nfs-rwx`) | NFS on first general worker | Git objects. Replicas can mount from any Ready general node. |
| LFS / attachments / avatars | R2 | `cronnecture-fleet-backups` prefix `gitea/` | Unchanged. |

**RWX class:** `nfs-rwx` (nfs-ganesha on `worker-general-01` + nfs-subdir-external-provisioner). Not Longhorn. Not on etcd. Not on mail-01 (Stalwart `hostPath` untouched). The NFS exporter is still a single-node SPOF for git objects until a second export exists — app pods are not sticky.

**Why not mail-01 / cp-master-01:** etcd taint stays. Mail pool stays tainted. Gitea `nodeSelector: pool=general`.

Ansible: `gitea_ha_git_storage: rwx` (live default). Do not revert to `rwo`.

## Recreate / converge

```bash
make gitea          # NFS RWX + ansible role → k3s addon
# git.cronnecture.com is skip_access (Authentik OIDC). Do not put Access back.
make site           # full converge includes gitea
make gitea-scale-hint
```

### Founder: second general worker

```bash
make pending-node IP=<vps> CLASS=general PROVIDER=<hetzner|hostinger> REGION=<hel1|fra>
# after Ready, site/gitea converge:
#   HPA max → min(4, Ready general count)
#   pod anti-affinity → requiredDuringSchedulingIgnoredDuringExecution (hostname)
#   one replica moves onto the new worker (RWX volume follows)
```

### Founder: Database_cluster

```bash
make pending-node IP=<vps> CLASS=db PROVIDER=<hetzner|hostinger> REGION=<hel1|fra>
make site
```

When `[db]` is empty, templates stay wired but the migrate job is **dry-run** and in-ns `gitea-postgres` stays 1. After a Ready postgres appears (`svc/postgres` in ns `db`, or `vault_gitea_database_host`), converge dumps the current gitea DB, restores onto the cluster, points `app.ini`/DSN at it, and scales the in-ns STS to 0.

## Backup

`backup-fleet.sh` (full) writes `gitea/gitea.sql.gz` (Postgres — in-ns STS or cluster DSN) and `gitea/gitea-data.tar.gz` (git objects) into the fleet bundle → R2. LFS blobs already live on R2 under `gitea/`.

## Webhooks

`POST https://ops.cronnecture.com/api/webhooks/gitea` (HMAC `X-Gitea-Signature` or `X-Hub-Signature-256`). Browser GET is **405 POST only**. GitHub path unchanged: `/api/webhooks/github`.

## Tenants

Each customer gets a **private Gitea org** `{slug}` and a **restricted user** `u-{slug}` (email matches Authentik). They cannot list other orgs or `gitadmin`. Kaniko clones as `c-{slug}` with a per-repo read token (in-cluster Service, not the public host).

Portal “open git” is `https://git.cronnecture.com/{slug}` (org), never `/explore`.

| Tenant | Backend |
|--------|---------|
| **New** hub create-repo / upload | Gitea `{slug}/site` |
| makeitmakesense (Bolt2841) | GitHub (unchanged) |
| NoordDrive | GitHub, locked |
| Platform sites / previews | GitHub PAT |
