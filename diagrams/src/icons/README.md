# Brand icons (optional)

Drop transparent PNG logos here for components that have **no built-in `diagrams` icon**, then
reference them via the `icon=` argument of `node()` in a diagram module — e.g. a file
`kargo.png` here makes `node(Flagger, "Kargo", icon="kargo.png")` render the real Kargo logo
instead of the semantic fallback.

Guidance:
- Transparent background, roughly 128–256 px square.
- Name the file after the component referenced in `icon=` (`authentik.png`, `longhorn.png`, …).
- Until a logo is added, the diagram still renders — the built-in fallback + label is used.

Most logos are vendored by `fetch-icons.sh` (GitHub org avatars + CNCF artwork). Components still
on a built-in **fallback** (no icon file): `cloudflared` (Cloudflare edge still uses its built-in
icon), `presidio`, `homer`, `velero`. Add any of these by dropping a PNG here with the matching name.
