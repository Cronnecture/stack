# Business management suite — **deprecated**

> **Use [Moneybird](https://www.moneybird.nl/) for bookkeeping / tax / expenses / banking, and Stripe for client subscriptions.**  
> The custom eenmanszaak registers in ops were removed in control-plane **0.99.64**.

## What replaced it

| Need | Tool |
|------|------|
| Invoices, expenses, bank, BTW, hours | **Moneybird** |
| Client subscriptions, pay links, portal, open invoices | **Stripe** via ops → **Business → Client billing** |

## Still in ops (Stripe client billing)

| Page | Path |
|------|------|
| Cash flow | `/business/cashflow` |
| Subscriptions | `/business/subscriptions` |
| Stripe invoices | `/business/invoices` |
| Billing clients | `/business/billing-clients` |

Settings → Billing still holds the Stripe secret key / webhook. Customer portal billing for clients is unchanged.

## Removed from ops

- Management: Overview, Sales, Expenses, Banking, Time, Mileage, Tax  
- Legal Documents (eenmanszaak contracts gallery)  
- UI: `eenmanszaak.js`  
- API mount: `/api/business/ez/*` (router unmounted; DB tables left in place, unused)  
- Old URLs (`/business/overview`, `/business/sales`, `ez-*`, …) redirect to Cash flow or Stripe invoices

## History

Earlier versions exposed practical ops registers for Cronnecture as a Dutch eenmanszaak. That suite is no longer maintained here.

```bash
cd "${FLEET_ROOT:-$PWD}"
make control-plane
# hard-refresh Business (current shell cache buster, e.g. ?v=2.1.0)
```
