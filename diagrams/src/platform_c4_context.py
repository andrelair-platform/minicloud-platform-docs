"""C4 **System Context view** of the minicloud PLATFORM — icon-rich (mingrammer `diagrams`).

The visual twin of the Structurizr C4 System Context: the platform as one system, its actors, the
external systems it depends on, and the Information System as its single *consumer*. Rendered with
brand logos + verb-labelled edges (the icon lens; Structurizr renders the formal boxes).

Run via the central venv:  python src/platform_c4_context.py   (see Makefile `make generate`).
Output → static/img/architecture/platform-c4-context.{svg,png} (base64-inlined by embed-svg-images.py).
"""
from __future__ import annotations

from diagrams import Cluster, Diagram
from diagrams.onprem.client import User
from diagrams.onprem.compute import Server
from diagrams.onprem.network import Internet
from diagrams.aws.engagement import SimpleEmailServiceSes
from diagrams.generic.blank import Blank

from _theme import OUT, GRAPH_ATTR, NODE_ATTR, EDGE_ATTR, cluster_attr, node, FLOW, WIRE, DASH
from _theme import MUTED

OUTFILE = str(OUT / "platform-c4-context")

with Diagram(
    "minicloud Platform — C4 System Context (who & what it talks to)",
    filename=OUTFILE,
    outformat=["svg", "png"],
    show=False,
    direction="LR",
    graph_attr={**GRAPH_ATTR, "nodesep": "0.8", "ranksep": "1.4"},
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    # ---- actors / consumer (left) --------------------------------------------
    dev = User("Platform engineer\n[Person]\nbuilds & ships workloads")

    with Cluster("INFORMATION SYSTEM — consumer", graph_attr=cluster_attr("#7c3aed")):
        isys = Blank("ktayl-solution IS\n[Software System]\ninsurer's business apps —\npolicy · claims · underwriting ·\nworkplace. Modelled in its own C4.")

    # ---- the platform (centre) -----------------------------------------------
    with Cluster("the system", graph_attr=cluster_attr("#1168bd", label_color="#1168bd")):
        platform = node(Server, "minicloud Platform\n[Software System]\nshared technical capabilities —\nthe internal cloud provider\n(business-agnostic)", icon="k3s.png")

    # ---- external systems (right) --------------------------------------------
    with Cluster("External systems", graph_attr=cluster_attr(MUTED)):
        cloudflare = node(Internet, "Cloudflare\n[Software System]\nCDN · WAF · Tunnel ·\nR2 off-site storage", icon="cloudflare.png")
        llms = node(Internet, "Cloud LLM providers\n[Software System]\nGroq · OpenAI · … reached\nonly through the gateway", icon="openai.png")
        ses = SimpleEmailServiceSes("AWS SES\n[Software System]\noutbound email relay\n(alerts + mail)")

    # ============================= relationships ==============================
    dev >> WIRE("pushes code · triggers CI") >> platform
    isys >> FLOW("authenticates via SSO · consumes") >> platform

    platform >> DASH("backs up off-site to (R2)") >> cloudflare
    cloudflare >> FLOW("tunnels traffic to") >> platform
    platform >> DASH("routes to") >> llms
    platform >> DASH("notifies via email through") >> ses
