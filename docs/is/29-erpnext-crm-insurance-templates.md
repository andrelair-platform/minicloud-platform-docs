---
id: erpnext-crm-insurance-templates
title: ERP-5 — CRM Insurance Customisations & Print Templates
sidebar_label: ERP-5 — CRM & Print Templates
---

## Overview

This page covers two sets of ERPNext customisations applied to the French insurance IS:

1. **CRM custom fields** — ORIAS number, broker reference, risk type on Lead and Opportunity
2. **Insurance print templates** — *Avis de prime* and *Quittance de prime* Jinja print formats on Sales Invoice

Both were applied live via the `setup_crm.py` and `setup_print_formats.py` scripts executed inside the gunicorn pod.

---

## CRM Custom Fields

### Fields created

| Doctype | Fieldname | Label | Type | Purpose |
|---|---|---|---|---|
| Lead | `orias_number` | Numéro ORIAS | Data | ORIAS registration number of the intermediary (CIF/COA/MIA/ALPSI) |
| Lead | `broker_ref` | Référence courtier | Data | Internal broker/cabinet reference |
| Lead | `risk_type` | Type de risque | Select | Insurance line of business |
| Opportunity | `orias_number` | Numéro ORIAS | Data | Same — carried over from Lead |
| Opportunity | `broker_ref` | Référence courtier | Data | Same |
| Opportunity | `risk_type` | Type de risque | Select | Same |

### `risk_type` options

Aligned with the LOB hierarchy created in ERP-1:

```
IARD - Automobile
IARD - MRH
IARD - RC Professionnelle
IARD - Transport
IARD - Construction
IARD - Agricole
IARD - Risques Industriels
IARD - Risques Divers
Vie
Prévoyance Individuelle
Prévoyance Collective
Épargne
```

### ORIAS context

The ORIAS number (Organisme pour le Registre des Intermédiaires en Assurance) is the mandatory French registry reference for any insurance intermediary. Capturing it on Lead and Opportunity allows:

- Pre-qualification of incoming leads from brokers
- Automatic ORIAS validation (future: API check against `https://www.orias.fr/`)
- Audit trail required by ACPR for intermediary relationships

---

## Sales Person Tree

Three channel groups created under the default `Sales Team` root:

```
Sales Team  (root group)
├── Courtage       → broker-originated business
├── Direct         → direct-to-customer (no intermediary)
└── Grands Comptes → large account / corporate relationships
```

Assign individual sales reps under each channel via **CRM → Sales Person**.

---

## Print Formats

### Avis de prime (Premium Notice)

**Name in ERPNext:** `Avis de prime (Assurance)`  
**Doctype:** Sales Invoice  
**Use:** Send before payment due date — requests settlement of the premium.

Key sections:

| Section | Content |
|---|---|
| Header | Company name, ORIAS number, invoice reference, issue date |
| Parties | Assureur (company) / Assuré (customer) side-by-side |
| Meta strip | Invoice number, issue date, due date (highlighted red), currency |
| Items table | Guarantee/service description, qty, unit price HT, amount HT, item code |
| Totals | Net HT + TSCA breakdown (per tax row) + **Total TTC** |
| Payment notice | Warning block quoting art. L113-3 Code des assurances (suspension of cover) |
| Payment instructions | IBAN / BIC / SEPA mandate mention |
| Legal footer | TSCA reference (art. 991 CGI), ORIAS mention |

**How to print:** Sales Invoice → Print → select `Avis de prime (Assurance)`.

### Quittance de prime (Payment Receipt)

**Name in ERPNext:** `Quittance de prime (Assurance)`  
**Doctype:** Sales Invoice  
**Use:** Issue after payment is confirmed — serves as proof of coverage.

Key sections:

| Section | Content |
|---|---|
| Header | Company name, ORIAS number, invoice reference, issue date (green theme) |
| Paid stamp | "✓ Prime acquittée" banner + amount + Stripe payment reference (if set) |
| Parties | Same two-column layout as Avis de prime |
| Meta strip | Invoice number, issue date, status (Payée), currency |
| Items table | Same as Avis + TTC column per line |
| Totals | Net HT + TSCA + **Total acquitté** |
| Coverage attestation | Legal statement: payment received, contract valid, customer name embedded |
| Legal footer | Quittance legal basis, TSCA reference, electronic document clause |

**How to print:** Sales Invoice → Print → select `Quittance de prime (Assurance)`.

:::tip Stripe integration
When `stripe_payment_intent_id` is set on the invoice (auto-populated by the Stripe webhook receiver — see issue #3), the Quittance stamp line automatically shows the Stripe payment reference.
:::

---

## Reproduction

To recreate these on a fresh ERPNext site:

```bash
# 1. Clone the repo
git clone https://github.com/andrelair-platform/minicloud-erpnext /tmp/erpnext-apps

# 2. Copy scripts into the gunicorn pod
POD=$(kubectl get pod -n erp -l app.kubernetes.io/name=erpnext-gunicorn \
  -o jsonpath='{.items[0].metadata.name}')

kubectl cp /tmp/erpnext-apps/erpnext_sepa/scripts/setup_crm.py erp/${POD}:/tmp/setup_crm.py
kubectl cp /tmp/erpnext-apps/print_formats/avis_prime.html erp/${POD}:/tmp/avis_prime.html
kubectl cp /tmp/erpnext-apps/print_formats/quittance.html erp/${POD}:/tmp/quittance.html
kubectl cp /tmp/erpnext-apps/print_formats/setup_print_formats.py erp/${POD}:/tmp/setup_print_formats.py

# 3. Run both scripts
BENCH=/home/frappe/frappe-bench
kubectl exec -n erp ${POD} -- bash -c \
  "cd ${BENCH}/sites && ${BENCH}/env/bin/python /tmp/setup_crm.py"
kubectl exec -n erp ${POD} -- bash -c \
  "cd ${BENCH}/sites && ${BENCH}/env/bin/python /tmp/setup_print_formats.py"
```

---

## Design decisions

**TSCA not TVA** — tax rows on both templates render generically from `doc.taxes`, so they correctly show TSCA (9%/13%/33%) as configured in ERP-1 rather than hard-coding TVA labels.

**Colour coding** — Avis de prime uses blue (`#1a3a5c`) to convey urgency/request; Quittance uses green (`#1a5c3a`) to convey completion/confirmation. Consistent with French insurance document conventions.

**No hard-coded IBAN** — the IBAN in the Avis de prime payment block should be updated to match the real creditor account once SEPA Direct Debit is fully wired (issue #3).
