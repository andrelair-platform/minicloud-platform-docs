---
id: third-party-app-integration
title: Third-Party Application Integration
sidebar_label: Third-Party App Integration
---

# Third-Party Application Integration

Most of the applications running on this platform are **third-party software** — I did not write
ERPNext, Authentik, or Vault. But deploying, integrating, configuring, hardening and operating them
into a coherent, governed information system is real engineering work, and it is version-controlled and
auditable. This page is the **engineer's view** of that fleet: for each app, *what I actually did* and
*where the evidence lives*.

:::note This is an integration view, not a business catalog
For what each application *does for the business* (functional domains, the IARD insurer model, coverage
and build order), see the **[Business Applications Catalog](../insurance-platform/business-applications-catalog)**
and the **[EA Blueprint](../insurance-platform/enterprise-architecture-blueprint)**. This page instead
answers *"what engineering did the operator do to each off-the-shelf app?"*
:::

## How to read the "What I did" column — verbs, not ownership

I never claim to have *built* a third-party app. The honest, and still substantial, verbs are:

| Verb | Meaning |
|---|---|
| **Deployed** | Packaged as a GitOps-delivered Helm release (ArgoCD app + version-pinned `helm-values`), dev/prod overlays |
| **SSO** | Integrated with Authentik as the identity provider (OIDC or forward-auth) + MFA |
| **Secrets** | Secrets sourced from Vault via External Secrets Operator (ESO) — no plaintext in Git |
| **TLS** | Certificates issued by cert-manager (internal CA / Let's Encrypt); ingress + NetworkPolicy |
| **Configured** | Tuned to a real domain (e.g. ERPNext → French PCG 2025 / TSCA / Factur-X) |
| **Custom code** | I wrote code *around* the app — a custom image or an integration service (**own repo**) |
| **Backup/DR** | Velero + object-storage backups, restore-tested |
| **Hardened** | Gatekeeper policies, PSA, egress default-deny, image scanning |

The uniform pattern applied to (almost) every app on the fleet: **GitOps-delivered Helm ·
Authentik SSO + MFA · ESO/Vault secrets · cert-manager TLS · default-deny NetworkPolicies · Velero
backup**. That repeatable "off-the-shelf chart → governed, SSO'd, backed-up service" pipeline *is* the
capability this page evidences.

---

## Digital workplace (the M365 / Google-Workspace alternative)

| App | What I did | Custom code? | Evidence |
|---|---|---|---|
| **Stalwart Mail** | Deployed; configured SMTP/IMAP/JMAP; wired **Amazon SES** outbound relay + the inbound SES→S3→SQS pipeline; Alertmanager STARTTLS integration | — | `helm-values/…/…`, `apps/workloads/stalwart.yaml`; docs: *Collaboration / Mail* |
| **Matrix Synapse + Element** | Deployed; **Authentik OIDC** SSO; dedicated `postgresql-synapse`; federation config | — | `apps/workloads/matrix-synapse.yaml`, `helm-values/…/synapse-values.yaml` |
| **Jitsi Meet** | Deployed; JVB on `hostNetwork` (pinned node) for WebRTC; **Authentik forward-auth** | — | `apps/workloads/jitsi.yaml`, `helm-values/…/jitsi-values.yaml` |
| **Nextcloud + OnlyOffice** | Deployed; **Authentik OIDC** (`user_oidc` auto-provision); document editing | ✅ **OnlyOffice** ([`minicloud-onlyoffice`](https://github.com/andrelair-platform/minicloud-onlyoffice) — CA cert + `NODE_EXTRA_CA_CERTS`) | `apps/workloads/nextcloud.yaml` |
| **Docuseal** | Deployed; e-signature (eIDAS Simple); insurance templates | — | `apps/workloads/docuseal.yaml` |

## Business applications

| App | What I did | Custom code? | Evidence |
|---|---|---|---|
| **ERPNext / Frappe** | Deployed; **configured for a French insurer** — 845-account PCG 2025 chart, TSCA tax templates, Factur-X Minimum PoC; HR as source of truth | ✅ **[`minicloud-erpnext`](https://github.com/andrelair-platform/minicloud-erpnext)** — custom **DSN + SEPA payroll** apps (`erpnext_dsn`, `erpnext_sepa`), 108 unit tests / ~76% coverage | `apps/workloads/erpnext.yaml`, `helm-values/…/erpnext-values.yaml` |
| **Plane CE** | Deployed; project management for non-technical stakeholders | ✅ **[`minicloud-plane`](https://github.com/andrelair-platform/minicloud-plane)** — Go API + webhook→NATS bridge + Backstage plugin | `apps/workloads/plane.yaml` |
| **n8n** | Deployed; workflow automation (5Gi RWO) | — | `apps/workloads/n8n.yaml` |
| **Temporal** | Deployed; durable workflow engine; PostgreSQL backend; **Authentik OIDC** | — | `apps/workloads/temporal.yaml` |

:::warning Honesty: installed ≠ operational
Following the platform's *"installed ≠ operational"* rule (see **[HR Tooling](../insurance-platform/hr-tooling)**),
ERPNext HR is claimed precisely: the **payroll** modules (custom DSN/SEPA) are genuinely built + tested;
Appraisal / Leave / Attendance / Job-Opening are **installed but empty**. Deploying an app is not the same
as operating a populated business process, and this catalog says which is which.
:::

## AI platform (third-party components)

| App | What I did | Custom code? | Evidence |
|---|---|---|---|
| **LiteLLM** | Deployed as the **AI gateway**; configured multi-provider routing, virtual keys, department budgets, Presidio PII/DLP pre-call hook, Prometheus cost metrics | — | `apps/workloads/litellm.yaml`, `litellm-manifests.yaml` |
| **Open WebUI** | Deployed; **Authentik OIDC**; RAG chat | ✅ **[`minicloud-open-webui`](https://github.com/andrelair-platform/minicloud-open-webui)** — CA cert + **French BM25** preprocessor | `apps/workloads/open-webui.yaml` |
| **Langfuse** | Deployed; **Authentik OIDC**; ClickHouse + Valkey analytics backend; traces every LLM call | — | `apps/workloads/langfuse.yaml`, `helm-values/…/langfuse-values.yaml` |
| **Flowise / MLflow / Qdrant** | Deployed; visual LLM flows / experiment tracking / vector store for RAG | — | `ai` namespace manifests |

## Platform & IS foundations (third-party)

| App | What I did | Custom code? | Evidence |
|---|---|---|---|
| **Authentik** | Deployed; **it is the SSO/identity hub** — configured OIDC + forward-auth providers for every other app, department RBAC, MFA enforced | — | `apps/platform/authentik.yaml`, `helm-values/…/authentik-values.yaml` |
| **HashiCorp Vault** | Deployed; **AWS KMS auto-unseal**; PKI; Raft; the ESO backend for all platform secrets | — | `apps/platform/vault.yaml`, `helm-values/…/vault-values.yaml` |
| **Harbor** | Deployed; proxy-cache mirrors (docker/ghcr/quay/k8s) + tag-retention + scheduled GC; Trivy scanning | — | `apps/platform/harbor.yaml`, `helm-values/…/harbor-values.yaml` |
| **Grafana + Prometheus** | Deployed (kube-prometheus-stack); **Authentik OIDC**; custom dashboards (LiteLLM cost, cert expiry, backup DR) | — | `apps/platform/kube-prometheus-stack.yaml` |
| **Loki · Tempo · OTel** | Deployed; logs/traces pipeline; OTTL transforms; Alertmanager routing | — | `apps/platform/{loki,tempo,otelcol}.yaml` |
| **Backstage** | Deployed; developer portal | ✅ **[`minicloud-backstage`](https://github.com/andrelair-platform/minicloud-backstage)** — custom image, K8s/ArgoCD/TechDocs/Grafana plugins, Software Templates | `apps/workloads/backstage.yaml` |
| **Vaultwarden** | Deployed (Timshel fork for the SSO button); **Authentik SSO**; human credential store | — | `apps/workloads/vaultwarden.yaml` |
| **ArgoCD · cert-manager · ESO · Cilium · Gatekeeper · Falco · KEDA · NATS · Velero · Kargo** | Deployed + configured the GitOps, security, networking, autoscaling, messaging and backup control plane the whole fleet depends on | — | `apps/platform/*.yaml` |

---

## The takeaway

Roughly **95 ArgoCD applications** run on this platform; most are third-party charts. What makes the
fleet a portfolio artifact isn't the software — it's that **every app was taken from an off-the-shelf
chart to a GitOps-delivered, SSO-gated, secrets-managed, TLS-terminated, network-isolated, backed-up
service**, and a handful were **extended with real custom code** in their own repos
([`minicloud-erpnext`](https://github.com/andrelair-platform/minicloud-erpnext),
[`minicloud-open-webui`](https://github.com/andrelair-platform/minicloud-open-webui),
[`minicloud-onlyoffice`](https://github.com/andrelair-platform/minicloud-onlyoffice),
[`minicloud-backstage`](https://github.com/andrelair-platform/minicloud-backstage),
[`minicloud-plane`](https://github.com/andrelair-platform/minicloud-plane)). The version-controlled
proof of the deployment + integration work lives in
**[`minicloud-gitops`](https://github.com/andrelair-platform/minicloud-gitops)** (`apps/`, `helm-values/`,
`services/`).
