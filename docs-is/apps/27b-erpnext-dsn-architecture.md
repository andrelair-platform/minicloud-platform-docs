---
id: erpnext-dsn-architecture
title: ERP-4 — DSN Technical Architecture
sidebar_label: ERP-4 — DSN Architecture
---

# ERP-4 — DSN Phase 3.1 Technical Architecture

Sprint 3 (2026-08-12). Implements the full Déclaration Sociale Nominative (DSN) Phase 3.1 pipeline inside the `erpnext-ktayl` custom image: a `erpnext_dsn` Frappe app that reads Salary Slips, generates a CRLF/UTF-8 DSN flat file, submits it to the Net-Entreprises CRM endpoint, and parses the ACK — wired end-to-end on-cluster using a mock depot for the test environment.

---

## Context

| Layer | Status |
|---|---|
| ERPNext v16.28.0 deployed | ✅ Phase 79 |
| French PCG 2025 + TSCA tax templates | ✅ ERP-1 |
| Custom image (`erpnext-ktayl`) + CI pipeline | ✅ ERP-3 |
| `erpnext_dsn` Frappe app — DSN Phase 3.1 generator | ✅ ERP-4 |
| `mock-net-entreprises` on-cluster depot | ✅ ERP-4 |
| DSN env vars via GitOps + ESO + Vault | ✅ ERP-4 |
| `hrms` app for real Salary Slip integration | ⬜ Phase 90 |
| Go-live with real Net-Entreprises SIRET | ⬜ Phase 90 |

---

## What DSN Phase 3.1 is

DSN (Déclaration Sociale Nominative) is the French unified payroll declaration. Every employer must file a monthly DSN for each employee with the social security bodies (URSSAF, caisse de retraite, Pôle Emploi). Phase 3.1 is the current mandatory format:

- A flat text file, **CRLF line endings, UTF-8**, block-structured
- Submitted over HTTPS to [Net-Entreprises CRM](https://www.net-entreprises.fr/) using SIRET + password credentials
- The depot endpoint returns a CRM XML ACK: `ACCEPTE`, `REJETE`, or `TRAITEMENT_SANS_ERREUR`

In France, a non-submitted or rejected DSN triggers URSSAF penalties. For an insurance IS, DSN is the upstream data source for employee contracts, salary data, and prévoyance collective declarations.

---

## Architecture Overview

```
ERPNext gunicorn pod (erp ns)
│
│  whitelisted API call from n8n / cron / user
│  POST /api/method/erpnext_dsn.api.submit_monthly_dsn?year=2026&month=1
│
▼
erpnext_dsn.api.submit_monthly_dsn()
    │
    ├── generate_monthly_dsn()          ← reads Salary Slips from Frappe DB
    │       builds DSN Phase 3.1 text (CRLF/UTF-8)
    │       blocks: S10 (declaration) / S20 (employees) / S90 (totals)
    │
    └── submit_monthly_dsn_to_crm()     ← HTTP POST to DSN_ENDPOINT
            │
            ▼  (test env)                        (prod)
    mock-net-entreprises                 api.net-entreprises.fr/crm
    Deployment (erp ns, port 8080)      (SIRET + DSN_LOGIN/PASSWORD)
            │
            ▼
    CRM ACK XML parsed
    → Comment stored on Payroll Entry ("DSN 01/2026 — ✅ Acceptée")
```

The test environment routes to `mock-net-entreprises` via `DSN_TEST_MODE=true` + `DSN_ENDPOINT`. The production switch is a one-line env var change in Vault — no code or image change required.

---

## `erpnext_dsn` Frappe App

### App layout

```
minicloud-erpnext/
└── erpnext_dsn/
    ├── setup.py
    ├── hooks.py                  ← no doc_events (API-only, no hooks)
    ├── api.py                    ← whitelisted endpoints
    ├── dsn_generator.py          ← DSN Phase 3.1 file builder
    ├── dsn_submitter.py          ← HTTP POST + CRM ACK parser
    └── scripts/
        └── setup_test_employee.py  ← seeds Jean Dupont + Jan 2026 Salary Slip
```

### DSN file structure

The generator builds three block types from Frappe documents:

| Block | Content | Frappe source |
|---|---|---|
| **S10** (declaration header) | SIRET, period (YYYY-MM), emitter, software ID | `DSN_SIRET` env var + `DSN_COMPANY_NAME` + system date |
| **S20** (employee) | NNI (NIR), name, birth date, job category, gross/net salary, contract type | `Salary Slip` → `Employee` fields |
| **S90** (footer) | Record counts for S10 + S20 | counted at build time |

Each block field follows the DSN specification: `rubrique.occurrence.rang: value\r\n`. Example S10 header:

```
S10.G00.00.001: 12345678900014   ← SIRET
S10.G00.00.002: 062026           ← period MMYYYY
S10.G00.00.005: 01               ← declaration nature (mensuelle)
S10.G00.00.006: 01               ← fraction (one file)
```

### API endpoints

Both functions are decorated with `@frappe.whitelist()` — accessible via the ERPNext REST API with session or API key auth:

```python
# Generate only (returns DSN text, does not submit)
GET /api/method/erpnext_dsn.api.generate_monthly_dsn?year=2026&month=1

# Generate + submit to CRM endpoint
POST /api/method/erpnext_dsn.api.submit_monthly_dsn?year=2026&month=1
```

`submit_monthly_dsn` response:

```json
{
  "message": {
    "success": true,
    "employees": 1,
    "submitted_at": "2026-08-12T10:23:44",
    "response": "ACCEPTE"
  }
}
```

On success, a Comment is stored on the Payroll Entry:
```
DSN 01/2026 — ✅ Acceptée
Soumis le 2026-08-12 à 10:23:44
```

On rejection, the full CRM error message is stored and `success: false` is returned.

---

## Mock Net-Entreprises Server

### Why an on-cluster mock

Net-Entreprises requires a real registered SIRET and valid employee NIR numbers for acceptance. Testing against the real endpoint during development would:
- Require a production SIRET (not available in the test environment)
- Risk polluting real URSSAF declarations with test data
- Require opening outbound HTTPS to `api.net-entreprises.fr` from the cluster

The `mock-net-entreprises` server validates the structure of the incoming DSN and always returns `ACCEPTE`, enabling full end-to-end pipeline testing on-cluster.

### Implementation

The mock is a pure Python stdlib `http.server.BaseHTTPRequestHandler` — no external dependencies, no Pip install, runs on the `python:3.11-slim` image. It performs minimal but meaningful validation:

```python
def do_POST(self):
    body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")

    # Validate DSN structure: must contain S10 (header) and S90 (footer) blocks
    if "S10.G00.00.001" not in body or "S90.G00.00.002" not in body:
        self.send_response(400)
        ...
        return

    # Return CRM ACK XML
    ack_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CR>
  <CodeRetour>ACCEPTE</CodeRetour>
  <Libelle>Déclaration acceptée</Libelle>
</CR>"""
    self.send_response(200)
    self.send_header("Content-Type", "application/xml; charset=utf-8")
    ...
```

If the DSN body is missing the S10 header or S90 footer (i.e. a malformed or empty file), the mock returns HTTP 400 — this catches generator bugs before they would reach the real endpoint.

### Kubernetes manifests (`manifests/erpnext/04-mock-net-entreprises.yaml`)

```
ConfigMap mock-net-entreprises-app   ← app.py Python source
Deployment mock-net-entreprises      ← python:3.11-slim, runs app.py
Service mock-net-entreprises         ← ClusterIP, port 8080
```

Security posture:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
```

The server is `ClusterIP` only — it is not reachable from outside the cluster. Only the gunicorn pod in the same namespace (`erp`) can reach `http://mock-net-entreprises.erp.svc.cluster.local:8080/depot`.

---

## Configuration — Env Vars & Secrets

### Design decision: test vs production split

Rather than hard-coding the Net-Entreprises endpoint or credentials, all DSN config is injected as pod environment variables. This makes the test→prod transition a Vault secret update with zero code change.

| Variable | Source | Purpose |
|---|---|---|
| `DSN_TEST_MODE` | Helm `envVars` (literal `"true"`) | When `"true"`, submitter logs each step verbosely and skips TLS verification |
| `DSN_ENDPOINT` | Helm `envVars` (literal URL) | CRM endpoint — mock URL in test, real in prod |
| `DSN_LOGIN` | ExternalSecret → Vault | Net-Entreprises username |
| `DSN_PASSWORD` | ExternalSecret → Vault | Net-Entreprises password |
| `DSN_SIRET` | ExternalSecret → Vault | Employer SIRET (14 digits) |
| `DSN_COMPANY_NAME` | ExternalSecret → Vault | Company name for S10 block |

`DSN_LOGIN`, `DSN_PASSWORD`, `DSN_SIRET`, `DSN_COMPANY_NAME` are all `optional: true` in their `secretKeyRef`. This means the gunicorn pod starts cleanly even if Vault has not yet been populated with real credentials — the mock path (`DSN_TEST_MODE=true`) works without them.

### GitOps wiring

The env vars are injected at two points in `helm-values/minicloud-1/erpnext-values.yaml` — once for the gunicorn Deployment and once for the worker Deployment (background jobs):

```yaml
# Applied to both gunicorn + worker sections:
envVars:
  - name: DSN_TEST_MODE
    value: "true"
  - name: DSN_ENDPOINT
    value: "http://mock-net-entreprises.erp.svc.cluster.local:8080/depot"
  - name: DSN_LOGIN
    valueFrom:
      secretKeyRef:
        name: erpnext-dsn-config
        key: DSN_LOGIN
        optional: true
  - name: DSN_PASSWORD
    valueFrom:
      secretKeyRef:
        name: erpnext-dsn-config
        key: DSN_PASSWORD
        optional: true
  - name: DSN_SIRET
    valueFrom:
      secretKeyRef:
        name: erpnext-dsn-config
        key: DSN_SIRET
        optional: true
  - name: DSN_COMPANY_NAME
    valueFrom:
      secretKeyRef:
        name: erpnext-dsn-config
        key: DSN_COMPANY_NAME
        optional: true
```

### ExternalSecret → Vault

`manifests/erpnext/01-externalsecrets.yaml` contains the `erpnext-dsn-config` ExternalSecret, which pulls from `secret/platform/net-entreprises` in Vault:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: erpnext-dsn-config
  namespace: erp
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: erpnext-dsn-config
    creationPolicy: Owner
  data:
    - secretKey: DSN_LOGIN
      remoteRef:
        key: secret/platform/net-entreprises
        property: login
    - secretKey: DSN_PASSWORD
      remoteRef:
        key: secret/platform/net-entreprises
        property: password
    - secretKey: DSN_SIRET
      remoteRef:
        key: secret/platform/net-entreprises
        property: siret
    - secretKey: DSN_COMPANY_NAME
      remoteRef:
        key: secret/platform/net-entreprises
        property: company_name
```

When the Vault path is not yet populated, ESO marks the ExternalSecret as `SecretSyncedError` but the pods stay Running thanks to `optional: true` on each `secretKeyRef`.

---

## L1 Test Suite

The `erpnext_dsn` app ships with 108 unit tests (76% coverage) that run in CI without a running Frappe bench, using a `sys.modules` mock:

```python
# tests/conftest.py
import sys
from unittest.mock import MagicMock
_frappe = MagicMock(name="frappe")
for _mod in ("frappe", "frappe.utils", "frappe.utils.file_manager"):
    sys.modules.setdefault(_mod, _frappe)
```

| Test file | Tests | What it covers |
|---|---|---|
| `test_dsn_generator.py` | 55 | S10/S20/S90 block output, CRLF enforcement, UTF-8 encoding, edge cases (zero employees, float amounts, special characters in names) |
| `test_dsn_submitter.py` | 23 | CRM XML parsing (`ACCEPTE`, `REJETE`, `SOAP_FAULT`, empty body), `submit_dsn()` with mocked `requests.post`, error propagation |
| `test_api_helpers.py` | 15 | Contract type codes (CDI/CDD/interim), salary warnings collection |
| `test_facturx.py` | 15 | CII XML assertions (Factur-X Minimum profile, shared with `erpnext_facturx`) |

Run locally:

```bash
cd ~/Developer/cloudplateform/minicloud-erpnext
pip install -r requirements-test.txt
make test-cov   # pytest --cov --cov-fail-under=70
```

---

## Switching to Production

When a real SIRET becomes available, the go-live requires two steps and zero code change:

**Step 1 — Populate Vault:**

```bash
ssh controller "kubectl exec -n vault vault-0 -- sh -c \
  'VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=\$(cat /vault-root-token) \
   vault kv put -mount=secret platform/net-entreprises \
   login=<NET_ENTREPRISES_USER> \
   password=<NET_ENTREPRISES_PASSWORD> \
   siret=<14_DIGIT_SIRET> \
   company_name=\"Ktayl Solutions\"'"
```

ESO refreshes the Secret within 1 hour (or immediately: `kubectl annotate externalsecret erpnext-dsn-config -n erp force-sync=$(date +%s)`).

**Step 2 — Switch endpoint and disable test mode in GitOps:**

In `helm-values/minicloud-1/erpnext-values.yaml`, update the two literal env vars for both gunicorn and worker:

```yaml
  - name: DSN_TEST_MODE
    value: "false"
  - name: DSN_ENDPOINT
    value: "https://api.net-entreprises.fr/crm/service/dsn/v3/jeton"
```

Push to main → ArgoCD syncs → pods restart with the new env. No image rebuild needed.

---

## Gotchas

| Gotcha | Root cause | Fix |
|---|---|---|
| `frappe.init()` raises `FileNotFoundError: site/logs/database.log` | Frappe logger uses a relative `site/logs/` path — only valid from within the `sites/` directory | Always `cd /home/frappe/frappe-bench/sites` before running Python scripts in the pod |
| `Sales Stage` vs `CRM Stage` DoesNotExistError | ERPNext v16 stores CRM pipeline stages in the `Sales Stage` doctype; `CRM Stage` does not exist | Query `frappe.db.get_all("Sales Stage", ...)` not `"CRM Stage"` |
| `erpnext_dsn` API returns empty results in test | `hrms` app (separate repo from `erpnext`) is not installed — `Salary Slip` doctype is part of `hrms`, not core ERPNext v16 | Install hrms app in the site (Phase 90 plan) or use the `setup_test_employee.py` script to seed test data |
| Pod starts but `DSN_LOGIN` is empty | Vault path `secret/platform/net-entreprises` not yet populated → ESO error → Secret has empty keys | `optional: true` on `secretKeyRef` prevents pod failure; the mock path works without real credentials |
| `requests.post` to mock returns connection refused | Mock Deployment is down or Service selector mismatch | `kubectl get pods -n erp -l app=mock-net-entreprises` — confirm Running |
| CRLF stripped by git | DSN files use `\r\n` line endings; git `autocrlf=true` on Windows would corrupt them | The generator produces `\r\n` programmatically in Python (`"\r\n".join(lines)`) — file is never written to disk through git |

---

## Current State

**Verified 2026-08-12 on erp.devandre.sbs:**

| Check | Result |
|---|---|
| `mock-net-entreprises` pod Running | ✅ |
| `DSN_TEST_MODE=true` in gunicorn env | ✅ `kubectl exec -n erp <pod> -- env \| grep DSN` |
| `DSN_ENDPOINT` points to mock service | ✅ `http://mock-net-entreprises.erp.svc.cluster.local:8080/depot` |
| ESO ExternalSecret `erpnext-dsn-config` exists | ✅ (SecretSyncedError — Vault path not yet populated; mock path unaffected) |
| 108 unit tests passing (76% cov) | ✅ CI `test-unit` job green |

```bash
# Verify DSN env vars in gunicorn pod:
POD=$(kubectl get pod -n erp -l app.kubernetes.io/name=erpnext-gunicorn \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n erp $POD -- env | grep DSN

# Check mock server is reachable:
kubectl exec -n erp $POD -- curl -s \
  http://mock-net-entreprises.erp.svc.cluster.local:8080/depot \
  -X POST -d "S10.G00.00.001: test" \
  -H "Content-Type: text/plain"
```

---

## Phase 90 — Next Steps

| Item | Description |
|---|---|
| Install `hrms` app | Adds `Salary Slip` doctype to Frappe — enables real payroll data in DSN generator instead of seed data |
| Go-live with real SIRET | Populate `secret/platform/net-entreprises` in Vault, switch `DSN_TEST_MODE=false` and real endpoint in gitops |
| n8n monthly trigger | n8n workflow fires on the 5th of each month: calls `submit_monthly_dsn` for the previous month, stores result in Plane issue |
| DSN anomaly alerts | Alertmanager rule: if `submit_monthly_dsn` POST to CRM returns `REJETE` → page on-call via Stalwart mail |
