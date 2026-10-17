workspace "minicloud Platform" "Complete C4 system design of the self-hosted enterprise Kubernetes platform (the internal cloud provider)." {

    model {
        # ---- people --------------------------------------------------------
        dev = person "Developer" "Builds and ships workloads."
        user = person "End user" "Reaches applications over the web."

        # ---- external systems ---------------------------------------------
        github = softwareSystem "GitHub" "Source control + CI (GitHub Actions)." "External"
        cloudLLM = softwareSystem "Cloud LLM providers" "Groq / OpenAI / … reached only through the gateway." "External"
        cloudflare = softwareSystem "Cloudflare" "CDN · WAF · Tunnel · R2 off-site object storage." "External"
        ses = softwareSystem "AWS SES" "Outbound email relay (alerts + mail)." "External"

        # The Information System is a SEPARATE system that runs ON and CONSUMES the platform.
        is = softwareSystem "ktayl-solution Information System" "The insurer's business applications (policy, claims, underwriting, workplace…). Runs on and consumes the platform — modelled in its own C4 later." "IS"

        # ---- the subject: the minicloud Platform --------------------------
        platform = softwareSystem "minicloud Platform" "Shared technical capabilities — the internal cloud provider. Business-agnostic." {

            group "Access & Networking" {
                ingress = container "NGINX Ingress" "L7 routing + TLS termination for every app." "Networking"
                cilium = container "Cilium" "CNI · LB-IPAM (10.0.0.200) · NetworkPolicy. Cluster-wide." "Networking"
                authentik = container "Authentik" "SSO — OIDC + forward-auth for every app." "Security"
                certmgr = container "cert-manager" "Issues TLS (Let's Encrypt public + minicloud CA internal)." "Networking"
            }
            group "Delivery (GitOps)" {
                ci = container "GitHub Actions (CI)" "Build · Trivy scan · Cosign sign · SBOM." "Delivery"
                registry = container "Image registries" "Harbor (dev) + ghcr.io (prod, SHA-pinned)." "Delivery"
                kargo = container "Kargo" "Promotes one artifact dev→prod via a CODEOWNERS-gated PR." "Delivery"
                argocd = container "ArgoCD" "GitOps reconcile (app-of-apps, ~95 apps)." "Delivery"
                rollouts = container "Argo Rollouts" "Progressive delivery (canary / blue-green)." "Delivery"
            }
            group "Security & Secrets" {
                vault = container "Vault + ESO" "Secrets · PKI · AWS-KMS auto-unseal. ESO writes k8s Secrets." "Security"
                gatekeeper = container "Gatekeeper (OPA)" "Admission policy. Cluster-wide." "Security"
                falco = container "Falco" "Runtime threat detection (DaemonSet). Cluster-wide." "Security"
            }
            group "Data & Messaging" {
                cnpg = container "PostgreSQL / CNPG" "Postgres-as-a-service (HA + PITR)." "Data"
                nats = container "NATS JetStream" "Durable eventing." "Data"
                valkey = container "Valkey" "Cache / ephemeral state." "Data"
            }
            group "Storage & Backup" {
                longhorn = container "Longhorn" "Distributed block storage — provides PVCs." "Storage"
                velero = container "Velero" "Backup + DR (snapshots → MinIO + R2)." "Storage"
                minio = container "MinIO" "S3-compatible backup target (runs on the controller, off-cluster)." "OffCluster"
            }
            group "Observability" {
                prometheus = container "Prometheus" "Metrics · SLO + recording/alert rules." "Observability"
                grafana = container "Grafana" "Dashboards." "Observability"
                loki = container "Loki" "Log aggregation." "Observability"
                tempo = container "Tempo" "Distributed tracing." "Observability"
                otel = container "OpenTelemetry Collector" "Ships logs + traces." "Observability"
                alertmgr = container "Alertmanager" "Alert routing (burn-rate)." "Observability"
            }
            group "AI Runtime" {
                litellm = container "LiteLLM Gateway" "Governed LLM access — keys · routing · PII." "AI"
                qdrant = container "Qdrant" "Vector database (RAG)." "AI"
                langfuse = container "Langfuse" "LLM observability (traces · cost · evals)." "AI"
                vllm = container "vLLM" "On-cluster inference." "AI"
            }
            group "Runtime & Tooling" {
                k3s = container "k3s cluster" "6-node Kubernetes runtime (where workloads run)." "Runtime"
                backstage = container "Backstage" "Developer portal / IDP (golden paths, TechDocs)." "Tooling"
            }
        }

        # ====================================================================
        # Relationships — every one verified against the GitOps manifests.
        # ====================================================================

        # request path
        user -> cloudflare "Reaches apps over HTTPS"
        cloudflare -> ingress "Tunnels traffic to"
        cilium -> ingress "Assigns the LB IP 10.0.0.200 to"
        ingress -> authentik "Gates every app via forward-auth"
        certmgr -> ingress "Issues TLS certs to"

        # delivery path (code → production)
        dev -> ci "Pushes code, triggers"
        ci -> registry "Builds + pushes images to"
        registry -> kargo "Provides the newest image to"
        kargo -> argocd "Promotes (CODEOWNERS-gated PR), driving"
        argocd -> k3s "Reconciles workloads onto"
        argocd -> rollouts "Drives progressive delivery via"
        rollouts -> prometheus "Is gated by metrics from"

        # secrets & policy
        vault -> k3s "Supplies secrets to workloads (via ESO) on"
        gatekeeper -> k3s "Enforces admission policy on"
        falco -> k3s "Monitors runtime syscalls on"

        # data & storage
        longhorn -> cnpg "Provides persistent volumes to"
        velero -> minio "Backs up to"
        velero -> cloudflare "Backs up off-site to (R2)"

        # observability
        prometheus -> k3s "Scrapes metrics from"
        otel -> loki "Ships logs to"
        otel -> tempo "Ships traces to"
        prometheus -> grafana "Is a datasource for"
        prometheus -> alertmgr "Fires alerts to"
        alertmgr -> ses "Notifies via email through"

        # AI runtime
        litellm -> vllm "Routes to"
        litellm -> cloudLLM "Routes to"
        litellm -> langfuse "Emits traces to"

        # the Information System consumes the platform (the ownership boundary)
        is -> authentik "Authenticates via (SSO)"
        is -> cnpg "Stores business data in"
        is -> nats "Publishes / consumes domain events on"
        is -> litellm "Calls LLMs through"
        is -> longhorn "Persists files on"

        # ---- physical deployment (where it runs) --------------------------
        deploymentEnvironment "Live" {
            deploymentNode "MAAS controller" "Off-cluster · ThinkPad X390 · NAT · Tailscale · 100.88.123.8" {
                containerInstance minio
            }
            deploymentNode "k3s cluster" "6 nodes · Longhorn network-attached storage" {
                deploymentNode "set-hog · control-plane" "10.0.0.2 · API/scheduler · kine/SQLite (SPOF)" {
                    containerInstance k3s
                }
                deploymentNode "fast-skunk · worker" "10.0.0.4 · general workloads" {
                }
                deploymentNode "fast-heron · storage" "10.0.0.7 · Vault-pinned" {
                    containerInstance vault
                    containerInstance longhorn
                }
                deploymentNode "star-kitten · AI" "10.0.0.8 · vLLM · Jitsi JVB" {
                    containerInstance vllm
                }
                deploymentNode "loving-gannet · storage" "10.0.0.9 · ThinkPad T490" {
                    containerInstance longhorn
                }
                deploymentNode "swift-mac · storage" "10.0.0.10 · MacBook Pro 2012" {
                    containerInstance longhorn
                }
            }
        }
    }

    views {
        systemContext platform "Context" "Who and what the platform talks to — including the Information System as its consumer." {
            include *
            autolayout lr
        }

        container platform "Containers" "The complete platform — every capability as a container, and how they work together." {
            include *
        }

        deployment platform "Live" "Deployment" "Where it physically runs — the 6-node k3s cluster + the off-cluster controller, with placement." {
            include *
            autolayout lr
        }

        styles {
            element "Person" {
                background "#334155"
                color "#ffffff"
                shape person
            }
            element "Software System" {
                background "#1168bd"
                color "#ffffff"
            }
            element "External" {
                background "#8c8c8c"
                color "#ffffff"
            }
            element "IS" {
                background "#7c3aed"
                color "#ffffff"
            }
            element "Container" {
                background "#0e7490"
                color "#ffffff"
            }
            element "Networking" {
                background "#0891b2"
                color "#ffffff"
            }
            element "Delivery" {
                background "#047857"
                color "#ffffff"
            }
            element "Security" {
                background "#b45309"
                color "#ffffff"
            }
            element "Data" {
                background "#6d28d9"
                color "#ffffff"
            }
            element "Storage" {
                background "#0e7490"
                color "#ffffff"
            }
            element "Observability" {
                background "#2563eb"
                color "#ffffff"
            }
            element "AI" {
                background "#be185d"
                color "#ffffff"
            }
            element "Runtime" {
                background "#334155"
                color "#ffffff"
            }
            element "OffCluster" {
                background "#64748b"
                color "#ffffff"
            }
        }
    }
}
