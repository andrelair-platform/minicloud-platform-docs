"""Delivery pipeline — system-design view (icon-rich, mingrammer `diagrams`).

Visualises the end-to-end delivery workflow AND the continuous-delivery-vs-continuous-deployment
split: the same artifact is built+proved once, Kargo auto-promotes it to **dev (continuous
DEPLOYMENT — no human)**, then a CODEOWNERS-gated PR promotes it to **prod (continuous DELIVERY —
a human decides when)**. ArgoCD is the only cluster writer.

Run via the central venv:  python src/platform_delivery_pipeline.py   (see Makefile `make generate`).
Output → static/img/architecture/platform-delivery-pipeline.{svg,png} (base64-inlined afterwards).
"""
from __future__ import annotations

from diagrams import Cluster, Diagram
from diagrams.onprem.client import User
from diagrams.onprem.compute import Server
from diagrams.onprem.vcs import Github
from diagrams.onprem.gitops import Argocd

from _theme import OUT, GRAPH_ATTR, NODE_ATTR, EDGE_ATTR, cluster_attr, node, FLOW, WIRE, DASH
from _theme import GREEN, AMBER, SLATE, CYAN, RED

OUTFILE = str(OUT / "platform-delivery-pipeline")

with Diagram(
    "Delivery Pipeline — continuous delivery (prod) + continuous deployment (dev)",
    filename=OUTFILE,
    outformat=["svg", "png"],
    show=False,
    direction="LR",
    graph_attr={**GRAPH_ATTR, "ranksep": "1.1", "nodesep": "0.6"},
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    # ---- 1. build & prove (application repo) ----------------------------------
    with Cluster("1 · Build & prove  (application repo)", graph_attr=cluster_attr(SLATE)):
        dev = User("Developer\ngit push → main")
        gh = node(Github, "GitHub repo\nsource + CI", icon="github-actions.png")
        ci = node(Server, "CI\ntest · build · scan\ncosign · SBOM", icon="github-actions.png")
        with Cluster("registries", graph_attr=cluster_attr(SLATE)):
            harbor = node(Server, "Harbor\ndev image", icon="harbor.png")
            ghcr = node(Server, "ghcr.io\nprod SHA (signed)", icon="ghcr.png")

    # ---- 2. promote (Kargo) --------------------------------------------------
    with Cluster("2 · Promote  (Kargo — the only promoter)", graph_attr=cluster_attr(CYAN)):
        warehouse = node(Server, "Warehouse\ndetects image → Freight\n(immutable artifact)", icon="kargo.png")

    # ---- 3. dev = CONTINUOUS DEPLOYMENT (automatic, no human) -----------------
    with Cluster("3 · dev  —  CONTINUOUS DEPLOYMENT  (automatic · no human)", graph_attr=cluster_attr(GREEN)):
        kdev = node(Server, "Stage dev\nauto-promote\n(ProjectConfig)", icon="kargo.png")
        devpr = node(Github, "dev values PR\n→ auto-merge\n(kargo-automerge)", icon="github-actions.png")
        argodev = node(Argocd, "ArgoCD\nreconciles dev", icon="argocd.png")
        devcluster = node(Server, "dev workload\n(1 replica)", icon="k3s.png")
        verify = node(Server, "dev-verify\nAnalysisRun →\n'Verified in dev'", icon="argo-rollouts.png")

    # ---- 4. prod = CONTINUOUS DELIVERY (human-gated) -------------------------
    with Cluster("4 · prod  —  CONTINUOUS DELIVERY  (human decides when)", graph_attr=cluster_attr(AMBER)):
        kprod = node(Server, "Stage prod\naccepts only\nverified Freight", icon="kargo.png")
        reviewer = User("CODEOWNERS review\n@AndreLair + live QA gate\n← the manual gate")
        prodpr = node(Github, "prod values PR\n(NO auto-merge)", icon="github-actions.png")
        argoprod = node(Argocd, "ArgoCD\nreconciles prod", icon="argocd.png")
        prodcluster = node(Server, "prod workload\n(2–3 replicas · canary)", icon="k3s.png")

    # ============================= relationships ==============================
    # build & prove (solid green = delivery flow)
    dev >> WIRE("push") >> gh
    gh >> WIRE("triggers") >> ci
    ci >> WIRE("dev tag") >> harbor
    ci >> WIRE("prod SHA · sign · SBOM") >> ghcr
    ghcr >> WIRE("new image") >> warehouse

    # dev — automatic continuous deployment (green, no human in the path)
    warehouse >> WIRE("auto-promote") >> kdev
    kdev >> WIRE("opens + auto-merges") >> devpr
    devpr >> WIRE("reconciles") >> argodev
    argodev >> WIRE("deploys") >> devcluster
    devcluster >> DASH("smoke / analysis") >> verify

    # the dev→prod gate: only dev-verified Freight is promotable
    verify >> WIRE("verified Freight →") >> kprod

    # prod — human-gated continuous delivery (amber/red = the manual decision)
    kprod >> FLOW("opens gated PR", ) >> prodpr
    prodpr >> DASH("blocks on", color=RED) >> reviewer
    reviewer >> FLOW("human approves (squash)", ) >> argoprod
    argoprod >> FLOW("deploys") >> prodcluster
