"""minicloud — Production Stack Architecture (diagram-as-code).

Code-generated replacement for the hand-maintained
`static/diagrams/minicloud-production-stack.html` (871 lines of absolute-positioned
SVG). Same information architecture — the full ktayl-solution IS — but auto-laid-out
by Graphviz from this file, so it never drifts to pixel-edits again. This is the
**canonical** platform architecture diagram (the HTML poster is retired).

Run:  make generate   (or: python src/platform_overview.py)
Out:  static/img/architecture/minicloud-platform.{png,svg}  (open the SVG full-screen)

Icon note: components without a built-in `diagrams` icon use the closest semantic
built-in; the label is authoritative. Drop a brand PNG in src/icons/ + pass
icon="name.png" to node() to upgrade fidelity (see _theme.node / README).
"""
from __future__ import annotations

from diagrams import Cluster, Diagram

# ---- built-in nodes (all confirmed present in diagrams==0.24.4) --------------
from diagrams.aws.engagement import SimpleEmailServiceSes
from diagrams.aws.integration import SimpleNotificationServiceSns, SimpleQueueServiceSqs
from diagrams.aws.storage import SimpleStorageServiceS3
from diagrams.generic.compute import Rack
from diagrams.generic.database import SQL
from diagrams.generic.network import Firewall, Router, VPN
from diagrams.generic.os import Ubuntu
from diagrams.generic.storage import Storage
from diagrams.k8s.chaos import ChaosMesh
from diagrams.k8s.clusterconfig import HPA
from diagrams.k8s.compute import DaemonSet, Job, Pod
from diagrams.k8s.infra import Master, Node
from diagrams.k8s.network import Ingress
from diagrams.k8s.others import PSP
from diagrams.k8s.podconfig import ConfigMap, Secret
from diagrams.onprem.aggregator import Vector
from diagrams.onprem.analytics import Metabase
from diagrams.onprem.certificates import CertManager, LetsEncrypt
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Client, Users
from diagrams.onprem.compute import Server
from diagrams.onprem.database import ClickHouse, MariaDB, PostgreSQL
from diagrams.onprem.gitops import ArgoCD, Flagger
from diagrams.onprem.groupware import Nextcloud
from diagrams.onprem.iac import Ansible, Terraform
from diagrams.onprem.identity import Dex
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.logging import Loki
from diagrams.onprem.mlops import Mlflow
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.network import Kong, Nginx
from diagrams.onprem.queue import Nats
from diagrams.onprem.registry import Harbor
from diagrams.onprem.security import Bitwarden, Trivy, Vault
from diagrams.onprem.tracing import Tempo
from diagrams.onprem.vcs import Github
from diagrams.onprem.workflow import NiFi
from diagrams.saas.alerting import Pagerduty
from diagrams.saas.automation import N8N
from diagrams.saas.cdn import Cloudflare
from diagrams.saas.security import Crowdstrike

from _theme import (
    AMBER,
    CYAN,
    DASH,
    EDGE_ATTR,
    FLOW,
    GRAPH_ATTR,
    GREEN,
    NODE_ATTR,
    OUT,
    WIRE,
    cluster_attr,
    node,
)

# Tighter ranks than the default — a ~70-node poster, kept as compact as Graphviz allows.
GRAPH_ATTR = {**GRAPH_ATTR, "ranksep": "0.7", "nodesep": "0.4", "fontsize": "26"}

with Diagram(
    "minicloud — Production Stack  ·  k3s v1.36  ·  6 nodes  ·  ~95 ArgoCD apps  ·  the ktayl-solution IS",
    filename=str(OUT / "minicloud-platform"),
    outformat=["png", "svg"],
    direction="TB",
    show=False,
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    # ======================================================= external world
    users = Users("Internet users\nbrowsers · mobile")
    dev = Client("Developer\nMacBook Air (local)")
    groq = node(Rack, "Groq API\nllama-3.1-8b-instant", icon="groq.png")
    ses = SimpleEmailServiceSes("AWS SES\neu-west-1")

    # ======================================================= ACCESS & EDGE
    with Cluster("ACCESS LAYER", graph_attr=cluster_attr(CYAN)):
        cf = Cloudflare("Cloudflare\nCDN · WAF · DNS")
        tunnel = node(VPN, "Cloudflared Tunnel\npublic → internal", icon="cloudflared.png")
        tailscale = node(VPN, "Tailscale VPN\n*.nip.io internal", icon="tailscale.png")
        metallb = node(Router, "MetalLB\nLB IP 10.0.0.200", icon="metallb.png")
        ingress = Nginx("NGINX Ingress")
        authentik = node(Dex, "Authentik SSO\nOIDC · TOTP · all apps", icon="authentik.png")
        certmgr = CertManager("cert-manager")
        le = LetsEncrypt("Let's Encrypt\n+ minicloud CA")
        cilium = node(Firewall, "Cilium CNI\neBPF · NetworkPolicies", icon="cilium.png")

    # ======================================================= GITOPS & DELIVERY
    with Cluster("GITOPS & AUTOMATION", graph_attr=cluster_attr(GREEN)):
        argocd = ArgoCD("ArgoCD\napp-of-apps · ~95 apps")
        rollouts = node(Flagger, "Argo Rollouts\nCanary · BlueGreen", icon="argo-rollouts.png")
        kargo = node(Flagger, "Kargo\npromote dev→prod", icon="kargo.png")
        keda = node(HPA, "KEDA\nevent-driven scale", icon="keda.png")
        vpa = HPA("VPA\nright-sizing")
        reloader = node(ConfigMap, "Reloader\nConfigMap hot-reload", icon="reloader.png")
        backstage = node(Rack, "Backstage IDP\nTechDocs · templates", icon="backstage.png")
        sysupgrade = Job("system-upgrade\nk3s Plans")

    # ======================================================= CI / CD
    with Cluster("CI / CD PIPELINE", graph_attr=cluster_attr(GREEN)):
        gh = Github("GitHub\n8+ repos")
        actions = GithubActions("GitHub Actions\nbuild · Trivy · Cosign · SBOM")
        harbor = Harbor("Harbor\ndev registry")
        ghcr = node(Rack, "ghcr.io\nprod registry", icon="ghcr.png")

    # ======================================================= SECURITY & SECRETS
    with Cluster("PLATFORM SECURITY", graph_attr=cluster_attr(AMBER)):
        vault = Vault("Vault + ESO\nPKI · secrets · KMS")
        eso = Secret("ESO\nExternalSecrets")
        vaultwarden = Bitwarden("Vaultwarden\nbreak-glass")
        gatekeeper = PSP("Gatekeeper\nOPA policies")
        falco = Crowdstrike("Falco\nruntime security")
        trivy = Trivy("Trivy\nCVE scan")
        polaris = node(PSP, "Polaris\nconfig best-practice", icon="polaris.png")
        chaos = ChaosMesh("Chaos Mesh\nfault injection")

    # ======================================================= AI / ML PLATFORM
    with Cluster("AI / ML PLATFORM  ·  ai namespace", graph_attr=cluster_attr(CYAN)):
        litellm = Kong("LiteLLM Proxy\ngateway · keys · routing")
        openwebui = node(Client, "Open WebUI\nchat · RAG · SSO", icon="openwebui.png")
        flowise = node(NiFi, "Flowise\nvisual LLM builder", icon="flowise.png")
        mlflow = Mlflow("MLflow\nexperiments · registry")
        qdrant = node(SQL, "Qdrant\nvector DB · RAG", icon="qdrant.png")
        ragingest = Pod("rag-ingest\nconvert→chunk→embed")
        markitdown = Pod("markitdown\nPDF/Office/img → MD")
        agent = node(Rack, "minicloud-agent\nLangGraph ReAct · MCP", icon="langgraph.png")
        crew = node(Rack, "crew-agent\nCrewAI 3-agent", icon="crewai.png")
        vllm = node(Rack, "vLLM\nstar-kitten inference", icon="vllm.png")
        phi3 = node(Rack, "Phi-3-mini (CPU)\nfallback", icon="ollama.png")
        presidio = node(Firewall, "Presidio\nPII / DLP guardrail", icon="presidio.png")
        with Cluster("AI OBSERVABILITY", graph_attr=cluster_attr(GREEN)):
            langfuse = node(Rack, "Langfuse\nLLM traces · evals · cost", icon="langfuse.png")
            langfuse_ch = ClickHouse("ClickHouse\ntrace store")

    # ======================================================= COLLABORATION / IS
    with Cluster("COLLABORATION & IS APPS", graph_attr=cluster_attr(CYAN)):
        erpnext = node(Server, "ERPNext\nHR · finance · GL", icon="erpnext.png")
        nextcloud = Nextcloud("Nextcloud\nfiles · OnlyOffice")
        matrix = node(Server, "Matrix + Element\nSynapse · SSO", icon="matrix.png")
        jitsi = node(Server, "Jitsi Meet\nJVB · star-kitten", icon="jitsi.png")
        plane = node(Rack, "Plane CE\nproject mgmt", icon="plane.png")
        homer = node(Client, "Homer\ndashboards", icon="homer.png")
        docuseal = node(Server, "Docuseal\ne-signature", icon="docuseal.png")
        paperless = node(Server, "Paperless-ngx\nDMS · OCR", icon="paperless.png")
        metabase = Metabase("Metabase\nBI / analytics")

    # ======================================================= AUTOMATION & WORKFLOW
    with Cluster("AUTOMATION & WORKFLOW", graph_attr=cluster_attr(GREEN)):
        n8n = N8N("n8n\nworkflow automation")
        temporal = node(Rack, "Temporal\ndurable workflows", icon="temporal.png")

    # ======================================================= DATA & MESSAGING
    with Cluster("DATA & MESSAGING", graph_attr=cluster_attr(AMBER)):
        pg = PostgreSQL("PostgreSQL (CNPG)\npostgresql-ai · app DBs")
        pg_synapse = PostgreSQL("postgresql-synapse\nMatrix DB")
        mariadb = MariaDB("MariaDB\nERPNext")
        valkey = Redis("Valkey\nlitellm-cache")
        nats = node(Nats, "NATS\nJetStream · events", icon="nats.png")

    # ======================================================= STORAGE & BACKUP
    with Cluster("STORAGE & INFRA", graph_attr=cluster_attr(CYAN)):
        longhorn = node(Storage, "Longhorn\ndistributed block PVCs", icon="longhorn.png")
        minio = node(Storage, "MinIO\nS3-compatible", icon="minio.png")
        velero = node(Storage, "Velero + Kopia\ndaily → MinIO + R2", icon="velero.png")

    # ======================================================= OBSERVABILITY
    with Cluster("OBSERVABILITY STACK  ·  64/64 targets up", graph_attr=cluster_attr(GREEN)):
        prometheus = Prometheus("Prometheus (kps)\nSLO + regression rules")
        grafana = Grafana("Grafana\n35+ dashboards")
        loki = Loki("Loki\nlog aggregation")
        tempo = Tempo("Tempo 2.9\ndistributed tracing")
        otel = node(Vector, "OTel Collector\nDaemonSet 0.156", icon="otel.png")
        alertmgr = Pagerduty("Alertmanager\nburn-rate 2-tier")
        nodeexp = DaemonSet("Node Exporter\n:9100")
        ksm = Pod("kube-state-metrics")
        hubble = node(Pod, "Hubble UI\nCilium flow obs", icon="cilium.png")

    # ======================================================= EMAIL PIPELINE
    with Cluster("EMAIL PIPELINE", graph_attr=cluster_attr(CYAN)):
        stalwart = Server("Stalwart Mail\nSMTP 587 · IMAP 993")
        sns = SimpleNotificationServiceSns("SNS")
        sqs = SimpleQueueServiceSqs("SQS")
        s3in = SimpleStorageServiceS3("S3 inbound")

    # ======================================================= HARDWARE
    with Cluster("HARDWARE  ·  MAAS provisioned  ·  Ubuntu 22.04", graph_attr=cluster_attr("#64748b")):
        controller = Ubuntu("MAAS controller\nX390 · NAT · Tailscale\n100.88.123.8")
        tofu = Terraform("OpenTofu / MAAS\nnode provisioning")
        ansible = Ansible("Ansible\nbootstrap roles")
        with Cluster("k3s cluster — 6 nodes", graph_attr=cluster_attr(CYAN)):
            sethog = Master("set-hog · 10.0.0.2\ncontrol plane")
            skunk = Node("fast-skunk · 10.0.0.4\nworker")
            heron = Node("fast-heron · 10.0.0.7\nstorage")
            kitten = Node("star-kitten · 10.0.0.8\nAI · JVB · vLLM")
            gannet = Node("loving-gannet · 10.0.0.9\nT490 · storage")
            swiftmac = Node("swift-mac · 10.0.0.10\nMacBook Pro · storage")

    # =====================================================================
    # EDGES — the backbone flows, kept sparse to stay legible.
    # =====================================================================

    # --- request path (cyan) ---------------------------------------------
    users >> FLOW() >> cf >> FLOW() >> tunnel >> FLOW() >> ingress
    tailscale >> FLOW("internal") >> ingress
    metallb >> FLOW() >> ingress
    ingress >> FLOW("SSO gate") >> authentik
    certmgr >> DASH("issues TLS") >> ingress
    le >> DASH() >> certmgr
    authentik >> FLOW() >> [litellm, erpnext, openwebui, nextcloud]

    # --- delivery path (green) -------------------------------------------
    dev >> WIRE("git push") >> gh >> WIRE() >> actions
    actions >> WIRE("dev image") >> harbor
    actions >> WIRE("prod image") >> ghcr
    actions >> WIRE("sign + SBOM") >> trivy
    [harbor, ghcr] >> WIRE("newest build") >> kargo
    kargo >> WIRE("CODEOWNERS PR") >> argocd
    argocd >> WIRE("reconcile") >> sethog
    argocd >> DASH() >> rollouts
    rollouts >> DASH("metrics gate") >> prometheus

    # --- secrets / policy backing (dashed) -------------------------------
    vault >> DASH("secrets") >> eso >> DASH() >> argocd
    gatekeeper >> DASH("admission") >> sethog
    falco >> DASH("runtime") >> sethog
    cilium >> DASH("netpol / CNI") >> sethog

    # --- data / storage backing ------------------------------------------
    litellm >> DASH() >> valkey
    litellm >> DASH("traces") >> langfuse
    langfuse >> DASH() >> langfuse_ch
    ragingest >> DASH() >> qdrant
    [erpnext] >> DASH("db") >> mariadb
    [nextcloud, plane] >> DASH("db") >> pg
    matrix >> DASH("db") >> pg_synapse
    longhorn >> DASH("PVCs") >> [pg, minio]
    velero >> DASH("backup") >> minio
    nats >> DASH("events") >> crew

    # --- observability scrape --------------------------------------------
    otel >> DASH() >> [loki, tempo]
    [nodeexp, ksm] >> DASH() >> prometheus
    prometheus >> DASH() >> [grafana, alertmgr]

    # --- mail pipeline ---------------------------------------------------
    stalwart >> FLOW("relay 587") >> ses
    ses >> FLOW("inbound") >> sns >> sqs
    s3in >> DASH() >> sqs
    alertmgr >> DASH("alerts") >> stalwart

    # --- hardware fabric --------------------------------------------------
    tofu >> DASH("provisions") >> controller
    ansible >> DASH("configures") >> controller
    controller >> DASH("NAT · Tailscale") >> sethog
    sethog >> DASH() >> [skunk, heron, kitten, gannet, swiftmac]
