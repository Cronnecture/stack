# Operations guide

Day-to-day fleet management from the control machine.

## Prerequisites

- Operator root `STACK_ROOT=/home/dev/stack` (`FLEET_ROOT=$STACK_ROOT/ansible`)
- `~/.ansible/vault_pass` present
- SSH key access to all inventory hosts
- Run commands as user with kubectl access (or `sudo k3s kubectl`)

First paying clients checklist: [first-clients.md](../business/first-clients.md). Ops planes: [control-plane.md](../platform/control-plane.md).

## Ops UI runbooks

In **Fleet → Runbooks**, each automation shows scope, typical duration, impact (Safe / Restarts / Destructive), bullet points for what it changes, and the equivalent `make` or Ansible command. Job paths: [fleet-operations.yml](../architecture/config-sources.md). Human copy: `services/control-plane/app/fleet_runbook_meta.py`.

## Makefile reference

```bash
cd /home/dev/stack

make help              # List targets
make ping              # SSH connectivity
make check             # Syntax-check playbooks
make deploy            # stack.yml + operator images
make stack             # stack.yml, no image rebuild
make site              # Full converge (baseline→…→identity→stack)
make baseline          # Hardening + tunnel only
make cluster           # k3s only
make control-plane     # Ops API + registry (production playbook)
make release           # Staging → smoke → production (standard)
make deploy-staging    # Staging sandbox only (:30081)
make deploy-production # Production only with health gates
make cloudflare        # Edge policy + portals
make lockdown          # Verify CF SSH, then close public :22
make clients           # Sync client tunnels
make fleet-ops         # Backup/health cron + ansible-runner unit
make monitoring        # Prometheus + Alertmanager + kube-state-metrics + node-exporter
make mail              # Stalwart mail stack
make backup            # Manual fleet backup
make restore-drill     # Scratch restore proof (non-destructive)
make health            # Synthetic health check
make add-node IP=x     # Bootstrap → autoplace → site
make rebalance         # Placement audit
make cf-mint ARGS="..." # Mint CF tokens
make r2-registry       # R2 bucket + S3 keys in vault (see RB-12)
make ci                # Vault-less local gate (same as GitHub Actions)
make cp-images         # Compare staging vs production CP image tags
```

Local PR checklist: [contributing.md](../contributing.md).

## Full convergence

```bash
cd /home/dev/stack
make add-node IP=1.2.3.4   # preferred for new VPS (ends in site.yml)
# or after inventory is already correct:
make site
```

Expected duration: 10–30 minutes depending on image builds.

Scope with tags or single playbooks:

```bash
ansible-playbook playbooks/site.yml --tags cloudflare,clients
ansible-playbook -i config/inventory/hosts.ini playbooks/control_plane.yml
ansible-playbook -i config/inventory/hosts.ini playbooks/cloudflare.yml --limit localhost
```

## Automated maintenance (cron on control node)

Installed by `fleet_ops` role:

| Schedule | Task | Log |
|----------|------|-----|
| `0 3 * * *` | etcd snapshot | `/var/log/k3s-etcd-snapshot.log` |
| `15 3 * * *` | Fleet backup | `/var/log/cronnecture-fleet-backup.log` |
| `*/15 * * * *` | Health check (+ email on fail) | `/var/log/cronnecture-fleet-health.log` |
| `*/5 * * * *` | Incident watchdog (**self-heal on**, `FLEET_AUTOHEAL=1`) | `/var/log/cronnecture-fleet-watchdog.log` |

### Watchdog auto-heal vs alert-only

The control-node cron runs `incident-watchdog.sh` every **5 minutes** with heal enabled. Day-to-day status is **Fleet → Self-heal** (`/infrastructure/selfheal`); legacy `/quickops*` redirects there. Manual Incident / Tooling / Clients click-ops are gone from chrome — use cron/CLI for runbooks.

| Auto-heals (safe, rate-limited) | Alert / email only (never auto) |
|--------------------------------|----------------------------------|
| Restart down critical units (`k3s`, `k3s-agent`, `cloudflared`, `fail2ban`, `cron`) | Host unreachable over SSH |
| Restart `k3s-agent` on NotReady nodes | Kubernetes API outage (after debounce) |
| Delete crash-loop / ImagePull pods (K8s reschedules) | Node Memory/Disk/PID pressure |
| Journal vacuum + image prune when root disk ≥ 90% | Platform deployments below desired replicas |
| Client HTTPS 5xx: rewrite stale tunnel origin (localhost/node IP → Traefik ClusterIP), else restart `cloudflared-client-<slug>` | IP block, node isolate, arbitrary service restart — **CLI only** (`make block-ip` / `isolate-node` / `restart-service`) |

Audit JSONL: `/var/log/cronnecture-incidents.jsonl`. Cooldowns under `/var/lib/cronnecture-incidents/` prevent heal loops.
| `*/2 * * * *` | Prometheus textfile metrics (backup/health/jobs) | `/var/log/cronnecture-fleet-metrics.log` |
| `0 6 * * 1` | Rebalance audit | `/var/log/cronnecture-fleet-rebalance.log` |
| `0 * * * *` | Cloudflare sync | `/var/log/cronnecture-cloudflare.log` |
| `0 2 * * 0` | CF orphan dry-run → alerts@ (+ Webhooky) | `/var/log/cronnecture-fleet-orphan-cleanup.log` |
| `0 3 * * 1` | CF orphan apply (disabled by default) | same |

**Operator email alerts:** health / backup / watchdog failures call `lib/notify-ops.sh` (control-plane SMTP → `FLEET_NOTIFY_TO`, comma-separated, default `alerts@cronnecture.com,svenbraad.work@gmail.com`, 1h subject cooldown). From address stays platform SMTP (`noreply@`). Watchdog also dedupes by open-incident fingerprint (email only on transition / new keys, after `FLEET_NOTIFY_MIN_FAILS` consecutive failing runs). Cron jobs set `PATH` including `/usr/local/bin` so `k3s`/`kubectl` resolve. State: `/var/lib/cronnecture-notify/`, `/var/lib/cronnecture-incidents/`. Open alerts in **Webmail** → `alerts@cronnecture.com` (or `https://ops.cronnecture.com/webmail`).

### Prometheus → Alertmanager (Ops confidence)

Deeper push alerts live in the `monitoring` namespace (plain Prometheus + Alertmanager + kube-state-metrics — no operator CRDs):

| Alert | Signal |
|-------|--------|
| `NodeFilesystemAlmostFull` / `NodeFilesystemCritical` | node-exporter root filesystem free % |
| `KubeNodeDiskPressure` / `KubeNodeNotReady` | kube-state-metrics |
| `BackupR2SyncStale` / `BackupOnsiteStale` | textfile metrics from `.r2-last-sync` / backup `STATUS=ok` |
| `FleetHealthCheckFailed` / `FleetWatchdogIncidents` | textfile from health/watchdog |
| `FleetDeployOrConvergeFailed` | failed `Job` / `Deployment` rows in control-plane DB |

Rules ConfigMap: `monitoring/prometheus-rules`. Alertmanager routes **critical/warning → ops email** via host webhook `cronnecture-alertmanager-webhook` → `notify-ops.sh` (same SMTP path as health/backup). Alertmanager uses `hostNetwork` on the control node to reach `http://127.0.0.1:9095/webhook`. Ops push (Webhooky) is wired when `vault_slack_webhook_url` is set — Alertmanager `ops-slack` receiver POSTs **Alertmanager webhook JSON** to that URL (`webhook_configs`, not Slack client — Webhooky returns non-Slack JSON). Critical keeps email + push (`continue: true`).

**Rotate ops webhook:** `ansible-vault edit config/inventory/group_vars/all/vault.yml` → update `vault_slack_webhook_url` → `make monitoring` (syncs `monitoring/alertmanager-slack` secret). Never commit the plaintext URL.

```bash
make monitoring          # apply stack + metrics cron + notify webhook
# Verify rules loaded:
kubectl -n monitoring port-forward svc/prometheus 9090:9090
# open http://127.0.0.1:9090/alerts
kubectl -n monitoring exec deploy/prometheus -- wget -qO- http://127.0.0.1:9090/api/v1/rules
# Smoke (Alertmanager hostNetwork on control node → webhook → notify-ops email):
curl -sS -H 'Content-Type: application/json' \
  -d '[{"labels":{"alertname":"OpsAlertSmoke","severity":"critical"},"annotations":{"summary":"smoke — ignore"},"startsAt":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}]' \
  http://127.0.0.1:9093/api/v2/alerts
# or hit the bridge directly:
curl -sS -H 'Content-Type: application/json' \
  -d '{"status":"firing","alerts":[{"labels":{"alertname":"OpsAlertSmoke"},"annotations":{"summary":"smoke"}}]}' \
  http://127.0.0.1:9095/webhook
```

**Silence** (while port-forwarding Alertmanager):

```bash
# UI: http://127.0.0.1:9093/#/silences
amtool --alertmanager.url=http://127.0.0.1:9093 silence add alertname=NodeFilesystemAlmostFull --duration=4h --comment='maintenance'
amtool --alertmanager.url=http://127.0.0.1:9093 silence query
```

Textfile dir on every node: `/var/lib/node_exporter/textfile/` (control node writes `cronnecture-fleet.prom`).

Manual runs:

```bash
make health
make backup
./scripts/fleet/rebalance.sh
/usr/local/lib/cronnecture-fleet/write-fleet-metrics.sh
```

## kubectl access

From control node:

```bash
sudo k3s kubectl get nodes -L pool,node-class
sudo k3s kubectl -n platform get pods
```

Or fetch kubeconfig locally:

```bash
ansible-playbook -i config/inventory/hosts.ini playbooks/fetch-kubeconfig.yml
export KUBECONFIG=~/.kube/k3s.yaml
```

## Health verification

```bash
# Lightweight probe (matches K8s readiness/liveness)
curl -sf http://127.0.0.1:30080/api/health/live

# Full check including DB
curl -sf http://127.0.0.1:30080/api/health
# {"status":"ok"}

/usr/local/lib/cronnecture-fleet/health-check.sh
```

External:

```bash
curl -sf https://ops.cronnecture.com/api/health/live
curl -sf https://ops.cronnecture.com/api/health
```

Control plane pods should show **2/2 Ready** (2 uvicorn workers per pod). If one replica flaps, see [RB-08](../runbooks/troubleshooting.md#control-plane--ops-ui).

## Common workflows

| Task | Command / runbook |
|------|-------------------|
| Add VPS | Ops **Fleet → Nodes**, [RB-01](../runbooks/add-node.md), or `make add-node IP=x` |
| Remove VPS | [RB-02](../runbooks/remove-node.md) |
| Upgrade k3s | [RB-03](../runbooks/upgrade-k3s.md) |
| Deploy ops UI changes | [RB-04](../runbooks/deploy-control-plane.md) |
| **Cluster maintenance page** | Ops UI → **Home** or **Automations** → **Cluster maintenance**; served at **Cloudflare edge** for **client + marketing** hostnames (see [maintenance.md](maintenance.md)); auto-enabled during **control_plane**, **cluster**, **site**, **Platform refresh** jobs; ops/webmail/portal host bypassed |
| New client | [RB-05](../runbooks/onboard-client.md) |
| Self-serve Pilot | Public [client.cronnecture.com/start](https://client.cronnecture.com/start); live pay gated until KVK/VAT (~2026-08-18) — see [stripe-billing.md](../platform/stripe-billing.md#self-serve-standard-pilot) |
| Audit Cloudflare drift | Ops UI → **Platform → Inventory** ([control-plane.md](../platform/control-plane.md#fleet-cloudflare-inventory)) |
| Baseline / cluster / CF sync | Ops UI → **Platform → Fleet** → **Infrastructure operations** |
| Cordon / drain a node | Ops UI → **Platform → Fleet** → node **Actions** |
| Delete a contact lead | **Platform → Leads** → **Delete** (requires `vault_supabase_leads_service_key`) |
| Rotate CF tokens | [RB-06](../runbooks/cloudflare-tokens.md) |
| R2 registry setup | [RB-12](../runbooks/registry-recovery.md), `make r2-registry` |
| Restore from backup | [RB-07](../runbooks/backup-restore.md) |
| Something broken | [RB-08](../runbooks/troubleshooting.md) |

## Vault operations

```bash
ansible-vault view config/inventory/group_vars/all/vault.yml
ansible-vault edit config/inventory/group_vars/all/vault.yml
```

After vault changes affecting control plane:

```bash
make control-plane
sudo kubectl -n platform rollout restart deployment/control-plane
```

Wait 8s for k3s to reconcile secrets if manifest changed.

## Logs

| Component | Location |
|-----------|----------|
| Control plane API | `kubectl -n platform logs deploy/control-plane -c api` |
| k3s | `journalctl -u k3s -f` |
| cloudflared | `journalctl -u cloudflared -f` |
| Wazuh | SIEM node `/var/ossec/logs/` |
| Ansible cron | `/var/log/cronnecture-*.log` |
| Restore fire drill | Host cron log `/var/log/cronnecture-fleet-restore-drill.log`; JSONL `/var/log/cronnecture-fleet/restore-drill.jsonl` |
| Break-glass pack | `/var/log/cronnecture-fleet-break-glass.log`; JSONL `/var/log/cronnecture-fleet/break-glass.jsonl` |

## Scheduled restore fire drill

Weekly **Sunday 05:30 UTC** (after break-glass at 04:00):

| Path | Detail |
|------|--------|
| Host cron | `cronnecture restore fire drill` on k3s server → `restore-drill.sh` |
| Automation | Ops UI → **Automation** → preset **Weekly restore fire drill** (`restore_drill`, `30 5 * * 0`, enabled) |
| Manual | `make restore-drill` (scratch only — never overwrites production) |
| Logs | `/var/log/cronnecture-fleet-restore-drill.log` + `/var/log/cronnecture-fleet/restore-drill.jsonl` |

## Scheduled CF orphan cleanup (DNS / Access / tunnels)

Weekly **Sunday 02:00 UTC** dry-run only (default). Never touches `node-tunnel`, declared portals/SSH, or DNS in zone `cronnecture.eu`.

| Path | Detail |
|------|--------|
| Host cron | `cronnecture cf orphan dry-run` → `cf-orphan-cleanup.sh --dry-run` |
| Automation | Ops UI → **Automation** → **Weekly CF orphan dry-run** (`inventory_cleanup_report`, `0 2 * * 0`) |
| Report | Email `alerts@` (via notify-ops / platform SMTP); Webhooky when `vault_slack_webhook_url` is set |
| Evidence | `/var/lib/cronnecture-orphan-cleanup/last-dry-run.json` |
| Manual | `make orphan-cleanup` (dry-run) |
| Logs | `/var/log/cronnecture-fleet-orphan-cleanup.log` |

**What the report lists:** orphan tunnels, DNS records, platform ingress routes, and Access apps that cleanup would remove — plus `skipped_protected` (node-tunnel / portals / `cronnecture.eu`).

### Enable Monday apply (opt-in)

Apply stays **off** until you have reviewed Sunday dry-run evidence:

1. Confirm candidates in the Sunday email / evidence JSON.
2. Edit `/etc/cronnecture/orphan-cleanup-allowlist.conf` — one hostname/tunnel/Access domain per line, or a single `*` to accept the full dry-run set.
3. In inventory/group vars (or ad-hoc): set `fleet_ops_orphan_cleanup_apply_enabled: true`.
4. `make fleet-ops` (installs Monday `0 3 * * 1` cron).
5. Or one-shot: `ORPHAN_APPLY=1 make orphan-cleanup` (still requires fresh evidence + non-empty allowlist).

Do **not** re-enable unattended `inventory_drift_cleanup` from Automation — that path is retired for schedules; use **Fleet → Cluster** orphan sweep (confirm-gated) instead.

## Client app image roll

CRM → client → **Apps**:

- **Rebuild & deploy** — rescan GitHub, Kaniko build, push to fleet registry, roll out (`POST …/apps/{id}/deploy` with `{"mode":"rebuild"}`).
- **Roll image** — redeploy the last recorded image without rebuilding (`{"mode":"roll"}`).
- Cards show **image tag**, job status (`deploying` / `building`), and **Auto-deploy** when GitHub push-to-deploy is on (Configure → **Deploy on push**).
- Deployment history (Configure) lists recent tags/triggers; rollback from a prior succeeded deploy.

## Related docs

- [runbooks/README.md](../runbooks/README.md)
- [control-plane.md](../platform/control-plane.md)
- [backup.md](backup.md)
