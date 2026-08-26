# Mail identity freeze

Do not recreate Cronnecture mail as a new product. Addresses and store must
survive the JS API rewrite and any later IP move.

## Frozen names

| Kind | Value |
|------|--------|
| SMTP/MX host | `mail.cronnecture.com` |
| Webmail | `webmail.cronnecture.com` |
| Addresses | `info@` `support@` `noreply@` `alerts@` `socials@` `svenbraad@` |
| DKIM | `202607r` (RSA), `202607e` (Ed25519) |
| Public IP today | `31.97.126.9` (PTR + SPF `ip4:`) |

People and SPF talk to **`mail.cronnecture.com`**, not the VPS IP.

## What daily backup now captures

`backup-fleet.sh` (full) writes `mail/` in the stamp:

- `IDENTITY.txt` — frozen host + addresses
- `stalwart-data.tar.gz` — PVC store (inboxes). Losing this is empty mailboxes with the same address.
- `stalwart-config.yaml` — live ConfigMap
- `dns.txt` — MX / SPF / DKIM / DMARC / A snapshot
- `.mail_admin_password` if present on the control host

Mailbox IMAP passwords stay in the platform DB (encrypted). The JS `api-mail`
module must **read** those rows, never generate new passwords on cutover.

## Later move (not this pass)

1. Restore the same PVC (or `stalwart-data.tar.gz`) onto the new pod.
2. Keep every `@cronnecture.com` address and both DKIM selectors.
3. Change only A + PTR + SPF `ip4:` to the new mail IP.
4. Dual-MX only if you need a zero-downtime window.
5. Never `make mail` against a blank volume and call it a migration.

## JS API

`api-mail` is a catalog module. It calls the existing Stalwart admin/JMAP API
and `api-data` for mailbox metadata. It is not a second mail store.
