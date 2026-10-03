---
id: itsm-glpi
title: ITSM — GLPI (ITIL v4) · as-built
sidebar_label: 🛠 ITSM (GLPI)
sidebar_position: 10
---

# ITSM — GLPI (ITIL v4)

:::note Status
🟢 **S001 live on dev (2026-10-03).** GLPI is deployed and reachable at
`https://itsm.10.0.0.200.nip.io` (internal/Tailscale). Authentik SSO + the public route land in **S002**
— GLPI is deliberately **not** public until it is SSO-gated. Detailed design (PRD, solution
architecture, NFR register, threat model, ADRs, sprint plan) lives in the **`ktayl-itsm` repo**
(`docs/`); this page is the org-site map.
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
| **URL** | `https://itsm.10.0.0.200.nip.io` (internal only in S001) |
| **Database** | dedicated **MariaDB 11.4** StatefulSet (GLPI requires MySQL/MariaDB — the one deviation from the CNPG/Postgres standard); GLPI auto-installs its schema on first boot |
| **Auth** | GLPI local login in S001 → **Authentik OIDC in S002** (then the public `itsm.devandre.sbs` route) |
| **Secrets** | Vault `secret/platform/ktayl-itsm` (mariadb-root-password, db-password) → ESO |
| **Security** | non-root, `allowPrivilegeEscalation:false`, `drop:[ALL]`, seccomp RuntimeDefault, no SA-token automount; default-deny netpol (GLPI ↔ MariaDB only); Trivy **flags** image CVEs to the GitHub Security tab (SARIF, nothing suppressed) |

## Operate / verify
```bash
# health (internal, Tailscale + minicloud CA):
/usr/bin/curl --cacert ~/minicloud-ca.crt -sI https://itsm.10.0.0.200.nip.io/   # -> 200, "Authentication - GLPI"
ssh controller "kubectl get pods -n itsm"                                       # glpi + glpi-mariadb
ssh controller "kubectl get application ktayl-itsm-dev -n argocd"               # Synced / Healthy
```

## Deploy gotchas (captured — reusable for any apache/php vendor image on this hardened cluster)
- **File-capability binaries fail to exec under `no_new_privs`.** apache2 carries `cap_net_bind_service`;
  with `allowPrivilegeEscalation:false` the kernel refuses to exec it (`EPERM`, exit 126). Fix: `setcap -r`
  the binary in the custom image **and** bind an unprivileged port (**8080**).
- **GLPI data lives at `/var/glpi/{config,files}`**, not `/var/www/glpi/*` — mount the PVCs there (wrong
  paths → config unpersisted → re-install crashloop). First-boot install needs a **startupProbe**.

Full detail + rationale: `ktayl-itsm` repo `docs/` (deployment-architecture, ADRs) and the platform
memory `project_ktayl_itsm_glpi`.

## Roadmap (board #16)
| Story | Status |
|---|---|
| **S001** — Deploy GLPI (wrapper chart + custom image) | ✅ **Done** (dev) |
| **S002** — Authentik OIDC SSO + roles + public route | ⬜ next |
| **S003** — Incident + request + SLA | ⬜ |
| **S004** — Minimal CMDB (BYOD-scoped) + seed | ⬜ |
| **S005** — Alertmanager → auto-ticket | ⬜ |
| **S006** — KPI dashboard (GLPI → Grafana) | ⬜ |
| **S007** — Self-service portal + KB | ⬜ |

## Compliance mapping
ITIL v4 service management · **DORA** (ICT incident management + change governance — the ITSM record is
evidence) · **ACPR / Solvency II** operational-risk + incident logging · GDPR (ticket-PII retention,
handled in S003). Certification: **BC03 (déployer & sécuriser)**.
