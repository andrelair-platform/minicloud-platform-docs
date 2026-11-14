#!/usr/bin/env python3
"""
Regenerate the org SERVICE-READINESS scorecard on the central docs page — so "is this repo on the golden
path / production-ready?" is a self-service, always-current view instead of tribal knowledge. The 5th
self-maintaining index (after ADR / ERD / traceability / SI-delivery); same shape + rationale as
gen-adr-index.py: enumerate every non-archived org repo, read its git tree ONCE, score it against the
repo-standardization + golden-path rubric, and emit a table between the SCORECARD markers on the page.

It ALSO writes a machine-readable JSON (static/data/readiness-scorecard.json) with the per-repo facts, so
the SAME rubric feeds a second surface (the Backstage tech-insights scorecard cards) without re-implementing
the scoring in TypeScript — Backstage's fact retriever just fetches this JSON.

The rubric (8 scored criteria — the standardize-new-repo baseline, checkable from the git tree; presence,
not quality — a `tests/` dir doesn't prove coverage, it proves the repo is wired for the layer):
  readme · license · contributing · ci (.github/workflows) · catalog-info · release-please · tests · docs/
Plus two INFORMATIONAL deployment columns (not part of the /8 score, since not every repo deploys), read
from the minicloud-gitops tree: Helm wrapper chart (services/<repo>/helm) and Kargo (services/<repo>/kargo).

Scaffold/infra repos legitimately score low — that is the point: the scorecard surfaces the gap honestly.

Run: `python3 scripts/gen-readiness-scorecard.py` (needs `gh` authenticated with org read). CI runs it +
opens a PR on drift (.github/workflows/update-readiness-scorecard.yml). No manual per-repo step.
"""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ORG = "andrelair-platform"
SELF = "minicloud-platform-docs"      # the central map repo — don't score itself
GITOPS = "minicloud-gitops"           # holds services/<svc>/{helm,kargo} deployment config
ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "engineering-standards" / "service-readiness.md"
JSON_OUT = ROOT / "static" / "data" / "readiness-scorecard.json"
START, END = "{/* SCORECARD:START */}", "{/* SCORECARD:END */}"

# The 8 scored criteria, in display order: (key, column header).
RUBRIC = [
    ("readme", "README"),
    ("license", "LICENSE"),
    ("contributing", "CONTRIB"),
    ("ci", "CI"),
    ("catalog", "Catalog"),
    ("release", "Release"),
    ("tests", "Tests"),
    ("docs", "Docs"),
]

TEST_SUFFIXES = ("_test.go", "_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")


def gh_json(args: list[str]):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def repo_tree(repo: str) -> list[str]:
    """All committed blob paths in the default branch (one API call); [] if unreadable."""
    data = gh_json(["api", f"repos/{ORG}/{repo}/git/trees/HEAD?recursive=1"])
    if not data or "tree" not in data:
        return []
    return [e["path"] for e in data["tree"] if e.get("type") == "blob"]


def has_test(paths: list[str]) -> bool:
    for p in paths:
        segs = p.split("/")
        if "tests" in segs[:-1] or "test" in segs[:-1]:
            return True
        name = segs[-1]
        if name.startswith("test_") and name.endswith(".py"):
            return True
        if name.endswith(TEST_SUFFIXES):
            return True
    return False


def score_repo(paths: list[str]) -> dict:
    s = set(paths)
    return {
        "readme": "README.md" in s,
        "license": "LICENSE" in s or "LICENSE.md" in s,
        "contributing": "CONTRIBUTING.md" in s,
        "ci": any(p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml")) for p in paths),
        "catalog": "catalog-info.yaml" in s,
        "release": "release-please-config.json" in s,
        "tests": has_test(paths),
        "docs": any(p.startswith("docs/") for p in paths),
    }


def tick(b: bool) -> str:
    return "✅" if b else "⬜"


def main() -> int:
    repos = gh_json(["repo", "list", ORG, "--limit", "300", "--json", "name,isArchived"]) or []
    if not repos:
        print("no repos returned — aborting (likely a gh/auth issue)", file=sys.stderr)
        return 1

    # One read of the gitops tree → which repos have a Helm wrapper chart / a Kargo pipeline.
    gitops_paths = repo_tree(GITOPS)
    helm_svcs = {p.split("/")[1] for p in gitops_paths if p.startswith("services/") and "/helm/" in p}
    kargo_svcs = {p.split("/")[1] for p in gitops_paths if p.startswith("services/") and "/kargo/" in p}

    results: dict[str, dict] = {}
    for r in sorted(repos, key=lambda x: x["name"]):
        if r.get("isArchived") or r["name"] in (SELF, GITOPS):
            continue
        name = r["name"]
        facts = score_repo(repo_tree(name))
        facts["score"] = sum(1 for k, _ in RUBRIC if facts[k])
        facts["max"] = len(RUBRIC)
        facts["helm"] = name in helm_svcs
        facts["kargo"] = name in kargo_svcs
        results[name] = facts

    if not results:
        print("no repos scored — aborting", file=sys.stderr)
        return 1

    # JSON artifact (feeds the Backstage tech-insights fact retriever) — single source of truth.
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rubric": [k for k, _ in RUBRIC],
        "repos": results,
    }, indent=2) + "\n")

    # Markdown table — highest score first (production services lead; scaffold/infra gaps trail; ties by name).
    headers = ["Repo", "Score"] + [h for _, h in RUBRIC] + ["Deploy"]
    sep = ["---"] * len(headers)
    rows = []
    for name in sorted(results, key=lambda n: (-results[n]["score"], n)):
        f = results[name]
        deploy = "🚀 Kargo" if f["kargo"] else ("Helm" if f["helm"] else "—")
        cells = [f"**{name}**", f"{f['score']}/{f['max']}"] + [tick(f[k]) for k, _ in RUBRIC] + [deploy]
        rows.append("| " + " | ".join(cells) + " |")
    table = "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(sep) + " |", *rows])

    text = PAGE.read_text()
    if START not in text or END not in text:
        print(f"markers {START}/{END} not found in {PAGE}", file=sys.stderr)
        return 1
    pre, rest = text.split(START, 1)
    _, post = rest.split(END, 1)
    new = f"{pre}{START}\n{table}\n{END}{post}"
    changed = new != text
    if changed:
        PAGE.write_text(new)
    print(f"scored {len(results)} repo(s); page {'updated' if changed else 'already current'}; JSON → {JSON_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
