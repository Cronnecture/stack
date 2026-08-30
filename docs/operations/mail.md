# Mail — Stalwart, DNS, deliverability

Self-hosted mail on k3s (Stalwart). Inbound/outbound SMTP, webmail, and Cloudflare DNS sync.

## Quick commands

```bash
make mail              # Deploy / update Stalwart stack
make mail-dns          # Publish MX/SPF/DKIM/DMARC to Cloudflare
make mail-smoke        # API + pod sanity checks
make health            # Includes stalwart mail API check
```

Webmail (inbox): `https://webmail.cronnecture.com` and `https://ops.cronnecture.com/webmail` — full-scale SPA (folders, compose, read) on Stalwart IMAP/SMTP via `/api/mail/*`.  
Mail admin: Manage → **Mail** at `https://ops.cronnecture.com/#/mail` (domains, mailboxes, DNS, send test).  
`/business/mail` redirects to `/webmail`. Both webmail hosts are CF Access → Authentik (same as ops; does not affect Logto portal or Vaultwarden).

## Architecture

| Component | Location | Public access |
|-----------|----------|---------------|
| Stalwart (SMTP/IMAP/JMAP) | k3s `mail` namespace | Public **25**, **587** only (IMAP/JMAP via Cloudflare tunnel / Access — not public 993) |
| Webmail SPA (canonical) | Control plane `static/webmail/` | `webmail.{zone}` + `ops.{zone}/webmail` |
| Mail admin (Manage) | Control plane Manage SPA | `ops.{zone}/#/mail` |
| Mail admin API | Control plane | Ops session / CF Access on `/api/mail/*` |
| DNS records | Cloudflare | MX, SPF, DKIM, DMARC via API |

**Important:** Cloudflare tunnels cover **HTTP(S)** only. SMTP/IMAP go **directly to the VPS public IP** (`MAIL_SERVER_PUBLIC_IP`, default control node `31.97.126.9`).

## Inbound mail checklist

1. Port **25** and **587** open on the VPS firewall (UFW) and listening on the host (Stalwart `hostPort`).
2. Cloudflare MX points to `mail.{zone}` → A record to mail server IP.
3. SPF, DKIM, DMARC published (`make mail-dns` or Mail → DNS in ops UI).

**Status (2026-07-26 evening):** MX, SPF (`-all`), DMARC (`p=quarantine`), PTR, and **DKIM** are live.

| Selector | Algorithm | DNS name |
|----------|-----------|----------|
| **`202607r`** (canonical / Mail domain row) | RSA | `202607r._domainkey.cronnecture.com` |
| `202607e` | Ed25519 | `202607e._domainkey.cronnecture.com` |

Publish/refresh: `make mail-dns` (or Ops → Business → Mail → **Apply DNS**). Deliverability check returns `ok: true` when these TXT records resolve.

**Local caveat:** Debian **exim4** may listen on `127.0.0.1:25`. Probe Stalwart via the mail node (`nc -zv 72.60.32.178 25`) or the mail pod, not localhost.

Verify:

```bash
make mail-smoke
dig @1.1.1.1 MX cronnecture.com +short
dig @1.1.1.1 TXT 202607r._domainkey.cronnecture.com +short   # expect v=DKIM1; k=rsa
dig @1.1.1.1 TXT 202607e._domainkey.cronnecture.com +short   # expect v=DKIM1; k=ed25519
nc -zv 72.60.32.178 25
```

**Automated probe (2026-07-26):**
- Internal delivery with dual DKIM signatures (`s=202607r`, `s=202607e`); host `dkim.verify` = **True**.
- External auth verifier (Port25): `SPF=pass`, `iprev=pass`, `DKIM=pass` (RSA `202607r`). Ed25519 signature reported `permerror` (verifier unsupported algo — harmless while RSA passes).
- **Gmail** ↔ `info@cronnecture.com` roundtrip — **confirmed 2026-07-26** (see [first-clients.md](../business/first-clients.md)).
- **Ops alerts inbox (2026-07-29):** `alerts@cronnecture.com` created; fleet/Alertmanager notify To retargeted from `info@` → `alerts@` (From remains `noreply@`). `test@` removed.
- **Socials / outreach (2026-08-11):** `socials@cronnecture.com` created for social-channel outreach. Open in Ops UI: **Business → Mail** → `socials@`.

## Platform mailboxes

| Address | Role |
|---------|------|
| `info@` | Human sales / prospect outreach From; **marketing contact-form notify To** |
| `support@` | Public support / contact |
| `noreply@` | Platform transactional SMTP From |
| `alerts@` | Fleet / Alertmanager notify To |
| `socials@` | Social-channel outreach |
| `svenbraad@` | Personal |

Mailbox passwords are generated on create (shown once in Ops → Mailboxes), stored encrypted in control-plane DB for IMAP, and for `socials@` also mirrored to gitignored `config/.mail_socials_password` (mode `0600`). Do **not** commit mailbox passwords. Web UI login is ops session (no mailbox password). External SMTP/IMAP: user `socials@cronnecture.com`, host `mail.cronnecture.com` (submission **587**, IMAP via tunnel/Access — not public 993).

## Marketing contact form → email

Public `/contact` on cronnecture.com (and standalone main-site previews) posts to **`POST /api/public/contact`** on the control plane (`VITE_API_URL`, default `https://client.cronnecture.com`). The API validates + honeypot + IP rate-limit (5 / 15 min), inserts into Supabase **`contact_leads`** (service_role) and the CRM inbound prospect pipeline, SMTP-sends immediately to platform setting **`ops_notify_email`** (**To:** `info@cronnecture.com`; **From:** `noreply@`; **Reply-To:** the lead’s email), then auto-acks the lead from **`info@`**. Insert failure does not drop the ops email. The older poller (`leads_notify_service`) is watermarked past the new row so it does not double-mail ops. Portal referrals use the same pipeline with `source=referral`.

Client comms (down/recovered, onboarding sequence, monthly ops report, maintenance 48h/1h, expansion cap) also go through this SMTP path (`noreply@` / `info@`). Presets: **Client comms (hourly)** and **Monthly client ops report**.

## Fleet / ops alerts

Health, backup, watchdog, and Alertmanager failures email `FLEET_NOTIFY_TO` (comma-separated): **`alerts@cronnecture.com`** and `svenbraad.work@gmail.com` via `notify-ops.sh` / control-plane SMTP (**From:** `noreply@`). Open the alerts inbox in Ops UI: **Business → Mail** → `alerts@`. Transactional/human mail stays on `noreply@` / `info@` / `support@`. See [overview.md](overview.md).

## Phone-alert copy-forward (inbound)

Stalwart trusted sieve `copy-to-phone` (in `mail_server` role config) keeps normal delivery to the Cronnecture mailbox **and** sends a copy to `svenbraad.work@gmail.com` when mail arrives at:

- `support@cronnecture.com`
- `info@cronnecture.com`
- `svenbraad@cronnecture.com`

Configured via `mail_phone_alert_*` in `roles/mail_server/defaults/main.yml`. Uses Sieve `redirect :copy` (not a replace). Does **not** change outbound From for outreach (`info@` / `support@`). Apply with `make mail` (brief SMTP gap) or live settings insert + `GET /api/reload/config`.

Verify: send a short message to one of the three addresses → local inbox in Business → Mail **and** Gmail (check spam).

## Outbound mail

Stalwart sends directly from the VPS IP (not via Cloudflare). Reputation depends on:

- SPF/DKIM/DMARC alignment
- **Reverse DNS (PTR)** matching the SMTP HELO hostname
- Low spam complaint rate

Ops UI **Mail → Setup** shows deliverability warnings.

## Reverse DNS (PTR) — Hostinger

PTR affects **outbound** mail only (Gmail/Yahoo spam scoring). It does **not** block inbound mail, web traffic, or tunnels.

### Expected configuration

| Item | Value |
|------|--------|
| Mail server IP | Control node public IP (e.g. `31.97.126.9`) |
| SMTP HELO / mail hostname | `mail.{zone}` (e.g. `mail.cronnecture.com`) |
| Forward DNS | `mail.{zone}` A → same IP |
| Reverse DNS (PTR) | IP → `mail.{zone}` |

**Status (2026-08-27):** public PTR for `72.60.32.178` is `mail.cronnecture.com.` — aligned with HELO. `31.97.126.9` PTR is `cp-master-01.cronnecture.com.`  
Hostinger sometimes defaults PTR to the VPS hostname (`cp-master-01`); that triggers a **PTR mismatch** warning in ops until fixed.

### Steps at Hostinger (if PTR drifts)

1. Log in to [hPanel](https://hpanel.hostinger.com)
2. **VPS** → select the server at your mail IP
3. **Settings** → **Reverse DNS** (or Network → PTR)
4. Set hostname to **`mail.cronnecture.com`**
5. Save (minutes–24h)

### Verify

```bash
# Use an external resolver — local NSS may map the public IP to cp-master-01.
dig @1.1.1.1 -x 31.97.126.9 +short
# expect: mail.cronnecture.com.
```

Ops → **Business → Mail** → deliverability uses public PTR (DoH), not the host's local reverse lookup.

### Alternative to fixing PTR

Relay outbound mail through SendGrid, SES, or Mailgun (transactional SMTP). Inbound can stay on Stalwart. Not configured by default in this fleet.

## Platform SMTP (onboarding emails)

Ops → **Business / Settings → Email**, or:

```bash
curl -X POST http://127.0.0.1:30080/api/mail/bootstrap-smtp ...
```

Required for onboarding emails and platform notifications. See platform readiness:

```bash
curl -s http://127.0.0.1:30080/api/platform/readiness | python3 -m json.tool
```

## Mail rules (filters, auto-reply)

Stored in Supabase PostgREST when `vault_supabase_platform_service_key` is set. Falls back to SQLAlchemy otherwise.

## Prospect reply poll (lead-gen)

Outbound Approve & send uses `info@`. The control-plane **leader** polls that mailbox every ~3 minutes (IMAP `BODY.PEEK`) and sets matching prospects to stage `replied` (or `unsubscribed` on `stop`). Matching and verification steps: [lead-generation.md](../business/lead-generation.md#reply--stage-sync-automated). Manual trigger: `POST /api/prospects/reply-poll`. Does **not** auto-send.

## External send/receive test (manual)

Roadmap item — run after any mail infrastructure change:

1. Gmail → `info@{zone}` (or another live mailbox)
2. Reply from webmail → Gmail inbox (check spam)
3. Confirm DKIM pass in Gmail headers

```bash
make mail-smoke
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Inbound bounces | Port 25 open? MX correct? `kubectl -n mail get pods` |
| Mail in spam (outbound) | PTR, SPF, DKIM, DMARC in Mail → deliverability |
| Webmail 502 | Tunnel + `make control-plane`; not a PTR issue |
| Junk folder empty / errors | IMAP folder quoting fix in control-plane mail service |

See [RB-08 Troubleshooting](../runbooks/troubleshooting.md).

## Related

- [deployment.md](deployment.md) — `make mail` causes brief SMTP gap; use maintenance mode
- [cloudflare.md](cloudflare.md) — DNS API tokens
- [roadmap.md](../architecture/roadmap.md) — Phase 0 mail checklist
- [first-clients.md](../business/first-clients.md) — go-live mail gate
