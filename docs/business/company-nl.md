# Dutch eenmanszaak books (Cronnecture)

**Operator books in Cronnecture are the books of record.** Stripe collects card and SEPA payments. There is no Moneybird API and none is planned.

Identity lives in encrypted platform settings (never git):

| Setting | Value (when go-live has been run) |
|---------|-----------------------------------|
| `business_kvk` | KVK `42140905` |
| `business_vat` | BTW-id `NL005528822B26` |
| `business_omzetbelastingnummer` | `322284338B01` |
| `business_legal_name` | Cronnecture |

## What is source of truth

| Need | Tool |
|------|------|
| Ledger, expenses, BTW kinds (incl. reverse-charge), Hosting/Software COGS | **Operator books** (control portal Business board + PdfDrop). Persist disk + etcd ConfigMap + **R2 prefix `operator-books/`** |
| Client quotes, invoices, offers | **Cronnecture commercial docs** (ops Quotes). PDF on `/data/client-documents` and R2 `operator-books/commercial/` |
| Legal pack | **`legal/*.md` → PDF**, public `/legal/*.pdf`, R2 `operator-books/legal/` |
| Client subscriptions, pay links, Customer Portal, dunning URLs | **Stripe** via ops → Business → Client billing |

## Still in ops (Stripe client billing)

| Page | Path |
|------|------|
| Cash flow | `/business/cashflow` |
| Subscriptions | `/business/subscriptions` |
| Stripe invoices | `/business/invoices` |
| Billing clients | `/business/billing-clients` |
| Quotes | Manage → Quotes |

Settings → Billing holds the Stripe secret key / webhook. Customer portal billing is unchanged. Public `/start` Checkout stays **off** unless you explicitly pass `--enable-live-gate`.

## Offsite persist

- Operator ledger: R2 `operator-books/ledger.json` (agent-core `books.py`)
- Legal / commercial / startup PDFs: R2 `operator-books/{legal,commercial,startup-invoices,client-docs}/`
- Fleet backup also tars control-plane `/data/client-documents` into the bundle, then `sync-backup-r2.sh`

## History

Earlier versions exposed practical ops registers for Cronnecture as a Dutch eenmanszaak. Those UI pages were removed from ops; **do not send books to Moneybird**. Use operator books + Stripe.

```bash
cd "${FLEET_ROOT:-$PWD}"
make control-plane
# hard-refresh Business (current shell cache buster, e.g. ?v=2.1.0)
```
