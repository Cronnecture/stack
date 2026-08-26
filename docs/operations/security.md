# Security

Security layers, secrets handling, and tenant isolation.

## Defense in depth

| Layer | Mechanism |
|-------|-----------|
| Edge | Cloudflare WAF, rate limits, bot fight, TLS 1.2+ |
| Access | Cloudflare Access → Authentik TOTP on admin portals (not email OTP) |
| Network | UFW default-deny; cluster peers mutually trusted |
| Transport | flannel wireguard-native pod encryption |
| Host | fail2ban, auditd, unattended-upgrades, sysctl hardening |
| Secrets | ansible-vault, k3s secrets encryption at rest |
| SIEM | Wazuh FIM, log analysis, auto-block at CF edge |
| Tenant | Per-client namespace, quota, network policy, isolated tunnel |

## Firewall (UFW)

- Default: deny incoming from internet
- **Cluster peers**: full access to each other (inventory-based) — k3s, Ansible, tunnel backends (including kubelet `:10250` for `kubectl exec`/`logs`)
- **Public ports**: only what each group declares in `firewall_public_tcp_ports`
- Do not insert a host INPUT DROP for `:10250` ahead of the peer allows — that breaks apiserver→kubelet and fails Passbolt dumps in fleet backup. `baseline.yml` removes leftover `fleet-input-guard` rules if they reappear.
- **SSH**: Cloudflare Access hostnames (`cf_ssh.yml`); run `make lockdown` (`playbooks/lockdown.yml`) to close public port 22
- **Safety net**: optional `firewall_admin_cidrs` keeps rate-limited SSH from your home IP

| Group | Typical public ports |
|-------|---------------------|
| `k3s_server` | 25, 587 (SMTP only) |
| `compute_general` | none (Traefik via tunnel/peers) |
| `edge_lb` | 6443, 80, 443, VRRP |
| `siem` | none (dashboard via tunnel) |

## SSH (Cloudflare Access)

Login as **`dev`** via Cloudflare short-lived certificates — no VPS password, no keys in `authorized_keys`.

Hostnames in `config/inventory/group_vars/all/cf_ssh.yml`.

**One-time:** install the Cloudflare SSH CA on all nodes (Zero Trust → Access controls → Service credentials → SSH → Generate SSH CA, copy public key):

```bash
# paste key into config/.cf_ssh_ca.pub, then:
ansible-playbook -i config/inventory/hosts.ini playbooks/baseline.yml
```

Or add **Access: SSH Auditing Edit** to `cf_access_token` and run:

```bash
python3 scripts/cloudflare/cf-fetch-ssh-ca.py      # gateway CA (Access for Infrastructure)
python3 scripts/cloudflare/cf-ensure-ssh-app-ca.py # per-app CAs (cloudflared ssh-gen)
ansible-playbook -i config/inventory/hosts.ini playbooks/baseline.yml
```

The `ssh-gen` client flow signs certs with **per-application** CAs. Servers must trust those keys in `/etc/ssh/cloudflare_access_ca.pub` (the ensure script writes all of them to `config/.cf_ssh_ca.pub`).

**Your laptop** `~/.ssh/config` uses `cloudflared access ssh-gen` (ephemeral certs in `~/.cloudflared/`, not your personal key on servers). Cloudflare puts your **email prefix** in the cert principal (e.g. `svenbraad.work`), while fleet login is **`dev`** — servers map this via `AuthorizedPrincipalsFile` (`/etc/ssh/cloudflare_authorized_principals`) in the `cf_ssh_server` role.

**sshd drop-ins:** Debian `Include`s `/etc/ssh/sshd_config.d/*.conf` at the top of `sshd_config`. CA trust lives in `60-cloudflare-ca.conf` (global); `Match User` only in `99-cloudflare-access.conf` so it does not swallow the rest of the config. If `Include` is missing, CF SSH silently fails (`TrustedUserCAKeys none`) while emergency password/key login may still work.

```bash
ssh dev@ssh-cp.cronnecture.com
```

## Cloudflare tokens (least privilege)

Minted by `make cf-mint` / `scripts/cloudflare/cf-mint-tokens.py`. Full inventory and rotation: [RB-06](../runbooks/cloudflare-tokens.md).

| Token | Scope |
|-------|-------|
| `vault_cf_dns_token` | DNS edit |
| `vault_cf_tunnel_token` | Tunnel + DNS |
| `vault_cf_access_token` | Zero Trust Access (+ SSH apps) |
| `vault_cf_waf_token` | WAF, rate limits, zone settings |
| `vault_cf_workers_token` | Workers / maintenance page |
| `vault_cf_block_token` | IP Access Rules (SIEM node only) |
| `vault_cf_readonly_token` | Read diagnostics |
| `vault_cf_analytics_token` | Zone analytics |
| `vault_cf_r2_storage_token` | R2 API |

Bootstrap token is shredded after mint; if self-revoke fails, delete it in the dashboard. Never commit plaintext tokens. Treat anything pasted in chat/history as compromised → full re-mint.

## SSH trust model (honest)

| Path | Who | Notes |
|------|-----|-------|
| Internet → `:22` | Closed after `make lockdown` (`playbooks/lockdown.yml`, `firewall_ssh_public: false`) | Use Cloudflare Access SSH hostnames |
| Admin CIDR → `:22` | Optional `firewall_admin_cidrs` safety net | Rate-limited; remove when CF SSH is your only break-glass |
| Peer VPS → `:22` | Allowed (default `firewall_ssh_peer_restrict: false`) | Shared `node-tunnel` SSH origins dial peer IPs; denying peer `:22` breaks CF SSH when another connector handles the request |
| Automation key | Operator `~/.ssh/id_ed25519` on the **host runner** | Not mounted into the API pod |

Cloudflare Zero Trust protects **internet** SSH. East-west Ansible remains key-based from the control node over the peer mesh (not via CF Access SSH).

### Close public SSH (`make lockdown`)

After Cloudflare Access SSH hostnames work, close internet `:22`:

```bash
make lockdown    # playbooks/lockdown.yml — verify CF SSH via API, then set firewall_ssh_public: false
```

Do this **instead of** a full `make site`. Optional safety net: set `firewall_admin_cidrs` (home/office IP) before the first lockdown. Rollback: set `firewall_ssh_public: true` in group_vars and re-run `playbooks/baseline.yml` (or `make lockdown` after reverting the flag — see `playbooks/lockdown.yml`).

## Control plane pod security

- Non-root (`uid 1001` / `fleet`); capabilities dropped; `seccompProfile: RuntimeDefault`; NetworkPolicy ingress on `:8080` (kube-system + same ns, plus open `:8080` for NodePort — peer `node-tunnel` connectors; UFW is the host perimeter)
- **Ansible runner split:** API pod has no SSH key and no vault password. Inventory/playbooks go through `cronnecture-ansible-runner` (`:18765`, Bearer token + source CIDR allowlist; UFW also limits to pod CIDR / localhost). `ANSIBLE_RUNNER_TOKEN` must be set and must not equal `OPS_API_TOKEN`.
- **hostPath (honest):** ansible tree mount is **off by default** (`control_plane_mount_ansible_dir: false`). Remaining mounts: writable `client-documents`, read-only `/var/log` for ops log views
- **RBAC:** ClusterRole has no cluster-wide `secrets`; Ansible creates reusable ClusterRole `control-plane-secrets` and the API binds it per namespace (`ensure_namespace_rbac`). SA may `bind` that ClusterRole only — not mint Roles that grant secrets
- CF / GitHub / Supabase / Fernet / ops + runner tokens: Kubernetes Secret `control-plane-cf` (fail-closed if `vault_control_plane_token_key` is missing/placeholder)
- Ops API: **admin session cookie** (per-user password at `/login`) **or** `OPS_API_TOKEN` — Cloudflare Access alone is not enough for `/api/*`
- Ops passwords: pbkdf2 hashes on `ops_users.password_hash`. Legacy `/etc/cronnecture/ops-admin.password` / `OPS_ADMIN_PASSWORD` seeds the **superadmin** hash once (see [operator-access.md](operator-access.md))
- Ansible-runner bind: `127.0.0.1,<node InternalIP>` (not `0.0.0.0`); UFW + CIDR allowlist still gate sources. Pure loopback breaks pod→`HOST_IP`
- Pod must reach kube-apiserver, Supabase, Cloudflare, and host `:18765` — egress NetworkPolicy left open on purpose

## Supply chain

| Artifact | Pin |
|----------|-----|
| `get.k3s.io` install script | `k3s_install_script_checksum` in `config/inventory/group_vars/k3s_cluster.yml` |
| Helm binary (Rancher path) | `helm_install_checksum` + `helm_version` (no `curl \| bash` from `main`) |
| CI Ansible | `ansible-core==2.16.14` (workflow + lint venv) |
| Images touched by CP templates | version-pinned (`postgres:16.8-alpine`, `registry:2.8.3`, `nginx:1.27.4-alpine`) |

Full digest-pin of every third-party image (monitoring, Stalwart, Wazuh apt, etc.) is intentionally deferred — refresh version pins when bumping those roles. CI runs **gitleaks** (`make gitleaks` / `GITLEAKS_STRICT=1`) and **ansible-lint** strict.

## Secret rotation

| Secret | How |
|--------|-----|
| Cloudflare API tokens | `make cf-mint` — [RB-06](../runbooks/cloudflare-tokens.md) |
| Fernet `TOKEN_ENCRYPTION_KEY` | `python3 scripts/security/rotate-token-encryption-key.py` then `make control-plane` |
| Ops API + mail admin | `python3 scripts/security/rotate-local-secrets.py` then `make control-plane` |
| GitHub OAuth client secret | Settings → Integrations (preferred) or GitHub dashboard → vault |
| Supabase service / anon keys | Settings → Integrations (preferred) or Supabase dashboard → vault |

## Admin portal access

Defined in `cf_portals.yml`. Most portals get:

1. Tunnel ingress on `node-tunnel`
2. Proxied DNS CNAME
3. Cloudflare Access app (allowed emails in `cloudflare.yml`)

Exceptions: **Client customer portal** (`client.cronnecture.com`) uses `skip_access: true` — Logto product SSO gates the hub in the control plane (not Authentik/Access). Public marketing hostnames have no Access. Ops additionally requires `/login` (or `OPS_API_TOKEN`) after Access; GitHub/Stripe webhook paths bypass Access.

**Ops team RBAC:** who may use `ops.cronnecture.com` is managed in-dashboard (**Settings → Users / Access**). Source of truth is Postgres `ops_users` (per-user password hashes; admins set/reset — not recoverable). Active emails sync to the ops Access allowlist. Break-glass superadmin: `svenbraad.work@gmail.com` (never removable). See [operator-access.md](operator-access.md).

### Fleet inventory cleanup

Ops UI → **Platform → Inventory** compares live Cloudflare state to Postgres + `cf_portals.yml` + `cf_ssh.yml`. **Cleanup stale** removes orphan DNS, Access apps, and client tunnels (connectors stopped first). Declared platform portals, public sites, and Cloudflare SSH hostnames are protected. Weekly **Sunday dry-run** emails `alerts@` (apply is opt-in Monday behind allowlist + evidence — see [overview.md](overview.md)).

## Client isolation

Each client (`client-{slug}` namespace):

- **ResourceQuota**: caps pods, CPU, memory
- **NetworkPolicy**:
  - Ingress: same namespace (any port); `kube-system` + `platform` only on `80`/`8080`/`3000`
  - Egress: same namespace, platform registry :5000, HTTPS / DNS / Postgres outbound
- **Dedicated Cloudflare tunnel** — not shared with fleet `node-tunnel`
- **Separate DNS zone** — delegated to your CF account

## Secrets you must back up off-repo

| Asset | Risk if lost |
|-------|--------------|
| `~/.ansible/vault_pass` | Cannot decrypt vault |
| `~/.ssh/id_ed25519` | Cannot SSH to nodes |
| Supabase credentials | DB recovery depends on provider backups/PITR when enabled (identity PITR deferred — [backup.md](backup.md)) |

See [backup.md](backup.md).

## Audit & compliance

- **auditd** rules on all nodes (k3s token access, identity changes)
- **Wazuh** agents on all non-siem nodes → manager on `[siem]`
- Auto-block: alert level ≥ 10 with source IP → CF block for 24h

## Hardening checklist (new node)

Automatic via `baseline.yml`:

- [ ] UFW enabled
- [ ] fail2ban active
- [ ] cloudflared connector running
- [ ] unattended-upgrades configured
- [ ] sysctl hardening applied
- [ ] Wazuh agent enrolled (if siem group exists)

## Related docs

- [cloudflare.md](cloudflare.md)
- [siem.md](siem-retired.md)
- [RB-06 Cloudflare tokens](../runbooks/cloudflare-tokens.md)
