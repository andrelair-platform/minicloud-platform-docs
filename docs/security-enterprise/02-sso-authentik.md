---
id: sso-authentik
title: Phase 23 — SSO + IAM via Authentik
sidebar_position: 2
---

# Phase 23 — SSO + IAM via Authentik

By Phase 22, the platform was running 13 user-facing apps. Seven of those had local admin passwords (`~/.argocd-admin`, `~/.grafana-admin`, `~/.harbor-admin`, `~/.minio-admin`, MAAS admin, plus the chart-installed defaults), four were wide-open ("none" auth — Homer, podinfo, platform-demo, whoami, NATS monitoring), and the rest used guest auth or first-signup. **Credential sprawl**. Every onboarding required tracking down 7+ passwords; every offboarding required revoking 7+ accounts; security audit said "show me who has access to what" required walking through 13 separate UIs.

Phase 23 ships **one Authentik instance that every app trusts**: log in once, access everything. Native OIDC for the apps that support it, NGINX `forward-auth` for the apps that don't. Same architectural skill set as deploying Auth0/Okta in a real org, but self-hosted under your own control.

---

## What this phase delivers — the IAM capability map

The doc title says "SSO + IAM" because this phase covers both. "SSO" is what end-users experience (one login button). "IAM" is what the platform engineer is actually building: a centralized control plane for **identity** + **access management**. The two words describe the same system from different angles.

Industry-standard Identity & Access Management has six core capabilities. Phase 23 delivers all six:

| IAM capability | Industry term | Stage where shipped | What it means in practice |
|---|---|---|---|
| **Authentication** | "Who are you?" | Stage 1 (Authentik server) | Single login page (`auth.10.0.0.200.nip.io`) replaces 7 separate admin passwords |
| **Multi-factor auth** | MFA / 2FA | Stage 1.6 (mandatory first step) | TOTP or WebAuthn enforced once at the IdP; all 13 apps inherit the MFA-protected session |
| **Authorization** | RBAC | Stages 3 + 4 + 5 (per-app) | Group claim (`authentik-admins`) → role mapping (ArgoCD `role:admin`, Grafana `Admin`, Harbor admin group, etc.) |
| **Identity lifecycle** | Provisioning / deprovisioning | Stage 1 + Stage 6 | One Authentik UI toggle disables a user across all 13 apps instantly. No more "did we remember to revoke ArgoCD too?" |
| **Audit** | Event log / access log | Stage 1 (Events tab) | Every login, MFA challenge, consent decision recorded — answers "who accessed Grafana last Tuesday at 3 PM" in one query |
| **Session management** | Session control | Stage 1 + 6 (admin-side) | Admin can terminate any session globally; users see a forced logout from every app |

**TL;DR** — when someone asks "do you have IAM?", the answer after Phase 23 is *yes, here are the six capabilities, here's the runbook for each.* That's the bar that distinguishes "we have SSO" from "we have IAM."

---

## What's IAM, what's NOT (deliberate scope decisions)

These sub-categories sometimes get lumped under "IAM" in enterprise vendor marketing. Phase 23 deliberately does not include them:

| Sub-category | Status | Why this scope |
|---|---|---|
| **External identity federation** (LDAP, Google Workspace, Azure AD, SAML to upstream IdP) | Deferred | Single-user portfolio context — no external directory to federate to. Authentik supports it natively when you're ready (future phase, add 2 hours). |
| **SCIM auto-provisioning** (HR system pushes new hires → user accounts appear) | Deferred | Same reason — needs a source-of-truth HR system. Authentik supports SCIM 2.0 sources. |
| **Vault-backed OIDC client secrets** | Deferred | Vault itself is deferred (honest scope note from Phase 15). Today, per-app OIDC client secrets live in k8s Secrets in their consumer namespaces. |
| **Privileged Access Management** (just-in-time admin escalation, session recording, password vault rotation) | **Out of scope — separate category** | PAM is a different enterprise product line entirely — Teleport, CyberArk, BeyondTrust live there. Not on the roadmap for this platform. |
| **Conditional access policies** (location/device/risk-based) | Deferred | Authentik supports it via expression policies; not needed at single-user scale |
| **Passwordless / FIDO2-only** | Deferred | The hybrid (password + MFA) is the industry-standard configuration today. WebAuthn-only would be a future hardening step. |

The scope decisions above are the same discipline as Phase 11 (Crossplane deferred), Phase 13 (GitLab deferred), Phase 15 (Vault deferred), Phase 18 (Backstage plugins deferred). **Ship the foundational IAM first; layer federation/SCIM/PAM as separate dedicated phases when there's a real use case.**

---

## Why this pattern matters

| Problem this solves | Real-world payoff |
|---|---|
| **Credential sprawl across 13 apps** | One login, one password, one MFA enrolment |
| **Offboarding is invisible** ("did we revoke ArgoCD too?") | One toggle in Authentik disables everything |
| **Audit "who can see Grafana"** is 13 separate questions | One Authentik query answers everything |
| **No clean way to gate the unauthenticated apps** (podinfo, NATS dashboard, etc.) | NGINX `forward-auth` middleware applies SSO at the Ingress layer, no app code touched |
| **No identity to tie observability/audit logs to** | Every request now carries a verified `sub=<user>` claim |
| **MFA story is "you set it up per-app"** | MFA enforced once at the IdP, all 13 apps inherit |

---

## Why Authentik over Keycloak

The original Phase 15 plan paired Vault + cert-manager + Keycloak as the security trio. Phase 15 shipped cert-manager only; Vault and Keycloak were deferred. Re-evaluating now:

| | **Keycloak** | **Authentik** (chosen) |
|---|---|---|
| Position in market | Red Hat backed, enterprise default | Modern, growing fast, designed for self-hosted |
| Resource footprint | ~1.5 GiB RAM + Postgres + (optional infinispan) | ~512 MiB RAM + Postgres (no Redis as of 2026.5.x — embedded cache) |
| Config UX | Java/JPA admin console, dense | Modern React UI, well documented |
| OIDC / OAuth2 / SAML / LDAP / SCIM | All | All |
| Forward-auth for "no native auth" apps | Doable but external (oauth2-proxy) | **Built-in** as Outposts (Proxy provider) |
| Setup time to first working SSO | ~3 hours | ~90 min |
| Portfolio narrative | "I know enterprise IDM" | "I know modern self-hosted IDM" |
| When Keycloak wins | 10,000+ users, multi-realm federation, regulatory-mandated tool | n/a at our scale |

At our scale (one user, 13 apps, portfolio context), Keycloak's complexity is overhead, not value. Authentik gives us all the architectural skills — OIDC, OAuth2 PKCE, JWT validation, `forward-auth` middleware — with a fraction of the YAML and a friendlier admin UI. The old `02-keycloak.md` is kept in the sidebar for reference (deprioritized) but is not the implementation path.

---

## Architecture

```text
                          ┌─────────────────────────────────────────────────┐
   Browser                │  Authentik (in-cluster, auth.10.0.0.200.nip.io) │
       │                  │   ┌─────────────────────────────────────────┐  │
       │ GET app          │   │  PostgreSQL (Longhorn, 1 GiB)           │  │
       │                  │   │  (NO Redis — 2026.5.x embedded cache)   │  │
       ▼                  │   │  Server pod (HTTP API + admin UI)        │  │
   *.10.0.0.200.nip.io ──┐│   │  Worker pod (background tasks, email)    │  │
       │                  ││   └─────────────────────────────────────────┘  │
   ┌───┴────────────┐    ││         ▲                                       │
   │ NGINX Ingress  │    ││         │ OIDC discovery + JWT validation       │
   │ + cert-manager │────┼┘         │                                       │
   │ TLS            │    │          │                                       │
   └─┬──────────────┘    │          │                                       │
     │                    │ ┌────────┴───────────────────────────┐          │
     │   forward-auth     │ │ Proxy Outposts (per protected app)  │          │
     │   middleware       │ │   - argocd, grafana, harbor, ...    │          │
     │   ┌────────────────┴─►   - homer, podinfo, platform-demo… │          │
     │   │                  │   - via Authentik's built-in Proxy  │          │
     │   │                  │     provider (no oauth2-proxy)      │          │
     │   │                  └─────────────────────────────────────┘          │
     │   │                                                                  │
     └───┴─────► app's OWN OIDC client ──────────────────────────────────────┘
                 (ArgoCD, Grafana, Harbor, MinIO, Backstage, etc.)
```

**Two integration paths**, picked per-app based on capability:

1. **Native OIDC** (Tier A, ~6 apps): The app talks to Authentik directly via its own OIDC client. Best UX (auth state in the app's own session), maintains app-specific authorization (Grafana viewer vs editor roles, etc.).

2. **Proxy / forward-auth** (Tier C, ~5 apps): The app has no auth at all. Authentik's Proxy Outpost sits in front via NGINX's `auth-url` directive — every request must carry a valid session cookie from Authentik or it gets 302'd to `auth.10.0.0.200.nip.io/login`.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| IdP | **Authentik** v2024.x | See "Why Authentik over Keycloak" above |
| Helm chart | `goauthentik/authentik` (official) | Maintained by the Authentik team, sensible defaults |
| Persistence | PostgreSQL on Longhorn only (Bitnami subchart, standalone) | Authentik 2026.5.x ships an embedded cache backend instead of requiring external Redis — see Gotcha 3. Saves ~256 MiB RAM + one StatefulSet + one PVC. |
| Replicas | 1 each (server, worker, postgres) | Single user, portfolio scale; HA via worker scale-out is documented but deferred |
| TLS | cert-manager `minicloud-ca` ClusterIssuer (Phase 15) | Same as every other workload — green padlock for free |
| Image source | Pulled through Harbor `docker-hub` proxy (Phase 16) | All cluster image pulls route through Harbor |
| User store | Local (Authentik's own DB) | Portfolio scope. Real production would federate to LDAP / Google Workspace / Azure AD via Authentik's Source providers |
| Initial bootstrap | `AUTHENTIK_BOOTSTRAP_PASSWORD` env from k8s Secret | One-time bootstrap; rotate to MFA-enrolled account ASAP |
| Forward-auth implementation | **Authentik built-in Proxy Outpost** | Avoids running a separate `oauth2-proxy` deployment — one fewer moving part |
| OIDC client secret storage | k8s Secrets in each consumer namespace | Will migrate to Vault dynamic credentials in a future phase |
| Group/role mapping | Authentik group claim → per-app role | E.g. `authentik-admins` group → ArgoCD `role:admin`, Grafana `Admin` |
| GitOps | All Authentik Helm release + values go to `minicloud-ansible/helm-values/`; Outposts + OIDC client configs go to `minicloud-gitops/manifests/authentik/` | Hybrid: chart-installed for the IdP itself (live state too risky for ArgoCD), per-Application registrations and Outposts in GitOps |

---

## What's deliberately deferred

| Component | Reason | Future home |
|---|---|---|
| **HA Authentik** (3-replica server, Redis Sentinel) | Single-user portfolio scope; HA earns its keep at >100 concurrent sessions | Future "Authentik scale-out" phase if needed |
| **MFA enrolment** (WebAuthn / TOTP) | Will be added on Day 1 after bootstrap (it's a 5-min UI flow inside Authentik) — not strictly "deferred", just done out of band of this runbook | This doc, post-Stage 1 |
| **LDAP / external identity federation** | Single-user, no external directory to federate to | Future phase when team grows |
| **Vault-backed OIDC client secrets** | Vault itself is also deferred (Phase 15 honesty) | Pair this work with the Vault phase |
| **MAAS via native OIDC** | MAAS's OIDC support is incomplete / undocumented as of 3.4 — proxy path is safer | Sticking with MAAS local auth + forward-auth proxy in front, until upstream MAAS ships proper OIDC |
| **Backstage native OIDC config** | Off-the-shelf Backstage image bug blocks UI entirely (see Phase 18 doc) — Authentik integration must wait until custom Backstage image phase | Future "Backstage Plugins" phase |

---

## Pre-flight

```bash
# Verify cert-manager ClusterIssuer is ready (Phase 15)
kubectl get clusterissuer minicloud-ca
# Expected: True

# Verify Harbor docker-hub proxy works (Phase 16)
curl -sI --cacert ~/minicloud-ca.crt -u "admin:$(cat ~/.harbor-admin)" \
  https://harbor.10.0.0.200.nip.io/v2/docker-hub/library/alpine/manifests/3.20 | head -2
# Expected: HTTP/1.1 200 OK

# Verify Longhorn default StorageClass (Phase 5)
kubectl get storageclass | grep "longhorn (default)"

# Verify NGINX Ingress LoadBalancer at 10.0.0.200 (Phase 6)
kubectl get svc -n ingress-nginx | grep LoadBalancer
```

All four must be green before starting Stage 1.

---

## Stage 1 — Deploy Authentik (target: ~2 hours)

### 1.1 — Add the Helm repo and bootstrap secrets

```bash
helm repo add authentik https://charts.goauthentik.io
helm repo update authentik

# Bootstrap password and token (one-time; rotate after first login)
openssl rand -base64 32 > ~/.authentik-bootstrap-password
chmod 600 ~/.authentik-bootstrap-password
openssl rand -base64 32 > ~/.authentik-bootstrap-token
chmod 600 ~/.authentik-bootstrap-token

# Postgres password (mode 600, never committed)
openssl rand -base64 24 > ~/.authentik-postgres
chmod 600 ~/.authentik-postgres
```

### 1.2 — `authentik-values.yaml`

Save to `/home/ktayl/minicloud-ktaylorganisation/authentik-values.yaml` (template — substitute placeholders before `helm install`):

```yaml
# Authentik 2026.5.x has NO Redis subchart — embedded cache replaces it (Gotcha 3).
# Secrets use {{PLACEHOLDER}} substitution (Gotcha 4 — existingSecret.secretName is a trap).

authentik:
  log_level: info
  secret_key: "{{SECRET_KEY}}"              # from ~/.authentik-secret-key
  postgresql:
    host: "authentik-postgresql"
    name: "authentik"
    user: "authentik"
    password: "{{POSTGRES_PASSWORD}}"       # from ~/.authentik-postgres
    port: 5432
  error_reporting:
    enabled: false                          # no telemetry to upstream

# Server pod (HTTP + admin UI). Pulls via Harbor ghcr proxy.
server:
  enabled: true
  replicas: 1
  resources:
    requests: { cpu: 100m, memory: 384Mi }
    limits:   { cpu: 1000m, memory: 768Mi }
  ingress:
    enabled: false                          # we add our own with cert-manager TLS
  envFrom:
    - secretRef:
        name: authentik-bootstrap           # Gotcha 5: keys MUST be uppercase env-var-style

# Worker pod (background tasks)
worker:
  enabled: true
  replicas: 1
  resources:
    requests: { cpu: 50m,  memory: 256Mi }
    limits:   { cpu: 500m, memory: 512Mi }
  envFrom:
    - secretRef:
        name: authentik-bootstrap

# Bitnami Postgres subchart. Chart default uses library/postgres:17.10-bookworm,
# NOT bitnami/postgresql — no AGPL licensing gotcha.
postgresql:
  enabled: true
  global:
    security:
      allowInsecureImages: true
  auth:
    existingSecret: authentik-postgres-secret
    secretKeys:
      adminPasswordKey: postgres-password
      userPasswordKey: password
    username: authentik
    database: authentik
  primary:
    persistence:
      enabled: true
      storageClass: longhorn
      size: 1Gi
    resources:
      requests: { cpu: 50m,  memory: 128Mi }
      limits:   { cpu: 500m, memory: 512Mi }
```

**Render with real secrets via here-doc (avoids sed env-scope traps):**

```bash
SECRET_KEY=$(cat ~/.authentik-secret-key)
PG_PASSWORD=$(cat ~/.authentik-postgres)
cat > /tmp/authentik-values-rendered.yaml <<EOF
$(sed -e "s|{{SECRET_KEY}}|${SECRET_KEY}|" -e "s|{{POSTGRES_PASSWORD}}|${PG_PASSWORD}|" \
       /home/ktayl/minicloud-ktaylorganisation/authentik-values.yaml)
EOF
chmod 600 /tmp/authentik-values-rendered.yaml
```

### 1.3 — Out-of-band Secrets

**Important — Secret keys MUST be uppercase env-var-style** (see Gotcha 5). The chart's `envFrom: secretRef` sets each Secret key as a literal env var name; Authentik looks for `AUTHENTIK_BOOTSTRAP_PASSWORD`, not `bootstrap_password`.

```bash
kubectl create namespace authentik

# Postgres credentials — both keys reference the same password
# (postgres-password = admin superuser; password = the application user)
kubectl create secret generic authentik-postgres-secret \
  -n authentik \
  --from-literal=postgres-password="$(cat ~/.authentik-postgres)" \
  --from-literal=password="$(cat ~/.authentik-postgres)"

# Authentik bootstrap admin credentials (UPPERCASE env-var-style keys)
kubectl create secret generic authentik-bootstrap \
  -n authentik \
  --from-literal=AUTHENTIK_BOOTSTRAP_PASSWORD="$(cat ~/.authentik-bootstrap-password)" \
  --from-literal=AUTHENTIK_BOOTSTRAP_TOKEN="$(cat ~/.authentik-bootstrap-token)" \
  --from-literal=AUTHENTIK_BOOTSTRAP_EMAIL="kanmegnea@gmail.com"
```

The values file's `server.envFrom` + `worker.envFrom` reference `authentik-bootstrap` already (see Stage 1.2). Postgres password is inlined via the templated `{{POSTGRES_PASSWORD}}` substitution — DO NOT also add `authentik-postgres-secret` to envFrom or you'll get duplicate-env warnings.

### 1.4 — Install

Use the **rendered** values file (`/tmp/authentik-values-rendered.yaml`), NOT the template at `~/minicloud-ktaylorganisation/authentik-values.yaml` — the chart needs real `secret_key` + `postgres password` substituted (Gotcha 4).

```bash
helm install authentik authentik/authentik \
  --version 2026.5.3 \
  -n authentik \
  -f /tmp/authentik-values-rendered.yaml \
  --timeout 10m

# Watch the pods come up (Postgres first, then server+worker after Postgres ready)
kubectl get pods -n authentik -w
# Expected steady state: authentik-server-... (1/1), authentik-worker-... (1/1), authentik-postgresql-0 (1/1)
# (No Redis pod in 2026.5.x — embedded cache replaces it.)
```

If the server pod logs `Secret key missing` after startup, the substitution didn't take — re-render the values file with the here-doc one-liner from Stage 1.2, then `helm upgrade` (don't uninstall — Postgres data survives).

If the server pod logs `PostgreSQL connection failed, retrying...` and the host shows `127.0.0.1`, you set `authentik.existingSecret.secretName` and tripped Gotcha 4 — see that section.

### 1.5 — TLS Ingress

`manifests/authentik/ingress.yaml`:

```yaml
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: authentik-tls
  namespace: authentik
spec:
  secretName: authentik-tls
  duration: 2160h    # 90d
  renewBefore: 720h  # 30d
  issuerRef:
    name: minicloud-ca
    kind: ClusterIssuer
  dnsNames:
    - auth.10.0.0.200.nip.io
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: authentik
  namespace: authentik
  annotations:
    nginx.org/redirect-to-https: "true"
spec:
  ingressClassName: nginx
  tls:
    - hosts: [auth.10.0.0.200.nip.io]
      secretName: authentik-tls
  rules:
    - host: auth.10.0.0.200.nip.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: authentik-server
                port:
                  number: 80
```

```bash
kubectl apply -f manifests/authentik/ingress.yaml
curl -sIf --cacert ~/minicloud-ca.crt https://auth.10.0.0.200.nip.io/
# Expected: HTTP/1.1 200 OK
```

### 1.6 — First login + MFA enrollment

**Device choice — no restriction.** Use any tailnet-connected browser: controller's local browser (if you have a GUI session), Mac over Tailscale, phone over Tailscale, etc. All you need is reachability to `https://auth.10.0.0.200.nip.io`.

1. Browse `https://auth.10.0.0.200.nip.io` → click **Admin interface**
2. Log in as `akadmin` with the password from `~/.authentik-bootstrap-password`
3. **Switch to the User interface to enroll MFA** (admin interface intentionally doesn't expose self-MFA settings — see gotcha #4 below). Click your avatar top-right → **"User interface"**. URL becomes `/if/user/`.
4. In the User interface: top-right avatar → **Settings** → **"MFA Devices"** (left sidebar) → **Enroll** → **TOTP Device**. Scan the QR code with Google Authenticator / Authy / 1Password / Microsoft Authenticator. Enter the 6-digit code, save.
5. Log out, log back in as `akadmin` — Authentik now prompts for password + TOTP code (verify enrollment took).
6. Create a personal user: switch back to Admin interface → **Directory** → **Users** → **Create** (fill in email, name; set a password OR leave blank and use "Reset password by email" flow). Add to the built-in `authentik Admins` group.
7. Log out of `akadmin`, log back in with your personal account. Repeat the MFA enrollment for this account (User interface → Settings → MFA Devices).
8. Once verified your personal MFA-protected account can do admin work, **disable** `akadmin` (Admin interface → Directory → Users → akadmin → "Inactive" toggle ON). DO NOT delete — preserves audit trail of any bootstrap actions.

### Stage 1 acceptance

```bash
✔ kubectl get pods -n authentik shows 4 pods Running
✔ kubectl get certificate -n authentik authentik-tls reports Ready=True
✔ https://auth.10.0.0.200.nip.io returns 200 with valid TLS via minicloud-ca
✔ Personal user account created and MFA-enrolled
✔ akadmin user disabled
✔ authentik-values.yaml mirrored to minicloud-ansible/helm-values/ (Phase 18 pattern)
```

**Mirror to ansible** (matches Phase 18 + 19 pattern):

```bash
cp authentik-values.yaml ansible/helm-values/authentik-values.yaml
cd ansible && git add helm-values/authentik-values.yaml && \
  git commit -m "chore(helm-values): mirror authentik-values.yaml" && \
  git push origin main
```

---

## Stage 2 — Forward-auth for unauthenticated apps (target: ~1.5 hours)

The five unauthenticated apps (Homer, podinfo, platform-demo, whoami, NATS monitoring) get gated by Authentik's Proxy Outpost at the Ingress layer — no app code touched.

### 2.1 — Create a Proxy Provider in Authentik

In Authentik admin UI → **Applications** → **Providers** → **Create**:

| Field | Value |
|---|---|
| Type | **Proxy Provider** |
| Name | `minicloud-forward-auth` |
| Authentication flow | `default-authentication-flow` |
| Authorization flow | `default-provider-authorization-explicit-consent` |
| External host | `https://homer.10.0.0.200.nip.io` (placeholder — gets overridden per Application below) |
| Mode | **Forward auth (single application)** |
| Token validity | `hours=24` |

### 2.2 — Create one Authentik Application per protected app

For each of the 5 unauthenticated apps, in **Applications** → **Applications** → **Create**:

| App | Slug | Launch URL | Provider |
|---|---|---|---|
| Homer | `homer` | `https://homer.10.0.0.200.nip.io` | `minicloud-forward-auth` |
| podinfo | `podinfo` | `https://podinfo.10.0.0.200.nip.io` | `minicloud-forward-auth` |
| platform-demo | `platform-demo` | `https://platform-demo.10.0.0.200.nip.io` | `minicloud-forward-auth` |
| whoami | `whoami` | `https://whoami.10.0.0.200.nip.io` | `minicloud-forward-auth` |
| NATS monitoring | `nats` | `https://nats.10.0.0.200.nip.io` | `minicloud-forward-auth` |

### 2.3 — Deploy the embedded Outpost

In Authentik admin UI → **Applications** → **Outposts** → **Edit `authentik Embedded Outpost`** → check all 5 Applications → **Save**.

The embedded Outpost runs as part of the `authentik-server` pod, listening on port 9000 for forward-auth requests.

### 2.4 — Annotate each Ingress to use forward-auth

For each of the 5 Ingresses, add these NGINX annotations:

```yaml
annotations:
  nginx.org/server-snippets: |
    auth_request /outpost.goauthentik.io/auth/nginx;
    error_page 401 = @goauthentik_proxy_signin;
    auth_request_set $auth_cookie $upstream_http_set_cookie;
    add_header Set-Cookie $auth_cookie;
    auth_request_set $authentik_username   $upstream_http_x_authentik_username;
    auth_request_set $authentik_groups     $upstream_http_x_authentik_groups;
    auth_request_set $authentik_email      $upstream_http_x_authentik_email;
    proxy_set_header X-authentik-username  $authentik_username;
    proxy_set_header X-authentik-groups    $authentik_groups;
    proxy_set_header X-authentik-email     $authentik_email;
  nginx.org/location-snippets: |
    location /outpost.goauthentik.io {
      proxy_pass              http://authentik-server.authentik.svc.cluster.local:9000/outpost.goauthentik.io;
      proxy_set_header        Host $host;
      proxy_set_header        X-Original-URL $scheme://$http_host$request_uri;
      add_header              Set-Cookie $auth_cookie;
      auth_request_set        $auth_cookie $upstream_http_set_cookie;
      proxy_pass_request_body off;
      proxy_set_header        Content-Length "";
    }
    location @goauthentik_proxy_signin {
      internal;
      add_header Set-Cookie $auth_cookie;
      return 302 /outpost.goauthentik.io/start?rd=$request_uri;
    }
```

For Homer (GitOps-managed via `minicloud-gitops/manifests/homer/04-ingress.yaml`), bump the `config-checksum` annotation on the Deployment as always (Phase 12 GitOps gotcha).

### Stage 2 acceptance

```bash
✔ Visit https://homer.10.0.0.200.nip.io in incognito → 302 to auth.10.0.0.200.nip.io
✔ Log in via Authentik → 302 back to Homer dashboard
✔ Repeat for podinfo, platform-demo, whoami, NATS — all 5 forward-auth gated
✔ Authentik admin UI → Events → 5 "logged in" events visible per session
```

**Effort so far: 5 of 13 apps now on SSO. 8 to go.**

---

## Stage 3 — Tier A native OIDC: ArgoCD + Grafana + Backstage (target: ~1.5 hours)

These three have the cleanest OIDC integration — straightforward chart-values changes.

### 3.1 — ArgoCD

In Authentik:
1. **Providers** → Create **OAuth2/OpenID Provider** named `argocd`
2. Redirect URIs: `https://argocd.10.0.0.200.nip.io/auth/callback`
3. Note the generated **Client ID** and **Client Secret**
4. **Applications** → Create app `argocd`, attach the provider

In the cluster:

```bash
kubectl create secret generic argocd-oidc \
  -n argocd \
  --from-literal=clientSecret="<the-secret-from-authentik>"
```

Edit `argocd-values.yaml` (or `kubectl -n argocd edit cm argocd-cm`):

```yaml
configs:
  cm:
    url: https://argocd.10.0.0.200.nip.io
    oidc.config: |
      name: Authentik
      issuer: https://auth.10.0.0.200.nip.io/application/o/argocd/
      clientID: argocd
      clientSecret: $argocd-oidc:clientSecret
      requestedScopes: ["openid", "profile", "email", "groups"]
      requestedIDTokenClaims: {"groups": {"essential": true}}
  rbac:
    policy.csv: |
      g, authentik-admins, role:admin
      g, authentik-readers, role:readonly
    policy.default: role:readonly
```

`helm upgrade argocd argo/argo-cd -n argocd -f argocd-values.yaml`

**Verify:** ArgoCD login page shows a "Log in via Authentik" button. Clicking it 302s to Authentik, you log in, 302s back to ArgoCD with your `authentik-admins` group mapping you to `role:admin`. The local `admin` account still works as emergency fallback.

### 3.2 — Grafana

Same pattern:
1. Authentik → new OAuth2 Provider `grafana`, redirect `https://grafana.10.0.0.200.nip.io/login/generic_oauth`
2. New Application `grafana`, attach provider
3. k8s Secret with client_secret in `monitoring` namespace
4. Edit `kube-prometheus-stack-values.yaml`:

```yaml
grafana:
  grafana.ini:
    server:
      root_url: https://grafana.10.0.0.200.nip.io
    auth.generic_oauth:
      enabled: true
      name: Authentik
      client_id: grafana
      client_secret: $__file{/etc/secrets/oidc/client_secret}
      scopes: openid profile email groups
      auth_url: https://auth.10.0.0.200.nip.io/application/o/authorize/
      token_url: https://auth.10.0.0.200.nip.io/application/o/token/
      api_url: https://auth.10.0.0.200.nip.io/application/o/userinfo/
      role_attribute_path: contains(groups[*], 'authentik-admins') && 'Admin' || 'Viewer'
      allow_assign_grafana_admin: true
  extraSecretMounts:
    - name: grafana-oidc
      secretName: grafana-oidc
      defaultMode: 0440
      mountPath: /etc/secrets/oidc
      readOnly: true
```

`helm upgrade kps prometheus-community/kube-prometheus-stack -n monitoring -f kube-prometheus-stack-values.yaml`

### 3.3 — Backstage

**Skip in this phase.** As of 2026-06-15, the off-the-shelf Backstage image's UI is broken by the notifications-plugin bug (see Phase 18 doc). Adding OIDC would only matter if the UI worked. Wire Authentik for Backstage as part of the future "Backstage Plugins (custom image)" phase — same session that fixes the UI also adds Authentik.

The `bs_catalog` shell function continues to work without auth (guest token), so this is no regression.

### Stage 3 acceptance

```bash
✔ ArgoCD login page shows "Log in via Authentik" button
✔ Authentik login → land in ArgoCD with role:admin
✔ Grafana login page shows "Sign in with Authentik" button
✔ Authentik login → land in Grafana as Admin (group-derived)
✔ Backstage deliberately deferred (documented above)
```

**Effort so far: 7 of 13 apps on SSO. 6 to go (and Backstage handled by future phase).**

---

## Stage 4 — Tier A native OIDC: Harbor + MinIO + MAAS (target: ~2 hours)

These three have OIDC support but it's fiddlier.

### 4.1 — Harbor

In Harbor admin UI → **Administration** → **Configuration** → **Authentication**:

| Field | Value |
|---|---|
| Auth mode | **OIDC** |
| OIDC provider name | `Authentik` |
| OIDC endpoint | `https://auth.10.0.0.200.nip.io/application/o/harbor/` |
| OIDC client ID | `harbor` |
| OIDC client secret | (from Authentik) |
| Group claim | `groups` |
| Admin group | `authentik-admins` |
| OIDC scope | `openid,profile,email,groups,offline_access` |
| Verify cert | enabled |

In Authentik: new Provider + Application `harbor`, redirect URI `https://harbor.10.0.0.200.nip.io/c/oidc/callback`.

**Gotcha:** Harbor's mode switch from DB → OIDC is **one-way per project** at the UI. Existing users (admin) keep working but new users come in via OIDC. Save the admin password — it remains the emergency local fallback.

### 4.2 — MinIO

MinIO supports OIDC via environment variables on the systemd unit (Phase 14 still runs MinIO on the controller, not in the cluster):

Edit `/etc/systemd/system/minio.service`:

```ini
ExecStart=/usr/bin/docker run \
    ...existing flags...
    -e MINIO_IDENTITY_OPENID_CONFIG_URL="https://auth.10.0.0.200.nip.io/application/o/minio/.well-known/openid-configuration" \
    -e MINIO_IDENTITY_OPENID_CLIENT_ID="minio" \
    -e MINIO_IDENTITY_OPENID_CLIENT_SECRET="<from-authentik>" \
    -e MINIO_IDENTITY_OPENID_DISPLAY_NAME="Authentik" \
    -e MINIO_IDENTITY_OPENID_SCOPES="openid,profile,email,groups" \
    -e MINIO_IDENTITY_OPENID_CLAIM_NAME="policy" \
    -e MINIO_IDENTITY_OPENID_REDIRECT_URI="https://100.88.123.8:9001/oauth_callback" \
    ...rest...
```

In Authentik, the `minio` Application's redirect URI must match exactly: `http://100.88.123.8:9001/oauth_callback` (HTTP not HTTPS — MinIO console is still HTTP-only per Phase 14).

Restart: `sudo systemctl daemon-reload && sudo systemctl restart minio.service`.

**Verify:** MinIO console at `http://100.88.123.8:9001` shows a "Sign in with SSO" button.

### 4.3 — MAAS

**Honest answer:** MAAS's OIDC support as of 3.4 is incomplete — the upstream tracks issues for years. Two paths:

- **Option A** (cleaner long-term): wait for upstream MAAS to ship proper OIDC. Track [LP#1989012](https://bugs.launchpad.net/maas/+bug/1989012).
- **Option B** (what we do): **forward-auth proxy** (same pattern as Stage 2). Treat MAAS as an unauthenticated app and gate it with the Authentik Outpost. MAAS keeps its local `admin` user as the actual operator account; Authentik just controls *who can reach the MAAS UI at all*.

Option B steps:

1. Authentik: new Proxy Provider Application `maas`, external host `http://100.88.123.8:5240/MAAS`
2. NGINX in front of MAAS — we'd need to add NGINX on the controller in front of port 5240, or run a small proxy pod. (This is the most fiddly step in the whole phase — budget extra time.)

Probably worth tackling as its own sub-task on Day 2/3 rather than rushing it.

### Stage 4 acceptance

```bash
✔ Harbor UI shows "Login via OIDC Provider" button → Authentik → land as admin
✔ MinIO console shows "Sign in with SSO" → Authentik → land in console
✔ MAAS reachable only after Authentik login (forward-auth gated)
```

**Effort so far: 10 of 13 apps on SSO. 3 to go (Open WebUI + NATS coverage + Backstage deferred).**

---

## Stage 5 — Open WebUI (target: ~1 hour)

Open WebUI added native OIDC in v0.4. Set env vars in `open-webui-values.yaml`:

```yaml
extraEnvVars:
  - name: ENABLE_OAUTH_SIGNUP
    value: "true"
  - name: OAUTH_CLIENT_ID
    value: "open-webui"
  - name: OAUTH_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: open-webui-oidc
        key: client_secret
  - name: OPENID_PROVIDER_URL
    value: "https://auth.10.0.0.200.nip.io/application/o/open-webui/.well-known/openid-configuration"
  - name: OAUTH_PROVIDER_NAME
    value: "Authentik"
  - name: OAUTH_SCOPES
    value: "openid profile email"
```

`helm upgrade open-webui open-webui/open-webui -n ai -f open-webui-values.yaml`

**Verify:** Chat UI login page shows "Continue with Authentik".

---

## Stage 6 — Cleanup + portfolio polish (target: ~1 hour)

### 6.1 — Rotate admin secrets

Per-app, replace the local admin password files with much-shorter-validity local recovery passwords:

```bash
# Example: ArgoCD
NEW_PW=$(openssl rand -base64 32)
echo "$NEW_PW" > ~/.argocd-admin
chmod 600 ~/.argocd-admin
# Reset inside ArgoCD: argocd account update-password ...
# Document: "use this only if Authentik is down"
```

Repeat for: `~/.grafana-admin`, `~/.harbor-admin`, `~/.minio-admin`.

### 6.2 — Update Homer tiles

Each tile's `subtitle` now says "SSO via Authentik". Remove the "admin / cat ~/.X-admin on controller" hints from the GitOps-managed `minicloud-gitops/manifests/homer/01-configmap.yaml`. Bump `config-checksum` annotation (Phase 12 GitOps gotcha).

### 6.3 — Update operational docs

- This doc (`02-sso-authentik.md`): mark all stages ✅ Done
- `docs/intro.md`: add Phase 23 to the roadmap as ✅ Done
- `docs/platform-roadmap/00-overview.md`: same
- `docs/remote-access/00-overview.md`: rewrite the bookmark table — every "admin / cat ~/.X-admin" entry becomes "SSO via Authentik"

### 6.4 — Memorize the emergency fallback

Each native-OIDC app keeps a **local emergency admin account** (ArgoCD `admin`, Grafana `admin`, etc.). These exist for the scenario where Authentik is down and you need to fix something. Document in CLAUDE.md the recovery URL pattern for each (ArgoCD: `/login?_=...`, Grafana: `/login` direct, Harbor: `/c/login`).

---

## End-to-end verification

After all stages:

```bash
# 1. Single sign-on test: 13 apps, ONE login
# Browse each from incognito → check that after the first Authentik login,
# subsequent app visits don't re-prompt (cookie reused).
for url in homer argocd grafana harbor backstage podinfo platform-demo whoami nats chat; do
  curl -sI --cacert ~/minicloud-ca.crt "https://${url}.10.0.0.200.nip.io" -w "${url}: %{http_code}\n" -o /dev/null
done

# 2. Logout test: revoke session in Authentik
# Authentik admin UI → Users → your account → "Terminate session"
# All 13 apps should now require re-login on next request.

# 3. Group-based authorization
# Move your user OUT of authentik-admins → into authentik-readers
# Re-login → ArgoCD shows read-only banner, Grafana shows Viewer-only menu, etc.

# 4. Audit
# Authentik admin UI → Events → see every login event tied to your user
```

---

## Real install gotchas (documented after Stage 1 execution on 2026-06-17)

The first two predictions held. The next four were discovered during the actual Stage 1 deployment and would have cost ~30 min each without this documentation.

### Gotcha 1: NGINX `auth_request` requires the Outpost endpoint to respond at HTTP, not HTTPS

The Authentik Outpost runs on `http://authentik-server.authentik.svc.cluster.local:9000` (cluster-internal, no TLS). The `proxy_pass` lines in the Ingress annotations must use `http://...`, not `https://...`. Putting HTTPS results in NGINX upstream TLS errors.

### Gotcha 2: NGINX `nginx.org/*` annotations vs `nginx.ingress.kubernetes.io/*`

Phase 6 uses **F5 NGINX Ingress** (`nginx-stable` chart), not the archived community NGINX. The annotation prefix is `nginx.org/...`, NOT `nginx.ingress.kubernetes.io/...`. Any Authentik tutorial you copy from the internet will use the community prefix and silently no-op on this platform. **Always translate annotations to `nginx.org/`.** Same gotcha called out in CLAUDE.md for the F5 chart in Phase 6.

### Gotcha 3: Authentik 2026.5.x ships NO Redis subchart — embedded cache replaces it

Older Authentik docs and tutorials say "deploy Postgres + Redis." That's outdated. As of chart `2026.5.x`, the Helm chart's dependencies are PostgreSQL only — Authentik's internal caching uses an embedded backend that doesn't require an external Redis. **Don't waste time looking for `redis:` keys in the values file** — they're not there. This is good news: ~256 MiB RAM saved + one fewer StatefulSet + one fewer PVC.

If your Authentik install logs reference Redis URLs that the chart didn't set up, you're using an older chart version. Either upgrade or fall back to manually deploying Redis (Bitnami subchart).

### Gotcha 4: `authentik.existingSecret.secretName` is a trap

The chart's documented "existingSecret" mechanism for providing your own pre-created Secret SOUNDS like the clean path. It isn't. When you set `authentik.existingSecret.secretName: "my-secret"`, the chart **skips auto-generating its env-var ConfigMap/Secret entirely** — including all the non-secret fields like `AUTHENTIK_POSTGRESQL__HOST`, `AUTHENTIK_POSTGRESQL__PORT`, `AUTHENTIK_POSTGRESQL__USER`, `AUTHENTIK_LOG_LEVEL`, etc.

Result: the server pod boots with no DB connection config and tries to connect to `127.0.0.1:5432`, where nothing is listening. Crashloop with `PostgreSQL connection failed`.

**The reliable path: leave `existingSecret.secretName` blank, inline the sensitive values into the rendered values file via templated substitution.** Example workflow:

```bash
SECRET_KEY=$(cat ~/.authentik-secret-key)
PG_PASSWORD=$(cat ~/.authentik-postgres)
cat > /tmp/authentik-values-rendered.yaml <<EOF
authentik:
  secret_key: "${SECRET_KEY}"
  postgresql:
    host: "authentik-postgresql"
    password: "${PG_PASSWORD}"
    # ...
EOF
chmod 600 /tmp/authentik-values-rendered.yaml
helm install authentik authentik/authentik --version 2026.5.3 \
  -n authentik -f /tmp/authentik-values-rendered.yaml
```

The mirror in `minicloud-ansible/helm-values/authentik-values.yaml` keeps placeholders (`{{SECRET_KEY}}`, `{{POSTGRES_PASSWORD}}`) so the file is safe to commit; real values stay in mode-600 files at `~/.authentik-*`.

### Gotcha 5: Secret keys with `envFrom: secretRef` must be uppercase env-var-style

For Secrets ALSO injected via `envFrom: secretRef` on the server/worker pods (e.g. the bootstrap admin credentials), the chart sets **each Secret key as a literal env var name**. Authentik expects env vars like `AUTHENTIK_BOOTSTRAP_PASSWORD`, `AUTHENTIK_BOOTSTRAP_TOKEN`. So your Secret keys must match exactly:

```bash
# WRONG — Authentik sees env var "bootstrap_password" and ignores it:
kubectl create secret generic authentik-bootstrap \
  --from-literal=bootstrap_password="$(cat ~/.authentik-bootstrap-password)"

# RIGHT — Authentik sees env var "AUTHENTIK_BOOTSTRAP_PASSWORD":
kubectl create secret generic authentik-bootstrap \
  --from-literal=AUTHENTIK_BOOTSTRAP_PASSWORD="$(cat ~/.authentik-bootstrap-password)"
```

If you create the Secret with lowercase keys, the server pod boots and silently SKIPS the bootstrap-user creation — no error log, just no `akadmin` exists when you try to log in.

### Gotcha 6: MFA enrollment is in the USER interface, not the Admin interface

Authentik splits its frontend into two routes: `/if/admin/` (configure providers, applications, policies, OTHER users' accounts) and `/if/user/` (YOUR account settings, including self-MFA enrollment). The Admin interface deliberately doesn't expose self-MFA — the design assumption is that admin accounts are managed accounts, not personal accounts.

To enroll MFA on yourself: from `/if/admin/`, click your avatar top-right → **"User interface"** to switch to `/if/user/`. Then top-right avatar → **Settings** → **"MFA Devices"** → **Enroll** → **TOTP Device** / **WebAuthn**. Scan or pair, save.

After enrollment, the next login (`/if/flow/default-authentication-flow`) prompts for password + TOTP. Verify enrollment is sticky by logging out and back in BEFORE disabling `akadmin` — otherwise you risk locking yourself out.

---

## Done When

```text
Stage 1 ✔ Authentik server + worker + Postgres + Redis Running in authentik namespace
        ✔ TLS Ingress on auth.10.0.0.200.nip.io returns 200 via minicloud-ca
        ✔ Personal MFA-enrolled user account created; akadmin disabled
        ✔ authentik-values.yaml mirrored to minicloud-ansible/helm-values/

Stage 2 ✔ Embedded Outpost wired to 5 Applications (homer, podinfo,
          platform-demo, whoami, nats)
        ✔ All 5 Ingresses 302 unauthenticated requests to auth.10.0.0.200.nip.io
        ✔ Round-trip login → app works from incognito browser

Stage 3 ✔ ArgoCD "Log in via Authentik" button works; group → role mapping correct
        ✔ Grafana "Sign in with Authentik" button works; role_attribute_path
          correctly maps authentik-admins → Admin
        ✔ Backstage deliberately deferred to custom-image phase (documented)

Stage 4 ✔ Harbor login via OIDC works; admin group maps correctly
        ✔ MinIO console SSO works
        ✔ MAAS reachable only post-Authentik (forward-auth gated)

Stage 5 ✔ Open WebUI "Continue with Authentik" works

Stage 6 ✔ Local admin passwords rotated, marked "emergency only" in CLAUDE.md
        ✔ Homer tiles updated to remove per-app admin password hints
        ✔ Phase 23 marked Done in intro.md + platform-roadmap
        ✔ Bookmark table in remote-access/overview.md rewritten
```

---

## Real-world skills demonstrated

| Skill | Industry context |
|---|---|
| **OIDC / OAuth2 implementation across heterogeneous workloads** | The single most-asked skill in platform-engineer interviews. Every shop with >5 apps eventually faces this. |
| **Forward-auth pattern for legacy / unauthenticated apps** | The escape hatch every platform needs — not every internal tool will ever support OIDC natively |
| **MFA enrollment + emergency local fallback design** | The discipline of "SSO is the front door, but you keep a key for when the lock breaks" — interviewers grade this hard |
| **Group-claim → app-role mapping** | The actual implementation of RBAC across a fleet, not just theory |
| **Choosing Authentik over Keycloak with explicit reasoning** | Senior engineering judgment — picking the simpler tool when complexity isn't needed |
| **Deliberate deferrals (Backstage, Vault, LDAP)** | Same scope-reduction discipline as Phase 11 (Crossplane), Phase 13 (GitLab), Phase 15 (Vault), Phase 18 (plugins). Senior engineers ship working subsets, not perfect everything. |
| **Hybrid GitOps strategy** (chart-installed IdP + GitOps-managed Outposts/clients) | Recognizing that the IdP itself is too live/risky for ArgoCD's `selfHeal`, while per-app configs benefit from version control. Same pattern as Postgres for Backstage. |
| **Cross-doc consistency** (update Homer tiles, intro.md, roadmap, bookmark table, CLAUDE.md) | The cleanup discipline distinguishing "ships features" engineers from "owns the platform" engineers |
