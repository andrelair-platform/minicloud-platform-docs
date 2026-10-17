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
from diagrams.generic.compute import Rack
from diagrams.generic.database import SQL
from diagrams.generic.network import Firewall, VPN
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
from diagrams.onprem.certificates import CertManager, LetsEncrypt
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Client, Users
from diagrams.onprem.database import ClickHouse, MariaDB, PostgreSQL
from diagrams.onprem.gitops import ArgoCD, Flagger
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
    SLATE,
    WIRE,
    cluster_attr,
    node,
)

# Give labelled edges room to breathe (light theme, larger fonts).
GRAPH_ATTR = {**GRAPH_ATTR, "ranksep": "0.95", "nodesep": "0.5"}

with Diagram(
    "minicloud PLATFORM — Technology Topology (logical)  ·  k3s v1.36 · 6 nodes  ·  solid = principal flow · dashed = backing dependency",
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
    groq = node(Rack, "Groq API\nllama-3.1-8b", icon="groq.png")
    r2 = Storage("Cloudflare R2\noffsite backup")
    alerts_out = Client("AWS SES email\n+ Slack\n(alert sink)")

    # ======================================================= ACCESS & EDGE
    with Cluster("ACCESS & NETWORKING", graph_attr=cluster_attr(CYAN)):
        cf = Cloudflare("Cloudflare\nCDN · WAF · DNS")
        tunnel = node(VPN, "Cloudflared Tunnel\npublic → internal", icon="cloudflared.png")
        tailscale = node(VPN, "Tailscale VPN\n*.nip.io internal", icon="tailscale.png")
        ingress = Nginx("NGINX Ingress")
        authentik = node(Dex, "Authentik SSO\nOIDC · forward-auth", icon="authentik.png")
        certmgr = CertManager("cert-manager")
        le = LetsEncrypt("Let's Encrypt\n+ minicloud CA")
        cilium = node(Firewall, "Cilium\nCNI · LB-IPAM 10.0.0.200\n· NetworkPolicy", icon="cilium.png")

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

    # ======================================================= DATA & MESSAGING
    # Platform-provided data-infra ENGINES (a capability). The *schemas/data* they hold are
    # IS-owned and appear in the IS Application Landscape — not here (ownership ≠ deployment).
    with Cluster("DATA & MESSAGING  ·  managed capability", graph_attr=cluster_attr(AMBER)):
        pg = PostgreSQL("PostgreSQL / CNPG\nPostgres-as-a-service")
        mariadb = MariaDB("MariaDB\nmanaged instance")
        valkey = Redis("Valkey / Redis\ncache-as-a-service")
        nats = node(Nats, "NATS\nJetStream eventing", icon="nats.png")

    # ======================================================= STORAGE & BACKUP (on-cluster)
    with Cluster("STORAGE & BACKUP", graph_attr=cluster_attr(CYAN)):
        longhorn = node(Storage, "Longhorn\ndistributed block PVCs", icon="longhorn.png")
        velero = node(Storage, "Velero + Kopia\ndaily snapshots", icon="velero.png")

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

    # ======================================================= HARDWARE / OFF-CLUSTER
    with Cluster("HARDWARE & OFF-CLUSTER  ·  MAAS controller + 6 nodes", graph_attr=cluster_attr(SLATE)):
        controller = Ubuntu("MAAS controller\nX390 · NAT · Tailscale\n100.88.123.8 (off-cluster)")
        minio = node(Storage, "MinIO (on controller)\nS3 backup target", icon="minio.png")
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
    # EDGES — every edge carries a VERB.  solid = principal flow · dashed = backing.
    # (All relationships verified against the gitops manifests — no invented edges.)
    # =====================================================================

    # --- request path (solid, principal) ---------------------------------
    users >> FLOW("HTTPS") >> cf >> FLOW("tunnel") >> tunnel >> FLOW("routes") >> ingress
    tailscale >> FLOW("internal *.nip.io") >> ingress
    cilium >> DASH("assigns LB IP 10.0.0.200") >> ingress
    ingress >> FLOW("forward-auth") >> authentik
    certmgr >> DASH("issues-certs") >> ingress
    le >> DASH("ACME / CA") >> certmgr
    authentik >> FLOW("authenticates") >> [litellm, openwebui]

    # --- delivery path: code → production (solid, green) ------------------
    dev >> WIRE("git push") >> gh >> WIRE("triggers") >> actions
    actions >> WIRE("builds + pushes (dev)") >> harbor
    actions >> WIRE("builds + pushes (prod)") >> ghcr
    actions >> DASH("scans · signs (Trivy/Cosign/SBOM)") >> trivy
    ghcr >> WIRE("newest image") >> kargo
    kargo >> WIRE("promotes · CODEOWNERS PR") >> argocd
    argocd >> WIRE("reconciles") >> sethog
    argocd >> DASH("drives") >> rollouts
    rollouts >> DASH("gated by metrics") >> prometheus

    # --- secrets & policy (dashed, backing) ------------------------------
    vault >> DASH("supplies-secrets") >> eso
    argocd >> DASH("deploys ExternalSecret CR") >> eso
    eso >> DASH("writes k8s Secrets → workloads") >> litellm
    gatekeeper >> DASH("admission · cluster-wide") >> sethog
    falco >> DASH("runtime monitoring · cluster-wide") >> sethog
    cilium >> DASH("CNI + NetworkPolicy · cluster-wide") >> sethog

    # --- AI runtime (routes-to is a principal flow) ----------------------
    litellm >> FLOW("routes-to") >> [vllm, groq]
    litellm >> DASH("caches in") >> valkey
    litellm >> DASH("traces") >> langfuse
    langfuse >> DASH("stores") >> langfuse_ch
    ragingest >> DASH("writes vectors") >> qdrant

    # --- storage & backup (backing) --------------------------------------
    longhorn >> DASH("provides PVCs") >> [pg, mariadb]
    velero >> WIRE("backs-up") >> minio
    velero >> WIRE("backs-up (offsite)") >> r2

    # --- observability (scrape / ship / notify) --------------------------
    otel >> DASH("ships logs") >> loki
    otel >> DASH("ships traces") >> tempo
    [nodeexp, ksm] >> DASH("scraped by") >> prometheus
    prometheus >> DASH("datasource") >> grafana
    prometheus >> DASH("fires alerts") >> alertmgr
    alertmgr >> FLOW("notifies") >> alerts_out

    # --- provisioning vs reconciliation (hardware fabric) ----------------
    tofu >> DASH("provisions") >> controller
    ansible >> DASH("configures") >> controller
    sysupgrade >> DASH("upgrades k3s") >> sethog
    controller >> DASH("NAT · Tailscale") >> sethog
    controller >> DASH("hosts") >> minio
    sethog >> DASH("control plane") >> [skunk, heron, kitten, gannet, swiftmac]
