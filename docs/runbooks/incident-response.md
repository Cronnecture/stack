# Incident response

Runbook **RB-09**.

Checklist for outages, security incidents, and data loss events.

## Severity levels

| Level | Definition | Example |
|-------|------------|---------|
| SEV-1 | Full platform down | k3s API down, all client sites 502 |
| SEV-2 | Partial outage | Ops UI down, or one client affected |
| SEV-3 | Degraded | Slow builds, single pod crash looping |
| SEV-4 | Security event | Suspected breach, leaked token |

## Immediate actions (all severities)

1. **Assess scope** — what is down? since when?
2. **Do not panic-delete** — preserve logs and snapshots
3. **Run health check:**

```bash
cd $FLEET_ROOT
make health
/usr/local/lib/cronnecture-fleet/health-check.sh
```

4. **Capture state:**

```bash
date -u > /tmp/incident-$(date +%s).log
sudo k3s kubectl get nodes >> /tmp/incident-*.log
sudo k3s kubectl get pods -A >> /tmp/incident-*.log
curl -sf http://127.0.0.1:30080/api/health/live >> /tmp/incident-*.log || true
curl -sf http://127.0.0.1:30080/api/health >> /tmp/incident-*.log || true
```

## SEV-1: Full platform outage

### Triage order

| Check | Command |
|-------|---------|
| k3s server alive | `systemctl status k3s` on `31.97.126.9` |
| Nodes Ready | `sudo k3s kubectl get nodes` |
| Platform pods | `sudo k3s kubectl -n platform get pods` |
| etcd | `sudo k3s check-config` |
| Disk full | `df -h` on server |

### Recovery paths

1. **Service restart** (fastest):

```bash
sudo systemctl restart k3s
sudo k3s kubectl -n platform rollout restart deployment/control-plane
```

2. **etcd restore** — [RB-07](backup-restore.md)

3. **Full rebuild** — [bootstrap.md](../operations/bootstrap.md)

### Communication

- Note start time, impact (all clients vs ops only)
- ETA after triage (15 min reassess)

## SEV-2: Partial outage

### Ops UI down, cluster healthy

- Cloudflare tunnel: `systemctl status cloudflared` on k3s_server
- Direct test: `curl http://127.0.0.1:30080/api/health/live` then `/api/health`
- [RB-04 Deploy control plane](deploy-control-plane.md)

### Client sites down, ops UI up

- Compute node status
- Traefik + connector on `135.181.58.45`
- `make clients`
- Per-client: IngressRoute + tunnel in CF dashboard

### Supabase unavailable

- Supabase status page
- Control plane will fail health if DB down
- Client apps with Supabase deps also affected
- Enable PITR restore if data corruption

## SEV-3: Degraded performance

```bash
sudo k3s kubectl top nodes 2>/dev/null || true
make rebalance
```

- Single compute node → high CPU/memory → plan second worker ([RB-10](scale-to-ha.md))
- Kaniko queue → check build jobs, registry disk

## SEV-4: Security incident

### Suspected credential leak

1. **Rotate immediately** — [RB-06 Cloudflare tokens](cloudflare-tokens.md)
2. Rotate Supabase passwords in dashboard + vault
3. Rotate GitHub OAuth app secret
4. `ansible-vault edit` → new `vault_control_plane_token_key` invalidates stored GitHub tokens — users re-connect
5. Review Wazuh alerts for exfiltration / lateral movement
6. Check CF audit log for DNS/tunnel changes

### Active attack

- Wazuh auto-block should fire at level ≥ 10
- Manual block in CF dashboard if needed
- Increase WAF sensitivity temporarily
- Preserve `/var/ossec/logs/alerts/` for forensics

### Compromised node

1. Cordon: `kubectl cordon <node>`
2. Capture logs (Wazuh, auditd)
3. Drain if safe — [RB-02 Remove node](remove-node.md)
4. Rebuild VPS from clean image
5. Re-add via [RB-01](add-node.md)

## Post-incident

- [ ] Root cause documented
- [ ] Timeline recorded
- [ ] Backup verified post-fix (`make backup`)
- [ ] Runbooks updated if gap found
- [ ] Tokens rotated if any doubt

## Contacts & access

| System | Access path |
|--------|-------------|
| Ops UI | `https://ops.cronnecture.com` |
| Wazuh | `https://wazuh.cronnecture.com` |
| Cloudflare | dashboard.cloudflare.com |
| Supabase | supabase.com dashboard |
| VPS provider | Hostinger / Hetzner console |

## Related

- [RB-07 Backup and restore](backup-restore.md)
- [RB-08 Troubleshooting](troubleshooting.md)
- [security.md](../operations/security.md)
