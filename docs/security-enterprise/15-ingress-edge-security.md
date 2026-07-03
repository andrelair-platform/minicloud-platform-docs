---
id: ingress-edge-security
title: "Phase 15 — Ingress & Edge Security"
sidebar_label: "15 — Ingress & Edge Security"
---

# Ingress & Edge Security

**Status:** Complete — 2026-07-03  
**Components:** F5 NGINX Ingress Controller v5.4.1, Authentik Embedded Outpost, cert-manager

---

## Threat Model

External traffic enters the cluster via two paths:
- **Cloudflare Tunnel** (`*.devandre.sbs`) — all internet traffic terminates here; WAF managed by Cloudflare
- **NGINX Ingress Controller** (`10.0.0.200`) — handles TLS termination for both public and internal paths

Gaps identified at Gap 12 audit (2026-07-03):
- Prometheus and Alertmanager accessible without authentication
- Polaris dashboard accessible without authentication
- No HSTS header at ingress level
- No rate limiting on public endpoints
- Wrong nginx annotation prefix on ktayl-web and polaris ingresses

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
- `prometheus.ingress.annotations` in `kube-prometheus-stack-values.yaml` (REVISION: 16)
- `alertmanager.ingress.annotations` in `kube-prometheus-stack-values.yaml` (REVISION: 16)
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

**Nginx inheritance note:** `add_header` does not inherit into child location blocks that define their own `add_header`. For location blocks with Authentik (which add `Set-Cookie`), HSTS is present only in the server block context. Browsers cache HSTS once received — subsequent requests to all subdomains enforce HTTPS regardless.

**Verify:**
```bash
/usr/bin/curl -sk -D - https://ktayl.10.0.0.200.nip.io \
  --cacert ~/minicloud-ca.crt | grep -i strict-transport
# Expected: Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Check nginx.conf has HSTS in 19 server blocks:
```bash
kubectl exec -n ingress-nginx \
  $(kubectl get pods -n ingress-nginx -o name | head -1) \
  -- nginx -T 2>/dev/null | grep -c 'Strict-Transport'
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

The `auth_ratelimit` zone is available for application to login pages (e.g., Authentik) when needed — Authentik's built-in brute-force protection is the primary defense for `/application/o/*/authorize/` paths.

**Verify:**
```bash
# Rate limit zones present in running config
kubectl exec -n ingress-nginx \
  $(kubectl get pods -n ingress-nginx -o name | head -1) \
  -- nginx -T 2>/dev/null | grep limit_req_zone
```

---

### 4. Annotation Prefix Fix

F5 NGINX IC uses `nginx.org/` prefix (not `nginx.ingress.kubernetes.io/` which belongs to kubernetes/ingress-nginx). Fixed on:
- `polaris/01-ingress.yaml`: `ssl-redirect`, `proxy-read-timeout`, `proxy-send-timeout`
- `ktayl-solution-web/02-ingress.yaml`: `ssl-redirect`

---

## Accepted Gaps

| Gap | Rationale |
|---|---|
| WAF on nip.io paths | Cloudflare Free plan has no WAF. Internal nip.io traffic is Tailscale-restricted. |
| Harbor `/api/v2.0/systeminfo` public | Harbor design; returns only version info. `anonymous_access` disabled at system level. |
| Harbor proxy-cache projects public | Required for kubelet to pull images without imagePullSecrets. Acceptable for air-gap-adjacent cluster. |

---

## Posture Summary (post Gap 12)

| Control | Status |
|---|---|
| TLS everywhere | ✅ cert-manager + minicloud CA, 17 certs Ready |
| HTTP → HTTPS redirect | ✅ F5 NGINX IC automatic on TLS ingresses |
| HSTS globally | ✅ server-snippets via ConfigMap |
| Rate limiting (public) | ✅ ktayl-web: 20r/s, burst 30 |
| Auth on all dashboards | ✅ Authentik OIDC (Homer, Platform-demo, Prometheus, Alertmanager, Polaris, Grafana, ArgoCD, Backstage, Harbor, Vault, Nextcloud) |
| WAF | ⚠️ Cloudflare Tunnel only (Free plan, no custom WAF rules) |
| IP allowlist for admin | ✅ Internal tools on nip.io only reachable via Tailscale |

