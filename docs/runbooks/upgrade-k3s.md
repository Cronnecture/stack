# Upgrade k3s

Runbook **RB-03**.

Rolling upgrade of k3s across server and agent nodes.

## Prerequisites

- Read [k3s release notes](https://github.com/k3s-io/k3s/releases) for breaking changes
- Fresh backup: `make backup`
- etcd snapshot: automatic or manual
- Maintenance window for single-server / single-worker fleets

## Pin new version

Edit `config/inventory/group_vars/k3s_cluster.yml`:

```yaml
k3s_version: v1.32.5+k3s1   # example — use target release
```

## Upgrade order

Always upgrade **server(s) before agents**. With one server and one agent (current fleet):

### 1. Server node (`k3s_server`)

```bash
ansible-playbook -i config/inventory/hosts.ini playbooks/cluster.yml --limit k3s_server
```

Or SSH to server and restart after package/binary update (playbook handles idempotently):

```bash
sudo systemctl restart k3s
```

Wait for API:

```bash
sudo k3s kubectl get nodes
curl -k https://127.0.0.1:6443/version
```

### 2. Agent nodes (`compute_*`)

```bash
ansible-playbook -i config/inventory/hosts.ini playbooks/cluster.yml --limit k3s_agent
```

### 3. Full verification

```bash
sudo k3s kubectl get nodes
sudo k3s kubectl -n platform get pods
make health
make site   # optional full converge for drift
```

## Multi-server HA order

When 3+ servers exist:

1. Upgrade one server at a time
2. Wait for etcd healthy between each
3. Upgrade agents last
4. Never upgrade all servers simultaneously

See [RB-10 Scale to HA](scale-to-ha.md).

## Rollback

k3s downgrade is **not officially supported**. If upgrade fails:

1. Restore etcd snapshot from before upgrade ([RB-07](backup-restore.md))
2. Re-pin previous `k3s_version` in group_vars
3. Re-run `make cluster`

For single-node disaster: full [bootstrap.md](../operations/bootstrap.md) from backup.

## Verification checklist

- [ ] All nodes `Ready`, matching k3s version
- [ ] Platform pods Running
- [ ] `curl -sf http://127.0.0.1:30080/api/health/live`
- [ ] `curl -sf http://127.0.0.1:30080/api/health`
- [ ] Sample client site loads
- [ ] Wazuh agents connected

## Related

- [kubernetes.md](../architecture/kubernetes.md)
- [RB-07 Backup and restore](backup-restore.md)
