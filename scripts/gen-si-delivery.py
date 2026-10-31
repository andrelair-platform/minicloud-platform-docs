#!/usr/bin/env python3
"""
Regenerate the **SI Delivery Board** (`docs-is/delivery-board.md`) — the living "what's built vs what's
still to build" view of the ktayl Information System — so it is AUTO-maintained and never hand-curated
(a hand-made snapshot is what went stale on the EA-blueprint gap table). Same shape + CI pattern as
gen-adr-index.py / gen-erd-index.py.

The idea (boards-as-target): three gh-only sources are joined, no cluster access required —
  1. TARGET  = every GitHub product board (`gh project list`). Add a board → it appears here on its own.
  2. CODE    = each board's repo(s) size (`gh repo list`): real code vs scaffold vs no repo.
  3. DEPLOYED= the gitops `apps/**` Application manifests (`gh api .../git/trees`): which domains have a
               dev/prod Application DEFINED (a gh-only proxy for "deployed", with env from the filename).

Per board → a status is derived:
  🟢 live (prod)  · a prod (or singleton) Application is defined
  🔵 dev only     · only a -dev Application is defined
  🔶 in progress  · no Application, but the repo has real content (≥ SCAFFOLD_KB)
  ❌ not started  · no Application and the repo is a scaffold (< SCAFFOLD_KB) or absent
  ⏸ parked        · a deliberate hold (see PARKED)

The BRIDGE map below is the ONLY hand-maintained part (board# → repos + app-name prefixes) and it changes
rarely; a board missing from BRIDGE still shows up (as ❌/🔶 from its repo alone). The tables are written
between the SI-DELIVERY markers on the page; the surrounding prose (intro, legend, drift note) is untouched.

Run: `python3 scripts/gen-si-delivery.py` (needs `gh` authenticated with org read). CI runs it + opens a
PR on drift (.github/workflows/update-si-delivery.yml) weekly + on demand — run it INSTEAD of a manual
gap analysis.
"""
from __future__ import annotations
import csv
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ORG = "andrelair-platform"
GITOPS = "minicloud-gitops"
ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs-is" / "delivery-board.md"
# Canonical capability register (committed, plain-text, VSCode-editable) — the single source of truth.
# The xlsx in B2BAssurance is a derived presentation view. Maturity is read from here and shown honestly:
# "not assessed" until the Maturity % cells are filled (the register is a target schema, not an assessment).
CSV_PATH = ROOT / "data" / "capability-register.csv"
# Domain-level FIRST-PASS maturity (5-dimension rubric per board) — evidence-based ESTIMATES pending owner
# confirmation, NOT a per-capability assessment (which stays in the register, honestly empty). Board# →
# a row with Functional/Process/Integration/Data/Operational (1-5) + a one-line basis.
MATURITY_PATH = ROOT / "data" / "maturity-assessment.csv"
START, END = "{/* SI-DELIVERY:START */}", "{/* SI-DELIVERY:END */}"
SCAFFOLD_KB = 40  # gh diskUsage (KB) below this + no Application ⇒ treat the repo as a scaffold

# board# → how to find its CODE + DEPLOYMENT. `apps` = app-name prefixes to match in gitops apps/**.
# `repos` = member repos (first is the home). flags: parked / external (off-cluster) / platform.
# A board NOT in this map still renders (❌/🔶 from repo alone) — the map only adds deploy fidelity.
BRIDGE: dict[int, dict] = {
    2:  {"repos": ["retrieva", "retrieva-backend", "retrieva-assessment-crew"], "apps": ["retrieva"]},
    3:  {"repos": ["minicloud-gitops", "minicloud-ansible", "minicloud-opentofu", "minicloud-backstage", "minicloud-ops", "platform-demo"], "apps": ["argo-cd", "harbor", "vault", "backstage"], "platform": True},
    4:  {"repos": ["minicloud-agent", "minicloud-crew-agent", "minicloud-open-webui", "minicloud-plane"], "apps": ["minicloud-agent", "minicloud-crew-agent", "litellm", "langfuse", "open-webui"], "platform": True},
    5:  {"repos": ["ktayl-data-platform"], "apps": ["data-platform"]},
    6:  {"repos": ["ktayl-policy-service"], "apps": ["ktayl-policy-service"]},
    7:  {"repos": ["ktayl-solution-web"], "apps": [], "external": "GitHub Pages"},
    8:  {"repos": ["minicloud-erpnext"], "apps": ["erpnext"]},
    9:  {"repos": ["ktayl-solution-web"], "apps": ["ktayl-base"]},
    10: {"repos": ["ktayl-workplace", "minicloud-onlyoffice"], "apps": ["bookstack", "nextcloud", "stalwart", "matrix-synapse", "jitsi", "docuseal", "n8n", "vaultwarden", "plane"]},
    11: {"repos": ["ktayl-claims"], "apps": ["ktayl-claims"]},
    12: {"repos": ["ktayl-underwriting"], "apps": ["ktayl-underwriting"]},
    13: {"repos": ["ktayl-distribution"], "apps": []},
    14: {"repos": ["ktayl-finance"], "apps": []},
    15: {"repos": ["ktayl-compliance"], "apps": []},
    16: {"repos": ["ktayl-itsm"], "apps": ["ktayl-itsm"]},
    17: {"repos": ["ktayl-iam"], "apps": ["ktayl-iam"]},
    18: {"repos": [], "apps": [], "parked": "needs real upstream systems first"},
    19: {"repos": ["ktayl-ai-copilot"], "apps": [], "parked": "needs real upstream systems first"},
    20: {"repos": ["ktayl-mdm"], "apps": [], "parked": "keystone for analytics; deferred"},
    21: {"repos": ["ktayl-risk-engineering"], "apps": []},
    22: {"repos": ["ktayl-reinsurance"], "apps": []},
    23: {"repos": ["ktayl-international-programs"], "apps": []},
    24: {"repos": ["ktayl-dms"], "apps": []},
    25: {"repos": ["ktayl-integration"], "apps": []},
    27: {"repos": ["ktayl-submission"], "apps": []},
    28: {"repos": ["ktayl-core"], "apps": ["ktayl-core"]},
    29: {"repos": ["ktayl-investment"], "apps": ["ktayl-investment"]},    # Investment & Treasury (ALM) — blind-spot 2026-10-30 (repo/app to create)
    30: {"repos": ["ktayl-complaints"], "apps": ["ktayl-complaints"]},    # Complaints & Disputes — blind-spot 2026-10-30 (repo/app to create)
    31: {"repos": ["ktayl-procurement"], "apps": ["ktayl-procurement"]},  # Procurement & Contract Mgmt — blind-spot 2026-10-30 (repo/app to create)
}

ORDER = ["🟢", "🔵", "🔶", "❌", "⏸"]
HEADING = {
    "🟢": "## 🟢 Live — a prod deployment is defined",
    "🔵": "## 🔵 On dev — deployed to dev, not yet promoted to prod",
    "🔶": "## 🔶 In progress — real code, not yet deployed",
    "❌": "## ❌ Not started — scaffold or no repo yet",
    "⏸": "## ⏸ Parked — deliberate hold",
}


def gh_json(args: list[str]):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def load_boards() -> list[dict]:
    data = gh_json(["project", "list", "--owner", ORG, "--limit", "80", "--format", "json"])
    if not data:
        return []
    projects = data.get("projects", data) if isinstance(data, dict) else data
    # skip the template board (#26) and any closed ones
    return sorted((p for p in projects if p.get("number") != 26 and not p.get("closed")),
                  key=lambda p: p["number"])


def load_repo_sizes() -> dict[str, int]:
    repos = gh_json(["repo", "list", ORG, "--limit", "300", "--json", "name,diskUsage,isArchived"]) or []
    return {r["name"]: r.get("diskUsage", 0) for r in repos if not r.get("isArchived")}


def load_app_envs() -> dict[str, set[str]]:
    """app basename (sans .yaml / -dev / -prod) → {'dev','prod','singleton'} from gitops apps/**."""
    tree = gh_json(["api", f"repos/{ORG}/{GITOPS}/git/trees/HEAD?recursive=1"])
    envs: dict[str, set[str]] = {}
    if not tree or "tree" not in tree:
        return envs
    for e in tree["tree"]:
        p = e.get("path", "")
        if not (p.startswith("apps/") and p.endswith(".yaml")):
            continue
        base = p.rsplit("/", 1)[-1][:-5]  # strip .yaml
        if any(x in base for x in ("kargo", "appproject", "project", "-base", "environments", "repos")):
            continue
        if base.endswith("-prod"):
            envs.setdefault(base[:-5], set()).add("prod")
        elif base.endswith("-dev"):
            envs.setdefault(base[:-4], set()).add("dev")
        else:
            envs.setdefault(base, set()).add("singleton")
    return envs


def load_maturity() -> dict[int, tuple[int, int, float | None]]:
    """Per board# → (total_caps, scored_caps, mean_maturity%|None) from the committed capability register.
    A cap counts toward every board# referenced in its `Product Board` cell (e.g. `#17/#3` → both).
    `Maturity %` is read as-is: today it is empty for all 630 (the register is a NOT-ASSESSED target
    schema), so this yields `scored=0` → the board honestly shows "not assessed · N caps" until someone
    fills the cells in the CSV. No number is invented."""
    if not CSV_PATH.exists():
        return {}
    agg: dict[int, list] = {}
    with CSV_PATH.open(newline="") as f:
        for row in csv.DictReader(f):
            nums = {int(n) for n in re.findall(r"#(\d+)", row.get("Product Board") or "")}
            raw = (row.get("Maturity %") or "").strip().rstrip("%")
            try:
                score = float(raw)
            except ValueError:
                score = None
            for n in nums:
                agg.setdefault(n, [0, 0, 0.0])
                agg[n][0] += 1
                if score is not None:
                    agg[n][1] += 1
                    agg[n][2] += score
    return {n: (tot, sc, (s / sc if sc else None)) for n, (tot, sc, s) in agg.items()}


def load_domain_maturity() -> dict[int, int]:
    """board# → first-pass maturity % (mean of the 5 rubric dimensions ×20). {} if the file is absent."""
    if not MATURITY_PATH.exists():
        return {}
    out: dict[int, int] = {}
    dims = ["Functional", "Process", "Integration", "Data", "Operational"]
    with MATURITY_PATH.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                scores = [int(row[d]) for d in dims]
                out[int(row["Board"])] = round(sum(scores) / len(scores) * 20)
            except (ValueError, KeyError):
                continue
    return out


def maturity_cell(num: int, caps: dict[int, tuple[int, int, float | None]],
                  est: dict[int, int]) -> str:
    """First-pass domain estimate if we have one; else the register's (empty) per-cap roll-up as
    'not assessed · N caps' (N = the domain's capability count — the size of the gap)."""
    if num in est:
        return f"~{est[num]}% (est.)"
    m = caps.get(num)
    if not m:
        return "—"
    total, scored, mean = m
    if scored == 0:
        return f"not assessed · {total} caps"
    return f"~{mean:.0f}% · {scored}/{total} scored"


def argo_health() -> dict[str, tuple[str, str]]:
    """OPTIONAL live overlay: app-name → (sync, health) from ArgoCD, {} if the cluster is unreachable
    (e.g. in CI — which is why this never feeds the COMMITTED board, only the `--live` terminal view).
    Tries, in order: local `--context minicloud`, local plain kubectl (the controller's own default), then
    `ssh controller` (the reliable path from the Mac, whose kubeconfig has no minicloud context)."""
    attempts = [
        ["kubectl", "--context", "minicloud", "-n", "argocd", "get", "applications", "-o", "json"],
        ["kubectl", "-n", "argocd", "get", "applications", "-o", "json"],
        ["ssh", "controller", "kubectl -n argocd get applications -o json"],
    ]
    for cmd in attempts:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            continue
        try:
            items = json.loads(r.stdout).get("items", [])
        except json.JSONDecodeError:
            continue
        if items:
            return {a["metadata"]["name"]: (a.get("status", {}).get("sync", {}).get("status", "?"),
                                            a.get("status", {}).get("health", {}).get("status", "?"))
                    for a in items}
    return {}


def classify(cfg: dict, sizes: dict[str, int], app_envs: dict[str, set[str]]):
    """→ (glyph, evidence_str, matched_app_names)."""
    if cfg.get("parked"):
        return "⏸", f"parked — {cfg['parked']}", []
    # collect envs across this board's app prefixes
    envs: set[str] = set()
    hit_apps: list[str] = []
    for app, es in app_envs.items():
        if any(app == pre or app.startswith(pre) for pre in cfg.get("apps", [])):
            envs |= es
            hit_apps.append(app)
    hits = sorted(set(hit_apps))
    repos = cfg.get("repos", [])
    sized = [(r, sizes.get(r)) for r in repos if r in sizes]
    biggest = max((s or 0) for _, s in sized) if sized else 0

    if cfg.get("external"):
        return "🟢", f"live off-cluster ({cfg['external']})", []
    if "prod" in envs or "singleton" in envs:
        env_note = "dev+prod" if "dev" in envs else "prod"
        return "🟢", f"{env_note} · apps: {', '.join(hits[:4])}", hits
    if "dev" in envs:
        return "🔵", f"dev · apps: {', '.join(hits[:4])}", hits
    if biggest >= SCAFFOLD_KB:
        return "🔶", f"repo has content ({biggest} KB), no Application yet: {repos[0] if repos else '—'}", []
    if repos and biggest > 0:
        return "❌", f"scaffold repo ({biggest} KB): {repos[0]}", []
    if repos:
        return "❌", f"repo not found / empty: {repos[0]}", []
    return "❌", "no repo yet", []


def health_cell(apps: list[str], health: dict[str, tuple[str, str]]) -> str:
    """Summarise live ArgoCD sync/health for a board's matched apps (for the --live overlay). `apps` are
    de-suffixed manifest stems (e.g. `retrieva`); live app names carry the env suffix (`retrieva-dev`,
    `retrieva-prod`) — so match a live app when its name == the stem or starts with `<stem>-`."""
    seen: dict[str, tuple[str, str]] = {}
    for stem in apps:
        for name, sh in health.items():
            if name == stem or name.startswith(stem + "-"):
                seen[name] = sh
    if not seen:
        return "—"
    bad = [f"{a}:{s}/{h}" for a, (s, h) in sorted(seen.items()) if not (s == "Synced" and h == "Healthy")]
    return "✓ Synced/Healthy" if not bad else "⚠ " + "; ".join(bad[:3])


def main() -> int:
    live = "--live" in sys.argv
    boards = load_boards()
    if not boards:
        print("no boards from `gh project list` — aborting (gh/auth/scope issue)", file=sys.stderr)
        return 1
    sizes = load_repo_sizes()
    app_envs = load_app_envs()
    if not app_envs:
        print("warning: no gitops apps/** read — deploy status will be degraded", file=sys.stderr)
    maturity = load_maturity()
    est = load_domain_maturity()
    show_mat = bool(maturity or est)
    if not show_mat:
        print("warning: no capability register / maturity assessment found — maturity column omitted", file=sys.stderr)
    health = argo_health() if live else {}
    if live and not health:
        print("warning: --live could not reach ArgoCD (no cluster access) — showing declared status only",
              file=sys.stderr)

    rows: dict[str, list[tuple[int, str, str, list[str]]]] = {g: [] for g in ORDER}
    counts: dict[str, int] = {g: 0 for g in ORDER}
    for b in boards:
        num, title = b["number"], b["title"]
        cfg = BRIDGE.get(num, {"repos": [], "apps": []})
        glyph, evidence, hits = classify(cfg, sizes, app_envs)
        rows[glyph].append((num, title, evidence, hits))
        counts[glyph] += 1

    summary = " · ".join(f"{g} {counts[g]}" for g in ORDER if counts[g])

    # --live: print an enriched view to STDOUT and exit WITHOUT writing the committed page
    # (CI has no cluster, so live health must never land in the committed, CI-regenerated file → no drift).
    if live:
        print(f"SI Delivery Board — LIVE ({date.today().isoformat()})   {summary}")
        for g in ORDER:
            if not rows[g]:
                continue
            print(f"\n{HEADING[g].lstrip('# ')}")
            for num, title, evidence, hits in sorted(rows[g]):
                h = f"   [{health_cell(hits, health)}]" if (hits and health) else ""
                mat = f"   {{{maturity_cell(num, maturity, est)}}}" if show_mat else ""
                print(f"  {g} #{num:<3} {title:<46} {evidence}{mat}{h}")
        if not health:
            print("\n(live health unavailable — ran without cluster access; the COMMITTED page is unchanged)")
        return 0
    out: list[str] = [
        f"_Auto-generated {date.today().isoformat()} by `scripts/gen-si-delivery.py` from the live GitHub "
        f"product boards + the gitops `apps/**` manifests + repo sizes — do not hand-edit between the markers._",
        "",
        f"**At a glance:** {summary}  (of {len(boards)} product boards)",
        "",
    ]
    for g in ORDER:
        if not rows[g]:
            continue
        mat_hdr = " Maturity |" if show_mat else ""
        mat_sep = "---|" if show_mat else ""
        out += [HEADING[g], "", f"| Board | Domain |{mat_hdr} Evidence |", f"|---|---|{mat_sep}---|"]
        for num, title, evidence, _ in sorted(rows[g]):
            link = f"[#{num}](https://github.com/orgs/{ORG}/projects/{num})"
            mat = f" {maturity_cell(num, maturity, est)} |" if show_mat else ""
            out.append(f"| {link} | {title} |{mat} {evidence} |")
        out.append("")

    table = "\n".join(out).rstrip()
    text = PAGE.read_text()
    if START not in text or END not in text:
        print(f"markers {START}/{END} not found in {PAGE}", file=sys.stderr)
        return 1
    pre, rest = text.split(START, 1)
    _, post = rest.split(END, 1)
    new = f"{pre}{START}\n{table}\n{END}{post}"
    if new != text:
        PAGE.write_text(new)
        print(f"updated SI Delivery Board: {summary} across {len(boards)} boards")
    else:
        print("SI Delivery Board already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
