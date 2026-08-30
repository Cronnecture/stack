# Cronnecture docs

Operator documentation for `/home/dev/stack`. Ansible is the engine; this
folder is the human reference.

## Quick links

| I want to… | Start here |
|---|---|
| Understand the system | [Architecture](architecture/overview.md) |
| See the folder layout | [Repository](architecture/repository.md) |
| Run day-to-day commands | [Operations](operations/overview.md) |
| Follow a procedure | [Runbooks](runbooks/README.md) |
| Recover from total loss | [Bootstrap](operations/bootstrap.md) |
| Back up or restore | [Backup](operations/backup.md) |
| Operator UI / CRM | [Control plane](platform/control-plane.md) |
| Auto-heal | [Control plane](platform/control-plane.md) · `make auto-heal` |
| Operator access / RBAC | [Operator access](operations/operator-access.md) |
| Stripe | [Billing](platform/stripe-billing.md) |
| Customer hub | [Client portal](platform/client-portal.md) |
| First paying client | [First clients](business/first-clients.md) |
| Cloudflare / DNS / tunnels | [Cloudflare](operations/cloudflare.md) |
| Identity | [Identity](operations/identity.md) |
| Delete a client | [Delete client](runbooks/delete-client.md) |
| Contribute | [Contributing](contributing.md) |

## Categories

### Architecture

| Document | Contents |
|---|---|
| [overview.md](architecture/overview.md) | Topology, traffic, namespaces |
| [repository.md](architecture/repository.md) | Stack folder layout |
| [config-sources.md](architecture/config-sources.md) | Config sources of truth |
| [inventory.md](architecture/inventory.md) | Host groups and group_vars |
| [kubernetes.md](architecture/kubernetes.md) | k3s manifests |
| [backup.md](architecture/backup.md) | Backup layers |
| [resilience.md](architecture/resilience.md) | SPOFs and blast radius |
| [roadmap.md](architecture/roadmap.md) | Product roadmap |
| [control-plane-roadmap.md](architecture/control-plane-roadmap.md) | UI / automation north star |
| [freeze-list.md](architecture/freeze-list.md) | What must not be rewritten casually |

### Operations

| Document | Contents |
|---|---|
| [overview.md](operations/overview.md) | Converge, cron, make targets |
| [bootstrap.md](operations/bootstrap.md) | Fresh control machine |
| [deployment.md](operations/deployment.md) | Staging and `make release` |
| [backup.md](operations/backup.md) | Automated backups and restore |
| [maintenance.md](operations/maintenance.md) | Edge maintenance worker |
| [operator-access.md](operations/operator-access.md) | Operators and RBAC |
| [security.md](operations/security.md) | Vault, firewall, tunnels, Access |
| [siem-retired.md](operations/siem-retired.md) | Wazuh — retired |
| [mail.md](operations/mail.md) | Stalwart, DNS, PTR |
| [mail-freeze.md](operations/mail-freeze.md) | Frozen mail addresses and store |
| [identity.md](operations/identity.md) | Vaultwarden, Passbolt, Authentik, Cerbos (Logto and Hanko retired) |
| [gitea.md](operations/gitea.md) | In-cluster Gitea (tenant git, HTTPS, 2 replicas) |
| [cloudflare.md](operations/cloudflare.md) | Edge policy, portals, client tunnels |
| [supabase.md](operations/supabase.md) | Control-plane database |

### Platform

| Document | Contents |
|---|---|
| [control-plane.md](platform/control-plane.md) | Ops API, Fleet, CRM, jobs |
| [mas-retired.md](platform/mas-retired.md) | MAS is gone — use `/app/` |
| [client-portal.md](platform/client-portal.md) | Customer hub |
| [client-app-repo.md](platform/client-app-repo.md) | Client GitHub repo layout |
| [payment-providers.md](platform/payment-providers.md) | Mollie / Stripe Connect |
| [previews.md](platform/previews.md) | `previews.cronnecture.com` |
| [stripe-billing.md](platform/stripe-billing.md) | Webhooks, suspend |

### Business

| Document | Contents |
|---|---|
| [first-clients.md](business/first-clients.md) | First-clients plan |
| [commercial-offer.md](business/commercial-offer.md) | Offer and soft SLA |
| [pricing.md](business/pricing.md) | Live EUR catalog |
| [lead-generation.md](business/lead-generation.md) | Lead pipeline (plan) |
| [acquisition.md](business/acquisition.md) | Inbound acquisition |
| [go-live.md](business/go-live.md) | KVK + VAT → Stripe live gate |
| [company-nl.md](business/company-nl.md) | Deprecated Dutch company notes |

### Legal

| Document | Contents |
|---|---|
| [overview.md](legal/overview.md) | Legal pack (GDPR + Dutch templates) |

### Runbooks

Step-by-step procedures: [runbooks/README.md](runbooks/README.md). IDs `RB-01`…`RB-15` stay in the index so the operator HUD can parse them. File names are the procedure.

## Live fleet

| Host | Inventory | Group | Role |
|---|---|---|---|
| `31.97.126.9` | `cp-master-01` | `k3s_server` | Hostinger KVM8 — etcd only (after taint) |
| `135.181.58.45` | `worker-general-01` | `compute_general` | Hetzner HEL1 — primary compute |
| `72.60.32.178` | `mail-01` | `mail` | Hostinger KVM4 — Stalwart (`mail.cronnecture.com`) |

HTTP origin is Traefik ClusterIP (`10.43.125.134:80`), not host `:80`.
Do not add a second k3s server (1→2 etcd is split-brain). HA is 1→3 only.

Public: https://control.cronnecture.com (operators), https://client.cronnecture.com (customers), https://cronnecture.com, https://previews.cronnecture.com, https://noorddriveautos.com.

**Roots:** `STACK_ROOT=/home/dev/stack`. `FLEET_ROOT=/home/dev/stack/ansible`. Vault: `ansible/config/inventory/group_vars/all/vault.yml`.
