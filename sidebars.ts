import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  tutorialSidebar: [

    // ── Entry point ─────────────────────────────────────────────────
    {type: 'doc', id: 'intro', label: '🗺 Overview & Roadmap'},

    // ── Phase 0 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 0 — MAAS Infra ✅',
      collapsed: false,
      items: [
        'phase-0-maas/objective',
        'phase-0-maas/architecture',
        'phase-0-maas/core-concepts',
        'phase-0-maas/hardware',
        'phase-0-maas/network',
        'phase-0-maas/maas-setup',
        'phase-0-maas/provisioning',
        'phase-0-maas/cloud-init',
        'phase-0-maas/validation',
        'phase-0-maas/troubleshooting',
        'phase-0-maas/add-node',
      ],
    },

    // ── Phase 1 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 1 — Kubernetes (k3s)',
      collapsed: true,
      items: ['platform-roadmap/phase-1-kubernetes'],
    },

    // ── Phase 2 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 2 — kubectl Local Access',
      collapsed: true,
      items: ['platform-roadmap/phase-2-access'],
    },

    // ── Phase 3 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 3 — Remote Access',
      collapsed: true,
      items: [
        'remote-access/remote-access-overview',
        'remote-access/tailscale',
        'remote-access/cloudflare-tunnel',
        'remote-access/homer-dashboard',
      ],
    },

    // ── Phase 4 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 4 — MetalLB (Load Balancer)',
      collapsed: true,
      items: ['networking/metallb'],
    },

    // ── Phase 5 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 5 — Storage',
      collapsed: true,
      items: [
        'storage/longhorn',
        'storage/nfs',
        'storage/minio',
      ],
    },

    // ── Phase 6 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 6 — Ingress Controller',
      collapsed: true,
      items: ['platform-roadmap/phase-6-ingress'],
    },

    // ── Phase 7 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 7 — Harbor (Registry)',
      collapsed: true,
      items: [
        'registry/harbor',
        'registry/harbor-proxy-cache',
      ],
    },

    // ── Phase 8 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 8 — Monitoring',
      collapsed: true,
      items: ['platform-roadmap/phase-8-monitoring'],
    },

    // ── Phase 9 ─────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 9 — First Workload',
      collapsed: true,
      items: [
        'platform-roadmap/phase-9-workload',
        'platform-roadmap/phase-8-containers',
      ],
    },

    // ── Phase 10 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 10 — Ansible',
      collapsed: true,
      items: ['ansible/ansible'],
    },

    // ── Phase 11 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 11 — IaC (Terraform / Crossplane)',
      collapsed: true,
      items: [
        'iac/terraform',
        'iac/crossplane',
      ],
    },

    // ── Phase 12 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 12 — GitOps (ArgoCD)',
      collapsed: true,
      items: ['platform-roadmap/phase-12-gitops'],
    },

    // ── Phase 13 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 13 — CI/CD',
      collapsed: true,
      items: ['platform-roadmap/phase-13-cicd'],
    },

    // ── App Deployment Guide ─────────────────────────────────────────
    {
      type: 'category',
      label: '📦 App Deployment Guide',
      collapsed: true,
      items: [
        'app-deployment/deploy-overview',
        'app-deployment/helm-chart',
        'app-deployment/deploy-helm',
        'app-deployment/deploy-argocd',
        'app-deployment/deploy-yaml',
        'app-deployment/cicd-pipeline',
      ],
    },

    // ── Data Layer ──────────────────────────────────────────────────
    {
      type: 'category',
      label: '🗄 Data Layer (Kafka → ClickHouse → dbt → BI)',
      collapsed: true,
      items: [
        'data-layer/data-layer-overview',
        'data-layer/kafka-redpanda',
        'data-layer/clickhouse',
        'data-layer/dbt',
        'data-layer/openmetadata',
      ],
    },

    // ── Security Layer ───────────────────────────────────────────────
    {
      type: 'category',
      label: '🔒 Security Layer (Authentik → OPA → Falco → Cosign)',
      collapsed: true,
      items: [
        'security-enterprise/security-overview',
        'security-enterprise/host-hardening',
        'security-enterprise/opa-gatekeeper',
        'security-enterprise/falco',
        'security-enterprise/cosign-sbom',
        'security-enterprise/compliance',
        'security-enterprise/ghas',
      ],
    },

    // ── Phase 14 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 14 — Backup & DR ✅',
      collapsed: true,
      items: [
        'backup-dr/velero',
        'backup-dr/longhorn-backup',
        'backup-dr/etcd-backup',
        'backup-dr/disk-management',
        'backup-dr/database-backup',
        'backup-dr/dr-runbook',
      ],
    },

    // ── Phase 15 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 15 — Security ✅',
      collapsed: true,
      items: [
        'platform-roadmap/phase-15-cert-manager',
        'security-enterprise/ingress-edge-security',
      ],
    },

    // ── Phase 16 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 16 — Harbor as Sovereign Registry ✅',
      collapsed: true,
      items: ['registry/harbor-proxy-cache'],
    },

    // ── Phase 83 — n8n ──────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 83 — n8n Workflow Automation ✅',
      collapsed: true,
      items: [
        'automation/n8n',
      ],
    },

    // ── Deferred: Automation & Workflows ────────────────────────────
    {
      type: 'category',
      label: '🔜 Deferred — Automation (Temporal / Airflow)',
      collapsed: true,
      items: [
        'automation/temporal',
        'automation/airflow',
      ],
    },

    // ── Phase 17 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 17 — Event-Driven (KEDA + NATS)',
      collapsed: true,
      items: [
        'event-driven/keda',
        'event-driven/nats',
      ],
    },

    // ── Phase 18 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 18 — Developer Platform',
      collapsed: true,
      items: ['developer-platform/backstage'],
    },

    // ── Phase 19 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 19 — AI / ML Platform',
      collapsed: true,
      items: [
        'ai-ml/ollama',
        'ai-ml/model-distribution',
        'ai-ml/mlflow',
        'ai-ml/kubeflow',
        'ai-ml/ai-security-overview',
        'ai-ml/hallucination-controls',
        'ai-ml/bias-detection',
        'ai-ml/prompt-injection',
        'ai-ml/data-poisoning',
        'ai-ml/model-inversion',
        'ai-ml/membership-inference',
        'ai-ml/sampling-configuration',
        'ai-ml/ai-gateway',
        'ai-ml/inference-optimization',
        'ai-ml/rag-pipeline',
        'ai-ml/rag-internals',
        'ai-ml/langfuse',
        'ai-ml/phi3-financial',
        'ai-ml/phi3-financial-eval-cicd',
        'ai-ml/domain-specialization-framework',
        'ai-ml/rag-eval-pipeline',
      ],
    },

    // ── Phase 20 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 20 — Reliability (Chaos Mesh)',
      collapsed: true,
      items: ['reliability/chaos-mesh', 'reliability/phase81-chaos-game-day'],
    },

    // ── Phase 21 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 21 — Advanced Observability ✅',
      collapsed: true,
      items: [
        'observability/loki',
        'observability/alertmanager',
        'observability/jaeger',
        'observability/falco-sidekick-polaris',
        'observability/k8s-monitoring-gaps',
        'observability/loki-ruler-logql-alerting',
        'observability/grafana-log-dashboards-controller-logs',
      ],
    },

    // ── Phase 22 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 22 — Cilium (eBPF Networking)',
      collapsed: true,
      items: ['networking/cilium'],
    },

    // ── Phase 85 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 85 — CoreDNS HA (2 replicas) ✅',
      collapsed: true,
      items: ['networking/coredns-ha'],
    },

    // ── Phase 23 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 23 — SSO via Authentik ✅',
      collapsed: true,
      items: ['security-enterprise/sso-authentik'],
    },

    // ── Phase 24 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 24 — Backstage Custom Image',
      collapsed: true,
      items: ['developer-platform/backstage-plugins'],
    },

    // ── Phase 25 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 25 — Public Access & SSO Migration ✅',
      collapsed: true,
      items: ['security-enterprise/phase25-public-access'],
    },

    // ── Phase 26 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 26 — Vault (Secrets Management) ✅',
      collapsed: true,
      items: ['developer-platform/vault'],
    },

    // ── Phase 27 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 27 — OPA/Gatekeeper (Policy as Code) ✅',
      collapsed: true,
      items: ['security-enterprise/opa-gatekeeper'],
    },

    // ── Phase 28 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 28 — Falco (Runtime Threat Detection) ✅',
      collapsed: true,
      items: ['security-enterprise/falco'],
    },

    // ── Phase 29 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 29 — kube-bench (CIS Benchmark) ✅',
      collapsed: true,
      items: ['security-enterprise/kube-bench'],
    },

    // ── Phase 30 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 30 — Cosign + SBOM (Supply Chain Security) ✅',
      collapsed: true,
      items: ['security-enterprise/cosign-sbom'],
    },

    // ── Phase 56 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 56 — Multi-Environment Namespaces ✅',
      collapsed: true,
      items: ['developer-platform/multi-env-namespaces'],
    },

    // ── Phase 57 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 57 — Nextcloud + Authentik SSO ✅',
      collapsed: true,
      items: ['developer-platform/nextcloud'],
    },

    // ── Phase 58 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 58 — Vault GitOps Migration ✅',
      collapsed: true,
      items: ['developer-platform/vault-gitops'],
    },

    // ── GitOps Workflow ─────────────────────────────────────────────
    {
      type: 'category',
      label: '🔁 GitOps Workflow — Service Onboarding & Promotion',
      collapsed: true,
      items: ['developer-platform/gitops-workflow'],
    },

    // ── Phase 60 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 60 — Cert Observability ✅',
      collapsed: true,
      items: ['developer-platform/cert-observability'],
    },

    // ── Phase 65 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 65 — Vault Auto-Unseal (AWS KMS) ✅',
      collapsed: true,
      items: ['developer-platform/vault-kms-unseal'],
    },

    // ── Phase 59 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 59 — External Secrets Operator + Vault KV ✅',
      collapsed: true,
      items: ['developer-platform/eso-vault'],
    },

    // ── Phase 62 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 62 — IAM Hardening (OIDC + RBAC + MFA) ✅',
      collapsed: true,
      items: ['security-enterprise/iam-hardening'],
    },

    // ── Phase 63 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 63 — Cluster Hardening ✅',
      collapsed: true,
      items: ['security-enterprise/cluster-hardening'],
    },

    // ── Phase 64 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 64 — Namespace Isolation ✅',
      collapsed: true,
      items: ['security-enterprise/namespace-isolation'],
    },

    // ── Phase 67 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 67 — Pod Security Hardening ✅',
      collapsed: true,
      items: ['security-enterprise/pod-security'],
    },

    // ── Phase 68 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 68 — Plane CE (Project Tracker) ✅',
      collapsed: true,
      items: ['developer-platform/plane-ce'],
    },

    // ── Phase 69 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 69 — minicloud-plane (Level 4 Integration + Backstage) ✅',
      collapsed: true,
      items: ['developer-platform/minicloud-plane'],
    },

    // ── Phase 70 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 70 — Backstage Software Templates (Golden Path) ✅',
      collapsed: true,
      items: ['developer-platform/backstage-software-templates'],
    },

    // ── Phase 71 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 71 — TechDocs ✅',
      collapsed: true,
      items: ['developer-platform/techdocs'],
    },

    // ── Phase 73 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 73 — Argo Rollouts (Canary Deployments) ✅',
      collapsed: true,
      items: ['developer-platform/argo-rollouts'],
    },

    // ── CI/CD Gap Analysis ───────────────────────────────────────────
    {
      type: 'category',
      label: '🧪 CI/CD Gap Analysis — Unit Tests, Security Scans, Progressive Delivery ✅',
      collapsed: true,
      items: ['developer-platform/cicd-gap-analysis'],
    },

    // ── Automated Regression Detection ───────────────────────────────
    {
      type: 'category',
      label: '🔁 Automated Regression Detection ✅',
      collapsed: true,
      items: ['developer-platform/automated-regression-detection'],
    },

    // ── Phase 74 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 74 — VPA Auto Mode ✅',
      collapsed: true,
      items: ['developer-platform/vpa-auto'],
    },

    // ── Phase 80 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 80 — Amazon SES (Outbound Email Relay) ✅',
      collapsed: true,
      items: ['developer-platform/amazon-ses'],
    },

    // ── Phase 79 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 79 — ERPNext HR (Employee Onboarding Automation) ✅',
      collapsed: true,
      items: ['developer-platform/erpnext-hr'],
    },

    // ── Phase 76 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 76 — AI Governance & Operations Dashboard ✅',
      collapsed: true,
      items: ['observability/ai-governance-dashboard'],
    },

    // ── Application Monitoring ───────────────────────────────────────
    {
      type: 'category',
      label: '📊 Application Monitoring — RED Metrics & Canary Analysis ✅',
      collapsed: true,
      items: ['observability/application-monitoring'],
    },

    // ── OTel Log Pipeline ────────────────────────────────────────────
    {
      type: 'category',
      label: '📡 OTel Collector Log Pipeline — Stack-Agnostic Shipping ✅',
      collapsed: true,
      items: ['observability/otelcol-log-pipeline'],
    },

    // ── Alerting Gap Analysis ────────────────────────────────────────
    {
      type: 'category',
      label: '🔔 Alerting Gap Analysis — 9 Gaps Closed ✅',
      collapsed: true,
      items: ['observability/alerting-gaps'],
    },

    // ── Distributed Tracing Gaps ─────────────────────────────────────
    {
      type: 'category',
      label: '🔍 Distributed Tracing — Gaps A–E Closed ✅',
      collapsed: true,
      items: ['observability/distributed-tracing-gaps'],
    },

    // ── OTel Log Pipeline Gaps ───────────────────────────────────────
    {
      type: 'category',
      label: '📋 OTel Log Pipeline — 7 Gaps Closed ✅',
      collapsed: true,
      items: ['observability/otelcol-log-pipeline-gaps'],
    },

    // ── Application Monitoring Gaps ──────────────────────────────────
    {
      type: 'category',
      label: '📊 Application Monitoring — Gap Analysis & Fixes ✅',
      collapsed: true,
      items: ['observability/application-monitoring-gaps'],
    },

    // ── Regression Detection Gaps ─────────────────────────────────────
    {
      type: 'category',
      label: '📉 Regression Detection — Before/After Deployment ✅',
      collapsed: true,
      items: ['observability/regression-detection-gaps'],
    },

    // ── Capacity Planning Gaps ────────────────────────────────────────
    {
      type: 'category',
      label: '📈 Capacity Planning — Forecasting & Right-Sizing ✅',
      collapsed: true,
      items: ['observability/capacity-planning-gaps'],
    },

    // ── Cost Optimization Gaps ────────────────────────────────────────
    {
      type: 'category',
      label: '💰 Cost Optimization — Waste & Right-Sizing ✅',
      collapsed: true,
      items: ['observability/cost-optimization-gaps'],
    },

    // ── SLO Dashboard ─────────────────────────────────────────────────
    {
      type: 'category',
      label: '🎯 SLO Dashboard — 7 Service-Level Objectives ✅',
      collapsed: true,
      items: ['observability/slo-dashboard'],
    },

    // ── Admission Control Hardening ─────────────────────────────────
    {
      type: 'category',
      label: '🔒 Admission Control Hardening — 8/8 Policies ✅',
      collapsed: true,
      items: ['security-enterprise/admission-control'],
    },

    // ── Full Helm→ArgoCD Migration ───────────────────────────────────
    {
      type: 'category',
      label: '🚀 Full Helm→ArgoCD Migration — 54/54 Apps ✅',
      collapsed: true,
      items: ['developer-platform/helm-argocd-migration'],
    },

    // ── KEDA Cron Scale-to-Zero ──────────────────────────────────────
    {
      type: 'category',
      label: '⏱ KEDA Cron Scale-to-Zero — Dev Environments ✅',
      collapsed: true,
      items: ['developer-platform/keda-cron-scale-to-zero'],
    },

    // ── GitOps Directory Patterns ────────────────────────────────────
    {
      type: 'category',
      label: '📁 GitOps Directory Patterns — Design Decisions',
      collapsed: true,
      items: ['developer-platform/gitops-directory-patterns'],
    },

    // ── Helm vs Kustomize ────────────────────────────────────────────
    {
      type: 'category',
      label: '⚖️ Helm vs Kustomize — When to Use Which',
      collapsed: true,
      items: ['developer-platform/helm-vs-kustomize'],
    },

    // ── Backstage + Helm/Kustomize ───────────────────────────────────
    {
      type: 'category',
      label: '🎭 Backstage — Helm vs Kustomize Integration',
      collapsed: true,
      items: ['developer-platform/backstage-helm-kustomize'],
    },

    // ── Custom Images ────────────────────────────────────────────────
    {
      type: 'category',
      label: '🔧 Custom-Built Images — Inventory & Upgrade Guide',
      collapsed: true,
      items: ['developer-platform/custom-images'],
    },

    // ── Branch Strategy & CI/CD ──────────────────────────────────────
    {
      type: 'category',
      label: '🌿 Branch Strategy & CI/CD Flow — dev → staging → main',
      collapsed: true,
      items: ['developer-platform/branch-strategy-cicd'],
    },

    // ── CI Registry Migration ─────────────────────────────────────────
    {
      type: 'category',
      label: '🚢 CI Registry Migration — Tailscale + Harbor Direct',
      collapsed: true,
      items: ['developer-platform/ci-registry-migration'],
    },

    // ── Dependency Auditability ───────────────────────────────────────
    {
      type: 'category',
      label: '🔍 Dependency Auditability — Version Pinning & Renovate',
      collapsed: true,
      items: ['developer-platform/dependency-auditability'],
    },

    // ── RBAC Audit ────────────────────────────────────────────────────
    {
      type: 'category',
      label: '🔑 RBAC Audit — SA vs Human Identity Separation',
      collapsed: true,
      items: ['security-enterprise/rbac-audit'],
    },

    // ── kubectl OIDC Access ───────────────────────────────────────────
    {
      type: 'category',
      label: '🔑 kubectl OIDC Access — Setup & 4-Root-Cause Debug ✅',
      collapsed: true,
      items: ['security-enterprise/kubectl-oidc-access'],
    },

    // ── Phase 76 — Matrix Synapse + Element Web ───────────────────────
    {
      type: 'category',
      label: '💬 Phase 76 — Matrix Synapse + Element Web (Team Chat)',
      collapsed: true,
      items: ['developer-platform/matrix-synapse-element-web'],
    },

    // ── Phase 77 — Jitsi Meet ────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 77 — Jitsi Meet + Coturn TURN Server ✅',
      collapsed: true,
      items: ['developer-platform/jitsi-meet'],
    },

    // ── Phase 78 — Stalwart Mail ─────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 78 — Stalwart Mail Server (devandre.sbs) ✅',
      collapsed: true,
      items: ['developer-platform/stalwart-mail'],
    },

    // ── Phase 86 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 86 — Per-App-Per-Env Namespace Isolation ✅',
      collapsed: true,
      items: ['app-deployment/per-env-isolation'],
    },

    // ── Production Stack Architecture ────────────────────────────────
    {
      type: 'category',
      label: '🗺 Production Stack Architecture — Complete Diagram ✅',
      collapsed: true,
      items: ['developer-platform/production-stack-architecture'],
    },
  ],
};

export default sidebars;
