# SIEM (Wazuh) — retired

**Status (2026-08-26):** Wazuh is **not running**. Inventory group `[siem]` is empty. `72.60.32.178` is `worker-general-02`, not a SIEM host. `wazuh.cronnecture.com` must not be treated as a live dashboard. Cloudflare `cf_autoblock_*` keys remain in policy with **no manager to fire them**.

The rest of this file is the **historical** Wazuh operations manual, kept so the playbooks can be revived. Do not follow it as current incident response.

---

# SIEM (Wazuh) — historical runbook

## Architecture

SIEM hosts are **dual-role** in inventory:

| Group | Purpose |
|-------|---------|
| `[siem]` | Wazuh manager, indexer, dashboard (systemd) |
| `[compute_siem]` | k3s agent pool (`pool=siem`, tainted `NoSchedule`) |

The control plane treats SIEM nodes as first-class fleet members — visible in **Fleet → Topology** / **Nodes**, scalable via the same `make cluster` / `add-node.sh` flow as compute pools. Wazuh stays on systemd (not in-cluster pods); the k3s join gives the master unified node visibility, labels, and future scheduling hooks.

```
Every node (except siem)          SIEM node (k3s agent + Wazuh)
┌─────────────────────┐          ┌─────────────────────┐
│ wazuh-agent         │  ──────► │ wazuh-manager       │
│ auditd              │   1514   │ wazuh-indexer       │
│ FIM, rootkit, logs  │          │ wazuh-dashboard :5601│
└─────────────────────┘          │ pool=siem (tainted) │
                                 └──────────┬──────────┘
                                            │
                                   active response
                                            ▼
                                   Cloudflare IP block
```

Join SIEM into the cluster after inventory registration:

```bash
make cluster
# or: ansible-playbook playbooks/cluster.yml --limit compute_siem
```

Verify:

```bash
kubectl get nodes -l pool=siem
```

## Deployment

```bash
make siem
# ansible-playbook playbooks/siem.yml
```

Components (Ansible role `siem_server`):

- **Wazuh indexer** — OpenSearch backend
- **Wazuh manager** — rules, decoders, active response
- **Wazuh dashboard** — Kibana-like UI on `:5601`

Agents installed by `siem_agent` role on all other inventory hosts during `make baseline` / `make site`.

## Access

| Method | URL |
|--------|-----|
| Public (recommended) | `https://wazuh.<platform-zone>` — Cloudflare Access; do **not** expose `:5601` on the public internet |
| Break-glass | SSH to the SIEM host (CF Access SSH), then `https://127.0.0.1:5601` over that session |

UFW on `[siem]` does not publish 5601 publicly — only peer/tunnel paths.

**Wrong login page (e.g. Wazuh URL shows Rancher or redirects to `argocd.*`):** Cloudflare Access apps are out of sync — duplicate apps, legacy `argocd` apps, or a Rancher Access app bound to the wrong hostname. In ops: **Security → Fix portals (reconcile + cloudflare)**, or `make cloudflare` after removing stale apps. Each portal in `cf_portals.yml` must have its **own** Access application (unique app per hostname).

Cloudflare tunnel ingress from `cf_portals.yml`:

- Hostname: `wazuh.<cf_zone>` (not legacy names like `argocd.*` — run **Fleet → cloudflare** or **Security → Sync Cloudflare portals** if DNS/Access is wrong)
- Backend: first `[siem]` host
- Scheme: HTTPS (`origin_no_tls_verify: true` for self-signed cert)
- Access: Authentik OIDC (emails from `ops_users` / `cf_access_allowed_emails`)

## Credentials

In vault:

| Key | Purpose |
|-----|---------|
| `vault_wazuh_api_password` | Wazuh Manager API (`wazuh` / `wazuh-wui`) — used by ops Security HQ |
| `vault_wazuh_indexer_password` | Indexer admin — alerts search + dashboard login |
| `vault_wazuh_registration_password` | Agent enrollment |
| `vault_cf_block_token` | Auto-block at CF edge (SIEM node only) |

Default indexer user in group_vars: `admin`.

## Control plane (Security HQ)

Ops (`https://ops.<zone>/security`) treats Wazuh as the **engine**, not the primary UI:

| Page | Source |
|------|--------|
| Overview / Agents / Coverage | Manager API `:55000` |
| Alerts | Indexer `:9200` (`wazuh-alerts-*`) |
| Engine | Manager + indexer health; break-glass link to Wazuh dashboard |

Filebeat must ship `/var/ossec/logs/alerts/alerts.json` into the indexer. OpenSearch 2.x needs `compatibility.override_main_response_version: true` (set by the `siem_server` role) so Filebeat 7.10 bulk indexing works.

**Noise suppression (k3s):** `local_rules.xml` on the manager silences auditd promiscuous-mode (`80710`) and containerd rootcheck hits (`521`). Agents also ignore `/var/lib/rancher/k3s` and `/var/lib/containerd` in rootcheck/FIM. Security HQ hides those rule IDs from signal views by default.

**Memory / T1499 caveat:** Kernel OOM-killer events often surface as Wazuh critical “System running out of memory” with MITRE **T1499**. On this fleet that is usually a **Kubernetes memcg** kill (container hit its memory limit — e.g. `platform/control-plane` at **`10Gi`**), not host DoS. Confirm with `journalctl -k` for `CONSTRAINT_MEMCG` and `free -h` before treating it as node availability risk — see [RB-08](../runbooks/troubleshooting.md#control-plane-oom--wazuh-memory-alert).

## What agents monitor

| Capability | Description |
|------------|-------------|
| File integrity (FIM) | Critical paths, config changes |
| Rootkit detection | Known rootkit signatures |
| Log analysis | syslog, auth, web server logs |
| Vulnerability detection | CVE correlation (when feeds enabled) |
| auditd integration | Identity changes, k3s token access |

Host hardening (baseline role) complements SIEM:

- fail2ban on SSH
- UFW default-deny
- unattended-upgrades

## Auto-block workflow

Configured in `config/policies/cloudflare.yml`:

```yaml
cf_autoblock_enabled: true
cf_autoblock_min_alert_level: 10
cf_autoblock_note_prefix: "wazuh-autoblock"
```

1. Attack triggers Wazuh rule (level ≥ 10)
2. Active response script on manager calls Cloudflare API
3. IP blocked account-wide at edge
4. `make cloudflare` (hourly cron) prunes blocks older than 24h

Verify auto-block token is only on SIEM node (least privilege).

## Common operations

### Check agent connectivity

On SIEM node:

```bash
/var/ossec/bin/agent_control -l
```

### Restart Wazuh stack

```bash
systemctl restart wazuh-manager
systemctl restart wazuh-indexer
systemctl restart wazuh-dashboard
```

### View manager logs

```bash
tail -f /var/ossec/logs/ossec.log
tail -f /var/ossec/logs/alerts/alerts.log
```

### Re-enroll agent

On worker node:

```bash
systemctl restart wazuh-agent
```

If registration fails, check `vault_wazuh_registration_password` and manager firewall (cluster peers allowed).

## Scaling

Placement policy (`config/policies/placement.yml`):

- 1 SIEM manager from 3+ fleet nodes
- 2 managers from 10+ nodes (manual failover planning)

Adding a second SIEM node: [RB-01 Add a node](../runbooks/add-node.md) with `CLASS=siem`. The host is registered under both `[siem]` and `[compute_siem]`, then `make cluster` joins it as a tainted agent.

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Dashboard 502 | Check cloudflared on SIEM + Wazuh dashboard service |
| No agents | `agent_control -l`; verify port 1514 from peers |
| Auto-block not firing | Test alert level; verify `vault_cf_block_token` on SIEM |
| High disk use | Index retention policies in indexer config |

See [RB-08 Troubleshooting](../runbooks/troubleshooting.md), [RB-09 Incident response](../runbooks/incident-response.md).

## Related docs

- [cloudflare.md](cloudflare.md) — auto-block and portal access
- [security.md](security.md)
- [overview.md](../architecture/overview.md)
