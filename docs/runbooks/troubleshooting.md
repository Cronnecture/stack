# Troubleshooting

Runbook **RB-08**.

Common failures, diagnostics, and fixes.

## First steps (any issue)

```bash
cd $FLEET_ROOT
make health
/usr/local/lib/cronnecture-fleet/health-check.sh
```

Check cron logs:

```bash
tail -50 /var/log/cronnecture-fleet-health.log
tail -50 /var/log/cronnecture-fleet-backup.log
tail -50 /var/log/cronnecture-cloudflare.log
```

## Control plane / ops UI

### Health check fails

```bash
curl -v http://127.0.0.1:30080/api/health/live
curl -v http://127.0.0.1:30080/api/health
sudo k3s kubectl -n platform get pods
sudo k3s kubectl -n platform logs deploy/control-plane -c api --tail=100
sudo k3s kubectl -n platform describe pod -l app=control-plane
```

| Cause | Fix |
|-------|-----|
| Readiness timeout | `/api/stats` blocks workers — ensure 2 uvicorn workers + `/api/health/live` probes (v0.13+) |
| DB connection | Verify `vault_platform_database_url`, Supabase reachable |
| Missing vault key | `vault_control_plane_token_key`, Fernet for GitHub tokens |
| CrashLoop | Read container logs; often env from stale secret → rollout restart |
| 2 replicas unhealthy | PDB allows 1; check both pod logs — expect **2/2 Ready** per pod |

```bash
make control-plane
sudo k3s kubectl -n platform rollout restart deployment/control-plane
```

### UI blank or stale

- Hard refresh (Ctrl+Shift+R)
- Check browser console for JS errors
- Verify `?v=` cache busters in `static/dashboards/*.html` (currently `2.1.0`)

### Control-plane OOM / Wazuh memory alert

Wazuh may raise **critical** “System running out of memory” / MITRE **T1499** when the kernel OOM-killer runs. On this fleet that is usually a **pod cgroup (memcg) kill**, not host RAM exhaustion and not a DoS attack.

```bash
# Host still healthy?
free -h
# Look for memcg kills (control-plane limit is 10Gi):
sudo journalctl -k --since '24 hours ago' | grep -E 'Memory cgroup out of memory|CONSTRAINT_MEMCG|oom-kill'
sudo k3s kubectl -n platform get pods -l app=control-plane -o custom-columns=NAME:.metadata.name,MEM_LIMIT:.spec.containers[0].resources.limits.memory,RESTARTS:.status.containerStatuses[0].restartCount
sudo k3s kubectl -n platform top pods -l app=control-plane
```

| Signal | Meaning |
|--------|---------|
| `CONSTRAINT_MEMCG` + `kubepods-…-pod…` | Container hit its limit (raise limit / fix leak) |
| Host `MemAvailable` still high | Not a node outage — ignore T1499 framing |
| Recurring ~12h spikes | Scheduled job / worker burst inside control-plane |

Template SoT: `roles/control_plane/templates/platform/_deployment.j2` (`limits.memory: 10Gi`). After editing, converge `make control-plane` or patch the live Deployment + k3s manifest under `/var/lib/rancher/k3s/server/manifests/`.

### Leads inbox empty / permission denied / HTTP 500

- Vault must use **service role** key: `vault_supabase_leads_service_key`
- `main.py` must import `fetch_platform_leads` / `platform_leads_config` from `app.supabase_leads`
- Rollout restart after vault change
- Test: `curl -sf http://127.0.0.1:30080/api/leads/status` then `curl -sf http://127.0.0.1:30080/api/leads`

### Fleet Cloudflare inventory

Ops UI → **Platform → Inventory** or `GET /api/inventory`.

| Symptom | Fix |
|---------|-----|
| False "system" labels | Only `node-tunnel` is system; hostnames need cf_portals + active ingress |
| Orphan DNS/Access left over | Review list, then **Cleanup stale** (`POST /api/inventory/cleanup`) |
| Client tunnel won't delete | Cleanup stops connector first via `uninstall_client_connector` |
| Drift after manual CF edits | **Sync all** (`POST /api/inventory/sync`) or per-client **Apply tunnel** |

See [control-plane.md](../platform/control-plane.md#fleet-cloudflare-inventory), [cloudflare.md](../operations/cloudflare.md#fleet-cloudflare-inventory-ops-ui).

### Jobs stuck

```bash
sudo k3s kubectl -n platform get lease control-plane-leader
# Only one replica should hold lease
curl http://127.0.0.1:30080/api/jobs/<id>
```

Leader election failure → jobs won't sweep; restart deployment.

## Kubernetes

### Node NotReady

```bash
sudo k3s kubectl describe node <name>
journalctl -u k3s -n 100        # server
journalctl -u k3s-agent -n 100  # agent
```

Common: disk pressure, kubelet crash, network partition.

### Platform pods pending

```bash
sudo k3s kubectl -n platform describe pod <name>
```

Control plane requires `node-role.kubernetes.io/control-plane=true` label.

### Client pod crash

```bash
sudo k3s kubectl -n client-{slug} logs deploy/{app} --tail=100
sudo k3s kubectl -n client-{slug} describe pod -l app={app}
```

Check env (`DATABASE_URL`), image pull, resource quota.

### Kaniko build failed

```bash
sudo k3s kubectl -n client-{slug} get jobs
sudo k3s kubectl -n client-{slug} logs job/kaniko-build-*
```

Registry reachability: `fleet-registry.platform.svc:5000`

## Cloudflare / ingress

### Admin portal 502

```bash
systemctl status cloudflared
journalctl -u cloudflared -n 50
```

Verify tunnel ingress matches backend IP/port in CF dashboard.

### Client site 502

1. Connector running on compute node
2. Traefik listening on :80
3. IngressRoute exists in client namespace
4. `cf_clients.yml` has tunnel entry

```bash
make clients
grep -A5 "client-{slug}" config/inventory/group_vars/all/cf_clients.yml
sudo k3s kubectl -n client-{slug} get ingressroutes.traefik.io
```

### Cloudflare Access loop

- Email in `cf_access_allowed_emails`
- OAuth callback path bypassed for `/api/github/callback`

### WAF blocking legitimate traffic

- CF dashboard → Security Events
- Temporarily disable rule or lower sensitivity in `cloudflare.yml`
- `make cloudflare`

## Ansible / converge

### Playbook fails on vault

```bash
test -f ~/.ansible/vault_pass && echo ok
ansible-vault view config/inventory/group_vars/all/vault.yml | head
```

### Host unreachable

```bash
ansible -i config/inventory/hosts.ini <host> -m ping -vvv
ssh -i ~/.ssh/id_ed25519 root@<ip>
```

### Cron jobs not running

```bash
systemctl status cron
crontab -l
which crontab || apt install cron
make fleet-ops
```

## SIEM

```bash
/var/ossec/bin/agent_control -l
tail /var/ossec/logs/ossec.log
```

Dashboard 502 → Wazuh dashboard service + cloudflared on SIEM node.

## Network

### Pod can't reach Supabase

NetworkPolicy allows egress HTTPS (443). Test from pod:

```bash
sudo k3s kubectl -n client-{slug} exec deploy/{app} -- wget -qO- https://example.com
```

### Inter-node pod traffic

flannel wireguard — verify all nodes Ready, UDP open between peers (UFW peer rules).

## Log reference

| Component | Command |
|-----------|---------|
| k3s server | `journalctl -u k3s -f` |
| k3s agent | `journalctl -u k3s-agent -f` |
| cloudflared | `journalctl -u cloudflared -f` |
| control plane | `kubectl -n platform logs deploy/control-plane -c api -f` |
| Traefik | `kubectl -n kube-system logs -l app.kubernetes.io/name=traefik` |
| Ansible backup | `/var/log/cronnecture-fleet-backup.log` |

## Escalation

If unresolved → [RB-09 Incident response](incident-response.md)

## Related

- [overview.md](../operations/overview.md)
- [control-plane.md](../platform/control-plane.md)
- [cloudflare.md](../operations/cloudflare.md)
