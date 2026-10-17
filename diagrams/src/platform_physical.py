"""minicloud PLATFORM — Physical / Deployment view (diagram-as-code).

The LOGICAL topology (platform_overview.py) says *what* capabilities exist; this says *where and how
they run* — the 6-node k3s cluster, control-plane vs worker roles, pinned workload placement, Longhorn
replication across the storage nodes, the off-cluster MAAS controller, and the failure domains. This is
the view that explains the on-prem reliability/operational constraints a logo topology can't.

Run:  make generate   ·   Out: ../../static/img/architecture/platform-physical.{png,svg}
Grounded in connectivity.md (node IPs/roles), scheduling.md (pins), datastore-selection.md (Longhorn).
"""
from __future__ import annotations

from diagrams import Cluster, Diagram
from diagrams.generic.compute import Rack
from diagrams.generic.os import Ubuntu
from diagrams.generic.storage import Storage
from diagrams.k8s.compute import Pod
from diagrams.k8s.infra import Master, Node
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.iac import Ansible, Terraform
from diagrams.onprem.security import Vault

from _theme import (
    CYAN,
    DASH,
    EDGE_ATTR,
    FLOW,
    GRAPH_ATTR,
    GREEN,
    NODE_ATTR,
    OUT,
    SLATE,
    cluster_attr,
    node,
)

GRAPH_ATTR = {**GRAPH_ATTR, "ranksep": "1.0", "nodesep": "0.55"}

with Diagram(
    "minicloud PLATFORM — Physical / Deployment view  ·  6-node k3s + off-cluster controller  ·  roles · placement · failure domains",
    filename=str(OUT / "platform-physical"),
    outformat=["png", "svg"],
    direction="TB",
    show=False,
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    # ---------------------------------------------------- off-cluster control host
    with Cluster("OFF-CLUSTER  ·  MAAS controller (ThinkPad X390)", graph_attr=cluster_attr(SLATE)):
        controller = Ubuntu("controller · 100.88.123.8\nNAT · Tailscale endpoint")
        maas = Terraform("MAAS + OpenTofu\nprovisioning")
        ansible = Ansible("Ansible\nbootstrap / config")
        minio = node(Storage, "MinIO (Docker)\nbackup target · S3", icon="minio.png")

    # ---------------------------------------------------- the k3s cluster
    with Cluster("k3s cluster  ·  v1.36  ·  10.0.0.0/24  ·  Longhorn network-attached storage", graph_attr=cluster_attr(CYAN)):

        with Cluster("set-hog · 10.0.0.2  ·  CONTROL PLANE (single — SPOF)", graph_attr=cluster_attr(GREEN)):
            sethog = Master("control plane")
            cp = Pod("kube-apiserver · scheduler\nctrl-manager · kine/SQLite")
            synapse_db = PostgreSQL("Synapse DB\n(pinned here)")

        with Cluster("fast-skunk · 10.0.0.4  ·  worker", graph_attr=cluster_attr(SLATE)):
            skunk = Node("general workloads")

        with Cluster("fast-heron · 10.0.0.7  ·  worker · storage", graph_attr=cluster_attr(SLATE)):
            heron = Node("worker")
            vault = Vault("Vault\n(nodeSelector pin)")
            heron_lh = Storage("Longhorn replica")

        with Cluster("star-kitten · 10.0.0.8  ·  worker · AI", graph_attr=cluster_attr(SLATE)):
            kitten = Node("worker")
            vllm = node(Rack, "vLLM\nCPU inference", icon="vllm.png")
            jvb = node(Rack, "Jitsi JVB\nhostNetwork", icon="jitsi.png")

        with Cluster("loving-gannet · 10.0.0.9  ·  worker · storage (T490)", graph_attr=cluster_attr(SLATE)):
            gannet = Node("worker")
            gannet_lh = Storage("Longhorn replica")

        with Cluster("swift-mac · 10.0.0.10  ·  worker · storage (MacBook Pro 2012)", graph_attr=cluster_attr(SLATE)):
            swiftmac = Node("worker")
            swift_lh = Storage("Longhorn preferred\n(dataLocality)")

        longhorn = node(Storage, "Longhorn\ndistributed volumes\n(replicated across storage nodes)", icon="longhorn.png")

    # ======================================================= edges
    # provisioning / control (solid green = control flow) ------------------
    maas >> FLOW("provisions nodes (PXE)") >> sethog
    ansible >> DASH("configures") >> sethog
    controller >> FLOW("NAT · Tailscale · kube-apiserver") >> sethog
    sethog >> FLOW("schedules / reconciles") >> [skunk, heron, kitten, gannet, swiftmac]

    # Longhorn replication across the three storage nodes (backing) --------
    longhorn >> DASH("replica") >> heron_lh
    longhorn >> DASH("replica") >> gannet_lh
    longhorn >> DASH("replica") >> swift_lh

    # backup off-cluster (solid = data flow) ------------------------------
    longhorn >> DASH("snapshots") >> controller
    controller >> DASH("hosts") >> minio
