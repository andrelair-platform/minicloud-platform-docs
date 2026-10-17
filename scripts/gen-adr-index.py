#!/usr/bin/env python3
"""
Regenerate the org DECISION-RECORD (ADR) index on the central docs page — so the house rule "every repo
ADR has a pointer on the central map" (documentation.md) is AUTO-maintained, never hand-curated. Same
shape + rationale as gen-erd-index.py (the ERD index).

What it does: enumerate every non-archived repo in the org, read its git tree ONCE, and emit a row for
each committed decision record — repo · title (derived from the filename) · a link to the source file on
GitHub (the content stays with the code; this page only points at it). The table is written between the
ADR-INDEX markers on the page; everything else is left untouched.

Definition of a decision record (kept deliberately simple + transparent — it's documented on the page):
  • a TOP-LEVEL `docs/*.md` file (the flat-ADR convention this platform uses), OR
  • any `*.md` under an `adr/` or `decisions/` directory inside a repo's `docs/` (the adr-dir convention).
Excluded: the central docs repo itself (it IS the map), `docs/data-model/**` (the ERD index's job),
`docs/templates/**`, `**/postmortems/**` (incident reports, not decisions), and README/index/intro/
CHANGELOG/_category_ files.

Run: `python3 scripts/gen-adr-index.py` (needs `gh` authenticated with org read). CI runs it + opens a
PR on drift (.github/workflows/update-adr-index.yml). No manual per-repo step → a new ADR appears here
on its own.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ORG = "andrelair-platform"
SELF = "minicloud-platform-docs"  # the central map repo — never index its own docs/
PAGE = Path(__file__).resolve().parent.parent / "docs" / "engineering-standards" / "decision-records.md"
START, END = "{/* ADR-INDEX:START */}", "{/* ADR-INDEX:END */}"

SKIP_NAMES = {"readme", "index", "intro", "changelog", "_category_"}
EXCLUDE_SEGMENTS = ("docs/data-model/", "docs/templates/", "/postmortems/", "/data-model/")
# strict "decision records" scope — drop scratch/status/setup docs (not decisions), keeping ADRs,
# architecture, PRDs, briefs, sprint plans + retrospectives. Matched as substrings of the kebab filename.
DENY_SUBSTRINGS = ("setup", "completion", "complete", "enhancements", "week", "project-context")


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


def title_from(path: str) -> str:
    """Human title from the filename: strip dir + .md + a leading NN- numeric prefix; kebab → Title."""
    stem = path.rsplit("/", 1)[-1][:-3]  # drop .md
    if "-" in stem and stem.split("-", 1)[0].isdigit():
        stem = stem.split("-", 1)[1]  # drop a leading `03-` ordering prefix
    return " ".join(w.capitalize() for w in stem.replace("_", "-").split("-"))


def is_decision_record(path: str) -> bool:
    if not path.endswith(".md"):
        return False
    if any(seg in path for seg in EXCLUDE_SEGMENTS):
        return False
    name = path.rsplit("/", 1)[-1][:-3].lower()
    if name in SKIP_NAMES:
        return False
    kebab = name.replace("_", "-")
    if any(bad in kebab for bad in DENY_SUBSTRINGS):
        return False
    parts = path.split("/")
    # flat convention: exactly docs/<file>.md
    if len(parts) == 2 and parts[0] == "docs":
        return True
    # adr-dir convention: any .md under an adr/ or decisions/ dir inside docs/
    if parts[0] == "docs" and ("adr" in parts[:-1] or "decisions" in parts[:-1]):
        return True
    return False


def main() -> int:
    repos = gh_json(["repo", "list", ORG, "--limit", "300", "--json", "name,isArchived"]) or []
    # rows grouped by repo → [(repo, [(title, path), ...]), ...]
    by_repo: dict[str, list[tuple[str, str]]] = {}

    for r in sorted(repos, key=lambda x: x["name"]):
        if r.get("isArchived") or r["name"] == SELF:
            continue
        name = r["name"]
        records = [(title_from(p), p) for p in repo_tree(name) if is_decision_record(p)]
        if records:
            by_repo[name] = sorted(records, key=lambda t: t[1])

    if not by_repo:
        print("no repos with committed decision records found — aborting (likely a gh/auth issue)", file=sys.stderr)
        return 1

    header = "| Repo | Decision record | Source (click through) |\n|---|---|---|"
    body: list[str] = []
    total = 0
    for repo in sorted(by_repo):
        for i, (title, path) in enumerate(by_repo[repo]):
            total += 1
            repo_cell = f"**{repo}**" if i == 0 else ""  # show the repo once per group
            link = f"[`{path}`](https://github.com/{ORG}/{repo}/blob/main/{path})"
            body.append(f"| {repo_cell} | {title} | {link} |")
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
        print(f"updated ADR index: {total} decision record(s) across {len(by_repo)} repo(s)")
    else:
        print("ADR index already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
