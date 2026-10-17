"""C4 **Container view** of the minicloud PLATFORM — icon-rich (mingrammer `diagrams`).

The visual twin of the Structurizr C4 Container view: same boundary (the Platform only; the
Information System is a single external *consumer*), same capability groups, but rendered with real
brand logos + verb-labelled edges — the icon look of a FANG-style system-design poster.

Structurizr renders the *formal* C4 (standard boxes) but its PlantUML export drops element icons;
this file is the icon lens of the exact same model. Keep the two in sync by hand (both are small).

Run via the central venv:  python src/platform_c4_container.py   (see Makefile `make generate`).
Output → static/img/architecture/platform-c4-container.{svg,png} (base64-inlined by embed-svg-images.py).
"""
from __future__ import annotations

from diagrams import Cluster, Diagram
from diagrams.onprem.client import User, Users
from diagrams.onprem.compute import Server
from diagrams.onprem.network import Nginx, Internet
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.queue import Nats as NatsIcon
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.monitoring import Prometheus, Grafana
from diagrams.onprem.gitops import Argocd
from diagrams.onprem.vcs import Github
from diagrams.generic.blank import Blank

# Loki / k3s / storage render from brand PNGs (src/icons/*.png); Server is only the fallback class.
Loki = StorageIcon = K3S = Server

from _theme import OUT, GRAPH_ATTR, NODE_ATTR, EDGE_ATTR, cluster_attr, node, FLOW, WIRE, DASH
from _theme import CYAN, GREEN, AMBER, SLATE, MUTED

OUTFILE = str(OUT / "platform-c4-container")

with Diagram(
    "minicloud Platform — C4 Container view (the internal cloud provider)",
    filename=OUTFILE,
    outformat=["svg", "png"],
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    # ---- actors + external systems (left / right) -----------------------------
    dev = User("Platform engineer\ngit push · PR")
    enduser = Users("End user\nbrowser (BYOD)")

    with Cluster("External systems", graph_attr=cluster_attr(MUTED)):
        github = Github("GitHub\nsource · Actions CI")
        clouds = Internet("Cloud LLMs\nGroq · Azure OpenAI")
        edge = Internet("Cloudflare\nDNS · Tunnel · R2")

    # ---- the Platform boundary ------------------------------------------------
    with Cluster("🏗  PLATFORM — minicloud (k3s on 6 nodes + off-cluster controller)",
                 graph_attr=cluster_attr(CYAN)):

        with Cluster("Access & Networking", graph_attr=cluster_attr(CYAN)):
            tunnel = node(Internet, "Cloudflared\npublic → internal", icon="cloudflared.png")
            tailscale = node(Server, "Tailscale\ninternal mesh", icon="tailscale.png")
            ingress = node(Nginx, "ingress-nginx\nTLS · routing", icon="nginx.png")
            cilium = node(Server, "Cilium\nCNI · LB-IPAM · netpol", icon="cilium.png")
            authentik = node(Server, "Authentik\nSSO · OIDC · forward-auth", icon="authentik.png")

        with Cluster("Delivery / GitOps", graph_attr=cluster_attr(GREEN)):
            actions = node(Github, "GitHub Actions\nbuild · sign · SBOM", icon="github-actions.png")
            harbor = node(Server, "Harbor\ndev registry", icon="harbor.png")
            ghcr = node(Server, "ghcr.io\nprod registry", icon="ghcr.png")
            argocd = node(Argocd, "ArgoCD\napp-of-apps · reconcile", icon="argocd.png")
            kargo = node(Server, "Kargo\npromote dev→prod", icon="kargo.png")
            rollouts = node(Server, "Argo Rollouts\ncanary · blue-green", icon="argo-rollouts.png")

        with Cluster("Security & Secrets", graph_attr=cluster_attr(AMBER)):
            vault = node(Server, "Vault\nKV · PKI · KMS-unseal", icon="vault.png")
            eso = node(Server, "External Secrets\nVault → k8s Secret", icon="external-secrets.png")
            gatekeeper = node(Server, "Gatekeeper (OPA)\nadmission policy", icon="gatekeeper.png")
            falco = node(Server, "Falco\nruntime threat-detect", icon="falco.png")
            certmgr = node(Server, "cert-manager\nTLS issuance", icon="cert-manager.png")

        with Cluster("Data & Messaging", graph_attr=cluster_attr(AMBER)):
            cnpg = node(PostgreSQL, "PostgreSQL / CNPG\noperator-managed", icon="cnpg.png")
            nats = node(NatsIcon, "NATS\nJetStream events", icon="nats.png")
            valkey = node(Redis, "Valkey\ncache · queues", icon="valkey.png")

        with Cluster("Storage & Backup", graph_attr=cluster_attr(SLATE)):
            longhorn = node(StorageIcon, "Longhorn\nreplicated block PVCs", icon="longhorn.png")
            velero = node(StorageIcon, "Velero + Kopia\ncluster backup", icon="velero.png")
            minio = node(StorageIcon, "MinIO (controller)\nS3 backup target", icon="minio.png")

        with Cluster("Observability", graph_attr=cluster_attr(CYAN)):
            prom = node(Prometheus, "Prometheus\nmetrics scrape", icon="prometheus.png")
            grafana = node(Grafana, "Grafana\ndashboards", icon="grafana.png")
            loki = node(Loki, "Loki\nlogs", icon="loki.png")
            tempo = node(Server, "Tempo\ntraces", icon="tempo.png")
            otel = node(Server, "OTel Collector\ntelemetry pipeline", icon="otel.png")
            alertmgr = node(Prometheus, "Alertmanager\n→ SES · Slack", icon="prometheus.png")

        with Cluster("AI Runtime", graph_attr=cluster_attr(GREEN)):
            litellm = node(Server, "LiteLLM\nmodel gateway · keys", icon="litellm.png")
            qdrant = node(Server, "Qdrant\nvector DB · RAG", icon="qdrant.png")
            langfuse = node(Server, "Langfuse\ntraces · evals · cost", icon="langfuse.png")
            vllm = node(Server, "vLLM\nGPU inference", icon="vllm.png")
            presidio = node(Server, "Presidio\nPII / DLP guardrail", icon="presidio.png")

        with Cluster("Runtime & Tooling", graph_attr=cluster_attr(SLATE)):
            k3s = node(K3S, "k3s\ncluster runtime", icon="k3s.png")
            backstage = node(Server, "Backstage\ndeveloper portal", icon="backstage.png")

    # ---- the Information System as a single external consumer -----------------
    with Cluster("🏢  INFORMATION SYSTEM — ktayl-solution (consumer)", graph_attr=cluster_attr("#7c3aed")):
        isys = Blank("Insurance business apps\nUnderwriting · Policy · Claims · Billing · …")

    # ============================= relationships ==============================
    # delivery (green, solid) — code → production
    dev >> WIRE("git push · PR") >> github
    github >> WIRE("builds · signs") >> actions
    actions >> WIRE("pushes image") >> ghcr
    ghcr >> WIRE("new artifact") >> kargo
    kargo >> WIRE("promotes (gated PR)") >> argocd
    argocd >> WIRE("reconciles") >> k3s
    argocd >> DASH("progressive rollout") >> rollouts

    # request (teal, solid) — user → app
    enduser >> FLOW("HTTPS") >> edge
    edge >> FLOW("tunnel") >> tunnel
    tunnel >> FLOW("routes") >> ingress
    ingress >> FLOW("forward-auth") >> authentik

    # backing (dashed) — the cross-cutting dependencies
    vault >> DASH("supplies secrets") >> eso
    eso >> DASH("renders Secret") >> k3s
    certmgr >> DASH("issues TLS") >> ingress
    prom >> DASH("scrapes") >> k3s
    otel >> DASH("ships logs/traces") >> loki
    alertmgr >> DASH("alerts") >> edge
    velero >> DASH("backs up → ") >> minio
    k3s >> DASH("PVCs") >> longhorn
    litellm >> DASH("routes to") >> vllm
    litellm >> DASH("egress (governed)") >> clouds

    # the IS consumes the platform (purple consumer edge)
    isys >> FLOW("SSO · DB · events · AI · storage") >> authentik
