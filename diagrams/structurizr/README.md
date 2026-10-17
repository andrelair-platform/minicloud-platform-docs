# C4 System Design (Structurizr, as code)

The **complete solution-architecture artefact** of the minicloud **Platform**, modelled once as a
[Structurizr](https://structurizr.com/) DSL and rendered to clean [C4-model](https://c4model.com)
diagrams. One source → **System Context → Container → Deployment** views (subsystem *Component* views
and an interactive Structurizr Lite come next). This is the FANG/industry-standard way to communicate
system design, done diagram-as-code (the evolution of the mingrammer `diagrams` approach).

**Boundary:** this models the **Platform** (the internal cloud provider). The **Information System**
(business apps) appears as a single external **consumer** — it gets its own C4 model later.

## Generate

```bash
# needs Docker (pulls structurizr/structurizr + plantuml/plantuml)
make c4        # DSL → PlantUML → SVGs into ../../static/img/c4/
make validate  # validate the DSL only
```

Output: `static/img/c4/structurizr-Context.svg`, `…-Containers.svg`, `…-Deployment.svg` (+ a `-key`
legend per view). Embedded in `docs/architecture/c4-system-design.md`.

## Files

- `workspace.dsl` — the single source of truth: the platform model (people, external systems, the
  platform's containers grouped by capability) + relationships (**verified against the GitOps
  manifests** — no invented edges) + the three views + styles.
- `Makefile` — the export+render pipeline (Docker).

## Editing

Edit `workspace.dsl`, run `make c4`, commit the refreshed SVGs. To add a **subsystem deep-dive** later,
add a `component` view of the relevant container (e.g. the delivery/GitOps pipeline) — the model already
holds the elements. Structurizr DSL reference: <https://docs.structurizr.com/dsl>.
