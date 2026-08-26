# Repository structure

Canonical root is `/home/dev/stack`. There is no `~/ansible` or
`~/cronnecture-fleet` symlink.

```
/home/dev/stack/
├── Makefile                 # operator entry — forwards fleet targets
├── README.md
├── deploy.sh                # ansible-playbook playbooks/stack.yml + images
├── ansible/                 # engine (own git checkout)
│   ├── ansible.cfg
│   ├── playbooks/           # site.yml imports stack.yml last
│   ├── roles/
│   ├── scripts/             # fleet / cloudflare / security
│   ├── config/              # inventory, vault, policies
│   ├── services/            # platform control-plane + JS APIs
│   └── workers/maintenance/
├── apps/
│   ├── marketing/           # cronnecture.com
│   ├── portfolio/           # preview starter
│   └── previews/            # notes — live hub is Ansible
├── docs/                    # this tree
├── kubernetes/              # mail, identity, operator YAML
├── operator/
│   ├── dashboard/
│   ├── agent-core/
│   └── billing/
├── overlays/
│   └── intelligence/
├── config/
├── lib/                     # stack_paths.sh / stack_paths.py
└── scripts/                 # keep-set, tunnel, overlay deploy
```

## Ansible vs stack

| Path | What runs it |
|---|---|
| `make deploy` | `playbooks/stack.yml` + operator image build |
| `make stack` | same playbook, no image rebuild |
| `make site` | full converge, then stack.yml (no image rebuild) |
| `make cloudflare` / `make clients` | fleet playbooks |

`FLEET_ROOT` is `stack/ansible`. `STACK_ROOT` is `stack`. Cron and systemd
already use those.

## Documentation

Start at **[docs/README.md](../README.md)**. First-client plan:
[first-clients.md](../business/first-clients.md).

## Commands

```bash
cd /home/dev/stack
make deploy
make site
make cloudflare
make reboot-node HOST=worker-general-01
```
