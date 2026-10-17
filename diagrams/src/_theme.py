"""Shared theme + helpers for the minicloud PLATFORM diagrams (mingrammer `diagrams`).

**Light / neutral theme** (white background, dark text, high-contrast coloured edges) — chosen for
legibility: the previous dark poster hid thin dashed edges and small labels, and a light diagram
prints + reads far better for engineers/recruiters/PDF. Vendor icons pop on white.

Edge semantics (used by every platform diagram — keep consistent, explain in the page legend):
  FLOW  = solid, teal   — principal request / data flow
  WIRE  = solid, green  — delivery / CI-CD / reconcile flow
  DASH  = dashed, slate — backing dependency (supplies-secrets, scrapes, backs-up, …)
Always put a VERB on the edge label (provisions · reconciles · supplies-secrets · routes-traffic ·
authenticates · scrapes · ships-logs · backs-up · promotes · issues-certs · scales · routes-to-LLM).

Usage:  from _theme import OUT, GRAPH_ATTR, NODE_ATTR, EDGE_ATTR, cluster_attr, node, FLOW, WIRE, DASH
"""
from __future__ import annotations

from pathlib import Path

from diagrams.custom import Custom

# ---------------------------------------------------------------- paths
_HERE = Path(__file__).resolve().parent          # .../diagrams/src
ICONS = _HERE / "icons"                           # drop brand PNGs here (optional)
OUT = _HERE.parent.parent / "static" / "img" / "architecture"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- palette (light)
BG = "#ffffff"          # page/diagram background
PANEL = "#f1f5f9"       # cluster fill (slate-100)
TEXT = "#0f172a"        # dark text (slate-900)
EDGE_LABEL = "#334155"  # edge label text (slate-700)
CYAN = "#0891b2"        # principal request/data flow + a cluster accent (cyan-700)
GREEN = "#047857"       # delivery / reconcile + accent (emerald-700)
AMBER = "#b45309"       # security / data accents (amber-700)
MUTED = "#64748b"       # backing dashed edges (slate-500)
SLATE = "#475569"       # neutral cluster border (slate-600)
RED = "#dc2626"

# ---------------------------------------------------------------- attrs
GRAPH_ATTR = {
    "bgcolor": BG,
    "fontcolor": TEXT,
    "fontname": "Helvetica-Bold",
    "fontsize": "26",
    "pad": "0.7",
    "nodesep": "0.5",
    "ranksep": "0.85",
    "splines": "spline",
    "compound": "true",
}

NODE_ATTR = {
    "fontcolor": TEXT,
    "fontname": "Helvetica",
    "fontsize": "13",
}

EDGE_ATTR = {
    "color": MUTED,
    "fontcolor": EDGE_LABEL,
    "fontname": "Helvetica",
    "fontsize": "11",
}


def cluster_attr(pencolor: str = CYAN, label_color: str | None = None) -> dict:
    """Styling for a Cluster box — a tinted panel with a strong coloured border on white."""
    return {
        "bgcolor": PANEL,
        "pencolor": pencolor,
        "fontcolor": label_color or pencolor,
        "fontname": "Helvetica-Bold",
        "fontsize": "14",
        "style": "rounded",
        "penwidth": "2.2",
    }


def node(cls, label: str, icon: str | None = None):
    """Create a node: use a brand PNG from src/icons/ if available, else the built-in fallback.
    The label is authoritative (components without a built-in icon render the closest semantic one)."""
    if icon:
        p = ICONS / icon
        if p.exists():
            return Custom(label, str(p))
    return cls(label)


# --- edge presets (solid = principal, dashed = backing) ----------------------
def FLOW(label: str = ""):
    """Solid, teal — principal REQUEST / DATA flow."""
    from diagrams import Edge
    return Edge(label=label, color=CYAN, fontcolor=EDGE_LABEL, penwidth="2.2")


def WIRE(label: str = ""):
    """Solid, green — DELIVERY / reconcile flow."""
    from diagrams import Edge
    return Edge(label=label, color=GREEN, fontcolor=EDGE_LABEL, penwidth="2.2")


def DASH(label: str = "", color: str = MUTED):
    """Dashed, slate — BACKING dependency."""
    from diagrams import Edge
    return Edge(label=label, color=color, fontcolor=EDGE_LABEL, style="dashed", penwidth="1.5")
