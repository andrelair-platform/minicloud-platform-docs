---
id: platform-access-matrix
title: Platform Access Matrix (role × tool enforcement)
sidebar_label: Platform Access Matrix
---

# Platform Access Matrix — role × tool enforcement

> **What this is:** the **Platform-layer enforcement map** for the engineering tools — *for each tool,
> which role gets what, and the mechanism that enforces it* (native RBAC vs SSO-gate) + the wiring recipe.
> It is **NOT** the source of truth for the roles themselves.
>
> **The source of truth is `ktayl-iam`** (Access Governance / IGA, board #17). Its catalog models
> `application → role → authentik_group_ref` and its [Access Role & Tier Model (IGA-02)](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/access-role-model.md)
> defines the personas, groups and the entitlement matrix. Authentik is the runtime **enforcement point**
> (the OIDC `groups` claim / forward-auth); ktayl-iam is the **governance** system that runs
> request → approval → provision and writes the Authentik groups. This page implements that model at the
> tool level — it **consumes** ktayl-iam's group names, it never mints its own.
>
> **Status (2026-11-17):** tools **registered in the ktayl-iam catalog** (PR #77). **Native RBAC live on
> Grafana · ArgoCD · Backstage**, each bound to the canonical groups, and **verified end-to-end with a
> real second identity** (see *Verification (live)* below). SSO-gate of the binary tools (wave 3) + the
> ktayl-iam provisioning engine (wave 4) remain; Vault + Kargo are blocked on prerequisites (below).

## Concepts — SoR, PEP, and the two "segregations"

Three terms used throughout this page (and across our IAM work):

- **SoR — System of Record.** The *one* authoritative place a fact officially lives; if two systems
  disagree, the SoR wins by definition. Here the **ktayl-iam catalog** (`application → role → group`) is
  the SoR for *who may access what* — it **decides and records** the entitlement.
- **PEP — Policy Enforcement Point.** The thing that *enforces* the decision at runtime but does **not**
  own it. Here **Authentik** is the PEP — it checks group membership at login (the OIDC `groups` claim /
  forward-auth). This matrix is neither: it is a **map** that *consumes* the SoR's group names and records
  how each tool enforces them.

**Two different "segregation" controls — do not conflate them:**

| Control | Question it answers | Status here |
|---|---|---|
| **Segregation of privilege** (least privilege) | can a *lower tier* do a *higher tier's* action? → **no** (Developer → Viewer, not Admin) | ✅ **proven live** (see *Verification*) |
| **Segregation of Duties (SoD)** | can *one person* hold two *conflicting duties*? e.g. **request** AND **approve** their own access → **no** (maker ≠ checker) | 🔵 a **ktayl-iam governance control** — its request → **dual-approval** → provision flow (access-role-model IGA-05); **planned, not yet exercised** in this rollout |

SoD is an **anti-fraud / anti-collusion** control, not a "read vs write" control — it will be enforced by
the ktayl-iam approval engine (wave 4), *separately* from the privilege tiers wired here.

## The one distinction that shapes everything: native RBAC vs SSO-gate

Not every tool can express "DevOps can sync but not delete." Tools fall into two classes, and the plan
treats them differently (this is the layer ktayl-iam's model §4 leaves to the tool):

| Class | Meaning | Granularity | How a role maps |
|---|---|---|---|
| **Native RBAC** | the tool has its own role model it can drive from the OIDC `groups` claim | fine (per-action) | a **per-app group** `ktayl-<app>-<level>` → a native role |
| **SSO-gated (binary)** | the tool only knows "logged in or not" (forward-auth / basic OIDC) | coarse (reach or not) | the Authentik **application↔group** binding decides *who can open it at all* |

**Native-RBAC tools:** ArgoCD · Kargo · Grafana · Vault · Backstage.
**SSO-gated (binary) tools:** Prometheus · Alertmanager · Hubble · Polaris · NATS monitor · MLflow ·
Flowise · Langfuse · Open WebUI · n8n · Temporal (most observability + AI UIs).

For a binary tool, "scoped access" means *is this role allowed to open it* — enforced by the Authentik
app policy, not an in-app role. Pretending otherwise is the trap; this page is honest about which is which.

## The roles → Authentik groups (ktayl-iam canonical — do not invent new names)

The engineering personas are ktayl-iam's [access-role-model §2](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/access-role-model.md).
Graded native-RBAC tools add a **per-app group**; `ktayl-engineering` is the umbrella "any engineer"
group that gates the binary tools.

| Role | Base Authentik group | Per-app groups it holds | Intent |
|---|---|---|---|
| **Admin** | `ktayl-admin` | all `ktayl-*-admin` | break-glass; full everywhere (owner `100001` is a member) |
| **DevOps / Platform Eng** | `ktayl-devops` | `ktayl-argocd-admin` · `ktayl-kargo-admin` · `ktayl-vault-admin` · `ktayl-observability-admin` | operates + owns the platform: deploy/promote, secrets, observe |
| **Developer** | `ktayl-developer` | `ktayl-kargo-readonly` · `ktayl-argocd-readonly` · `ktayl-observability-viewer` | builds apps: self-service golden paths, reads own |
| **SRE** | `ktayl-sre` | `ktayl-observability-admin` · `ktayl-kargo-promoter` | reliability: dashboards, alerts, incident promotion |
| *(Viewer)* | *(no base persona)* | per-app `…-viewer`/`…-readonly` only | read-only is expressed per-app, not as a base persona (honest to the SoR) |

> **`ktayl-admin` (owner 100001) is already full-access** — it is also a member of `Platform Admins` /
> `authentik Admins` / `k8s-cluster-admins`, so no action is needed to give it "everything". The work
> below is about the *other* roles. **DevOps and "Platform Engineering" are one persona** in the SoR
> (`ktayl-devops` = "DevOps / Platform engineer") — this page does **not** re-split them.

## The matrix

`full` = admin-equivalent · `edit`/`sync`/`promote` = operate · `read`/`view` = read-only · `—` = no access.
**(N)** = native RBAC · **(G)** = SSO-gate (binary: reach or not). Columns are the ktayl-iam personas; the
entitlement truth is [access-role-model §3](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/access-role-model.md) — this table adds the **enforcement mechanism**.

| Tool | class | Admin (`ktayl-admin`) | DevOps (`ktayl-devops`) | Developer (`ktayl-developer`) | SRE (`ktayl-sre`) |
|---|---|---|---|---|---|
| **ArgoCD** | N | full | sync + read (`ktayl-argocd-admin`) | read (`ktayl-argocd-readonly`) | read |
| **Kargo** | N | full (`ktayl-kargo-admin`) | full | read (`ktayl-kargo-readonly`) | promote (`ktayl-kargo-promoter`) |
| **Backstage** ✅ | N | full (`ktayl-admin`) | scaffold + refresh | scaffold + read (`ktayl-developer`) | read |
| **Grafana** | N | Admin (`ktayl-observability-admin`) | Admin | Viewer (`ktayl-observability-viewer`) | Admin |
| **Vault** | N | full (`ktayl-vault-admin`) | admin | — | read (`ktayl-vault-readonly`) |
| **Prometheus / Alertmanager** | G | ✓ | ✓ | ✓ | ✓ |
| **Hubble / Polaris / NATS** | G | ✓ | ✓ | read | ✓ |
| **MLflow / Langfuse / Flowise / Open WebUI** | G | ✓ | ✓ | ✓ | ✓ |
| **n8n / Temporal** | G | ✓ | ✓ | — | ✓ |

(The IS **business** apps — ERPNext, Nextcloud, Matrix, Plane, Docuseal… — are a **separate** matrix:
*business* personas (`ktayl-business`, `ktayl-data`) × *IS* apps, governed by the same ktayl-iam model /
the Digital Workplace, not this engineering matrix.)

## How each native-RBAC tool is wired (the implementation recipe)

- **ArgoCD** — `argocd-rbac-cm`: `policy.csv` with `g, ktayl-argocd-admin, role:admin` + custom roles
  (`p, role:devops, applications, sync, */*, allow`). OIDC groups already flow (`scopes: [groups]`).
- **Kargo** — Kargo RBAC (`Role`/`RoleBinding` per Project, subject = the OIDC group claim, e.g.
  `ktayl-kargo-promoter`); prod Stage stays CODEOWNERS-gated regardless.
- **Grafana** — `auth.generic_oauth` `role_attribute_path` (JMESPath over the groups claim:
  `ktayl-observability-admin` → `GrafanaAdmin`, else `ktayl-observability-viewer` → `Viewer`). One values change.
- **Vault** — OIDC auth role → an external **group alias** per Authentik group (`ktayl-vault-admin` /
  `ktayl-vault-readonly`) → a Vault **policy** (admin / app-read).
- **Backstage** ✅ — the `PermissionPolicy` reads the groups claim; its `permission.rbac` was **repointed
  to the canonical groups** (`group:default/ktayl-admin` + `group:default/ktayl-developer`, keeping
  `user:default/kanmegnea` as a break-glass fallback) — the pre-SoR `platform-admins`/`developers` drift
  is closed (live `[rbac] enforcing — admins=2, developerGroups=1`).

## How SSO-gated tools are scoped (the only lever)

For every **(G)** tool, access = *can this group open the app*, set once per app in Authentik: the
**Application → Policy binding** on the `ktayl-engineering` umbrella group (the §4 layer-3 binding, exactly
the pattern used for the two Homer portals). A tool with no in-app roles gets **all-or-nothing by group** —
that is the honest ceiling until/unless the tool grows real RBAC. No per-tool group is minted until a real
"this tool but not that one" need appears (need-first).

## Execution plan (by waves)

| Wave | Scope | Tools | Effort |
|---|---|---|---|
| **0 ✅ done** | Register tools in the ktayl-iam catalog | all | migration `SeedPlatformToolsCatalog` (PR #77) |
| **1 ✅ done** | Native-RBAC, highest value | Grafana · ArgoCD | canonical groups → native roles; **live + verified** (Grafana `role_attribute_path`, ArgoCD `policy.csv`) |
| **2 ◑ partial** | Native-RBAC, delivery + Backstage SoR align | Backstage ✅ · Vault · Kargo | Backstage `permission.rbac` repointed ✅. **Vault** needs break-glass root (OIDC not gitops-managed); **Kargo** needs Authentik OIDC login stood up first (it's admin/PAT only) |
| **3** | SSO-gate the binary tools | Prometheus/Alertmanager/Hubble/Polaris/NATS/MLflow/Langfuse/Flowise/Open WebUI/n8n/Temporal | one Authentik app↔`ktayl-engineering` binding each (`bind-app-group.sh`). The 3 native-RBAC tools are **already reach-bound** to `ktayl-engineering` |
| **4** | Governance lifecycle | all | ktayl-iam S005 sync engine **provisions** group membership + request→approval replaces manual membership — **and enforces SoD** (requester ≠ approver) |

**Pre-reqs (one-time, owned by ktayl-iam / Authentik):** create the Authentik groups the catalog names
(`ktayl-devops`, `ktayl-developer`, `ktayl-sre`, `ktayl-engineering`, and the per-app `ktayl-<app>-<level>`)
— until the S005 sync engine does this automatically, membership is set by hand (the
[access-role-model §5 interim](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/access-role-model.md)).
Attach each app's **groups scope-mapping** where a native-RBAC tool needs the claim (as was done for Backstage).
Then each wave is independent and reversible.

## Verification (live — real second identity)

Admin `100001` is admin-everywhere, so tier isolation can't be proven with it alone. A **standing QA
identity `ktayl-dev-demo`** (in `ktayl-developer` for the role tier + `ktayl-engineering` for reach) was
created for exactly this — the reusable primitive for verifying any tool's access tier.

- **Grafana — definitive.** A full OIDC login as `ktayl-dev-demo` → Grafana's own `grafanaBootData.user`
  reported **`orgRole = "Viewer"`, `isGrafanaAdmin = false`**. So `ktayl-developer` → **Viewer, not Admin**:
  the whole chain is proven — Authentik emits the `groups` claim → the `ktayl-engineering` binding grants
  *reach* → `role_attribute_path` maps the group to Viewer. *This is **segregation of privilege**, demonstrated.*
- **ArgoCD / Backstage — reach authorized, policy live.** Authentik **authorized** `ktayl-dev-demo` for
  both (the login proceeded past the `ktayl-engineering` binding); the policies are live (`g,
  ktayl-developer, role:readonly`; Backstage enforcing with `developerGroups=[ktayl-developer]`). The
  *automated* browser couldn't finish the click-through — ArgoCD serves a **self-signed passthrough cert**
  and Backstage uses **popup-OAuth** (both are test-harness quirks, not access failures) — they verify in
  a normal CA-trusting browser.

> Reminder: this proves **segregation of privilege** (a Viewer cannot act as an Admin), **not** SoD.
> **Segregation of Duties** (requester ≠ approver) is a separate ktayl-iam governance control, planned for
> the provisioning engine (wave 4).

## Principles

- **One source of truth (SoR)** — roles + entitlements live in ktayl-iam's catalog; this page only records
  the per-tool enforcement. Never invent a group name here.
- **Identity is the perimeter** — every tool SSO-gated behind Authentik; the group claim drives role.
- **Least privilege, graded** — read < operate < manage < admin; a role only gains what its job needs.
- **Prod stays double-gated** — RBAC never loosens the CODEOWNERS/Kargo prod gate (`gitops.md`).
- **Honest ceilings** — a binary tool cannot do per-action RBAC; say so, don't fake it.
- **Need-first** — don't mint a per-tool reach group or a `Security` role before a real second user.

Related: [SSO (Authentik)](./02-sso-authentik.md) · [IAM Hardening](./11-iam-hardening.md) ·
[RBAC Audit](./16-rbac-audit.md) · [ktayl-iam access-role-model (SoR)](https://github.com/andrelair-platform/ktayl-iam/blob/main/docs/access-role-model.md).
