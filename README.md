# Cronnecture stack

Operator root: `/home/dev/stack`. Ansible is the engine (`ansible/`). Product
checkouts live in `apps/`. Docs live in `docs/`.

The operator UI is **only** https://control.cronnecture.com.
`ops.cronnecture.com` and `stack.cronnecture.com` redirect there.

```
stack/
  ansible/       playbooks, roles, inventory, vault, fleet scripts
  apps/          marketing, portfolio, previews
  docs/          architecture, operations, platform, business, runbooks
  kubernetes/    mail, identity, operator YAML (keep-set; never wipe PVCs)
  operator/      dashboard, agent-core, billing
  overlays/      intelligence
  config/        stack-local config
  lib/           path helpers
  scripts/       stack deploy helpers
```

`kubernetes/control-plane.yaml` is the operator API + dashboard. The live
platform addon is k3s `manifests/control-plane.yaml` — do not overwrite it
with this file.

## Live map

| Piece | Namespace | Access |
|---|---|---|
| Stalwart | `mail` | `mail.cronnecture.com`, hostPorts 25/587 |
| Vault / Authentik / Logto / Passbolt / Hanko | `identity` | node-tunnel → Traefik ClusterIP |
| Webmail, website, customer portal | `platform` | same tunnel |
| Operator UI + API | `cronnecture-system` | https://control.cronnecture.com |
| Overlay | `cronnecture-intelligence` | in-cluster |

WAN: UFW default deny. Public origin ports are mail 25/587. HTTP is the tunnel.

## Deploy

```bash
cd /home/dev/stack
export KUBECONFIG="$HOME/.kube/config"
make check && make check-smoke   # gate before a roll
make deploy          # Ansible stack.yml + operator images
make stack           # same playbook, no image rebuild
make site            # full fleet converge (imports stack.yml)
make control-plane   # vault, manifests, docs hostPath
make control-plane-hot  # code/UI image only — does not change mounts
make marketing       # apps/marketing → cronnecture-website (pushes registry)
make cloudflare      # CF edge
make reboot-node HOST=worker-general-01
```

HTTP origins are Traefik ClusterIP (`10.43.125.134:80`), not `127.0.0.1:80`.
Do not add a second k3s server (1→2 etcd is split-brain). HA is 1→3 only.

Mail/identity YAML is installed into k3s addons **without replacing**
`identity-secrets` or PVCs. Vault: `ansible/config/inventory/group_vars/all/vault.yml`.
Host jobs read `/etc/cronnecture/stack.env`.
