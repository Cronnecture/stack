# Runbooks

Step-by-step procedures for fleet operations. Each runbook includes prerequisites, steps, verification, and rollback notes.

## Index

| ID | Runbook | When to use |
|----|---------|-------------|
| RB-01 | [Add a node](add-node.md) | New VPS joining the fleet |
| RB-02 | [Remove a node](remove-node.md) | Decommission a host |
| RB-03 | [Upgrade k3s](upgrade-k3s.md) | New k3s version available |
| RB-04 | [Deploy control plane](deploy-control-plane.md) | Ops API/UI code or config change |
| RB-05 | [Onboard a client](onboard-client.md) | New tenant in ops dashboard |
| RB-06 | [Cloudflare tokens](cloudflare-tokens.md) | Initial setup or token rotation |
| RB-07 | [Backup and restore](backup-restore.md) | Scheduled backup or disaster recovery |
| RB-08 | [Troubleshooting](troubleshooting.md) | Something is broken |
| RB-09 | [Incident response](incident-response.md) | Outage or security incident |
| RB-10 | [Scale to HA](scale-to-ha.md) | Multi-server etcd, edge LB, workers |
| RB-11 | [Emergency management](emergency-management.md) | Control node down; restore tunnels without ops UI |
| RB-12 | [Registry recovery](registry-recovery.md) | PVC loss, enable S3/R2 registry |
| RB-13 | [Staging and release](staging-and-release.md) | One-time staging setup; `make release` workflow |
| RB-14 | [Delete a client](delete-client.md) | Full teardown (Stripe, CF, k8s, DB, portal); dry-run first |
| RB-15 | [Orphan CF cleanup](orphan-cloudflare-cleanup.md) | Weekly dry-run → alerts@; opt-in Monday apply + allowlist |
| RB-16 | [Identity failsafe](identity-failsafe.md) | Raise Authentik pool, hosted Redis, dedicated Logto DB, laptop control |

## Conventions

- **Control machine:** `cp-master-01` — `STACK_ROOT=/home/dev/stack`, vault password, SSH key. Keep a second clone + vault on a laptop (see [RB-11](emergency-management.md)).
- **Commands:** run from `/home/dev/stack` unless noted (`make` forwards into `ansible/`)
- **Verify:** each runbook ends with explicit success criteria
- **Rollback:** noted where reversible; destructive steps are flagged

## Before any change

```bash
cd /home/dev/stack
make health
make backup   # recommended before risky changes
```

## Escalation

1. [RB-08 Troubleshooting](troubleshooting.md)
2. [RB-09 Incident response](incident-response.md)
3. Check logs: `/var/log/cronnecture-fleet-*.log`, `kubectl -n platform logs`

## Related docs

- [overview.md](../operations/overview.md) — daily commands
- [bootstrap.md](../operations/bootstrap.md) — full rebuild from scratch
- [resilience.md](../architecture/resilience.md) — known SPOFs and mitigations
