"""Shared theme + helpers for minicloud diagram-as-code (mingrammer `diagrams`).

Echoes the palette of the hand-made static/diagrams/minicloud-production-stack.html
(cyan #22d3ee / green #34d399 on slate #0f172a) so the generated poster feels
like the same product — but auto-laid-out from code instead of pixel coordinates.

Usage in a diagram module:

    from _theme import OUT, GRAPH_ATTR, NODE_ATTR, EDGE_ATTR, cluster_attr, node, FLOW, WIRE

Add a brand icon later: drop a transparent PNG in src/icons/ and call
`node(FallbackClass, "Kargo", icon="kargo.png")` — it uses the PNG if present,
otherwise the built-in fallback. See README.md.
"""
from __future__ import annotations

from pathlib import Path

from diagrams.custom import Custom

# ---------------------------------------------------------------- paths
_HERE = Path(__file__).resolve().parent          # .../diagrams/src
ICONS = _HERE / "icons"                           # drop brand PNGs here (optional)
# Generated images land in the Docusaurus static tree so the docs site can serve them.
OUT = _HERE.parent.parent / "static" / "img" / "architecture"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- palette
SLATE = "#0f172a"
SLATE_SOFT = "#111c33"
CYAN = "#22d3ee"
GREEN = "#34d399"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
AMBER = "#f59e0b"
RED = "#f87171"

# ---------------------------------------------------------------- attrs
GRAPH_ATTR = {
    "bgcolor": SLATE,
    "fontcolor": TEXT,
    "fontname": "Helvetica",
    "fontsize": "22",
    "pad": "0.6",
    "nodesep": "0.55",
    "ranksep": "0.85",
    "splines": "spline",
    "compound": "true",
}

NODE_ATTR = {
    "fontcolor": TEXT,
    "fontname": "Helvetica",
    "fontsize": "11",
}

EDGE_ATTR = {
    "color": MUTED,
    "fontcolor": MUTED,
    "fontname": "Helvetica",
    "fontsize": "9",
}


def cluster_attr(pencolor: str = CYAN, label_color: str | None = None) -> dict:
    """Styling for a Cluster box — coloured outline on the slate background."""
    return {
        "bgcolor": SLATE_SOFT,
        "pencolor": pencolor,
        "fontcolor": label_color or pencolor,
        "fontname": "Helvetica-Bold",
        "fontsize": "13",
        "style": "rounded",
        "penwidth": "1.6",
    }


def node(cls, label: str, icon: str | None = None):
    """Create a node: use a brand PNG from src/icons/ if available, else a built-in.

    This is the one extension point for fidelity — the platform has ~25 components
    with no built-in `diagrams` icon (Kargo, KEDA, Longhorn, Authentik, Langfuse …).
    Until a real icon is vendored, we render the closest *semantic* built-in and let
    the label carry the truth (exactly how the freeCodeCamp tutorial uses the library).
    """
    if icon:
        p = ICONS / icon
        if p.exists():
            return Custom(label, str(p))
    return cls(label)


# Edge presets — the two backbone flows the poster emphasises.
def FLOW(label: str = ""):
    """Request / data flow (cyan)."""
    from diagrams import Edge
    return Edge(label=label, color=CYAN, fontcolor=MUTED)


def WIRE(label: str = ""):
    """Delivery / CI-CD flow (green)."""
    from diagrams import Edge
    return Edge(label=label, color=GREEN, fontcolor=MUTED)


def DASH(label: str = "", color: str = MUTED):
    """Secondary / backing dependency (dashed)."""
    from diagrams import Edge
    return Edge(label=label, color=color, fontcolor=MUTED, style="dashed")
