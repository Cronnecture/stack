# Remove a node

Runbook **RB-02**.

Safely drain and decommission a VPS from the fleet.

## Prerequisites

- Replacement capacity if removing the only compute node
- No critical single-replica workloads on the node (check first)
- Control machine access

## Pre-flight checks

```bash
NODE=<hostname-or-ip>
sudo k3s kubectl get nodes
sudo k3s kubectl get pods -A -o wide | grep $NODE
```

**Warning:** Removing the sole `k3s_server` destroys the cluster control plane. Removing the sole `compute_general` node stops all client ingress until another compute node exists.

## Procedure

### 1. Cordon and drain (Kubernetes)

```bash
sudo k3s kubectl cordon $NODE
sudo k3s kubectl drain $NODE --ignore-daemonsets --delete-emptydir-data --timeout=300s
```

If drain hangs, identify blocking pods:

```bash
sudo k3s kubectl get pods -A -o wide | grep $NODE
```

For platform pods pinned to control-plane node, ensure another server exists before draining a control plane node.

### 2. Remove from k3s cluster

On the **node being removed**:

```bash
# Agent:
sudo /usr/local/bin/k3s-agent-uninstall.sh

# Server (destructive — only if decommissioning control plane member):
sudo /usr/local/bin/k3s-uninstall.sh
```

Or from control machine (if node still reachable):

```bash
sudo k3s kubectl delete node $NODE
```

### 3. Update inventory

Edit `config/inventory/hosts.ini` — remove the IP from its group.

### 4. Re-converge fleet

```bash
cd $FLEET_ROOT
make site
make cloudflare   # refresh LB/tunnel backends
make clients      # if compute backend changed
```

### 5. Optional: wipe the VPS

On decommissioned host (if repurposing):

```bash
# Remove Wazuh agent, cloudflared, etc. — or rebuild VPS from provider
```

## Verification

```bash
sudo k3s kubectl get nodes
make health
ansible -i config/inventory/hosts.ini all -m ping   # removed IP should fail/unlisted
```

Check client sites still resolve if compute pool changed.

## Rollback

If removed prematurely:

1. Re-add with [RB-01](add-node.md)
2. Restore workloads from ops UI (re-deploy apps) if etcd restore not performed
3. For data loss on registry PVC: rebuild images via Kaniko

## Related

- [RB-01 Add a node](add-node.md)
- [RB-07 Backup and restore](backup-restore.md)
