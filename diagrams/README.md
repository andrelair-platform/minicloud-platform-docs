# Diagram-as-code (`diagrams` + Graphviz)

Architecture diagrams for the minicloud / ktayl-solution platform, written as **Python**
and rendered by [mingrammer **`diagrams`**](https://diagrams.mingrammer.com/) on top of
Graphviz. Adapted from the freeCodeCamp tutorial
["How to Create System Design Diagrams using Python"](https://www.freecodecamp.org/news/how-to-create-system-design-diagrams-using-python/),
swapping its AWS provider nodes for our on-prem k3s stack (`k8s` + `onprem` + `generic`).

**Why this exists:** the previous whole-platform poster lived in
`static/diagrams/minicloud-production-stack.html` — 871 lines of **hand-placed SVG
coordinates**. Any change meant editing pixels, so it drifted. This project regenerates the
same information architecture from code: edit a `.py`, run `make generate`, commit the image.

## Prerequisites

| Dependency | Install |
|---|---|
| Python 3.9+ | already on macOS / CI |
| Graphviz (`dot`) | `brew install graphviz` (macOS) · `apt-get install -y graphviz` (CI) |

## Quick start

```bash
make install     # venv + pip install diagrams (requirements.txt), checks for Graphviz
make generate    # render every src/*.py → ../static/img/architecture/*.{png,svg}
make check       # CI drift gate: fails if committed images are stale vs source
make clean       # delete generated images
```

Output lands in `../static/img/architecture/` (the Docusaurus `static/` tree), so a file
`minicloud-platform.png` is served at `/img/architecture/minicloud-platform.png`.

## Layout

```
diagrams/
  requirements.txt            # diagrams>=0.24,<0.25 (Graphviz is a SYSTEM dep, not pip)
  Makefile                    # install / generate / check / clean
  src/
    _theme.py                 # shared palette, graph/node/edge attrs, node() helper, edge presets
    platform_overview.py      # the whole minicloud platform (the 11 layers)
    icons/                    # OPTIONAL brand PNGs for components with no built-in icon
```

Add a new diagram by dropping a `src/<name>.py` that ends with a `with Diagram(...)` block
writing to `_theme.OUT`; `make generate` picks it up automatically (any `src/*.py` not
prefixed `_`).

## Core concepts (same as the tutorial)

- **`Diagram(...)`** — the canvas (a `with` context). `outformat=["png","svg"]`, `direction="TB"`, `show=False`.
- **`Cluster(...)`** — a labelled, nestable box = one platform layer.
- **Node** — a component, imported per provider (`diagrams.onprem.gitops.ArgoCD`).
- **`Edge` / `>>` `<<` `-`** — connections; we wrap them as `FLOW()` (cyan, requests),
  `WIRE()` (green, CI/CD), `DASH()` (dashed, backing deps) in `_theme.py`.

## Icon fidelity — the one thing to know

~25 of our components have **no built-in `diagrams` icon** (Kargo, KEDA, Longhorn, MinIO,
Authentik, Langfuse, LiteLLM, Qdrant, Tailscale, …). For those we render the closest
**semantic built-in** and let the **label carry the truth** — exactly how the tutorial uses
the library. To upgrade one to its real logo:

1. Drop a transparent PNG in `src/icons/`, e.g. `kargo.png`.
2. It's already wired: `node(Flagger, "Kargo", icon="kargo.png")` uses the PNG when present,
   else falls back to the built-in. No code change needed — just add the file.

See `_theme.node()`. Keep icons small (≈128–256 px, transparent background).

## CI

`.github/workflows/update-architecture-diagrams.yml` installs Graphviz, runs `make generate`,
and **opens a bot PR if the rendered images changed** — same pattern as the ERD index
(`scripts/gen-erd-index.py`). It is deliberately *not* a hard blocking gate: Graphviz output is
not byte-identical across `dot` versions, so a strict gate would flake on coordinate noise.
`make check` exists for a *local* same-environment drift check. The images are committed so
GitHub Pages serves them without a build-time Graphviz dependency.
