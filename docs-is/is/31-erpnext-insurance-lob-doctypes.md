---
id: erpnext-insurance-lob-doctypes
title: ERP-7 — Insurance LOB Custom Doctypes
sidebar_label: ERP-7 — Insurance LOB Doctypes
---

## Overview

Three custom ERPNext doctypes model the insurance contract lifecycle on top of the standard CRM and billing modules:

| Doctype | Type | Role |
|---|---|---|
| **Insurance Product** | Reference data | Catalogue of insurance products (LOB, pricing, TSCA) |
| **Insurance Policy** | Submittable | Issued contract — links Customer, Product, CRM Opportunity, Sales Invoice |
| **Insurance Claim** | Submittable | Filed sinistre — linked to a Policy, tracks amounts and status |

Two custom fields are added to **Opportunity** to close the CRM → contract loop.

---

## Insurance Product

**Autoname:** `field:product_code` — the code is the unique identifier.

### Fields

| Field | Type | Notes |
|---|---|---|
| `product_code` | Data (unique) | Internal code: `IARD-AUTO-RC`, `IARD-HAB-MRH`, `PREV-IND-01` |
| `product_name` | Data | Commercial name |
| `risk_type` | Select | LOB aligned with CRM `risk_type` options |
| `is_active` | Check | Gates availability in CRM and Policy form |
| `base_premium` | Currency | Annual base premium (€) |
| `tsca_rate` | Float | TSCA rate: 9 / 13 / 33 — see art. 991 CGI |
| `company` | Link → Company | Issuing company |
| `item` | Link → Item | ERPNext Item used on Sales Invoice line |
| `description` | Text Editor | Commercial pitch |
| `coverage_details` | Text Editor | Covered guarantees |
| `exclusions` | Text Editor | Exclusion clauses |

### Seeded products

| Code | LOB | Base premium | TSCA |
|---|---|---|---|
| `IARD-AUTO-RC` | IARD - Automobile | 350 €/yr | 13 % |
| `IARD-HAB-MRH` | IARD - MRH | 180 €/yr | 9 % |
| `PREV-IND-01` | Prévoyance Individuelle | 420 €/yr | 9 % |

---

## Insurance Policy

**Autoname:** `naming_series:` → `INS-POL-.YYYY.-.####`  
**Submittable:** submit = issue the policy, cancel+amend = endorsement.

### Fields

| Field | Type | Notes |
|---|---|---|
| `naming_series` | Select | Series: `INS-POL-.YYYY.-.####` |
| `customer` | Link → Customer | Policyholder |
| `insurance_product` | Link → Insurance Product | Product |
| `status` | Select | En attente / En cours / Suspendu / Résilié / Expiré |
| `company` | Link → Company | |
| `effective_date` | Date | Start of coverage |
| `expiry_date` | Date | End of coverage |
| `renewal_date` | Date | Next renewal date |
| `payment_frequency` | Select | Annuel / Semestriel / Trimestriel / Mensuel |
| `risk_type` | Select | LOB (auto-fill from Product) |
| `insured_name` | Data | If the insured ≠ policyholder |
| `premium_amount` | Currency | Annual premium amount |
| `currency` | Link → Currency | Default EUR |
| `opportunity` | Link → Opportunity | Originating CRM opportunity |
| `sales_invoice` | Link → Sales Invoice | Premium invoice |
| `sepa_mandate_ref` | Data (read-only) | Copied from `Customer.sepa_mandate_id` at issuance |
| `notes` | Text | Free notes |

### Policy lifecycle

```
[Saved — En attente]
        │  submit
        ▼
[Submitted — En cours]
        │  manual status change
        ├──→ Suspendu (non-payment, art. L113-3)
        ├──→ Résilié  (cancelled by insurer or insured)
        └──→ Expiré   (expiry_date reached)
```

Endorsements (avenants) use the standard ERPNext **Cancel + Amend** pattern — each amendment creates a new version with an incremented revision suffix.

---

## Insurance Claim

**Autoname:** `naming_series:` → `INS-CLM-.YYYY.-.####`  
**Submittable:** submit = official claim filing.

### Fields

| Field | Type | Notes |
|---|---|---|
| `naming_series` | Select | Series: `INS-CLM-.YYYY.-.####` |
| `policy` | Link → Insurance Policy | Parent policy |
| `customer` | Link → Customer | Auto-fetched from `policy.customer` |
| `status` | Select | Déclaré → En cours → Expertisé → Accepté / Refusé → Réglé → Clôturé |
| `company` | Link → Company | Auto-fetched from `policy.company` |
| `incident_date` | Date | Date of loss event |
| `declaration_date` | Date | Date claim was filed (defaults to today) |
| `risk_type` | Select | Auto-fetched from `policy.risk_type` |
| `adjuster_name` | Data | Independent loss adjuster (expert) |
| `claim_amount` | Currency | Declared loss amount |
| `settlement_amount` | Currency | Settled/paid amount |
| `currency` | Link → Currency | Default EUR |
| `description` | Text Editor | Description of the loss event |
| `notes` | Text | Internal notes |

### Claim status workflow

```
Déclaré
   └──→ En cours d'instruction
              └──→ Expertisé
                      ├──→ Accepté  ──→ Réglé ──→ Clôturé
                      └──→ Refusé              ──→ Clôturé
```

---

## CRM Opportunity — New Fields

Two fields added to the **Opportunity** doctype (collapsible section, inserted after `risk_type`):

| Field | Type | Notes |
|---|---|---|
| `quoted_product` | Link → Insurance Product | Product shown to the prospect |
| `linked_policy` | Link → Insurance Policy (read-only) | Policy created at conversion — filled manually or by automation |

**Full CRM → Contract flow:**

```
Lead (ORIAS, broker_ref, risk_type)
   └──→ Opportunity (quoted_product, CRM stages)
              └──→ Insurance Policy (opportunity link back)
                       └──→ Sales Invoice (prime)
                       └──→ Insurance Claim (sinistres)
```

---

## Reproduction

```bash
POD=$(kubectl get pod -n erp -l app.kubernetes.io/name=erpnext-gunicorn \
  -o jsonpath='{.items[0].metadata.name}')

# Create doctypes + Opportunity fields
kubectl cp scripts/setup_insurance_doctypes.py erp/${POD}:/tmp/
kubectl exec -n erp ${POD} -- bash -c \
  "cd /home/frappe/frappe-bench/sites && \
   /home/frappe/frappe-bench/env/bin/python /tmp/setup_insurance_doctypes.py"

# Seed the 3 standard products
kubectl cp scripts/setup_insurance_products.py erp/${POD}:/tmp/
kubectl exec -n erp ${POD} -- bash -c \
  "cd /home/frappe/frappe-bench/sites && \
   /home/frappe/frappe-bench/env/bin/python /tmp/setup_insurance_products.py"
```

Expected summary output:
```
=== Summary ===
  ✓  Insurance Product
  ✓  Insurance Policy
  ✓  Insurance Claim
  Opportunity custom fields: 4/4
```

---

## Known gotchas

**`Series` fieldtype removed in Frappe v16.** Use `Select` with the series pattern as `options` (e.g. `"INS-POL-.YYYY.-.####\n"`). Set `doc.autoname = "naming_series:"` on the DocType. Frappe handles the auto-increment from the Select field at save time.

**`fetch_from` is UI-only.** Fields with `fetch_from = "policy.customer"` auto-populate in the browser form when the Link field changes. They do not populate on programmatic insert — always set them explicitly in scripts or API calls.

**Custom DocType module must be `"Custom"`.** Using any other module name (e.g. `"Selling"`) causes the DocType to appear in a non-existent app namespace and may conflict with standard module permissions.
