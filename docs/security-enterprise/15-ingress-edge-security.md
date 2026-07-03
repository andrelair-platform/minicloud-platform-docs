---
id: ingress-edge-security
title: "Phase 15 — Ingress & Edge Security"
sidebar_label: "15 — Ingress & Edge Security"
---

# Ingress & Edge Security

**Status:** Complete — 2026-07-03  
**Components:** F5 NGINX Ingress Controller v5.4.1, Authentik Embedded Outpost, cert-manager, Cloudflare Tunnel

---

## Threat Model

External traffic enters the cluster via two paths:

- **Cloudflare Tunnel** (`*.devandre.sbs`) — all internet traffic terminates at Cloudflare's edge before reaching the cluster; DDoS protection and bot management at Free tier
- **NGINX Ingress Controller** (`10.0.0.200`) — handles TLS termination for both public `devandre.sbs` and internal `nip.io` paths; internal paths reachable only via Tailscale

Gaps identified at audit (2026-07-03):
- Prometheus and Alertmanager accessible without authentication
- Polaris dashboard accessible without authentication
- No HSTS header at ingress level
- No rate limiting on public endpoints
- Wrong nginx annotation prefix (`nginx.ingress.kubernetes.io` instead of `nginx.org`) on two ingresses

---

## Gap Closures

### 1. Authentik Forward-Auth on Monitoring Dashboards

Prometheus, Alertmanager, and Polaris now require Authentik OIDC login via NGINX `auth_request`.

**Mechanism** (same as Homer/Platform-demo, Phase 23):
```yaml
nginx.org/server-snippets: |
  location /outpost.goauthentik.io {
      proxy_pass http://authentik-server.authentik.svc.cluster.local/outpost.goauthentik.io;
      proxy_set_header Host $host;
      proxy_set_header X-Original-URL $scheme://$http_host$request_uri;
      proxy_pass_request_body off;
      proxy_set_header Content-Length "";
      add_header Set-Cookie $auth_cookie;
      auth_request_set $auth_cookie $upstream_http_set_cookie;
  }
  location @goauthentik_proxy_signin {
      internal;
      add_header Set-Cookie $auth_cookie;
      return 302 /outpost.goauthentik.io/start?rd=$request_uri;
  }
nginx.org/location-snippets: |
  auth_request /outpost.goauthentik.io/auth/nginx;
  error_page 401 = @goauthentik_proxy_signin;
  auth_request_set $auth_cookie $upstream_http_set_cookie;
  add_header Set-Cookie $auth_cookie;
  auth_request_set $authentik_username $upstream_http_x_authentik_username;
  auth_request_set $authentik_groups $upstream_http_x_authentik_groups;
  auth_request_set $authentik_email $upstream_http_x_authentik_email;
  proxy_set_header X-authentik-username $authentik_username;
  proxy_set_header X-authentik-groups $authentik_groups;
  proxy_set_header X-authentik-email $authentik_email;
```

**Where applied:**
- `prometheus.ingress.annotations` + `alertmanager.ingress.annotations` in `kube-prometheus-stack-values.yaml` (REVISION: 16)
- `manifests/polaris/01-ingress.yaml` (ArgoCD synced, minicloud-gitops commit 258153f)

**Verify:**
```bash
# Must redirect to Authentik (302)
/usr/bin/curl -sk -D - https://prometheus.10.0.0.200.nip.io \
  --cacert ~/minicloud-ca.crt | grep -iE 'location|HTTP/'
# Expected: 302 → /outpost.goauthentik.io/start?rd=/
```

---

### 2. HSTS (HTTP Strict Transport Security)

HSTS is injected globally via the `nginx-ingress` ConfigMap `server-snippets` key, which appends to every NGINX server block:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

**Applied via:** `nginx-ingress-values.yaml`, `controller.config.entries.server-snippets` (NGINX IC REVISION: 5)

**Nginx `add_header` inheritance gotcha:** Nginx does not inherit `add_header` directives from a parent block into a child block that defines its own `add_header`. Location blocks using Authentik (which emit `add_header Set-Cookie`) therefore suppress the HSTS header for those locations. This is acceptable — browsers cache HSTS after receiving it once from any HTTPS response on the domain, then enforce it on all subsequent requests regardless of which endpoint is hit.

**Verify:**
```bash
/usr/bin/curl -sk -D - https://ktayl.10.0.0.200.nip.io \
  --cacert ~/minicloud-ca.crt | grep -i strict-transport
# Expected: Strict-Transport-Security: max-age=31536000; includeSubDomains
```

---

### 3. Rate Limiting on Public Endpoints

Rate limit zones are defined globally in the `http {}` context via ConfigMap `http-snippets`:

```nginx
limit_req_zone $binary_remote_addr zone=public_ratelimit:10m rate=20r/s;
limit_req_zone $binary_remote_addr zone=auth_ratelimit:10m rate=5r/s;
```

Rate limiting applied to `ktayl-solution-web` (public insurance site, no SSO):
```yaml
nginx.org/location-snippets: |
  limit_req zone=public_ratelimit burst=30 nodelay;
  limit_req_status 429;
```

The `auth_ratelimit` zone is available for login pages when needed — Authentik's built-in brute-force protection covers `/application/o/*/authorize/` natively.

**Verify:**
```bash
kubectl exec -n ingress-nginx \
  $(kubectl get pods -n ingress-nginx -o name | head -1) \
  -- nginx -T 2>/dev/null | grep limit_req_zone
```

---

### 4. Annotation Prefix Fix

F5 NGINX IC uses `nginx.org/` prefix — not `nginx.ingress.kubernetes.io/` which belongs to the community kubernetes/ingress-nginx project. Wrong-prefix annotations are silently ignored. Fixed on:
- `polaris/01-ingress.yaml`: `ssl-redirect`, `proxy-read-timeout`, `proxy-send-timeout`
- `ktayl-solution-web/02-ingress.yaml`: `ssl-redirect`

---

## Accepted Gaps

Two items were evaluated and deliberately accepted rather than closed. This section documents the reasoning so future reviewers can challenge the decision with full context.

---

### WAF (Web Application Firewall)

**Gap:** No WAF rules on any ingress path.

**Why not closed:**

The cluster uses two ingress paths:

1. **Cloudflare Tunnel** (`*.devandre.sbs`) — traffic passes through Cloudflare's edge. The **Free plan** provides DDoS protection and bot management but does **not** include WAF rules (OWASP Core Rule Set, custom firewall rules). WAF requires Cloudflare Pro ($20/mo) at minimum. For a portfolio-grade demo platform this cost is not justified.

2. **NGINX Ingress Controller** (`*.10.0.0.200.nip.io`) — internal paths reachable **only over Tailscale** (Tailscale subnet router on controller; no public exposure). A WAF on internal-only paths adds complexity with minimal security benefit given the access control at the network layer.

**What provides equivalent protection:**
- Cloudflare DDoS protection at the edge for all public paths
- Authentik forward-auth on every internal dashboard (blocks unauthenticated access before reaching the app)
- Rate limiting on public endpoints (20 r/s burst 30, NGINX `limit_req`)
- Tailscale restricts nip.io paths to authenticated devices

**What would close this gap:**
- Upgrade Cloudflare to Pro → WAF rules on `*.devandre.sbs`
- Deploy NGINX App Protect (requires NGINX Plus, commercial license) on the NGINX IC for nip.io paths
- Deploy ModSecurity as a sidecar — possible but complex to maintain; F5 NGINX IC Open Source does not bundle it

**Decision:** Accept. Revisit when the platform has internet-facing workloads with untrusted user-generated input (e.g., a public API).

---

### Harbor `/api/v2.0/systeminfo` Public Endpoint

**Gap:** `curl https://harbor.10.0.0.200.nip.io/api/v2.0/systeminfo` returns HTTP 200 without credentials.

**Why this endpoint is public by design:**

Harbor's API specification marks `/api/v2.0/systeminfo` as an unauthenticated endpoint intentionally. It is used by:
- Harbor CLI and client tools to discover the registry's auth mode before presenting login credentials
- `docker login harbor.example.com` — the Docker client calls systeminfo first to learn whether OIDC or basic auth is expected

The endpoint returns non-sensitive operational metadata:
```json
{
  "harbor_version": "v2.12.x",
  "auth_mode": "oidc_auth",
  "registry_url": "harbor.10.0.0.200.nip.io"
}
```

It does **not** return credentials, image content, user data, or project-level details.

**Why `anonymous_access: false` does not cover this:**

`anonymous_access` controls whether the Docker `anonymous` user can pull images from public projects. It is a registry-level pull control — it does not affect the REST API metadata endpoints. The systeminfo endpoint is governed by a separate Harbor RBAC rule that allows unauthenticated access, hardcoded in Harbor's router.

**What would close this gap:**

Closing it requires one of:
1. **Custom NGINX auth subrequest in front of Harbor** — add an Authentik `auth_request` to the Harbor ingress. This would break `docker login` (clients can't pre-auth to discover auth mode), requiring all users to know the auth mode in advance.
2. **Customize Harbor source** — patch the router to require auth on `/api/v2.0/systeminfo`. Not feasible via Helm; requires a fork.
3. **IP allowlist on Harbor ingress** — restrict `/api/v2.0/systeminfo` to known IPs via NGINX `allow/deny`. Would break kubelet pulls and CI pipelines that don't have fixed IPs.

None of these options preserve Harbor's normal operation.

**What the current posture provides:**
- `anonymous_access: false` — anonymous Docker pulls are disabled; all image pulls require a valid Harbor account
- Harbor OIDC (`auth_mode: oidc_auth`) — all interactive logins go through Authentik
- Harbor is behind Cloudflare Tunnel — no direct internet socket; Cloudflare rate-limits and DDoS-protects all requests
- Proxy-cache projects (docker-hub, ghcr, k8s-registry, quay) are public **by operational necessity** — kubelet on cluster nodes pulls images from Harbor without imagePullSecrets; making them private would require adding imagePullSecrets to every pod spec and every Helm chart

**Decision:** Accept. The information exposure is by Harbor specification, not a misconfiguration. The practical risk is version disclosure (`harbor_version`), which an attacker can use to check for known CVEs. This is mitigated by keeping Harbor up-to-date (Dependabot on minicloud-gitops monitors the Helm chart).

---

## Posture Summary (post Gap 12)

| Control | Status |
|---|---|
| TLS everywhere | ✅ cert-manager + minicloud CA, 17 certs Ready |
| HTTP → HTTPS redirect | ✅ F5 NGINX IC automatic on TLS ingresses |
| HSTS globally | ✅ server-snippets via ConfigMap (max-age 31536000) |
| Rate limiting (public) | ✅ ktayl-web: 20 r/s, burst 30 |
| Auth on all dashboards | ✅ Authentik OIDC on all 11 apps (Homer, Platform-demo, Prometheus, Alertmanager, Polaris, Grafana, ArgoCD, Backstage, Harbor, Vault, Nextcloud) |
| WAF | ⚠️ Accepted — Cloudflare Free (no WAF rules); nip.io paths Tailscale-gated |
| Harbor systeminfo public | ⚠️ Accepted — Harbor specification; version disclosure only; anonymous pulls disabled |
| IP allowlist for admin | ✅ All nip.io admin paths reachable only over Tailscale |
| Gatekeeper admission (9/9) | ✅ All deny mode, 0 violations |

