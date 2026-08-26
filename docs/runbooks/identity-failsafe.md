# Identity failsafe

Runbook **RB-16**.

Make login survive one general worker dying. The fleet side is wired. The remaining steps are paid/off-box hosts only you can create.

## Already done on the fleet

- Logto and Hanko: **retired 2026-08-26** (cluster objects deleted)
- Cerbos: 2 replicas, one per `pool=general` worker, ClusterIP load-balanced
- Authentik: stays **1** replica on in-cluster `identity-postgres` (not the identity Supabase pooler)
- `backup-fleet.sh` **requires** `pg_dump authentik` when identity-postgres has replicas
- Helper: `make identity-failsafe` (status) and `scripts/identity-failsafe.sh`

## What you do (in this order)

### 1. Raise the Authentik pool — then tell the fleet

Supabase → project **`cronnecture-identity`** → **Project Settings → Compute / Add-ons**.

- Keep **session** pooler port **5432**. Do not switch Authentik to `:6543`.
- Raise compute so session `pool_size` is **at least 30** (Micro or larger). Nano/15 is what just outaged `auth.cronnecture.com`.
- While you are there: if the project is still Free, **upgrade to Pro** so daily backups exist. PITR is optional (~€100/mo) — turn it on when you want point-in-time, not required for replica HA.

Then, on `cp-master-01`:

```bash
cd /home/dev/stack
./scripts/identity-failsafe.sh scale-authentik --i-raised-the-pooler
```

Expect one Authentik pod on each general worker and `https://auth.cronnecture.com/-/health/ready/` → 200.

### 2. Hosted Redis for Authentik

The PVC `identity-redis` is pinned to `worker-general-01`. Two Authentik pods still die if that node dies.

1. Create a small Redis (Upstash free / Redis Cloud). Enable TLS if the vendor requires it.
2. On the control node (values stay in your shell, not in git):

```bash
cd /home/dev/stack
AUTHENTIK_REDIS_HOST='your-redis.upstash.io' \
AUTHENTIK_REDIS_PORT=6379 \
AUTHENTIK_REDIS_TLS=true \
AUTHENTIK_REDIS_PASSWORD='…' \
  ./scripts/identity-failsafe.sh apply-redis
```

Leave the in-cluster Redis PVC in place. Do not delete it until Authentik has been healthy on the hosted Redis for a day.

Also store the Redis URL in the encrypted vault (`vault_authentik_redis_host` / password) so break-glass can rebuild it.

### 3. Laptop Ansible control

On your laptop (once):

1. `git clone <repo> ~/stack`
2. Copy `~/.ansible/vault_pass` and `~/.ssh/id_ed25519` from the break-glass pack (R2 or `worker-general-01:/var/backups/cronnecture-break-glass/latest/`)
3. `export STACK_ROOT=~/stack FLEET_ROOT=~/stack/ansible`
4. `make ping` from the laptop

Refresh the pack after key rotation: `make break-glass` on the control node, then download it again.

### 4. Do not

- Scale Authentik before step 1
- Add a second k3s server (HA is 1→3 only)
- `make identity` / retarget Authentik at in-cluster Postgres
- Dual-replica Redis, Vaultwarden, or Passbolt
- Restore Logto (`id.cronnecture.com`) — product SSO is Authentik

## Verify

```bash
cd /home/dev/stack
./scripts/identity-failsafe.sh status
curl -sS -o /dev/null -w '%{http_code}\n' https://auth.cronnecture.com/-/health/ready/
```

Done when: Authentik Redis host is not `identity-redis`, Authentik is 2/2 on two nodes, and the public health URL returns 200/204. Logto is retired — do not probe `id.cronnecture.com`.
