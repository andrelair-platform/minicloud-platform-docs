#!/usr/bin/env python3
"""
Regenerate the org TRACEABILITY-MATRIX index on the Documentation Standard page — so the "requirement →
component → test → pipeline" matrices self-index, same pattern as gen-adr-index.py (ADR) and
gen-erd-index.py (ERD). No manual per-product step: any repo that commits `docs/traceability-matrix.md`
(or `backend/docs/traceability-matrix.md` for a monorepo) appears on its own.

What it does: enumerate every non-archived repo in the org, read its git tree ONCE, and emit a row for each
repo that commits a traceability matrix — repo · a link to the matrix on GitHub. The content stays with the
code; this page only points at it. The table is written between the TRACE-INDEX markers; everything else is
left untouched.

Run: `python3 scripts/gen-trace-index.py` (needs `gh` authenticated with org read). CI runs it + opens a PR
on drift (.github/workflows/update-trace-index.yml).
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ORG = "andrelair-platform"
SELF = "minicloud-platform-docs"  # the central map repo
PAGE = Path(__file__).resolve().parent.parent / "docs" / "engineering-standards" / "documentation-standard.md"
START, END = "{/* TRACE-INDEX:START */}", "{/* TRACE-INDEX:END */}"
CANDIDATES = ("docs/traceability-matrix.md", "backend/docs/traceability-matrix.md")


def gh_json(args: list[str]):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def repo_tree(repo: str) -> set[str]:
    data = gh_json(["api", f"repos/{ORG}/{repo}/git/trees/HEAD?recursive=1"])
    if not data or "tree" not in data:
        return set()
    return {e["path"] for e in data["tree"] if e.get("type") == "blob"}


def main() -> int:
    repos = gh_json(["repo", "list", ORG, "--limit", "300", "--json", "name,isArchived"]) or []
    rows: list[tuple[str, str]] = []  # (repo, matrix-path)

    for r in sorted(repos, key=lambda x: x["name"]):
        if r.get("isArchived") or r["name"] == SELF:
            continue
        paths = repo_tree(r["name"])
        for cand in CANDIDATES:
            if cand in paths:
                rows.append((r["name"], cand))
                break

    if not rows:
        print("no repos with a committed docs/traceability-matrix.md found — aborting (likely a gh/auth issue)", file=sys.stderr)
        return 1

    header = "| Product | Traceability matrix (click through) |\n|---|---|"
    body = [
        f"| **{name}** | [`{path}`](https://github.com/{ORG}/{name}/blob/main/{path}) |"
        for (name, path) in rows
    ]
    table = "\n".join([header, *body])

    text = PAGE.read_text()
    if START not in text or END not in text:
        print(f"markers {START}/{END} not found in {PAGE}", file=sys.stderr)
        return 1
    pre, rest = text.split(START, 1)
    _, post = rest.split(END, 1)
    new = f"{pre}{START}\n{table}\n{END}{post}"
    if new != text:
        PAGE.write_text(new)
        print(f"updated traceability index: {len(rows)} product(s)")
    else:
        print("traceability index already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
