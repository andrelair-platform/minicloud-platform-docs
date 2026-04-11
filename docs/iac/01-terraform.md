---
id: terraform
title: Phase 11 — Terraform / OpenTofu
sidebar_position: 1
---

# Phase 11 — Terraform / OpenTofu — Infrastructure as Code

Terraform (and its open-source fork **OpenTofu**) lets you define your entire infrastructure in `.tf` files — MAAS machines, networks, Kubernetes namespaces, Harbor projects, Vault policies — and apply it with a single command. Your infra becomes version-controlled, reviewable, and reproducible.

:::info OpenTofu vs Terraform
OpenTofu is the community fork of Terraform after HashiCorp changed its license in 2023. It is fully compatible, actively maintained, and the recommended choice for new projects. Commands are identical (`tofu` instead of `terraform`).
:::

---

## The Core Idea

```text
Without IaC:
  → Click in MAAS UI to configure subnet
  → Run commands to create k8s namespace
  → Set up Harbor project manually
  → Next time: start from memory

With Terraform/OpenTofu:
  → Write infra.tf
  → tofu apply
  → Git commit infra.tf
  → Next time: tofu apply again — identical result
```

---

## Install OpenTofu

```bash
curl -fsSL https://get.opentofu.org/install-opentofu.sh | sh

tofu version
```

---

## Provider Setup

Terraform/OpenTofu uses **providers** to talk to different systems. Key ones for this cluster:

```hcl
# versions.tf
terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.27"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
    vault = {
      source  = "hashicorp/vault"
      version = "~> 3.25"
    }
  }
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}

provider "helm" {
  kubernetes {
    config_path = "~/.kube/config"
  }
}

provider "vault" {
  address = "http://10.0.0.200:8200"
  token   = var.vault_token
}
```

---

## Example 1 — Kubernetes Namespace + RBAC

```hcl
# namespaces.tf
resource "kubernetes_namespace" "production" {
  metadata {
    name = "production"
    labels = {
      environment = "production"
      managed-by  = "terraform"
    }
  }
}

resource "kubernetes_namespace" "staging" {
  metadata {
    name = "staging"
    labels = {
      environment = "staging"
      managed-by  = "terraform"
    }
  }
}

resource "kubernetes_resource_quota" "production_quota" {
  metadata {
    name      = "production-quota"
    namespace = kubernetes_namespace.production.metadata[0].name
  }
  spec {
    hard = {
      "requests.cpu"    = "16"
      "requests.memory" = "32Gi"
      "limits.cpu"      = "20"
      "limits.memory"   = "40Gi"
    }
  }
}
```

---

## Example 2 — Deploy Apps via Helm

```hcl
# monitoring.tf
resource "helm_release" "prometheus" {
  name       = "prometheus"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  namespace  = "monitoring"
  version    = "57.0.0"

  create_namespace = true

  set {
    name  = "grafana.adminPassword"
    value = var.grafana_password
  }

  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName"
    value = "longhorn"
  }
}
```

---

## Example 3 — Vault Secrets Engine

```hcl
# vault.tf
resource "vault_mount" "kv" {
  path = "secret"
  type = "kv-v2"
}

resource "vault_kv_secret_v2" "db_creds" {
  mount = vault_mount.kv.path
  name  = "myapp/database"

  data_json = jsonencode({
    username = "appuser"
    password = var.db_password
  })
}

resource "vault_policy" "myapp" {
  name = "myapp"
  policy = <<EOT
path "secret/data/myapp/*" {
  capabilities = ["read"]
}
EOT
}
```

---

## Project Structure

```text
terraform/
├── versions.tf          # providers + versions
├── variables.tf         # input variables
├── outputs.tf           # output values
├── namespaces.tf        # k8s namespaces + quotas
├── monitoring.tf        # prometheus + grafana helm
├── harbor.tf            # harbor helm release
├── vault.tf             # vault secrets + policies
├── argocd.tf            # argocd helm release
└── terraform.tfvars     # variable values (gitignored)
```

---

## State Backend — Store State in Kubernetes

Instead of local state files, store Terraform state in your cluster:

```hcl
terraform {
  backend "kubernetes" {
    secret_suffix    = "cluster-state"
    config_path      = "~/.kube/config"
    namespace        = "terraform"
  }
}
```

---

## Workflow

```bash
# Initialize
tofu init

# Preview changes
tofu plan

# Apply
tofu apply

# Destroy (careful!)
tofu destroy
```

---

## GitOps for IaC

Store your `.tf` files in GitLab. Add a CI pipeline:

```yaml
# .gitlab-ci.yml
stages:
  - plan
  - apply

tofu-plan:
  stage: plan
  script:
    - tofu init
    - tofu plan -out=plan.tfplan
  artifacts:
    paths: [plan.tfplan]

tofu-apply:
  stage: apply
  script:
    - tofu apply plan.tfplan
  when: manual          # human approval before apply
  environment: production
```

Every infra change goes through Git → review → manual approval → apply.

---

## Done When

```text
✔ OpenTofu installed and initialized
✔ Kubernetes namespaces created via tofu apply
✔ At least one Helm chart managed by Terraform
✔ State stored in Kubernetes backend
✔ Plan + apply running in GitLab CI
```
