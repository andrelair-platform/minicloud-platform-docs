"""minicloud PLATFORM — L0 Network & Boot Topology (diagram-as-code).

The physical view (platform_physical.py) shows *where workloads run*; this shows the layer BELOW them —
the L0 network/boot plumbing that the cluster stands on, and why the controller is a single point of
failure for it. Two panels:

  CURRENT  — the controller (ThinkPad X390) is gateway + NAT + MAAS DHCP/PXE + MinIO + Tailscale, all on
             one box, reached through a USB→ethernet dongle (the fragile physical link). The built-in
             gigabit NIC sits unused. Nodes have static IPs and now boot disk-first, so the cluster forms
             over the L2 switch even if the controller is off — only *internet* (the 10.0.0.1 gateway)
             waits for it.
  TARGET    — Niveau 1 hardening: a dedicated gateway box owns NAT/routing at 10.0.0.254; the nodes'
             default route points at it (one Ansible file: roles/network/files/99-default-gateway.yaml);
             the controller keeps 10.0.0.1 as a *services-only, sometimes-on* host (MinIO/MAAS/Tailscale).
             Result: the cluster has internet whether or not the controller is up.

Run:  make generate   ·   Out: ../../static/img/architecture/platform-network-boot.{png,svg}
Grounded in: connectivity.md (node IPs), ops-runbooks.md + live inspection 2026-11-26 (dongle
enx606d3cdf7160 = 10.0.0.1, enp0s31f6 unused, WiFi uplink wlp0s20f3), minicloud-ansible PR #31
(disk-first boot), reference_pxe_boot_order_controller_dependency.
"""
from __future__ import annotations

from diagrams import Cluster, Diagram, Edge
from diagrams.generic.compute import Rack
from diagrams.generic.network import Router, Switch, VPN
from diagrams.generic.storage import Storage
from diagrams.k8s.infra import Master, Node
from diagrams.onprem.iac import Terraform
from diagrams.onprem.network import Internet

from _theme import (
    AMBER,
    CYAN,
    DASH,
    EDGE_ATTR,
    EDGE_LABEL,
    FLOW,
    GRAPH_ATTR,
    GREEN,
    NODE_ATTR,
    OUT,
    RED,
    SLATE,
    cluster_attr,
    node,
)

GRAPH_ATTR = {**GRAPH_ATTR, "ranksep": "0.95", "nodesep": "0.55"}


def RISK(label: str = ""):
    """Solid RED — a fragile / single-point-of-failure link worth flagging."""
    return Edge(label=label, color=RED, fontcolor=EDGE_LABEL, penwidth="2.4")


def FIX(label: str = ""):
    """Dashed GREEN — a proposed hardening move."""
    return Edge(label=label, color=GREEN, fontcolor=EDGE_LABEL, style="dashed", penwidth="2.0")


with Diagram(
    "minicloud PLATFORM — L0 Network & Boot Topology  ·  CURRENT (controller = SPOF)  vs  TARGET (dedicated gateway)",
    filename=str(OUT / "platform-network-boot"),
    outformat=["png", "svg"],
    direction="TB",
    show=False,
    graph_attr=GRAPH_ATTR,
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):

    # =================================================================== CURRENT
    with Cluster("CURRENT  ·  controller is the whole L0 tier  ·  SINGLE POINT OF FAILURE", graph_attr=cluster_attr(RED)):
        inet_c = Internet("Internet")
        box_c = Router("home box\n192.168.1.0/24 · ISP uplink")

        with Cluster("controller · ThinkPad X390  ·  L0 + services on ONE box", graph_attr=cluster_attr(SLATE)):
            gw_c = node(Router, "GW + NAT + DHCP · 10.0.0.1\n⚠ carried on a USB→eth dongle\n(enx606d3cdf7160)")
            maas_c = Terraform("MAAS · DHCP + PXE\n(provisioning — toggle)")
            minio_c = node(Storage, "MinIO · backup target", icon="minio.png")
            tails_c = node(VPN, "Tailscale\nsubnet-router", icon="tailscale.png")
            nic_free = node(Rack, "built-in NIC enp0s31f6\nUNUSED — free gigabit")

        sw_c = Switch("L2 switch · 10.0.0.0/24")

        with Cluster("k3s cluster · 6 nodes · STATIC IPs · disk-boot-first (PR #31)", graph_attr=cluster_attr(CYAN)):
            cp_c = Master("set-hog · 10.0.0.2\ncontrol-plane")
            wk_c = Node("5× workers\n.4 .7 .8 .9 .10")

        inet_c >> FLOW("internet") >> box_c
        box_c >> FLOW("WiFi uplink (wlp0s20f3)") >> gw_c
        gw_c >> RISK("routes-traffic · NAT  (fragile USB link)") >> sw_c
        maas_c >> DASH("provisions · DHCP/PXE") >> sw_c
        sw_c >> FLOW("gateway + L2 peering") >> cp_c
        sw_c >> FLOW("") >> wk_c
        nic_free >> FIX("Niveau 0 (0€): move the cluster cable here") >> sw_c

    # =================================================================== TARGET
    with Cluster("TARGET  ·  Niveau 1 — gateway moved OFF the laptop onto a dedicated box", graph_attr=cluster_attr(GREEN)):
        inet_t = Internet("Internet")
        box_t = Router("home box\nISP uplink")
        gw_t = node(Router, "dedicated gateway · 10.0.0.254\nNAT + routing (always-on)")
        sw_t = Switch("L2 switch · 10.0.0.0/24")

        with Cluster("controller · 10.0.0.1  ·  SERVICES ONLY (sometimes-on)", graph_attr=cluster_attr(SLATE)):
            maas_t = Terraform("MAAS\n(commission only)")
            minio_t = node(Storage, "MinIO · backup target", icon="minio.png")
            tails_t = node(VPN, "Tailscale\nsubnet-router", icon="tailscale.png")

        with Cluster("k3s cluster · 6 nodes · STATIC IPs · disk-boot-first", graph_attr=cluster_attr(CYAN)):
            cp_t = Master("set-hog · 10.0.0.2\ncontrol-plane")
            wk_t = Node("5× workers")

        inet_t >> FLOW("internet") >> box_t
        box_t >> FLOW("uplink") >> gw_t
        gw_t >> FLOW("routes-traffic · NAT") >> sw_t
        sw_t >> FLOW("default route → 10.0.0.254") >> cp_t
        sw_t >> FLOW("") >> wk_t
        sw_t >> DASH("services: MinIO/MAAS/Tailscale\n(cluster runs even if controller off)", color=AMBER) >> maas_t
