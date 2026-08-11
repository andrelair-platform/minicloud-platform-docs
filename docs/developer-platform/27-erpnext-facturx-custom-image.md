---
id: erpnext-facturx-custom-image
title: ERP-3 — Factur-X Custom Image & CI Pipeline
sidebar_label: ERP-3 — Factur-X Custom Image
---

# ERP-3 — Factur-X Custom Image & CI Pipeline

Sprint 3 (2026-08-11). Extends ERP-1 to production-grade e-invoicing: a custom ERPNext Docker image bakes in a `erpnext_facturx` Frappe app that generates Factur-X Minimum CII XML on every submitted Sales Invoice, with a full CI pipeline (Trivy, Cosign, SBOM, GPG-signed GitOps bump).

---

## Context

| Layer | Status |
|---|---|
| ERPNext v16.28.0 deployed | ✅ Phase 79 |
| French PCG 2025 + CRM + TSCA tax templates | ✅ ERP-1 |
| Factur-X Minimum PoC (pure-Python, 5 assertions) | ✅ ERP-1 |
| Custom ERPNext image (`erpnext-ktayl`) | ✅ ERP-3 |
| `erpnext_facturx` Frappe app — `on_submit` hook | ✅ ERP-3 |
| CI pipeline: Trivy + Cosign + SBOM + GPG bump | ✅ ERP-3 |
| PDF/A-3 embedding (Phase 90) | ⬜ Phase 90 |
| n8n invoice workflow (SIRET/ORIAS verify → ERPNext) | ⬜ Phase 90 |

---

## Architecture — Option C (open-webui model)

`minicloud-erpnext` is an **image build repo only**, not a deployment repo. This mirrors [`minicloud-open-webui`](https://github.com/andrelair-platform/minicloud-open-webui): application artifacts live in the image repo, all cluster state (Helm values, ArgoCD Apps, ExternalSecrets, Ingress, Quota) stays in `minicloud-gitops`.

```
minicloud-erpnext/             ← image artifacts only
├── Dockerfile
├── erpnext_facturx/           ← Frappe app (baked into image)
│   ├── setup.py
│   ├── hooks.py
│   └── facturx.py
├── .trivyignore               ← accepted upstream CVEs
└── .github/workflows/
    └── build.yml              ← build → Harbor → GitOps bump

minicloud-gitops/
└── helm-values/minicloud-1/
    └── erpnext-values.yaml    ← image.tag is auto-bumped by CI
```

Future integrations (n8n webhooks, NATS events, ORIAS client) are added as new Python files inside `erpnext_facturx/` or as new Frappe apps alongside it in the repo — then baked into the next image.

---

## Dockerfile

The image extends `frappe/erpnext:v16.28.0`, installs `factur-x==2.0.0`, and bakes the `erpnext_facturx` Frappe app via `pip install -e`:

```dockerfile
FROM frappe/erpnext:v16.28.0

ARG CA_CERT

USER root

RUN /home/frappe/frappe-bench/env/bin/pip install \
    "factur-x==2.0.0" \
    --no-cache-dir

# Bake erpnext_facturx Frappe app into the image
COPY erpnext_facturx/ /home/frappe/frappe-bench/apps/erpnext_facturx/
RUN /home/frappe/frappe-bench/env/bin/pip install -e \
    /home/frappe/frappe-bench/apps/erpnext_facturx --no-cache-dir

RUN if [ -n "${CA_CERT}" ]; then \
        echo "${CA_CERT}" > /usr/local/share/ca-certificates/minicloud-ca.crt && \
        update-ca-certificates; \
    fi

USER frappe
```

:::caution Do not add `pypdf` as a dependency
`frappe` requires `pypdf==6.13.3`. Installing `pypdf==5.x` downgrades it and breaks Frappe. The `factur-x` library uses `PyPDF4` independently — no extra pypdf install needed.
:::

---

## Frappe App — `erpnext_facturx`

### Hook registration

```python
# hooks.py
doc_events = {
    "Sales Invoice": {
        "on_submit": "erpnext_facturx.facturx.generate_and_attach",
    }
}
```

When a Sales Invoice is submitted in ERPNext, Frappe calls `generate_and_attach`. There is no UI change — the Factur-X XML (or PDF/A-3 when available) appears as a private file attachment on the invoice.

### CII XML generation

`_build_cii_xml(doc)` builds a Factur-X Minimum profile CII XML (`urn:factur-x.eu:1p0:minimum`) using Python's standard `xml.etree.ElementTree`:

| CII element | ERPNext source |
|---|---|
| `ExchangedDocument/ID` | `doc.name` (e.g. ACC-SINV-2026-00001) |
| `TypeCode` | `380` (commercial invoice, fixed) |
| `IssueDateTime` | `str(doc.posting_date).replace("-", "")` → YYYYMMDD format 102 |
| Seller `Name` | `doc.company` |
| Seller SIRET (`schemeID=0002`) | parsed from Company `registration_details` via regex `SIRET[:\s]+(\d{14})` |
| Seller TVA (`schemeID=VA`) | `company.tax_id` (e.g. FR12345678900) |
| Buyer `Name` | `doc.customer` |
| `InvoiceCurrencyCode` | `doc.currency` |
| `TaxBasisTotalAmount` | `doc.net_total` |
| `TaxTotalAmount` | `doc.total_taxes_and_charges` |
| `GrandTotalAmount` | `doc.grand_total` |
| `DuePayableAmount` | `doc.outstanding_amount` or `grand_total` |

### PDF/A-3 embedding (with fallback)

```python
def generate_and_attach(doc, method=None):
    xml_bytes = _build_cii_xml(doc)
    pdf_bytes = _get_invoice_pdf(doc)

    if pdf_bytes:
        try:
            from facturx import generate_from_file
            # embed XML into PDF/A-3 as attachment
            ...
            save_file(f"{doc.name}-facturx.pdf", final_pdf, ...)
        except Exception:
            # fallback: XML only (PDF/A-3 embedding failed)
            save_file(f"{doc.name}-facturx.xml", xml_bytes, ...)
    else:
        save_file(f"{doc.name}-facturx.xml", xml_bytes, ...)
```

Full PDF/A-3 production embedding is Phase 90. The current fallback ensures the CII XML is always attached even if the `facturx` library cannot generate the PDF.

---

## CI Pipeline

The pipeline in `.github/workflows/build.yml` has two jobs.

### Job 1 — `build-and-push`

```
checkout → compute tag → Tailscale → trust CA → Harbor login
→ Buildx (insecure registry) → build + push → Trivy CRITICAL scan
→ Cosign sign → syft SBOM (CycloneDX JSON) → attach SBOM as OCI referrer
```

**Tag strategy:**
- `main` branch → `v16.28.0-facturx-{sha}` (SHA-pinned, immutable)
- other branches → `{branch}-{sha}` (development only, not promoted)

**Trivy configuration:**
- `scanners: 'vuln'` — disables secret scanning (avoids HTTP/2 stream errors on 838 MB image over Tailscale)
- `timeout: 20m`
- `.trivyignore` suppresses 18 CRITICAL CVEs from the upstream `frappe/erpnext:v16.28.0` base image (Chromium ×8, libgnutls30 ×2, Node.js banking deps ×3, Go stdlib ×4). None introduced by our layers.

### Job 2 — `bump-gitops` (main only)

```
Tailscale → trust CA → checkout minicloud-gitops
→ import GPG key (crazy-max/ghaction-import-gpg@v7)
→ verify image in Harbor (HTTP 200 on manifest endpoint)
→ sed erpnext-values.yaml image.tag
→ GPG-signed commit on branch ci/erpnext-bump-{tag}
→ gh pr create → gh pr merge --admin (auto-merge)
```

The Harbor verification step (`curl -o /dev/null -w "%{http_code}"`) prevents a GitOps bump if the push failed silently. Auto-merge requires `main` branch protection to allow `--admin` bypass — same pattern as `minicloud-open-webui`.

---

## Trivy — Accepted Upstream CVEs

All 18 suppressed CVEs are in the upstream `frappe/erpnext:v16.28.0` base image, not in layers added by minicloud:

| Package | CVEs | Source |
|---|---|---|
| `chromium-headless-shell` | 8 | Debian pkg (used for PDF generation) |
| `libgnutls30` | 2 | Debian base |
| `loader-utils`, `shell-quote`, `tar` | 3 | Node.js in ERPNext banking module |
| Go stdlib (embedded binary) | 4 | Go binary in base image |

Remediation: upgrade when ERPNext ships a new base image.

---

## Supply Chain Security

| Check | Scope |
|---|---|
| Trivy CRITICAL scan | Every push to main/staging |
| Cosign keyless signing | staging + main pushes |
| CycloneDX SBOM | main only (attached as OCI referrer) |
| GPG-signed GitOps commit | Every auto-bump to minicloud-gitops |

To verify the image signature:
```bash
cosign verify harbor.10.0.0.200.nip.io/library/erpnext-ktayl:<tag> \
  --certificate-identity-regexp=".*" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
```

---

## Adding a New Integration

To add a new Frappe integration (e.g. n8n webhook on invoice submit):

1. Add a Python file in `minicloud-erpnext/erpnext_facturx/` (e.g. `n8n_webhook.py`)
2. Register a new event in `hooks.py`:
   ```python
   doc_events = {
       "Sales Invoice": {
           "on_submit": [
               "erpnext_facturx.facturx.generate_and_attach",
               "erpnext_facturx.n8n_webhook.trigger",
           ],
       }
   }
   ```
3. Push to `main` — CI builds and bumps the image tag in `erpnext-values.yaml` automatically
4. ArgoCD syncs → ERPNext pods restart with the new app version

No manual `bench install-app` or pod exec needed — the app is baked into the image.

---

## Gotchas

| Gotcha | Root cause | Fix |
|---|---|---|
| `TypeError: 'str' object cannot be interpreted as an integer` on `posting_date.replace()` | `doc.posting_date` is `datetime.date`, not `str`. Its `.replace(year=, month=, day=)` takes keyword args. | `str(doc.posting_date).replace("-", "")` |
| `pypdf==5.1.0` conflicts with frappe | `frappe` hard-requires `pypdf==6.13.3`; downgrade breaks it | Don't install `pypdf` — `factur-x` uses `PyPDF4` independently |
| Buildx push → `x509: certificate signed by unknown authority` | `docker/build-push-action` runs Buildx in a separate container that doesn't inherit host CA certs | `buildkitd-config-inline: [registry."harbor..."] insecure = true` |
| Trivy HTTP/2 `INTERNAL_ERROR` on git binary in 838 MB image | Trivy secret scan reads every byte of every file; git binary triggers stream error | `scanners: 'vuln'` disables secret scanning |
| nginx rolling update deadlock | Chart injects `topologySpreadConstraint maxSkew:1` preventing 2 nginx pods on the same node | `nginx.topologySpreadConstraints: []` in erpnext-values.yaml |
| Frappe app files are ephemeral | Files copied to a running pod are lost on pod restart | Bake into Docker image with `COPY + pip install -e`, not copied at runtime |
| Redis stale cache after COA replacement | `get_party_account` returns deleted account from cache | `frappe.cache.flushall()` after migration (ERP-1 gotcha) |

---

## Current State

```bash
# Verify running image
ssh controller "kubectl get pods -n erp -l app.kubernetes.io/name=erpnext \
  -o jsonpath='{.items[0].spec.containers[0].image}'"
# → harbor.10.0.0.200.nip.io/library/erpnext-ktayl:v16.28.0-facturx-9e0425d

# Verify hook is registered
ssh controller "kubectl exec -n erp <gunicorn-pod> -- \
  /home/frappe/frappe-bench/env/bin/python -c \
  'import erpnext_facturx.hooks as h; print(h.doc_events)'"
```

---

## Phase 90 — Next Steps

| Item | Description |
|---|---|
| PDF/A-3 embedding | Full `facturx.generate_from_file()` production path — requires PDF generated from Frappe print format to be accessible as bytes without Chromium errors |
| n8n invoice workflow | ERPNext `on_submit` → n8n webhook → `minicloud-crew-agent` (SIRET INFOGREFFE + ORIAS verify) → result written back to ERPNext custom field |
| Factur-X EN16931 (Confort) | Add line-level items (`IncludedSupplyChainTradeLineItem`) for full audit trail |
