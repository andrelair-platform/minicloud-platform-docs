---
id: erpnext-billing-dunning
title: ERP-6 — Billing, SEPA Mandates & Dunning Automation
sidebar_label: ERP-6 — Billing & Dunning
---

## Overview

This page covers the full billing lifecycle for the French insurance IS:

1. **End-to-end payment → reconciliation** via Stripe PaymentIntent and ERPNext Payment Entry
2. **SEPA direct debit mandate tracking** on the Customer doctype
3. **Automated dunning pipeline** for unpaid premiums (Rappel amiable → Mise en demeure → Mise en demeure finale)

---

## Payment → Reconciliation Flow

### How it works

```
Stripe PaymentIntent.succeeded
         │
         ▼
stripe_webhook() endpoint
         │
         ▼
_handle_payment_succeeded()
    │  looks up Sales Invoice by stripe_payment_intent_id
    │  checks outstanding_amount > 0 (idempotent)
    ▼
_create_payment_entry()
    • mode_of_payment  = "Prélèvement SEPA"
    • party_type       = "Customer"
    • paid_from        = default_receivable_account (4111)
    • paid_to          = default_bank_account (5121)
    • references table → links to the Sales Invoice
    • PE.submit()      → ERPNext auto-decrements outstanding_amount
         │
         ▼
stripe_payment_status = "succeeded" stored on Sales Invoice
```

When the Payment Entry is submitted, ERPNext reconciles it against the Sales Invoice via the `references` child table — `outstanding_amount` drops to 0. No manual reconciliation step is needed.

### Mode of Payment

A dedicated Mode of Payment **"Prélèvement SEPA"** (type: Bank) is created and linked to account `5121 - Comptes en euros - KS`. All SEPA payments route through this MoP, keeping them distinct from wire transfers and card payments in GL reports.

---

## SEPA Mandate Tracking

When Stripe fires `setup_intent.succeeded` (confirming a new SEPA mandate), the webhook stores five fields on the ERPNext Customer:

| Customer field | Source | Notes |
|---|---|---|
| `stripe_payment_method_id` | `setup_intent.payment_method` | Stripe PM ID |
| `sepa_mandate_id` | `setup_intent.mandate` | Stripe Mandate ID (`mandate_xxx`) |
| `sepa_mandate_date` | Server date at webhook receipt | Date the mandate was confirmed |
| `sepa_iban_display` | `stripe.PaymentMethod.retrieve(pm_id).sepa_debit.last4` | Masked IBAN, e.g. `****3201` |
| `sepa_mandate_status` | Hard-coded `"Actif"` on creation | Lifecycle: Actif / Annulé / Suspendu / Expiré |

**IBAN display resilience:** the Stripe API call to retrieve `last4` is wrapped in a try/except. If Stripe is unreachable at webhook time, the mandate ID, date, and status are still stored correctly — only the display field is skipped.

**Status lifecycle:** `sepa_mandate_status` is a Select field updated manually (or by a future webhook handler for `mandate.updated` events) when a mandate is cancelled or suspended.

---

## Dunning Automation

### Dunning Types

Three Dunning Types are configured, corresponding to the three escalation levels under French insurance law:

| Level | Dunning Type | Trigger | Fee | Interest | Legal basis |
|---|---|---|---|---|---|
| 1 | Rappel amiable | J+10 | 0 € | 0% | Good faith reminder |
| 2 | Mise en demeure | J+30 | 10 € | 0.5%/month | Art. L113-3 Code des assurances — suspension notice |
| 3 | Mise en demeure finale | J+60 | 25 € | 1%/month | Art. L113-3 — résiliation notice + contentieux |

Each Dunning Type contains a French-language letter body stored in the `dunning_letter_text` child table (doctype: **Dunning Letter Text**, field: `body_text`).

### L113-3 Code des assurances timeline

```
Échéance non réglée
     │
    J+10  ──→  Rappel amiable
     │
    J+30  ──→  Mise en demeure (10 jours pour payer)
     │
    J+40  ──→  SUSPENSION DE GARANTIE (30 jours après mise en demeure)
     │
    J+50  ──→  RÉSILIATION DE PLEIN DROIT (10 jours après suspension)
```

### Auto-dunning Server Script

An ERPNext **Server Script** named `"Auto Dunning — Primes impayées"` runs daily via the Frappe scheduler. Logic:

```python
# Simplified pseudocode
for invoice in overdue_submitted_invoices(company="Ktayl Solutions"):
    days_over = date_diff(today, invoice.due_date)
    level = select_level(days_over)   # 10→L1, 30→L2, 60→L3
    if not already_dunned(invoice, level):
        create_dunning(invoice, level)
```

Deduplication: the script queries `tabDunning` joined to `tabOverdue Payment` — if a Dunning doc already exists for the (invoice, dunning_type) combination and is not cancelled (`docstatus != 2`), it is skipped.

**Error isolation:** each invoice is created inside a try/except; a failure on one invoice logs to `frappe.log_error("Dunning Automation")` and continues to the next invoice.

---

## Reproduction

```bash
# Get the gunicorn pod name
POD=$(kubectl get pod -n erp -l app.kubernetes.io/name=erpnext-gunicorn \
  -o jsonpath='{.items[0].metadata.name}')

# Copy and run the billing setup script (from minicloud-erpnext repo)
kubectl cp scripts/setup_billing.py erp/${POD}:/tmp/setup_billing.py
kubectl exec -n erp ${POD} -- bash -c \
  "cd /home/frappe/frappe-bench/sites && \
   /home/frappe/frappe-bench/env/bin/python /tmp/setup_billing.py"
```

Expected output:
```
=== Summary ===
  Prélèvement SEPA MoP : ✓
  Mandate fields        : 4/4
  Dunning Types         : 3/3
  Auto-dunning script   : ✓
```

---

## Known gotchas

**`dunning_letter_text` is a Table, not Text.** In ERPNext v16, the letter content lives in the child doctype `Dunning Letter Text` (field: `body_text`). Do not try to set it as a string via `doc.update()` or `doc.set()` — use `doc.append("dunning_letter_text", {})` and set `row.body_text`.

**Stripe PaymentMethod.retrieve uses attribute access.** The Stripe Python SDK returns `StripeObject` instances, not dicts. Use `getattr(pm, "sepa_debit", None)` and `getattr(sepa_obj, "last4", None)`, not `.get()`, to keep mypy happy.

**Prélèvement SEPA MoP must exist before deploying api.py.** The Payment Entry creation will fail with a validation error if the Mode of Payment does not exist. Run the setup script before or alongside the code deployment.

**Dunning deduplication is at (invoice, dunning_type) level.** If you want to re-send a dunning at the same level (e.g., after a partial payment), cancel the existing Dunning doc first (`docstatus = 2`).
