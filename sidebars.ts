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
        'data-layer/superset',
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
      ],
    },

    // ── Phase 14 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 14 — Backup & DR',
      collapsed: true,
      items: [
        'backup-dr/velero',
        'backup-dr/etcd-backup',
      ],
    },

    // ── Phase 15 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 15 — Security',
      collapsed: true,
      items: [
        'developer-platform/vault',
        'platform-roadmap/phase-15-cert-manager',
      ],
    },

    // ── Phase 16 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 16 — Harbor as Sovereign Registry ✅',
      collapsed: true,
      items: ['registry/harbor-proxy-cache'],
    },

    // ── Deferred: Automation & Workflows ────────────────────────────
    {
      type: 'category',
      label: '🔜 Deferred — Automation & Workflows (n8n / Temporal / Airflow)',
      collapsed: true,
      items: [
        'automation/n8n',
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
        'ai-ml/mlflow',
        'ai-ml/kubeflow',
        'ai-ml/hallucination-controls',
      ],
    },

    // ── Phase 20 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 20 — Reliability (Chaos Mesh)',
      collapsed: true,
      items: ['reliability/chaos-mesh'],
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
      ],
    },

    // ── Phase 22 ────────────────────────────────────────────────────
    {
      type: 'category',
      label: 'Phase 22 — Cilium (eBPF Networking)',
      collapsed: true,
      items: ['networking/cilium'],
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
  ],
};

export default sidebars;
