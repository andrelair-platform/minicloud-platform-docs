import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  tutorialSidebar: [

    // ── Platform Overview ────────────────────────────────────────────
    {type: 'doc', id: 'intro', label: '🗺 Platform Overview'},
    {type: 'doc', id: 'developer-platform/production-stack-architecture', label: '🏛 Production Stack Architecture'},

    // ── Infrastructure ───────────────────────────────────────────────
    {
      type: 'category',
      label: '🏗 Infrastructure',
      collapsed: false,
      items: [
        {
          type: 'category',
          label: 'MAAS & Bare-Metal Provisioning',
          collapsed: true,
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
            'phase-0-maas/power-broker',
          ],
        },
        {
          type: 'category',
          label: 'Kubernetes (k3s)',
          collapsed: true,
          items: [
            'platform-roadmap/phase-1-kubernetes',
            'platform-roadmap/phase-2-access',
          ],
        },
        {
          type: 'category',
          label: 'Remote Access',
          collapsed: true,
          items: [
            'remote-access/remote-access-overview',
            'remote-access/tailscale',
            'remote-access/cloudflare-tunnel',
            'remote-access/homer-dashboard',
          ],
        },
        {
          type: 'category',
          label: 'Networking',
          collapsed: true,
          items: [
            'networking/metallb',
            'networking/cilium',
            'networking/coredns-ha',
            'platform-roadmap/phase-6-ingress',
          ],
        },
        {
          type: 'category',
          label: 'Storage',
          collapsed: true,
          items: [
            'storage/longhorn',
            'storage/nfs',
            'storage/minio',
          ],
        },
        {
          type: 'category',
          label: 'Container Registry (Harbor)',
          collapsed: true,
          items: [
            'registry/harbor',
            'registry/harbor-proxy-cache',
          ],
        },
        {
          type: 'category',
          label: 'IaC & Configuration Management',
          collapsed: true,
          items: [
            'ansible/ansible',
            'iac/terraform',
            'iac/crossplane',
          ],
        },
      ],
    },

    // ── Security & Identity ──────────────────────────────────────────
    {
      type: 'category',
      label: '🔐 Security & Identity',
      collapsed: true,
      items: [
        {
          type: 'category',
          label: 'SSO & Access Control',
          collapsed: true,
          items: [
            'security-enterprise/sso-authentik',
            'security-enterprise/phase25-public-access',
            'security-enterprise/kubectl-oidc-access',
            'security-enterprise/iam-hardening',
            'security-enterprise/rbac-audit',
          ],
        },
        {
          type: 'category',
          label: 'Secrets Management',
          collapsed: true,
          items: [
            'developer-platform/vault',
            'developer-platform/vault-gitops',
            'developer-platform/vault-kms-unseal',
            'developer-platform/eso-vault',
            'developer-platform/cert-observability',
          ],
        },
        {
          type: 'category',
          label: 'Policy, Runtime & Admission',
          collapsed: true,
          items: [
            'security-enterprise/opa-gatekeeper',
            'security-enterprise/admission-control',
            'security-enterprise/falco',
            'security-enterprise/kube-bench',
          ],
        },
        {
          type: 'category',
          label: 'Supply Chain Security',
          collapsed: true,
          items: [
            'security-enterprise/cosign-sbom',
            'security-enterprise/ghas',
            'developer-platform/dependency-auditability',
          ],
        },
        {
          type: 'category',
          label: 'Hardening',
          collapsed: true,
          items: [
            'security-enterprise/security-overview',
            'security-enterprise/host-hardening',
            'security-enterprise/cluster-hardening',
            'security-enterprise/namespace-isolation',
            'security-enterprise/pod-security',
            'security-enterprise/ingress-edge-security',
            'security-enterprise/compliance',
            'platform-roadmap/phase-15-cert-manager',
          ],
        },
      ],
    },

    // ── GitOps & CI/CD ───────────────────────────────────────────────
    {
      type: 'category',
      label: '🚀 GitOps & CI/CD',
      collapsed: true,
      items: [
        {
          type: 'category',
          label: 'GitOps Foundation',
          collapsed: true,
          items: [
            'platform-roadmap/phase-12-gitops',
            'developer-platform/gitops-workflow',
            'developer-platform/gitops-directory-patterns',
            'developer-platform/helm-argocd-migration',
            'developer-platform/helm-vs-kustomize',
            'developer-platform/backstage-helm-kustomize',
          ],
        },
        {
          type: 'category',
          label: 'CI/CD Pipeline',
          collapsed: true,
          items: [
            'platform-roadmap/phase-13-cicd',
            'developer-platform/branch-strategy-cicd',
            'developer-platform/ci-registry-migration',
            'developer-platform/custom-images',
            'platform-roadmap/phase-8-containers',
          ],
        },
        {
          type: 'category',
          label: 'App Deployment Guide',
          collapsed: true,
          items: [
            'app-deployment/deploy-overview',
            'app-deployment/helm-chart',
            'app-deployment/deploy-helm',
            'app-deployment/deploy-argocd',
            'app-deployment/deploy-yaml',
            'app-deployment/cicd-pipeline',
            'app-deployment/per-env-isolation',
            'app-deployment/gitops-repo-patterns',
            'app-deployment/enterprise-gitops-controls',
            'platform-roadmap/phase-9-workload',
          ],
        },
        {
          type: 'category',
          label: 'Progressive Delivery',
          collapsed: true,
          items: [
            'developer-platform/argo-rollouts',
            'developer-platform/vpa-auto',
            'developer-platform/keda-cron-scale-to-zero',
          ],
        },
        {
          type: 'category',
          label: 'Quality Gates & Gap Analysis',
          collapsed: true,
          items: [
            'developer-platform/cicd-gap-analysis',
            'developer-platform/automated-regression-detection',
          ],
        },
      ],
    },

    // ── Developer Platform (IDP) ─────────────────────────────────────
    {
      type: 'category',
      label: '👨‍💻 Developer Platform',
      collapsed: true,
      items: [
        'developer-platform/backstage',
        'developer-platform/backstage-plugins',
        'developer-platform/backstage-software-templates',
        'developer-platform/techdocs',
        'developer-platform/multi-env-namespaces',
      ],
    },

    // ── Observability ────────────────────────────────────────────────
    {
      type: 'category',
      label: '📊 Observability',
      collapsed: true,
      items: [
        {
          type: 'category',
          label: 'Logs',
          collapsed: true,
          items: [
            'observability/loki',
            'observability/otelcol-log-pipeline',
            'observability/otelcol-log-pipeline-gaps',
            'observability/grafana-log-dashboards-controller-logs',
            'observability/loki-ruler-logql-alerting',
          ],
        },
        {
          type: 'category',
          label: 'Metrics & Alerting',
          collapsed: true,
          items: [
            'platform-roadmap/phase-8-monitoring',
            'observability/alertmanager',
            'observability/alerting-gaps',
            'observability/slo-dashboard',
            'observability/dora-metrics',
            'observability/k8s-monitoring-gaps',
            'observability/controlplane-node-monitoring-gaps',
            'observability/capacity-planning-gaps',
            'observability/cost-optimization-gaps',
          ],
        },
        {
          type: 'category',
          label: 'Distributed Tracing',
          collapsed: true,
          items: [
            'observability/jaeger',
            'observability/distributed-tracing-gaps',
          ],
        },
        {
          type: 'category',
          label: 'Application Monitoring',
          collapsed: true,
          items: [
            'observability/application-monitoring',
            'observability/application-monitoring-gaps',
            'observability/regression-detection-gaps',
          ],
        },
        {
          type: 'category',
          label: 'Security & Runtime',
          collapsed: true,
          items: [
            'observability/falco-sidekick-polaris',
            'observability/security-evaluation',
            'observability/security-resource-boundaries',
          ],
        },
        'observability/ai-governance-dashboard',
        'observability/lifecycle-day2-operations',
      ],
    },

    // ── Data Platform ────────────────────────────────────────────────
    {
      type: 'category',
      label: '🗄 Data Platform',
      collapsed: true,
      items: [
        'data-layer/data-layer-overview',
        'data-layer/kafka-redpanda',
        'data-layer/clickhouse',
        'data-layer/dbt',
        'data-layer/openmetadata',
      ],
    },

    // ── AI & ML ──────────────────────────────────────────────────────
    {
      type: 'category',
      label: '🤖 AI & ML',
      collapsed: true,
      items: [
        {
          type: 'category',
          label: 'Inference Infrastructure',
          collapsed: true,
          items: [
            'ai-ml/ollama',
            'ai-ml/model-distribution',
            'ai-ml/mlflow',
            'ai-ml/kubeflow',
            'ai-ml/inference-optimization',
            'ai-ml/sampling-configuration',
          ],
        },
        {
          type: 'category',
          label: 'Chat Interface',
          collapsed: true,
          items: [
            'ai-ml/open-webui',
          ],
        },
        {
          type: 'category',
          label: 'Gateway & Observability',
          collapsed: true,
          items: [
            'ai-ml/ai-gateway',
            'ai-ml/langfuse',
          ],
        },
        {
          type: 'category',
          label: 'RAG Pipeline',
          collapsed: true,
          items: [
            'ai-ml/rag-pipeline',
            'ai-ml/rag-internals',
            'ai-ml/rag-eval-pipeline',
          ],
        },
        {
          type: 'category',
          label: 'Safety & Compliance',
          collapsed: true,
          items: [
            'ai-ml/ai-security-overview',
            'ai-ml/hallucination-controls',
            'ai-ml/bias-detection',
            'ai-ml/prompt-injection',
            'ai-ml/data-poisoning',
            'ai-ml/model-inversion',
            'ai-ml/membership-inference',
            'ai-ml/content-safety',
          ],
        },
        {
          type: 'category',
          label: 'Evaluation & Specialization',
          collapsed: true,
          items: [
            'ai-ml/phi3-financial',
            'ai-ml/phi3-financial-eval-cicd',
            'ai-ml/domain-specialization-framework',
          ],
        },
        {
          type: 'category',
          label: 'Agents',
          collapsed: true,
          items: [
            'ai-ml/research-agent',
            'ai-ml/deep-research-agent',
          ],
        },
      ],
    },

    // ── Business Applications ────────────────────────────────────────
    {
      type: 'category',
      label: '🏢 Business Applications',
      collapsed: true,
      items: [
        {
          type: 'category',
          label: '🏦 Insurance Platform',
          collapsed: false,
          items: [
            'insurance-platform/business-applications-catalog',
          ],
        },
        {
          type: 'category',
          label: 'Collaboration',
          collapsed: true,
          items: [
            'developer-platform/matrix-synapse-element-web',
            'developer-platform/jitsi-meet',
            'developer-platform/nextcloud',
          ],
        },
        {
          type: 'category',
          label: 'Mail',
          collapsed: true,
          items: [
            'developer-platform/stalwart-mail',
            'developer-platform/amazon-ses',
          ],
        },
        {
          type: 'category',
          label: 'Project Management',
          collapsed: true,
          items: [
            'developer-platform/plane-ce',
            'developer-platform/minicloud-plane',
          ],
        },
        {
          type: 'category',
          label: 'ERP & Finance',
          collapsed: true,
          items: [
            'developer-platform/erpnext-hr',
            'developer-platform/erpnext-french-insurance-config',
            'developer-platform/erpnext-facturx-custom-image',
            'developer-platform/erpnext-dsn-architecture',
            'developer-platform/erpnext-dsn-guide-utilisateur',
            'developer-platform/erpnext-crm-insurance-templates',
            'developer-platform/erpnext-billing-dunning',
            'developer-platform/erpnext-insurance-lob-doctypes',
          ],
        },
        {
          type: 'category',
          label: 'Document & Signature',
          collapsed: true,
          items: [
            'developer-platform/docuseal',
          ],
        },
        {
          type: 'category',
          label: 'Security & Credentials',
          collapsed: true,
          items: [
            'developer-platform/vaultwarden',
          ],
        },
      ],
    },

    // ── Automation & Workflows ───────────────────────────────────────
    {
      type: 'category',
      label: '⚡ Automation & Workflows',
      collapsed: true,
      items: [
        'automation/n8n',
        'automation/temporal',
        'automation/airflow',
        'event-driven/keda',
        'event-driven/nats',
      ],
    },

    // ── Backup, DR & Reliability ─────────────────────────────────────
    {
      type: 'category',
      label: '💾 Backup, DR & Reliability',
      collapsed: true,
      items: [
        'backup-dr/velero',
        'backup-dr/longhorn-backup',
        'backup-dr/etcd-backup',
        'backup-dr/database-backup',
        'backup-dr/disk-management',
        'backup-dr/dr-runbook',
        'reliability/chaos-mesh',
        'reliability/phase81-chaos-game-day',
      ],
    },

    // ── Project Governance ───────────────────────────────────────────
    {
      type: 'category',
      label: '📐 Project Governance',
      collapsed: false,
      items: [
        'project-governance/project-governance-standard',
      ],
    },

    // ── Certification RNCP ───────────────────────────────────────────
    {
      type: 'category',
      label: '🎓 Certification RNCP39583',
      collapsed: false,
      items: [
        'certification/cahier-des-charges-fonctionnel',
      ],
    },

    // ── IS Governance ────────────────────────────────────────────────
    {
      type: 'category',
      label: '📋 IS Governance',
      collapsed: true,
      items: [
        'developer-platform/is-governance-scrumban-prince2',
      ],
    },

    // ── Engineering Standards ─────────────────────────────────────────
    {
      type: 'category',
      label: '🧪 Engineering Standards',
      collapsed: false,
      items: [
        'engineering-standards/testing-strategy',
      ],
    },

  ],
};

export default sidebars;
