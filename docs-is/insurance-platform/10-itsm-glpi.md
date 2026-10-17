---
id: itsm-glpi
title: ITSM — GLPI (ITIL v4) · as-built
sidebar_label: 🛠 ITSM (GLPI)
sidebar_position: 10
---

# ITSM — GLPI (ITIL v4)

:::note Status
🟢 **S001 + S002 live on dev (2026-10-04).** GLPI is deployed, reachable internally at
`https://itsm.10.0.0.200.nip.io` (Tailscale) and publicly at `https://itsm.devandre.sbs` (Cloudflare
tunnel), **gated by native Authentik OIDC** (the `glpi-singlesignon` plugin — not forward-auth).
Detailed design (PRD, solution architecture, NFR register, threat model, ADRs, sprint plan) lives in the
**`ktayl-itsm` repo** (`docs/`); this page is the org-site map.
:::

The ktayl-solution IS runs its **IT service management** on **GLPI** (ITIL v4 — CMDB, incident/request
management, SLAs, helpdesk), board **#16** (IS Foundations). It is the service-management system of
record; it is **not** project management (Plane) or metrics (Prometheus/Grafana). Delivered **via BMAD
(Path B — adopt + integrate)**: the planning set + readiness gate (**PASS**) are in the `ktayl-itsm` repo.

## As-built — what is live (S001)

| Aspect | As deployed |
|---|---|
| **Tool** | GLPI 10.0.28 — a **custom image built from `ktayl-itsm`** (`FROM glpi/glpi` + minicloud CA, apache on 8080, non-root), pushed to Harbor (dev) + ghcr (prod, cosign-signed + SBOM) |
| **Deploy** | **GAP wrapper chart** `minicloud-gitops/services/ktayl-itsm/helm/` + ArgoCD app `apps/workloads/ktayl-itsm-dev.yaml`, namespace **`itsm`**. GLPI + a dedicated **MariaDB** are both **stateful workloads in the chart's `templates/`** (each with its own PVC) — the shared stateless `minicloud-app-deployment` library does not fit a PVC-backed app |
| **URL** | internal `https://itsm.10.0.0.200.nip.io` (Tailscale) **+** public `https://itsm.devandre.sbs` (Cloudflare tunnel) |
| **Database** | dedicated **MariaDB 11.4** StatefulSet (GLPI requires MySQL/MariaDB — the one deviation from the CNPG/Postgres standard); GLPI auto-installs its schema on first boot |
| **Auth** | **native Authentik OIDC** via the `glpi-singlesignon` plugin (baked into the image) — GLPI's own login page offers *Log in with Authentik*; users **auto-provision on first sign-in**, keyed by email |
| **Secrets** | Vault `secret/platform/ktayl-itsm` (mariadb-root-password, db-password, **oidc-client-id, oidc-client-secret**) → ESO / provisioning script |
| **Security** | non-root, `allowPrivilegeEscalation:false`, `drop:[ALL]`, seccomp RuntimeDefault, no SA-token automount; default-deny netpol (GLPI ↔ MariaDB only); Trivy **flags** image CVEs to the GitHub Security tab (SARIF, nothing suppressed) |

## As-built — SSO + public route (S002)

| Aspect | As deployed |
|---|---|
| **SSO model** | GLPI's **native OIDC** (`glpi-singlesignon` v1.4.0, baked into the custom image) → Authentik. **Not** forward-auth: GLPI's own login page is the gate, so the public ingress carries no auth annotations |
| **Authentik** | provider+app **`glpi`** (confidential, `authorization_code`+`refresh_token`), scopes `openid email profile` (+ `groups`); redirect is a **REGEX** `…/callback.php.*` (the plugin appends a `/provider/<id>` path segment) |
| **Provisioning** | the provider row (endpoints + client creds) is upserted by the reusable `minicloud-ops/scripts/glpi/configure-sso-provider.sh` (creds read from Vault, never echoed) — GLPI stores SSO providers in its **DB**, not config |
| **User mapping** | `use_email_for_login=1` → GLPI account keyed off the OIDC **email**; first sign-in **auto-provisions** the user. The owner is pre-provisioned **Super-Admin** |
| **Public route** | `itsm.devandre.sbs` via the k8s Cloudflare tunnel (`manifests/cloudflare-tunnel/02-configmap.yaml`, `originServerName: itsm.10.0.0.200.nip.io`) + ingress rule/TLS SAN for both hosts |
| **Back-channel trust** | GLPI→Authentik token/userinfo over split-horizon DNS (`auth.devandre.sbs`→internal ingress), trusted via the S001 **runtime CA-trust initContainer** (minicloud CA appended to the bundle) |

:::note group → GLPI profile
The `glpi-singlesignon` v1.4.0 plugin **does not map the OIDC `groups` claim to GLPI profiles** — it
auto-provisions every new user with GLPI's **default** profile. Profile elevation / role mapping is done
in GLPI itself (manual profile assignment, or GLPI *authorization rules* by email domain), **not** from
the claim. Claim-driven group→profile is a later story (plugin v2.x / a rules layer). The owner's account
is pre-provisioned Super-Admin so the ITSM is administrable over SSO from first login.
:::

## Operate / verify
```bash
# internal health (Tailscale + minicloud CA):
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://itsm.10.0.0.200.nip.io/   # -> 200, "Authentication - GLPI"
# public edge (Cloudflare) + SSO redirect chain:
/usr/bin/curl -sI https://itsm.devandre.sbs/                                    # -> 200 (valid public TLS)
#   the GLPI login page carries a "Log in with Authentik" link →
#   /plugins/singlesignon/front/callback.php/provider/1 302s to auth.devandre.sbs/application/o/authorize/
#   → Authentik renders "Log in to continue to GLPI ITSM"
ssh controller "kubectl get pods -n itsm"                                       # glpi + glpi-mariadb
ssh controller "kubectl get application ktayl-itsm-dev -n argocd"               # Synced / Healthy
# (re)provision the SSO provider row idempotently:
ssh controller "cd ~/minicloud-ops && bash scripts/glpi/configure-sso-provider.sh itsm Authentik https://auth.devandre.sbs platform/ktayl-itsm"
```

## Deploy gotchas (captured — reusable for any apache/php vendor image on this hardened cluster)
- **File-capability binaries fail to exec under `no_new_privs`.** apache2 carries `cap_net_bind_service`;
  with `allowPrivilegeEscalation:false` the kernel refuses to exec it (`EPERM`, exit 126). Fix: `setcap -r`
  the binary in the custom image **and** bind an unprivileged port (**8080**).
- **GLPI data lives at `/var/glpi/{config,files}`**, not `/var/www/glpi/*` — mount the PVCs there (wrong
  paths → config unpersisted → re-install crashloop). First-boot install needs a **startupProbe**.
- **SSO (S002):** the `glpi-singlesignon` **v1.4.0** release asset is `glpi-singlesignon-v1.4.0.tar.bz2`
  (bzip2; the short `singlesignon.tgz` name is v2.x-only, which needs GLPI 11) and extracts to
  `glpi-singlesignon/` — **rename to `singlesignon/`** (GLPI only discovers a plugin whose dir = its key).
- **`grant_types` defaults to `[]` on a new Authentik 2026.x provider** → the authorize view rejects the
  browser flow (*"Invalid grant_type for provider"*). A web OIDC app needs `authorization_code`
  (+`refresh_token`); the shared `oidc-provider.py` now sets it (it previously left bookstack/glpi/plane
  login-broken — all three backfilled).
- **GLPI's `url_base` defaults to `http://localhost/glpi`** and the plugin builds `redirect_uri` from it
  → set `url_base` to the public host (`https://itsm.devandre.sbs`) or OIDC redirects point at localhost.
- **The plugin appends `/provider/<id>`** to the callback → the Authentik redirect must be **REGEX**
  (`…/callback.php.*`), not STRICT, or Authentik returns *invalid_request*.

Full detail + rationale: `ktayl-itsm` repo `docs/` (deployment-architecture, ADRs) and the platform
memory `project_ktayl_itsm_glpi`.

## Roadmap (board #16)
| Story | Status |
|---|---|
| **S001** — Deploy GLPI (wrapper chart + custom image) | ✅ **Done** (dev) |
| **S002** — Authentik OIDC SSO + public route | ✅ **Done** (dev) — native OIDC, auto-provision, public route; claim→profile deferred |
| **S003** — Incident + request + SLA | ⬜ |
| **S004** — Minimal CMDB (BYOD-scoped) + seed | ⬜ |
| **S005** — Alertmanager → auto-ticket | ⬜ |
| **S006** — KPI dashboard (GLPI → Grafana) | ⬜ |
| **S007** — Self-service portal + KB | ⬜ |

## Compliance mapping
ITIL v4 service management · **DORA** (ICT incident management + change governance — the ITSM record is
evidence) · **ACPR / Solvency II** operational-risk + incident logging · GDPR (ticket-PII retention,
handled in S003). Certification: **BC03 (déployer & sécuriser)**.
