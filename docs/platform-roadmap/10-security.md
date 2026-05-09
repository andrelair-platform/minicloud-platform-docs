---
id: phase-15-cert-manager
title: Phase 15 — TLS / cert-manager (PKI)
sidebar_position: 11
---

# Phase 15 — TLS via cert-manager

Phase 15 establishes a proper internal x509 PKI on the cluster: a
self-signed root CA managed by **cert-manager**, an everyday issuer
chained off it, and per-Ingress certificates auto-renewed every 60 days
(90-day lifetime, renew-before-30). After this phase every cluster
hostname serves HTTPS with a valid (chained) certificate, every HTTP
request returns `301` to HTTPS, and **the long-standing Phase 7 Harbor
pull issue is finally resolved** — kubelet trusts the new HTTPS Harbor
endpoint and pulls images successfully.

The original phase plan was "Vault + cert-manager + RBAC." We
**deliberately scoped down to TLS only** — same pattern as Phase 11
(scoped to OpenTofu, deferred Crossplane). Doing one thing well > three
things shallowly. See "What's deferred" below.

---

## Architecture: the 3-resource bootstrap chain

```text
ClusterIssuer "selfsigned-bootstrap"     ◀── used ONCE to sign the root CA below
       │
       ▼
Certificate "minicloud-root-ca"         ◀── this IS the root CA cert
  (cert-manager namespace)                  10 yr lifetime, ECDSA P-256, isCA: true
       │ produces secret "minicloud-root-ca" with tls.crt + tls.key
       ▼
ClusterIssuer "minicloud-ca"            ◀── everyday issuer; reads the secret above
       │
       ▼
Certificate "<workload>-tls"            ◀── one per Ingress, in the workload's namespace
  (workload namespace)                      90 day lifetime, renew at 30d remaining
       │ produces secret "<workload>-tls" with tls.crt + tls.key
       ▼
Ingress "<workload>"                    ◀── references the secret in spec.tls
       + nginx.org/redirect-to-https
```

This is the canonical cert-manager pattern for internal PKI. Real shops
running Vault PKI / Smallstep CA / Active Directory CS use the same
shape — just rooted at a different CA.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Issuer strategy | **Self-signed root CA + chained ClusterIssuer** | No public domain → Let's Encrypt HTTP-01 can't verify private IPs; DNS-01 needs a real DNS zone. Self-signed root is the right shape for homelab + portfolio, and demonstrates the same PKI knowledge a corporate CA hierarchy needs. |
| cert-manager version | v1.20.2 (chart `jetstack/cert-manager`) | Latest stable; supports all the resources we need |
| Root CA algorithm | ECDSA P-256, 10-year lifetime | Modern algorithm; smaller cert sizes than RSA; 10y is typical for an internal root |
| Workload cert lifetime | 90 days, renew at 30d remaining | Matches Let's Encrypt cadence; cert-manager handles renewal automatically |
| Cert distribution | Per-namespace `Certificate` resource → `tls.crt`/`tls.key` Secret | Each Ingress references its own Secret in `spec.tls`. cert-manager populates and renews. |
| HTTP→HTTPS redirect | `nginx.org/redirect-to-https: "true"` annotation on every Ingress | F5 NGINX Ingress's standard annotation; returns 301 |
| Harbor secret name | **`harbor-tls-cert`** (not the chart default) | Per the Phase 15 review tip; makes the chart's `expose.tls.secret.secretName` mapping explicit |
| Browser trust | User imports `~/minicloud-ca.crt` into browser/OS trust store (one-time) | Honest portfolio move; the cert chain technically works without it, but green padlocks require trust |
| Harbor pull-path fix | Update Phase 10 Ansible `k3s-registries` role: HTTPS endpoint + distribute the CA cert + reference via `tls.ca_file` | Resolves the Phase 7 known issue (k3s `/v2`-suffix mirror URL mismatch via HTTP) |
| **Vault** | **Deferred** to a future phase (likely alongside Backstage in Phase 18) | Vault on a single-control-plane homelab without HA introduces its own SPOF. Currently ~6 admin passwords (small enough for `~/.*-admin` files mode 600). |
| **RBAC** | **Deferred** to when there's a real second user | Single-operator system today; defining roles nobody applies is theatre. RBAC pairs naturally with multi-persona Backstage. |

---

## Pre-flight

```bash
# Add jetstack helm repo
helm repo add jetstack https://charts.jetstack.io
helm repo update jetstack
helm search repo jetstack/cert-manager  # confirm v1.20+
```

---

## Install cert-manager

`cert-manager-values.yaml`:

```yaml
crds:
  enabled: true

# Modest single-replica install for the small cluster
replicaCount: 1
webhook:
  replicaCount: 1
cainjector:
  replicaCount: 1

prometheus:
  enabled: true
  servicemonitor:
    enabled: true
    labels:
      release: kube-prometheus-stack
```

```bash
kubectl create namespace cert-manager
helm install cert-manager jetstack/cert-manager -n cert-manager \
  -f cert-manager-values.yaml \
  --wait --timeout 5m

# Verify
kubectl get pods -n cert-manager
# 3 pods: cert-manager, cainjector, webhook
```

---

## Bootstrap the PKI

Three manifests, applied in order.

### `01-selfsigned-bootstrap.yaml`

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: selfsigned-bootstrap
spec:
  selfSigned: {}
```

### `02-root-ca.yaml`

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: minicloud-root-ca
  namespace: cert-manager
spec:
  isCA: true
  commonName: minicloud Internal Root CA
  subject:
    organizations: [andrelair-platform]
    organizationalUnits: [minicloud platform]
  duration: 87600h          # 10 years
  renewBefore: 2160h        # renew at 90 days remaining
  privateKey:
    algorithm: ECDSA
    size: 256
  secretName: minicloud-root-ca
  issuerRef:
    name: selfsigned-bootstrap
    kind: ClusterIssuer
    group: cert-manager.io
```

### `03-minicloud-ca.yaml`

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  ca:
    secretName: minicloud-root-ca
```

Apply:

```bash
kubectl apply -f 01-selfsigned-bootstrap.yaml
kubectl apply -f 02-root-ca.yaml
kubectl apply -f 03-minicloud-ca.yaml

kubectl wait --for=condition=Ready certificate/minicloud-root-ca -n cert-manager
kubectl get clusterissuers
# selfsigned-bootstrap   True
# minicloud-ca           True
```

### Export the root CA for browser trust

```bash
kubectl -n cert-manager get secret minicloud-root-ca \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > ~/minicloud-ca.crt
chmod 644 ~/minicloud-ca.crt

# Verify the cert
openssl x509 -in ~/minicloud-ca.crt -noout -subject -issuer -dates
openssl x509 -in ~/minicloud-ca.crt -noout -fingerprint -sha256
```

---

## Per-Ingress migration recipe

For each Ingress, two manifests:

1. **`Certificate`** in the same namespace as the Ingress:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: <app>-tls
  namespace: <app-ns>
spec:
  secretName: <app>-tls          # ⚠ Harbor uses harbor-tls-cert (chart-specific)
  issuerRef:
    name: minicloud-ca
    kind: ClusterIssuer
  dnsNames: [<host>]
  duration: 2160h                # 90 days
  renewBefore: 720h              # renew at 30d remaining
  privateKey: { algorithm: ECDSA, size: 256 }
```

2. **Ingress** updates: add `nginx.org/redirect-to-https: "true"` annotation
   and `spec.tls` block:

```yaml
metadata:
  annotations:
    nginx.org/redirect-to-https: "true"
spec:
  tls:
    - hosts: [<host>]
      secretName: <app>-tls
```

For Helm-managed apps (podinfo, Grafana, Harbor, ArgoCD), translate the
above into the chart's values syntax. For ArgoCD-managed apps (homer,
whoami, platform-demo), commit to the gitops repo and let ArgoCD sync.

---

## Migration order (executed)

Lowest-risk → highest-risk. Each migration: add Certificate → wait Ready
→ update Ingress → verify HTTPS + redirect.

| Order | App | Method | Special note |
|---|---|---|---|
| 1 | whoami | gitops | Lowest blast radius |
| 2 | platform-demo | gitops | Verify CI/CD pipeline still works post-TLS |
| 3 | podinfo | helm | HPA still scales after TLS migration |
| 4 | Homer | gitops | |
| 5 | Grafana | helm | Login still works (302 redirect to /login) |
| 6 | Harbor | helm | **The big one** — `expose.tls.enabled: true` + `secret.secretName: harbor-tls-cert` |
| 7 | ArgoCD | helm | Last; flip annotations on the Ingress, leave `server.insecure: true` (TLS terminates at the Ingress) |

---

## Verification

```bash
# Each Ingress: HTTPS works, HTTP redirects
for host in homer harbor grafana podinfo whoami platform-demo argocd; do
  HTTPS=$(curl -sI --cacert ~/minicloud-ca.crt -m 5 https://$host.10.0.0.200.nip.io/ -o /dev/null -w "%{http_code}")
  HTTP=$(curl -sI -m 5 http://$host.10.0.0.200.nip.io/ -o /dev/null -w "%{http_code}")
  echo "$host: https=$HTTPS http=$HTTP"
done

# Cert chain inspection
echo | openssl s_client -servername whoami.10.0.0.200.nip.io -connect 10.0.0.200:443 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

Expected:
- All HTTPS = 200 (or 302 for Grafana, 405 for podinfo on HEAD — `-X GET` returns 200)
- All HTTP = 301 (redirect to HTTPS)
- Issuer = `minicloud Internal Root CA`

---

## Harbor pull-path fix (the Phase 7 issue)

Phase 7's k3s registries.yaml had been pointing at `http://harbor.10.0.0.200.nip.io`
which surfaced a `/v2`-suffix mismatch in containerd. With Harbor now on
HTTPS, the fix is straightforward: switch to HTTPS + add the CA bundle.

Update the Phase 10 `k3s-registries` Ansible role:

`roles/k3s-registries/files/registries.yaml`:

```yaml
mirrors:
  "harbor.10.0.0.200.nip.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io"
configs:
  "harbor.10.0.0.200.nip.io":
    tls:
      ca_file: /etc/rancher/k3s/minicloud-ca.crt
```

Drop the CA cert into `roles/k3s-registries/files/minicloud-ca.crt` and
add a task to install it. Add a handler that restarts k3s (control plane)
or k3s-agent (workers) on change:

```yaml
- name: Restart k3s
  ansible.builtin.systemd:
    name: "{{ 'k3s' if 'control_plane' in group_names else 'k3s-agent' }}"
    state: restarted
  become: true
```

Run the playbook. After restart:

```bash
# Push a test image
crane copy --insecure ghcr.io/stefanprodan/podinfo:6.11.2 \
  harbor.10.0.0.200.nip.io/library/podinfo:6.11.2

# kubelet pulls it (this used to fail with the /v2-suffix issue)
kubectl create namespace harbor-pull-test
kubectl run pull-test \
  --image=harbor.10.0.0.200.nip.io/library/podinfo:6.11.2 \
  --image-pull-policy=Always \
  --restart=Never \
  -n harbor-pull-test
kubectl wait --for=condition=Ready pod/pull-test -n harbor-pull-test --timeout=60s
# → Successfully pulled in ~344ms
```

The pull-path issue documented across 8 phases (7 → 14) is now closed.

---

## Browser trust (one-time user step)

Until you import the root CA into your browser/OS trust store, browsers
show "Not Secure" warnings. Curl-with-cacert works regardless.

**Linux (Ubuntu/Debian):**
```bash
sudo cp ~/minicloud-ca.crt /usr/local/share/ca-certificates/minicloud-ca.crt
sudo update-ca-certificates
```

**Firefox:** Settings → Privacy & Security → Certificates → View
Certificates → Authorities → Import → select `minicloud-ca.crt` → ✓
trust for websites.

**Chrome / Chromium:** Settings → Privacy and security → Security →
Manage device certificates → Authorities → Import.

**macOS:** Keychain Access → drag `minicloud-ca.crt` into "System" →
double-click the cert → Trust → "Always Trust."

After import, browsers verify the chain back to your root CA. Hover the
padlock — issuer should read "minicloud Internal Root CA."

---

## What's deferred (and why)

The original Phase 15 was "Vault + cert-manager + RBAC." We shipped only
cert-manager.

| Component | Status | Future home |
|---|---|---|
| **Vault** | Deferred | Pairs naturally with a real consumer (Phase 18 Backstage's secret needs, or external-DB-credentials when we add Postgres in the data layer). On single-control-plane k3s, Vault is its own SPOF. |
| **RBAC** | Deferred | Pairs with multi-persona Backstage (Phase 18). Defining roles for a single-operator system is theatre. |

This is the same scope-reduction pattern as Phase 11 (which dropped
Crossplane and shipped only OpenTofu). Honest, documented, with future
home identified — same shape every senior platform team uses when
managing scope on a busy roadmap.

---

## Done When

```text
✔ 3 cert-manager pods Running
✔ 2 ClusterIssuers (selfsigned-bootstrap, minicloud-ca) Ready
✔ Root CA Certificate Ready in cert-manager namespace
✔ ~/minicloud-ca.crt exported, SHA256 fingerprint verified
✔ 7 workload Certificates Ready, one per Ingress
✔ All 7 Ingresses serve HTTPS via curl --cacert ~/minicloud-ca.crt
✔ HTTP requests to all 7 hosts return 301
✔ Harbor pull-path verified: kubectl run --image=harbor.10.0.0.200.nip.io/... succeeds
✔ Phase 10 Ansible k3s-registries role updated; --check on all 3 nodes is idempotent
✔ Homer tiles all on https:// URLs
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **Self-signed root CA + chained ClusterIssuer** | Same pattern Vault PKI, Smallstep CA, AD Certificate Services use. The 3-resource bootstrap chain is the textbook cert-manager pattern. |
| **per-Ingress Certificate resources with auto-renewal** | The standard cert-manager workflow. Same shape whether the issuer is internal (here) or external (Let's Encrypt, Sectigo, DigiCert). |
| **HTTP→HTTPS redirect at the Ingress layer** | Edge redirect is more efficient than app-layer redirect. Saves a round trip into the cluster. |
| **Cross-team-conscious migration order** | Lowest-blast-radius first; critical-path apps last. Same calculus every platform team uses for any cluster-wide change. |
| **Harbor TLS chart configuration** | The `expose.tls.enabled: true` + explicit `secret.secretName` pattern is the cleanest way to make a chart consume a cert-manager-issued secret. |
| **k3s registries.yaml + CA bundle + handler restart** | Distribute the CA to each node, point containerd at it, restart k3s — every shop running an internal registry walks this exact path. |
| **Senior scope reduction** | Deferring Vault + RBAC is the same skill as Phase 11's Crossplane deferral. One thing well > three things shallowly. |
| **Honest documentation of "browser trust required"** | A self-signed root works perfectly on the wire but needs an out-of-band trust import for browsers. Naming the gap is more credible than pretending it's "production-ready" without it. |
