# Cleanup freeze list

**Purpose:** Structural strangler cleanup (Phases 0–5) must not casually touch these seams. Every cleanup change that touches a row below must name it in the PR/notes and pass the verification checklist.

**Pilot status (2026-08-18):** Paying handshake client **NoordDrive** (`noorddriveautos`, client 29) is live. Do **not** change handshake money (€39.99/mo + €79.99 setup) or open Access on the customer portal as a cleanup experiment. Former rehearsal tenant `decinemaat` was deleted. Empty Cloudflare zone `cronnecture.eu` may remain for reuse — do **not** delete the zone as cleanup. Keep freeze on vault / CF portals / Stripe / ansible-runner (below).

**Snapshot (2026-08-11):** UI cache buster `2.1.0` · API `Client Control Plane` `0.34.0` · control-plane memory limit **`10Gi`** (request `256Mi`) · staging NodePort `30081` · prod NodePort `30080`.

---

## Freeze-by-default zones

| Zone | Why fragile | Blast radius |
|------|-------------|--------------|
| **`config/inventory/group_vars/all/vault.yml`** (+ `~/.ansible/vault_pass`) | All CF / Stripe / Supabase / DB / GitHub secrets | Total outage / secret leak |
| **`platform.yaml.j2` + DATABASE_URL pooler** (`:5432`→`:6543`) | Dual rewrite in Jinja **and** `app/config.py`; multi-replica needs transaction pooler | CP crash loop / DB connection storms |
| **Ansible-runner** (`ansible-runner.py`, token file, `ANSIBLE_RUNNER_*`, CIDR/`HOST_IP`) | Pod has no vault/SSH; ansible hostPath off by default; jobs die if env/token/HOST_IP/CIDR wrong. Allowlists SoT: `config/policies/fleet-operations.yml` | Provision, CF, clients, connector, settings writes fail |
| **`cf_portals.yml` + `cloudflare_mgmt` (esp. portals)** | Access apps, bypass paths (OAuth/webhooks/status), tunnel ingress | Ops/webmail/portal lockout or public exposure |
| **Stripe / `billing_service.py` / webhook routes** | Billing / webhook / 90-day suspend gates | Wrong suspend / paywall / money path |
| **Customer portal path** (`client.cronnecture.com/client/portal/{uuid}`) | Customer hub for any live tenant | Client-facing outage |
| **Live inventory** (`hosts.ini`, node groups, firewall SSH peers) | Fleet topology | SSH/tunnel/cluster partition |
| **`cf_clients.yml` writes via runner** | Allowlisted write; drift vs Postgres | Wrong client tunnels on `make clients` |
| **CF zone `cronnecture.eu`** | May be empty after pilot delete; kept for reuse | Accidental zone wipe loses reusable domain |
| **Leader lease / jobs sweeper** | 2 replicas; advisory locks | Duplicate / stuck jobs |
| **Health-check Host header + maintenance middleware** | Full `/api/health` can 503 without `Host: ops…` | False pager storms / masking failures |
| **Mail (Stalwart) + DNS** | `make mail` / `mail-smoke` | Mail outage |
| **Staging vs production env overlays** | Wrong `-i` / namespace | Staging deploy mutating prod |

---

## Baseline smoke commands

Run from repo root (`FLEET_ROOT` = this tree). Prefer **staging first** for control-plane/image changes.

### Always (every cleanup change)

```bash
make check
make health
# Ops ready (Host header required for full health; ready is safer for gates):
curl -sf -H 'Host: ops.cronnecture.com' http://127.0.0.1:30080/api/health/ready
# Staging (if CP/staging touched):
curl -sf -H 'Host: staging-ops.cronnecture.com' http://127.0.0.1:30081/api/health/ready
```

### Characterization (local, no cluster required)

```bash
make check-smoke
# Equivalent:
python3 services/control-plane/scripts/test_billing_gates.py
python3 services/control-plane/scripts/test_delete_client_checklist.py
python3 services/control-plane/scripts/test_pooler_rewrite.py
python3 services/control-plane/scripts/test_runner_allowlist.py
python3 services/control-plane/scripts/test_fleet_catalog.py
python3 services/control-plane/scripts/test_portals_hostname_sanity.py
python3 services/control-plane/scripts/test_stripe_dispatch_parity.py
# After a CP roll: make cp-images   # staging vs production image tags
```

### Control-plane deploy path

```bash
make control-plane-staging   # or: make deploy-staging
# smoke staging ready, then:
make release                 # staging → smoke → production
# or carefully: make deploy-production / make control-plane
```

### Ansible-runner (after CP env/token changes)

```bash
systemctl is-active cronnecture-ansible-runner
curl -sf http://127.0.0.1:18765/health
# From a CP pod (token must match Secret): read-only fleet op via job dock
```

### Billing / portals (read-only)

```bash
# Any live customer portal UUID (expect 302/401/Access challenge — not 5xx):
# curl -sI 'https://client.cronnecture.com/client/portal/{uuid}' | head -5
# Ops CRM: billing_status / Stripe ledger read-only unless the change is intentional
# Do not delete CF zone cronnecture.eu as cleanup (may remain empty for reuse)
```

### Mail (when mail/notify touched)

```bash
make mail-smoke
```

---

## Rollback triggers (stop & revert)

- Ready probe failing >1–2 minutes after rollout
- Ansible-runner unreachable from pod
- Customer portal 5xx or Access misbind (any live tenant)
- Stripe webhooks 4xx/5xx spike
- `make health` hard FAIL emailing ops

**Rollback:** previous control-plane image/tag + previous git SHA. Do not “fix forward” on freeze zones without a dedicated change.

---

## Phase gates (cleanup)

| Phase | Allowed on freeze zones? |
|-------|--------------------------|
| **0** Safety net | Docs + tests only — **no** vault / CF portal / Stripe / runner edits; do not delete zone `cronnecture.eu` |
| **1** Hygiene | notify-ops dedupe, proven-dead static, e2e leftover via registry path — no vault/CF |
| **2** God-file peel | Routers / `{% include %}` / packages — **no** env/key renames; staging→smoke→prod for CP |
| **3** Config SoT | Docs + pooler documentation — **no** secret manager migration |
| **4** API/UI layering | Continue peel; retire proven-dead static — **no** UX redesign |
| **5** Ansible clarity | Comments / script layout — **no** role renames / mass `make site` |

See also: [repository.md](repository.md), [control-plane.md](../platform/control-plane.md), [stripe-billing.md](../platform/stripe-billing.md), runbook [RB-13](../runbooks/staging-and-release.md).
