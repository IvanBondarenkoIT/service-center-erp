# Baseline before warranty EUR / pay date / list chips / order history

Git: tag `baseline-pre-warranty-eur` = `5a79778` on `main`.
Branch for this work: `feature/warranty-pay-history`.

## What already existed

- `PaymentType.warranty` (`garanty`). Chip «Гарантия (0)» zeros GEL and sets `garanty`. Not in till, not in val (`VAL_METHODS` = cash, card, transfer, promo).
- `service_orders.paid_at` (UTC). Cash uses Tbilisi `cash_date()`. Not shown on the order form or list.
- Order list card: visit date, status, model, SN, client, GEL total. No payment-method chips.
- `audit_log` records admin `edit_issued` / `reopen` / `delete` only. Create, workflow status, and pay are not logged.
- No `/repay`. Admin edits an issued order or reopens it, then Pay again.

## Invariants to keep

- Pay still saves then issues; till = cash only; val = cash + terminal + transfer + promo.
- Closed period and issued-form lock stay as they are.
- Excel import warranty rows without EUR stay 0 EUR.

Hub health check currently expects `scerp_tables=16`. After merge this becomes 17 (`order_events`). Update `catalog/service-center-erp.yml` in the deploy hub when going to prod.
