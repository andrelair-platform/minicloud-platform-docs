---
id: erpnext-hr
title: Phase 79 — ERPNext / Frappe HR (Employee Onboarding Automation)
sidebar_label: Phase 79 — ERPNext HR
---

# Phase 79 — ERPNext / Frappe HR

Phase 79 deploys ERPNext v16.28.0 as the HR source of truth and wires it to the platform onboarding pipeline. Creating an Employee record in ERPNext automatically provisions a Stalwart email mailbox and an Authentik SSO account — no manual steps required.

---

## Architecture

```
HR creates Employee in ERPNext
        │
        │  after_insert webhook (async, Frappe queue)
        ▼
POST http://backstage.backstage.svc.cluster.local:7007/api/scaffolder/v2/tasks
        │  Bearer token (static API key)
        │  templateRef: template:default/onboard-employee
        ▼
Backstage scaffolder action minicloud:onboard:employee
        ├── Stalwart JMAP → create mailbox <username>@devandre.sbs
        └── Authentik API → create user, set temp password, assign department group
```

The webhook fires on every Employee insertion. There is no polling, no cron job, and no manual step between ERPNext and the platform account provisioning.

---

## Why ERPNext as the Source of Truth

The platform already has Backstage software templates for employee onboarding (Phase 78). The missing link was a canonical record store for employees — one that HR staff could manage without needing Backstage access. ERPNext provides:

- A form-based HR UI that non-technical users can operate
- A structured Employee doctype with department, designation, joining date, and personal email
- Native webhook support on any doctype event
- A Frappe Python backend that runs webhook dispatch asynchronously through its background job queue

Alternative considered: a Plane webhook on issue creation. Rejected — Plane is for engineering tickets, not HR records.

---

## Deployment

### Chart

```yaml
# helm-values/erpnext-values.yaml (key fields)
image:
  repository: frappe/erpnext
  tag: v16.28.0

jobs:
  createSite:
    enabled: false          # disabled after initial site creation 2026-07-19
    siteName: "erp.devandre.sbs"

mariadb-sts:
  enabled: true
  image:
    repository: mariadb
    tag: "10.6"

"valkey-cache":
  enabled: true
"valkey-queue":
  enabled: true

persistence:
  worker:
    storageClass: longhorn
    size: 8Gi
```

The chart creates a MariaDB StatefulSet (not bitnami — `mariadb-sts` is a distinct subchart), two Valkey instances for the Frappe queue and cache, a gunicorn web worker, a socket.io server, and two background job workers (`short` and `default` queues).

### ESO Double-Secret Pattern

The ERPNext chart unconditionally creates a Kubernetes Secret named `<release-name>` (= `erpnext`) containing `mariadb-root-password`. There is no `existingSecret` parameter to redirect this. Storing the real password in `values.yaml` would expose it in the public git repository.

Solution: pre-create the secret via ESO before Helm runs, then tell ArgoCD to ignore diffs on its `/data` field.

```yaml
# manifests/erpnext/01-externalsecrets.yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: erpnext-mariadb-root
  namespace: erp
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: erpnext            # must exactly match the Helm release name
    creationPolicy: Owner
  data:
    - secretKey: mariadb-root-password
      remoteRef:
        key: secret/platform/erpnext
        property: ERPNEXT_DB_ROOT_PASSWORD
```

```yaml
# apps/erpnext.yaml — ignoreDifferences section
ignoreDifferences:
  - group: ""
    kind: Secret
    name: erpnext
    jsonPointers:
      - /data
syncOptions:
  - RespectIgnoreDifferences=true
```

With `RespectIgnoreDifferences=true`, ArgoCD strips the ignored field from the server-side apply payload. ESO owns the field. Helm's placeholder `stringData` in `values.yaml` is never applied.

### ArgoCD Multi-Source App

```yaml
# apps/erpnext.yaml
sources:
  - repoURL: https://helm.erpnext.com
    chart: erpnext
    targetRevision: 8.0.67
    helm:
      valueFiles:
        - $values/helm-values/erpnext-values.yaml
  - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    ref: values
  - repoURL: https://github.com/andrelair-platform/minicloud-gitops.git
    targetRevision: main
    path: manifests/erpnext      # namespace + ESO secrets + ingress + cert
```

### Certificate

```yaml
# manifests/erpnext/02-certificate.yaml
spec:
  issuerRef:
    name: minicloud-ca
    kind: ClusterIssuer
  dnsNames:
    - erp.devandre.sbs
```

:::caution No Let's Encrypt on this cluster
The cluster uses `minicloud-ca` as its ClusterIssuer — `letsencrypt-prod` does not exist. Any cert that references `letsencrypt-prod` silently fails to issue (the Certificate object stays in `False` state indefinitely). Always use `minicloud-ca`.
:::

---

## Post-Install Bootstrap

The `createSite` job runs `bench new-site erp.devandre.sbs` inside the ERPNext container. It installs the `erpnext` app and creates the MariaDB schema. This runs once and is disabled immediately after to avoid creating a new Job pod on every ArgoCD sync.

After the site is created, run the setup wizard via API to skip the interactive UI:

```bash
# 1. Log in
curl -sk -c /tmp/erp.txt \
  -X POST https://erp.devandre.sbs/api/method/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'usr=Administrator&pwd=<ERPNEXT_ADMIN_PASSWORD>'

# 2. Extract CSRF token
CSRF=$(curl -sk -b /tmp/erp.txt https://erp.devandre.sbs \
  | grep -o 'csrf_token = "[^"]*"' | head -1 | cut -d'"' -f2)

# 3. Complete setup wizard (company name, currency, timezone)
ARGS=$(python3 -c "import json,urllib.parse; print(urllib.parse.quote(json.dumps({
  'language': 'english',
  'country': 'France',
  'timezone': 'Europe/Paris',
  'currency': 'EUR',
  'company_name': 'Ktayl Solutions',
  'company_abbr': 'KS',
  'company_tagline': '',
  'email': 'admin@devandre.sbs',
  'password': '<ERPNEXT_ADMIN_PASSWORD>',
  'chart_of_accounts': 'Standard with Numbers'
})))")

curl -sk -b /tmp/erp.txt \
  -X POST https://erp.devandre.sbs/api/method/frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
  -H "X-Frappe-CSRF-Token: $CSRF" \
  -d "args=$ARGS"
```

:::note Administrator, not admin
The ERPNext superuser username is `Administrator` (capital A). Logging in with `admin` returns "Invalid credentials" with no further hint.
:::

---

## Departments

ERPNext appends the company abbreviation to department names. When you create department "Direction IT / SI" in company "Ktayl Solutions" (abbr=KS), the stored `name` field becomes `Direction IT / SI - KS`.

The 15 departments created match the Authentik group names exactly:

| Authentik Group | ERPNext Department (stored name) |
|---|---|
| Direction IT / SI | Direction IT / SI - KS |
| Direction Cybersécurité | Direction Cybersécurité - KS |
| Direction Data & Analytics | Direction Data & Analytics - KS |
| Direction Transformation | Direction Transformation - KS |
| Actuariat | Actuariat - KS |
| Souscription | Souscription - KS |
| Sinistres | Sinistres - KS |
| Finance | Finance - KS |
| Réassurance | Réassurance - KS |
| Juridique | Juridique - KS |
| Opérations | Opérations - KS |
| Audit | Audit - KS |
| Direction Commercial | Direction Commercial - KS |
| RH | RH - KS |
| Services Généraux | Services Généraux - KS |

The webhook Jinja2 template strips the ` - KS` suffix before passing the department to the Backstage onboard template:

```jinja2
"department": "{{ (doc.department or '') | replace(' - KS', '') }}"
```

---

## Authentik SSO (Social Login)

ERPNext uses Frappe's Social Login mechanism — a `Social Login Key` doctype that stores the OIDC provider config.

### Authentik Provider

| Field | Value |
|---|---|
| Provider | `erpnext-oidc` (pk=16) |
| Application | slug `erpnext` |
| client_id | `erpnext` |
| client_type | confidential |
| Grant types | authorization_code, refresh_token |
| Redirect URI | `https://erp.devandre.sbs/api/method/frappe.integrations.oauth2_logins.login_via_oidc` |

### ERPNext Social Login Key

Created via the Frappe REST API (not the UI, to allow scripting):

```bash
curl -sk -b /tmp/erp.txt \
  -X POST https://erp.devandre.sbs/api/resource/Social%20Login%20Key \
  -H "Content-Type: application/json" \
  -H "X-Frappe-CSRF-Token: $CSRF" \
  -d '{
    "provider_name": "Authentik",
    "enable_social_login": 1,
    "client_id": "erpnext",
    "client_secret": "<CLIENT_SECRET>",
    "base_url": "https://auth.devandre.sbs",
    "authorize_url": "https://auth.devandre.sbs/application/o/erpnext/authorize/",
    "access_token_url": "https://auth.devandre.sbs/application/o/token/",
    "redirect_url": "https://erp.devandre.sbs/api/method/frappe.integrations.oauth2_logins.login_via_oidc",
    "api_endpoint": "https://auth.devandre.sbs/application/o/userinfo/"
  }'
```

The `redirect_url` field is mandatory — Frappe raises `RedirectUrlNotSetError` without it.

---

## Employee Onboarding Webhook

### Webhook Configuration

| Field | Value |
|---|---|
| Name | `employee-onboard-backstage` |
| DocType | `Employee` |
| Event | `after_insert` |
| URL | `http://backstage.backstage.svc.cluster.local:7007/api/scaffolder/v2/tasks` |
| Structure | JSON |

The webhook body uses Frappe Jinja2 templating (`doc` refers to the inserted document):

```json
{
  "templateRef": "template:default/onboard-employee",
  "values": {
    "firstName": "{{ doc.first_name }}",
    "lastName": "{{ doc.last_name or '' }}",
    "username": "{{ ((doc.last_name or '') | lower | replace(' ', '') | replace('-', ''))[:20] }}{{ (doc.first_name or '')[0] | lower if doc.first_name else '' }}",
    "personalEmail": "{{ doc.personal_email or doc.prefered_email or '' }}",
    "role": "{{ doc.designation or '' }}",
    "department": "{{ (doc.department or '') | replace(' - KS', '') }}"
  }
}
```

Username convention: `last_name` lowercased and stripped, truncated to 20 chars, then first initial of `first_name`. Example: `Kanmegne Tabouguie Andre` → `kanmegnetabouguiea`.

Frappe dispatches the webhook asynchronously via the `default` background job queue (not inline in the web request). The `Webhook Request Log` doctype records each attempt and its HTTP response status.

### NetworkPolicy Fix

The `backstage` namespace uses a default-deny ingress policy:

```yaml
# manifests/network-policies/backstage.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: backstage
spec:
  podSelector: {}
  policyTypes:
    - Ingress
```

ERPNext webhook calls were being silently dropped — no error appeared in the Frappe webhook logs because the TCP connection was refused before any HTTP response. Diagnosed by checking that the `Webhook Request Log` table had zero entries even after confirmed Employee insertion.

Fix — added in `manifests/network-policies/backstage.yaml` (PR #135):

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-erp-to-backstage
  namespace: backstage
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: backstage
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: erp
      ports:
        - port: 7007
          protocol: TCP
```

:::tip General pattern for cross-namespace service calls
Any namespace that needs to POST to a service behind a `default-deny-ingress` policy must have a matching `allow-<caller>-to-<target>` NetworkPolicy in the **target** namespace, scoped to the caller's namespace label and the target service port. A TCP-refused connection produces no HTTP error in the caller — always check the target namespace's network policies first when webhook calls silently disappear.
:::

---

## Operational Runbook

### Create an Employee (triggers onboarding)

1. Go to `https://erp.devandre.sbs` → HR module → Employee → New
2. Fill: First Name, Last Name, Personal Email (becomes SSO login), Department, Designation, Date of Joining, Company = Ktayl Solutions
3. Save

The `after_insert` webhook fires within 2–3 seconds (Frappe queue processing). Within ~10 seconds:
- Stalwart mailbox `<username>@devandre.sbs` is created
- Authentik user is created with `require-password-change: true`
- User is added to the matching department group in Authentik

### Verify a Webhook Fired

```bash
# Log in as Administrator
curl -sk -c /tmp/erp.txt \
  -X POST https://erp.devandre.sbs/api/method/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'usr=Administrator&pwd=<ERPNEXT_ADMIN_PASSWORD>'

# Check recent webhook logs
curl -sk -b /tmp/erp.txt \
  'https://erp.devandre.sbs/api/resource/Webhook%20Request%20Log?fields=%5B%22name%22%2C%22webhook%22%2C%22status%22%2C%22response_status_code%22%2C%22error%22%5D&limit=5&order_by=creation+desc' \
  | python3 -m json.tool
```

A successful call shows `"status": "Sent"` and `"response_status_code": 201`.

### Check Backstage Scaffolder Logs

```bash
kubectl logs -n backstage deployment/backstage --tail=50 \
  | grep -E 'scaffolder|onboard|stalwart|authentik'
```

Look for:
- `scaffolder.task ... status: initiated` — Backstage received the request
- `[stalwart] Mailbox created: <username>@devandre.sbs`
- `[authentik] User created pk=<n>`
- `scaffolder.task ... status: succeeded`

### Worker Health Check

ERPNext background jobs (including webhook dispatch) run in the `default` worker pod:

```bash
kubectl get pods -n erp -l app.kubernetes.io/component=worker-default
kubectl logs -n erp -l app.kubernetes.io/component=worker-default --tail=20
```

If the worker is not running, `after_insert` webhooks queue but do not fire until it restarts.

---

## Gatekeeper Exclusion

ERPNext's `frappe/erpnext` image runs processes as root and does not expose securityContext overrides in the chart. All 9 Gatekeeper constraints exclude the `erp` namespace via `matchExpressions.NotIn`:

```yaml
namespaceSelector:
  matchExpressions:
    - key: kubernetes.io/metadata.name
      operator: NotIn
      values:
        - erp
        # ... other excluded namespaces
```

This is intentional — ERPNext is a third-party workload that predates the platform's security constraints and cannot be practically hardened at the container level without forking the chart.

---

## Key Gotchas

| Symptom | Root cause | Fix |
|---|---|---|
| Webhook log has zero entries after Employee insert | `default-deny-ingress` in backstage ns blocks TCP from erp | Add `allow-erp-to-backstage` NetworkPolicy in backstage ns |
| 502 Bad Gateway on erp.devandre.sbs | Ingress backend pointed at `erpnext-nginx` (doesn't exist) | Use service name `erpnext` port 8080 |
| Certificate stuck in `False` / `Issuing` state | `letsencrypt-prod` ClusterIssuer doesn't exist on cluster | Use `minicloud-ca` ClusterIssuer |
| "Invalid credentials" logging in as admin | ERPNext superuser is `Administrator` (capital A) | Login with `Administrator` |
| `Webhook Request Log` GET returns 417 | Doctype name has a space — URL-encode as `Webhook%20Request%20Log` | Encode correctly, or use `frappe.client.get_list` API |
| `frappe.exceptions.ValidationError: Please set the document name` | `Webhook` doctype doesn't auto-generate names | Pass `"name": "<your-name>"` in the POST body |
| Department name mismatch between ERPNext and Backstage | ERPNext appends ` - KS` (company abbreviation) | Strip with `| replace(' - KS', '')` in Jinja2 template |
| New createSite Job on every ArgoCD sync | Chart creates timestamp-named Jobs; disabled by default after first run | Keep `jobs.createSite.enabled: false` |
| ESO secret overwritten by Helm on sync | `mariadb-root-password` in Helm release secret | `ignoreDifferences` on `/data` + `RespectIgnoreDifferences=true` |
