---
id: erpnext-french-insurance-config
title: ERP-1 — ERPNext French Insurance IS Configuration
sidebar_label: ERP-1 — French Insurance Config
---

# ERP-1 — ERPNext French Insurance IS Configuration

Sprint 3 (2026-08-10). ERPNext v16.28.0 is already deployed (Phase 79). This sprint activates the full French insurance IS scope: Chart of Accounts (PCG 2025), CRM pipeline, tax templates (TVA + TSCA), LOB product hierarchy, and a Factur-X e-invoicing proof of concept.

---

## Context

| Layer | Status |
|---|---|
| ERPNext v16.28.0 deployed | ✅ Phase 79 |
| HR module + Employee onboarding | ✅ Phase 79 |
| Authentik SSO | ✅ Phase 79 |
| French PCG 2025 chart of accounts | ✅ ERP-1 |
| CRM insurance pipeline | ✅ ERP-1 |
| Tax templates (TVA + TSCA) | ✅ ERP-1 |
| LOB product hierarchy | ✅ ERP-1 |
| Factur-X Minimum PoC | ✅ ERP-1 |
| Factur-X PDF/A-3 embedding | ⬜ Phase 90 |
| Insurance custom doctypes (Police, Sinistre) | ⬜ Phase 88 |

---

## French Plan Comptable Général 2025

### Why replace the default chart

The ERPNext setup wizard installs a generic English "Standard" chart (94 accounts with no account numbers, named "Cash - KS", "Debtors - KS", etc.). For a French company, this is unusable: no DGFIP audit compliance, no TSCA tax accounts, no PCG numbering.

ERPNext v16 ships `fr_plan2025_comptable_general_avec_code.json` — the 2025 PCG with full account numbers. This is the correct chart for a French commercial company.

### Migration script

:::caution Run from `sites/` not bench root
`frappe.init()` uses relative paths for logger. The script must be executed from `/home/frappe/frappe-bench/sites/`, not `/home/frappe/frappe-bench/`.
:::

```python
# Run via: kubectl exec -n erp <pod> -- bash -c 'cd /home/frappe/frappe-bench/sites && python /tmp/script.py'

import frappe
frappe.init(site="erp.devandre.sbs", sites_path="/home/frappe/frappe-bench/sites")
frappe.connect()

# Safe to delete if GL entries = 0 (verified first)
frappe.db.sql("DELETE FROM `tabAccount` WHERE company=%s", ("Ktayl Solutions",))
frappe.db.commit()

from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts
create_charts("Ktayl Solutions", chart_template="France - Plan Comptable General 2025 avec code")
frappe.db.commit()

# Flush Redis cache — required after COA replacement
frappe.cache.flushall()
frappe.db.commit()

frappe.destroy()
```

**Result: 845 accounts loaded** with PCG numbers (101-Capital, 411-Clients, 4111-Clients ventes, 512-Banques, 5121-Comptes en euros, 706-Prestations de services, etc.).

### Company default accounts

After loading the PCG, map the company default fields to the correct French accounts:

| ERPNext field | PCG account |
|---|---|
| `default_receivable_account` | `4111 - Clients - Ventes de biens ou de prestations de services - KS` |
| `default_payable_account` | `4011 - Fournisseurs - Achats de biens et prestations de services - KS` |
| `default_bank_account` | `5121 - Comptes en euros - KS` |
| `default_income_account` | `706 - Prestations de services - KS` |
| `round_off_account` | `6581 - Pénalités sur marchés ... - KS` |

:::warning Update via SQL, not `company_doc.save()`
After COA replacement, `company_doc.save()` raises `LinkValidationError` for any field that still references a deleted English account. Set fields via direct SQL `UPDATE` on `tabCompany`, then call `frappe.db.commit()`.
:::

```python
fields = {
    "default_receivable_account": "4111 - Clients - Ventes de biens ou de prestations de services - KS",
    "default_payable_account":    "4011 - Fournisseurs - Achats de biens et prestations de services - KS",
    "default_bank_account":       "5121 - Comptes en euros - KS",
}
for field, value in fields.items():
    frappe.db.sql(f"UPDATE `tabCompany` SET `{field}` = %s WHERE name = %s", (value, "Ktayl Solutions"))
frappe.db.commit()
```

### Key PCG accounts for insurance

| Account | Number | Use |
|---|---|---|
| Clients ventes | 4111 | Receivable — premium billing |
| Fournisseurs | 4011 | Payable — reinsurers, brokers |
| Banques EUR | 5121 | Bank — premium collection account |
| Prestations de services | 706 | Income — insurance premiums |
| Taxes assimilées à la TVA | 44578 | TSCA collection account |
| TVA collectée 20% | 445720 | Standard TVA (non-insurance products) |
| TVA collectée 10% | 445710 | Intermediate TVA |
| TVA collectée 5.5% | 445755 | Reduced TVA |
| TVA à décaisser | 44551 | TVA settlement |
| TVA 20% Déductible | 445620 | Input TVA on purchases |
| Sinistres à payer | 601 | Claims provision |

---

## CRM Pipeline — Insurance Stages

### Sales stages

Replaced the generic English stages with insurance-specific French stages:

| Stage | Description |
|---|---|
| **Prospection** | First contact, suspect identification |
| **Qualification** | Risk appetite, budget, decision timeline |
| **Analyse des besoins** | Risk assessment, coverage scope definition |
| **Proposition commerciale** | Quote issued, technical terms sent |
| **Négociation** | Premium adjustment, conditions discussion |
| **Accord souscription** | Underwriting accepted, contract pending |
| **Gagnée** | Policy issued and active |
| **Perdue** | Opportunity closed-lost |

### Opportunity types

| Type | When to use |
|---|---|
| **Nouvelle Affaire** | New policy, first contact with prospect |
| **Renouvellement** | Annual renewal of existing policy |
| **Avenant** | Mid-term amendment (coverage extension, address change) |
| **Résiliation & Remplacement** | Competitor policy replacing → Ktayl |
| **Upselling** | Additional coverage or product to existing client |

### Payment terms

| Template | Use |
|---|---|
| Comptant | One-time payment at binding |
| 30 jours nets | Standard trade term (non-insurance, ancillary services) |
| Mensuel prélèvement | Monthly direct debit (individual clients) |
| Trimestriel | Quarterly instalment (SME clients) |

```python
# Pattern: create CRM sales stages
from frappe import get_doc
for stage in ["Prospection", "Qualification", "Analyse des besoins",
              "Proposition commerciale", "Négociation", "Accord souscription",
              "Gagnée", "Perdue"]:
    get_doc({"doctype": "Sales Stage", "stage_name": stage}).insert(ignore_permissions=True)
frappe.db.commit()
```

---

## Tax Templates — TVA and TSCA

### Why insurance uses TSCA, not TVA

Insurance premiums in France are **exempt from TVA** (Article 261C-2 CGI) but subject to **TSCA** (Taxe Spéciale sur les Conventions d'Assurance, Article 991 CGI). TSCA is collected by the insurer and paid to the Treasury — it behaves like a tax on the invoice but books to a different account (`44578`, not `4457x`).

| Tax | Rate | Scope |
|---|---|---|
| TSCA | 9% | Life insurance, prévoyance |
| TSCA | 13% | Multi-risk habitation, property |
| TSCA | 33% | RC Auto (accidents corporels) |
| TVA | 20% | Ancillary services (non-insurance) |
| TVA | 10% | Intermediate rate products |
| TVA | 5.5% | Reduced rate (food, books, energy) |
| Exonéré | 0% | Export, intracommunautaire |

### PCG tax accounts

```
4457x — TVA collectée
  445710 — TVA 10% Collectée
  445720 — TVA 20% Collectée
  445721 — TVA 2.1% Collectée
  445755 — TVA 5.5% Collectée
  44578  — Taxes assimilées à la TVA   ← TSCA (all insurance rates)
```

**TSCA for all 3 insurance rates books to the same account `44578`**. The distinction (9%/13%/33%) is captured in the tax template name, not the account number.

### Creating tax templates

```python
def create_tax_template(title, rate, account_number):
    acct = frappe.db.get_value("Account", {"company": company, "account_number": account_number}, "name")
    frappe.get_doc({
        "doctype": "Sales Taxes and Charges Template",
        "title": title,
        "company": company,
        "taxes": [{
            "charge_type": "On Net Total",
            "account_head": acct,
            "description": title,
            "rate": rate,
        }]
    }).insert(ignore_permissions=True)
```

:::warning ERPNext appends company abbreviation to template names
When `company` is set, ERPNext stores the template `name` as `"{title} - {abbr}"`. Access templates as:
- `"TVA 20% (Taux Normal) - KS"` (not `"TVA 20% (Taux Normal)"`)
- `"TSCA (Assurance) 13% - KS"` (not `"TSCA (Assurance) 13%"`)

Use `frappe.db.get_all("Sales Taxes and Charges Template", fields=["name", "title"])` to verify actual stored names.
:::

---

## LOB Product Hierarchy

### Item group tree

```
All Item Groups
└── Produits d'Assurance          ← parent (is_group=1)
    ├── IARD                       ← is_group=1
    │   ├── Automobile             ← leaf (is_group=0)
    │   ├── Habitation
    │   ├── Responsabilité Civile
    │   ├── Construction
    │   ├── Marine & Transport
    │   ├── Lignes Financières
    │   ├── Agricole
    │   └── International
    └── Vie & Prévoyance           ← is_group=1
        ├── Prévoyance Individuelle
        ├── Prévoyance Collective
        └── Épargne
```

### Insurance product items

| Item Code | Name | LOB Group | Tax Template |
|---|---|---|---|
| `IARD-AUTO-RC` | Responsabilité Civile Automobile | Automobile | TSCA (RC Auto) 33% - KS |
| `IARD-HAB-MRH` | Assurance Multirisque Habitation | Habitation | TSCA (Assurance) 13% - KS |
| `PREV-IND-01` | Prévoyance Individuelle | Prévoyance Individuelle | *(none — exonéré)* |

```python
# Non-stock service item with LOB income account
frappe.get_doc({
    "doctype": "Item",
    "item_code": "IARD-HAB-MRH",
    "item_name": "Assurance Multirisque Habitation",
    "item_group": "Habitation",
    "is_stock_item": 0,
    "is_service_item": 1,
    "taxes": [{"item_tax_template": "TSCA (Assurance) 13% - KS"}],
    "item_defaults": [{"company": company, "income_account": "706 - Prestations de services - KS"}],
}).insert(ignore_permissions=True)
```

---

## Fiscal Year and Test Invoice

### Fiscal Year 2026

Must be created before any invoice with a 2026 posting date. ERPNext raises `FiscalYearError` if the posting date falls outside all configured fiscal years.

```python
frappe.get_doc({
    "doctype": "Fiscal Year",
    "year": "2026",
    "year_start_date": "2026-01-01",
    "year_end_date": "2026-12-31",
    "companies": [{"company": "Ktayl Solutions"}],
}).insert(ignore_permissions=True)
frappe.db.set_value("Global Defaults", "Global Defaults", "current_fiscal_year", "2026")
frappe.db.commit()
```

### Test invoice — ACC-SINV-2026-00001

| Field | Value |
|---|---|
| Customer | Entreprise ABC |
| Posting date | 2026-08-10 |
| Item | Assurance Multirisque Habitation |
| Qty | 1 | Rate | 1 500,00 € |
| Tax | TSCA (Assurance) 13% → 44578 | 195,00 € |
| **Grand total** | **1 695,00 €** |

The invoice validates that the full accounting chain works: product item → LOB group → TSCA tax account (`44578`) → French PCG receivable (`4111`).

---

## Factur-X e-Invoicing PoC

### Regulatory context

France mandates structured e-invoicing for B2B transactions between French VAT-registered companies:
- **September 2026**: Large enterprises must be capable of **receiving** Factur-X invoices via PPF or a PDP (Plateforme de Dématérialisation Partenaire)
- **September 2026**: Large enterprises must **emit** structured invoices
- SMEs follow in 2027

**Factur-X** is a Franco-German hybrid format: a PDF/A-3 file with an embedded UN/CEFACT CII (Cross-Industry Invoice) XML attachment. The profile hierarchy: MINIMUM → BASIC WL → BASIC → EN16931 → EXTENDED. `MINIMUM` contains only the legally mandatory fields.

### ERPNext v16 — no native Factur-X

ERPNext v16 does not include Factur-X generation. The `factur-x` Python library is not installed in the chart image. The production path is:

1. Install `factur-x` library in a custom ERPNext image (Phase 90)
2. Add a Frappe `on_submit` hook on Sales Invoice that calls the generator
3. Attach the PDF/A-3 to the submitted document and submit to PDP

### Factur-X Minimum XML PoC

The PoC demonstrates generating valid CII XML using only the Python standard library. No extra packages required.

```python
import xml.etree.ElementTree as ET
from xml.dom import minidom

NS_RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
NS_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
NS_UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

ET.register_namespace("rsm", NS_RSM)
ET.register_namespace("ram", NS_RAM)
ET.register_namespace("udt", NS_UDT)

root = ET.Element(f"{{{NS_RSM}}}CrossIndustryInvoice")

# 1. ExchangedDocumentContext — mandatory: GuidelineID
ctx = ET.SubElement(root, f"{{{NS_RSM}}}ExchangedDocumentContext")
param = ET.SubElement(ctx, f"{{{NS_RAM}}}GuidelineSpecifiedDocumentContextParameter")
ET.SubElement(param, f"{{{NS_RAM}}}ID").text = "urn:factur-x.eu:1p0:minimum"

# 2. ExchangedDocument — mandatory: ID, TypeCode 380, IssueDateTime
doc = ET.SubElement(root, f"{{{NS_RSM}}}ExchangedDocument")
ET.SubElement(doc, f"{{{NS_RAM}}}ID").text = "ACC-SINV-2026-00001"
ET.SubElement(doc, f"{{{NS_RAM}}}TypeCode").text = "380"  # Commercial Invoice
idt = ET.SubElement(doc, f"{{{NS_RAM}}}IssueDateTime")
ET.SubElement(idt, f"{{{NS_UDT}}}DateTimeString", format="102").text = "20260810"

# 3. SupplyChainTradeTransaction
txn = ET.SubElement(root, f"{{{NS_RSM}}}SupplyChainTradeTransaction")
agr = ET.SubElement(txn, f"{{{NS_RAM}}}ApplicableHeaderTradeAgreement")

# Seller — mandatory: Name + SpecifiedLegalOrganization (SIRET, schemeID=0002)
seller = ET.SubElement(agr, f"{{{NS_RAM}}}SellerTradeParty")
ET.SubElement(seller, f"{{{NS_RAM}}}Name").text = "Ktayl Solutions"
org = ET.SubElement(seller, f"{{{NS_RAM}}}SpecifiedLegalOrganization")
ET.SubElement(org, f"{{{NS_RAM}}}ID", schemeID="0002").text = "12345678900014"
addr = ET.SubElement(seller, f"{{{NS_RAM}}}PostalTradeAddress")
ET.SubElement(addr, f"{{{NS_RAM}}}CountryID").text = "FR"
tax_reg = ET.SubElement(seller, f"{{{NS_RAM}}}SpecifiedTaxRegistration")
ET.SubElement(tax_reg, f"{{{NS_RAM}}}ID", schemeID="VA").text = "FR12345678900"

# Buyer — mandatory: Name
buyer = ET.SubElement(agr, f"{{{NS_RAM}}}BuyerTradeParty")
ET.SubElement(buyer, f"{{{NS_RAM}}}Name").text = "Entreprise ABC"

# Delivery — mandatory (empty for MINIMUM profile)
ET.SubElement(txn, f"{{{NS_RAM}}}ApplicableHeaderTradeDelivery")

# Settlement — mandatory: currency, tax breakdown, monetary summation
stt = ET.SubElement(txn, f"{{{NS_RAM}}}ApplicableHeaderTradeSettlement")
ET.SubElement(stt, f"{{{NS_RAM}}}InvoiceCurrencyCode").text = "EUR"

tax = ET.SubElement(stt, f"{{{NS_RAM}}}ApplicableTradeTax")
ET.SubElement(tax, f"{{{NS_RAM}}}CalculatedAmount").text = "195.0"   # TSCA 13%
ET.SubElement(tax, f"{{{NS_RAM}}}TypeCode").text = "VAT"
ET.SubElement(tax, f"{{{NS_RAM}}}BasisAmount").text = "1500.0"
ET.SubElement(tax, f"{{{NS_RAM}}}CategoryCode").text = "S"
ET.SubElement(tax, f"{{{NS_RAM}}}RateApplicablePercent").text = "13"

summ = ET.SubElement(stt, f"{{{NS_RAM}}}SpecifiedTradeSettlementHeaderMonetarySummation")
ET.SubElement(summ, f"{{{NS_RAM}}}TaxBasisTotalAmount").text = "1500.0"
ET.SubElement(summ, f"{{{NS_RAM}}}TaxTotalAmount", currencyID="EUR").text = "195.0"
ET.SubElement(summ, f"{{{NS_RAM}}}GrandTotalAmount").text = "1695.0"
ET.SubElement(summ, f"{{{NS_RAM}}}DuePayableAmount").text = "1695.0"
```

**Validation assertions (all pass):**
- `urn:factur-x.eu:1p0:minimum` present in `GuidelineSpecifiedDocumentContextParameter/ID`
- Invoice number `ACC-SINV-2026-00001` present in `ExchangedDocument/ID`
- Seller name `Ktayl Solutions` present
- Net `1500.0` and tax `195.0` match the ERPNext draft invoice
- Grand total `1695.0` = net + TSCA

### Production path (Phase 90)

```bash
# In custom ERPNext image (Dockerfile):
RUN pip install factur-x pypdf

# In Frappe hook (hooks.py):
doc_events = {
    "Sales Invoice": {
        "on_submit": "erpnext_facturx.hooks.attach_facturx_pdf"
    }
}
```

The `factur-x` library embeds the CII XML inside the PDF/A-3 using the correct attachment specification (`AFRelationship=Data`). PDP submission then passes the PDF/A-3 to the registered platform (Chorus Pro or a private PDP).

---

## Operational Reference

### Check ERPNext accounting configuration

```bash
kubectl exec -n erp erpnext-gunicorn-<pod> -- bash -c '
cd /home/frappe/frappe-bench
bench --site erp.devandre.sbs execute frappe.db.sql \
  --args "[\"SELECT count(*) FROM \`tabAccount\` WHERE company=\\\"Ktayl Solutions\\\"\"]" \
  --kwargs "{\"as_dict\":True}"'
# Expected: 845
```

### Access ERPNext

| Access method | URL / command |
|---|---|
| Web UI | `https://erp.devandre.sbs` |
| Login (admin) | Username: `Administrator`, password from Vaultwarden item `a73b44aa` |
| Login (SSO) | Authentik OIDC button → `kanmegnea` + TOTP |
| API | `POST /api/method/login` (form-urlencoded: `usr`, `pwd`) |

### Run a migration script in the ERPNext pod

```bash
POD=$(kubectl get pod -n erp -l app.kubernetes.io/component=gunicorn -o name | head -1 | cut -d/ -f2)

# Copy local script to pod
kubectl cp /tmp/my_script.py erp/$POD:/tmp/my_script.py

# Execute — MUST run from sites/ directory
kubectl exec -n erp $POD -- bash -c '
cd /home/frappe/frappe-bench/sites
/home/frappe/frappe-bench/env/bin/python /tmp/my_script.py
'
```

### Flush Redis cache

Required after any bulk account/doctype replacement:

```bash
kubectl exec -n erp $POD -- bash -c '
cd /home/frappe/frappe-bench/sites
/home/frappe/frappe-bench/env/bin/python -c "
import frappe
frappe.init(site=\"erp.devandre.sbs\", sites_path=\"/home/frappe/frappe-bench/sites\")
frappe.connect()
frappe.cache.flushall()
frappe.db.commit()
print(\"Cache flushed\")
frappe.destroy()
"'
```

---

## Gotchas

| Symptom | Root cause | Fix |
|---|---|---|
| `FileNotFoundError: site/logs/database.log` | `frappe.init()` resolves log path relative to CWD | Run script from `sites/` directory, not bench root |
| `get_party_account` returns deleted English account | Redis caches account lookups; not invalidated by SQL DELETE | Call `frappe.cache.flushall()` after COA migration |
| `LinkValidationError` on `company_doc.save()` | Company still references deleted English accounts | Update via `frappe.db.sql("UPDATE tabCompany SET ...")` instead of ORM save |
| Tax template `"TSCA (Assurance) 13%"` not found | ERPNext appends ` - KS` (company abbr) to template `name` | Use `"TSCA (Assurance) 13% - KS"` as the lookup key |
| `FiscalYearError: Posting Date ... not in any active Fiscal Year` | No fiscal year configured for 2026 | Create Fiscal Year 2026 before any invoice |
| `TypeError: cannot unpack non-iterable NoneType` on invoice insert | `get_party_account` returned stale deleted account | Flush Redis cache, then retry |
| `bench execute` with `True`/`False` in `--kwargs` | Python `True` must be capitalized; JSON `true` causes `NameError` | Use `"{\"as_dict\":True}"` not `"{\"as_dict\":true}"` |
| COA delete hangs if GL entries exist | `DELETE FROM tabAccount` blocked by FK or existing GL | Verify `SELECT COUNT(*) FROM tabGL Entry` = 0 before migration |

---

## Phase 90 Backlog

| Gap | Effort | Priority |
|---|---|---|
| Factur-X PDF/A-3 embedding — custom ERPNext image | L | P1 (Sept 2026 deadline) |
| PDP registration (Chorus Pro or private PDP) | M | P1 (Sept 2026 deadline) |
| FEC export — `fichier_des_ecritures_comptables` for DGFIP | S | P2 |
| SEPA direct debit mandate management (premium collection) | L | P2 |
| Insurance custom doctypes — Police d'assurance, Sinistre | XL | P2 (Phase 88) |
| Broker portal — commissions, bordereau production | XL | P3 (Phase 89) |
