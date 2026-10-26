"""GitOps Workflow System — the reconcile-loop view (icon-rich, mingrammer `diagrams`).

Where the delivery-pipeline diagram follows the *artifact's journey*, this shows the GitOps **system**
as a loop: humans and Kargo only ever write to **Git (the single source of truth)**; **ArgoCD is the
only cluster writer**, continuously reconciling desired state (Git) against live state (cluster) and
self-healing drift. The two-repo model, app-of-apps, Kargo promotion + protected PR/check gate, and the Helm
wrapper/library render are all in one view.

Run via the central venv:  python src/platform_gitops_system.py   (see Makefile `make generate`).
Output → static/img/architecture/platform-gitops-system.{svg,png} (base64-inlined afterwards).
"""
from __future__ import annotations

from diagrams import Cluster, Diagram
from diagrams.onprem.client import User
from diagrams.onprem.compute import Server
from diagrams.onprem.vcs import Github
from diagrams.onprem.gitops import Argocd

from _theme import OUT, GRAPH_ATTR, NODE_ATTR, EDGE_ATTR, cluster_attr, node, FLOW, WIRE, DASH
from _theme import GREEN, AMBER, SLATE, CYAN, RED

OUTFILE = str(OUT / "platform-gitops-system")

with Diagram(
    "GitOps Workflow System — Git is the source of truth, ArgoCD is the only cluster writer",
    filename=OUTFILE,
    outformat=["svg", "png"],
    show=False,
    direction="TB",
    graph_attr={**GRAPH_ATTR, "ranksep": "1.0", "nodesep": "0.7"},
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    engineer = User("Engineer\nopens PRs — never touches the cluster")

    # ---- 1. source — application repos ---------------------------------------
    with Cluster("1 · Source  (application repos)", graph_attr=cluster_attr(SLATE)):
        apprepo = Github("application repo\ncode · Dockerfile · tests")
        ci = node(Server, "CI\nbuild · scan · cosign · SBOM", icon="github-actions.png")
        registry = node(Server, "image registry\nHarbor (dev) · ghcr (prod, signed)", icon="ghcr.png")

    # ---- 2. promote — Kargo (writes to Git, never to the cluster) -------------
    with Cluster("2 · Promote  (Kargo)", graph_attr=cluster_attr(CYAN)):
        kargo = node(Server, "Kargo\nimage → Freight → promotion PR\ndev: checked auto-merge · prod: maintainer merge", icon="kargo.png")

    # ---- 3. the single source of truth — Git ---------------------------------
    with Cluster("3 · Git — SINGLE SOURCE OF TRUTH  (protected main: PR + checks + signed commits)", graph_attr=cluster_attr(AMBER)):
        gitops = Github("minicloud-gitops  (deployment repo)\nArgoCD Applications · wrapper + library\nHelm charts · manifests · AppProjects")

    # ---- 4. reconcile — ArgoCD (the ONLY cluster writer) ---------------------
    with Cluster("4 · Reconcile — ArgoCD  (the only thing that writes to the cluster)",
                 graph_attr=cluster_attr(GREEN)):
        root = node(Argocd, "Root App-of-Apps\n(recurse: true)", icon="argocd.png")
        appsets = node(Server, "ApplicationSets\n+ AppProjects (RBAC)", icon="argocd.png")
        apps = node(Server, "Applications\nrender Helm (wrapper + library @ OCI)", icon="argocd.png")
        sync = node(Server, "Sync + Health controller\ncompare desired ↔ live → apply\nselfHeal · prune on drift", icon="argocd.png")

    # ---- 5. cluster ----------------------------------------------------------
    with Cluster("5 · Cluster  (dev + prod namespaces)", graph_attr=cluster_attr(SLATE)):
        workloads = node(Server, "workloads\nRollout/Deploy · Svc · Ingress · ESO\ndev (1) · prod (2–3 · canary)", icon="k3s.png")

    # ============================= relationships ==============================
    # humans only ever write to Git (code or config) — never the cluster
    engineer >> WIRE("code PR") >> apprepo
    engineer >> FLOW("config PR + maintainer release decision") >> gitops

    # build → image → Kargo → Git (desired state is only ever changed via Git)
    apprepo >> WIRE("push → CI") >> ci
    ci >> WIRE("signed image") >> registry
    registry >> WIRE("new image") >> kargo
    kargo >> WIRE("promotion PR (into Git)") >> gitops

    # Git → ArgoCD → cluster (apply), then the reconcile loop back
    gitops >> FLOW("declares desired state") >> root
    root >> WIRE("owns") >> appsets
    appsets >> WIRE("generates") >> apps
    apps >> WIRE("feeds") >> sync
    sync >> FLOW("apply / sync (writes cluster)") >> workloads
    workloads >> DASH("observe live → detect drift", color=RED) >> sync   # the reconcile loop
