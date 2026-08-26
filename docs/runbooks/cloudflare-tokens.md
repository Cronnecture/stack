# Cloudflare tokens

Runbook **RB-06**.

Mint, rotate, and verify Cloudflare API tokens for Cronnecture Fleet.

## Token inventory (after `make cf-mint`)

| Vault variable | Dashboard name (typical) | Scope | Used by |
|----------------|--------------------------|-------|---------|
| `vault_cf_dns_token` | `k3s-fleet cf_dns_token` | Zone DNS + Zone | `make cloudflare`, ops API |
| `vault_cf_tunnel_token` | `k3s-fleet cf_tunnel_token` | Cloudflare Tunnel + Zone DNS | tunnels, portals, ops API |
| `vault_cf_access_token` | `k3s-fleet cf_access_token` | Access: Apps and Policies **+** Organizations / Identity Providers write | Access apps, CF SSH apps, Authentik IdP wire, ops API |
| `vault_cf_waf_token` | `k3s-fleet cf_waf_token` | WAF, Bot Management, zone settings | edge policy |
| `vault_cf_workers_token` | `k3s-fleet cf_workers_token` | Workers Scripts (+ KV when needed) | maintenance worker |
| `vault_cf_block_token` | `k3s-fleet cf_block_token` | Account Firewall Access Rules | SIEM autoblock **only** |
| `vault_cf_readonly_token` | `k3s-fleet cf_readonly_token` | Account Settings + Zone read | inventory / diagnostics |
| `vault_cf_analytics_token` | `k3s-fleet-cf-analytics` | Zone Analytics | customer portal traffic KPIs |
| `vault_cf_r2_storage_token` | (minted) | R2 storage API | registry/backup helpers |
| `vault_cf_zone_id` | — | Platform zone ID string | all CF playbooks |
| `vault_cf_account_id` | — | Account ID | all CF APIs |

**Bootstrap token** (`cfut_…`, dashboard name often `bootstrap`): **Account → API Tokens Edit** only. Never store in vault. One-shot for minting; revoke immediately after.

## Full re-mint (compromised history / rotate all)

### 1. Create a short-lived bootstrap token

Cloudflare → **My Profile → API Tokens → Create Token**

- Permission: **Account → API Tokens → Edit**
- TTL: **1 hour** (or delete manually right after mint)
- No DNS / Workers / Zone write on the bootstrap itself

### 2. Mint scoped fleet tokens

On the Ansible control machine:

```bash
# Prefer writing the file without putting the token on the shell command line:
#   python3 -c 'from pathlib import Path; Path.home().joinpath(".cf_bootstrap").write_text("cfut_…\n"); Path.home().joinpath(".cf_bootstrap").chmod(0o600)'

cd "${FLEET_ROOT:-$PWD}"
make cf-mint ARGS="--zone cronnecture.com"
```

The mint script scopes DNS/WAF/Analytics tokens to:

1. The primary `--zone` (platform), and  
2. **Every client zone** listed in `config/inventory/group_vars/all/cf_clients.yml`, and  
3. Any `--extra-zone-id` you pass  

If bootstrap cannot list zones (API Tokens Edit only), it falls back to `vault_cf_account_id` + `vault_cf_zone_id` **plus** client zones from `cf_clients.yml`. Without that merge, client domains (e.g. `cronnecture.eu`) fail with “No zone found”.

What the script does:

1. Verifies bootstrap can mint account tokens  
2. Resolves zone/account (may use an existing readonly vault token if still valid)  
3. Mints **all** scoped tokens above  
4. Encrypts them into `config/inventory/group_vars/all/vault.yml`  
5. Attempts to **self-revoke** the bootstrap token and **shreds** `~/.cf_bootstrap`  
6. If self-revoke warns, **delete the bootstrap token in the dashboard** yourself  

### 3. Revoke every old fleet token in the dashboard

In **API Tokens**, delete any previous `k3s-fleet *` / `bootstrap` entries that were active before the mint. The new set should be the only Active fleet tokens.

### 4. Re-apply consumers

```bash
make cloudflare          # edge policy, portals, tunnels, SSH Access apps
make control-plane       # ops API Secret refreshed from vault
make siem                # block token on SIEM node
make clients             # if client tunnels use vault CF tokens
# optional:
make maintenance-worker
```

### 5. Hygiene

```bash
# Remove accidental token echoes from shell history (values never printed)
# Manually or via a small local scrub of lines matching cfut_/cfat_
history -c
truncate -s 0 ~/.bash_history   # if you are sure nothing else valuable is only there
```

Never paste live tokens into chat after mint. Prefer `~/.cf_bootstrap` + shred.

## Verify

```bash
# Playbook succeeds with new tokens
make cloudflare

# Ops health (after control-plane redeploy)
curl -sf http://127.0.0.1:30080/api/health/ready

# East-west API auth (after OPS_API_TOKEN is set): bare curl should 401
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30080/api/clients
```

SIEM should receive **only** the block token (not DNS/WAF).

## Rotate a single token

1. Create a replacement in the dashboard with the **same** permission set as the table above  
2. `ansible-vault edit config/inventory/group_vars/all/vault.yml` — update that one key  
3. Re-converge:

| Token | Action |
|-------|--------|
| DNS / WAF / Access / Workers | `make cloudflare` (+ maintenance-worker if workers) |
| Tunnel | `make cloudflare && make control-plane && make clients` |
| Block | `make siem` |
| Analytics / readonly | `make control-plane` |

4. Revoke the old token in the dashboard  

## Related secrets (not minted by cf-mint)

| Item | Where |
|------|--------|
| `vault_ops_api_token` | East-west ops API auth; else `config/.ops_api_token` (gitignored) |
| `vault_registry_auth_*` | Registry htpasswd; else `config/.registry_auth_password` |
| `vault_backup_s3_*` / `vault_registry_s3_*` | R2 S3 API keys (separate from `vault_cf_r2_storage_token`) |
| GitHub OAuth | `vault_github_client_id` / `vault_github_client_secret` |

## Security notes

- Encrypted vault in git is OK only if `~/.ansible/vault_pass` never leaks  
- Bootstrap + scoped tokens that appeared in shell history or chat must be treated as compromised → full re-mint  
- Platform Secrets are applied via `apply_secrets.yml` / `0600` manifest sidecar — not world-readable Addon YAML stringData  
- Documented in [security.md](../operations/security.md) and [cloudflare.md](../operations/cloudflare.md)

## Related

- [cloudflare.md](../operations/cloudflare.md)
- [security.md](../operations/security.md)
- [RB-09 Incident response](incident-response.md)
