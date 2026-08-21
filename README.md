# Cronnecture stack

This directory (`/home/dev/stack`) is the operator backbone for the live k3s cluster.

The operator UI is **only** https://stack.cronnecture.com (`cronnecture-system/dashboard`). `ops.cronnecture.com` is the existing platform product, not a second copy of that dashboard.

`kubernetes/control-plane.yaml` in this repo is the operator API + dashboard. The live platform addon is k3s `manifests/control-plane.yaml` — do not overwrite it with this file.

Mail and identity **are part of this stack**. The live YAML lives in `kubernetes/mail.yaml` and `kubernetes/identity.yaml`. Secrets and PVCs stay in the cluster and are never written from git or deleted by deploy.

## Live map

| Piece | Namespace | Access |
|---|---|---|
| Stalwart | `mail` | `mail.cronnecture.com` A record, hostPorts 25/587 |
| Vault / Authentik / Logto / Passbolt / Hanko | `identity` | Cloudflare `node-tunnel` → Traefik |
| Ops, webmail, website | `platform` | same tunnel |
| Dashboard + API | `cronnecture-system` | https://stack.cronnecture.com |
| Overlay | `cronnecture-intelligence` | in-cluster |

WAN: UFW default deny. Public origin ports are mail 25/587. HTTP is the tunnel.

## Deploy

```bash
export KUBECONFIG="$HOME/.kube/config"
bash deploy.sh
```

`deploy.sh` installs mail/identity YAML from this tree into k3s addons **without replacing** `identity-secrets` or PVCs, then the control plane and tunnel.

Dashboard: Mail and Identity pages can restart workloads. They cannot delete data.

Cloudflare tokens stay in Ansible vault (`/home/dev/ansible/.../vault.yml`).
