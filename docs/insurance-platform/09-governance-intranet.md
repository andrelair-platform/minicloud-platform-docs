---
id: governance-intranet
title: Governance Framework & Intranet (BookStack) — scoping
sidebar_label: 🏛 Governance Framework & Intranet
sidebar_position: 9
---

# Governance Framework & Intranet — Scoping

:::note Status
🟡 **Scoping (design only — nothing deployed).** Path-C design for the insurer's **governance corpus**
(policies → standards → guidelines → procedures → runbooks) and the **intranet** that serves it to staff.
Owner decisions at the end. Companions: [Regulatory Operating Model](./regulatory-operating-model) ·
[Capability Map](./capability-map) · [System-of-Record](./system-of-record) · [HR Tooling](./hr-tooling) ·
obligations register (`ktayl-compliance/docs/obligations-register.md`).
:::

## 1. The gap (and why it matters)

The IS has built the **business domains** (Underwriting, Claims, Policy…) but not the **governance layer**
that frames them, nor the **intranet** staff consult to do their work. This is **Solvency II Pillar 2** (the
system of governance: written policies, delegation of authority, four-eyes, ORSA, internal control), plus
**IDD** product governance, **DORA** ICT governance, and the **ACPR** written-policy expectations. It is
direct **certification evidence for BC01 (piloter)** and **BC03 (déployer & sécuriser)**.

Today only fragments exist: the obligations register (#15), the AI-Act gate, the internal-control loop
*concept*, and — notably — **ktayl-underwriting already executes guidelines** (appetite / eligibility /
referral / rating). The full framework (the ~40 guideline types, the policy hierarchy) does not exist, and
there is **no intranet** (the self-hosted SharePoint/Viva equivalent is the one missing Digital-Workplace piece).

## 2. The model — two layers, not either/or

- **Intranet = the human, readable layer** (the SharePoint-equivalent): one internal portal where **every
  audience** consults what it needs — business lines (UW/Claims/Pricing/Risk-Eng/Reinsurance guidelines),
  **HR** (charte de travail, règlement intérieur, onboarding), **Legal** (contract templates, legal notes),
  and **Governance/Compliance** (Solvency II policies, procedures). This is the source of truth people read.
- **Executable layer = a complement** for the highest-value rules: a subset of the guidelines is also encoded
  as **policy-as-code / decision services** consumed by the business workflows (e.g. when an underwriter opens
  a submission, the system surfaces the applicable guidelines and enforces referral/DoA/pricing-floors).
  ktayl-underwriting already proves this. **The intranet stays the truth; the workflows execute its critical rules.**

> The anti-pattern is **dead, unversioned PDFs nobody reads** — not an intranet. A real intranet (searchable,
> versioned, role-owned, SSO-gated) is exactly the right human layer.

## 3. Positioning in the portfolio

| Concern | Home |
|---|---|
| **The intranet itself** (the tool / container) | **Digital Workplace #10** (M365-alternative stack) |
| **The governance corpus** (authoring, approval, review, audit) | **Compliance & Legal #15** |
| **Executable rules** (a subset) | the owning domain service (UW first) + the Backstage capability registry |

## 4. Tool decision — BookStack

**BookStack** (self-hosted open-source wiki/intranet) — chosen over reusing Nextcloud or adopting Outline.
- **Structure fits a multi-audience policy intranet:** **Shelves → Books → Chapters → Pages**, so each
  function owns a shelf (RH, Juridique, Underwriting, Claims…) and the policy hierarchy maps to books/pages.
- **Per-space permissions** (role-based) → HR, Legal and each business line own and gate their own space.
- **OIDC (Authentik) SSO**, full-text search, page **versioning/history**, WYSIWYG + markdown — light to run.
- **Build-vs-buy:** adopt (open-source, self-hosted) — consistent with the M365-alternative philosophy and the
  *need-first* rule; no bespoke build. (Nextcloud-reuse = zero new infra but weaker structure/permissions;
  Outline = nicer UX but heavier: Node+Postgres+Redis+S3.)

## 5. Target architecture (how BookStack lands on the platform)

- **Deploy:** GAP wrapper chart / Helm → ArgoCD (single prod instance → no Kargo). Browser-first, **SSO-gated
  via Authentik** (OIDC), consistent with the platform's browser-first / BYOD workplace architecture (device
  untrusted; identity is the perimeter; group-gated, not "any authenticated user").
- **⚠️ Datastore caveat:** BookStack requires **MySQL/MariaDB**, *not* Postgres — so it needs a **MariaDB**
  instance (the platform standard is CNPG/Postgres). Deploy a small dedicated MariaDB (or reuse one); this is
  an explicit deviation to record in an ADR.
- **Access model:** Authentik **groups → BookStack roles**, per shelf (e.g. `Direction RH` → RH shelf editor;
  `Underwriting` → UW shelf reader/editor). Membership lifecycle governed by `ktayl-iam`.
- **Exposure:** internal (`intranet.10.0.0.200.nip.io`) and/or public-behind-forward-auth
  (`intranet.devandre.sbs`) — owner decision (§10). Default-deny egress netpol; private datastore.
- **Backup/DR:** the MariaDB + BookStack uploads PVC in the backup set (prod-only rule).

## 6. Content architecture — Shelves → Books → Pages

One **shelf per function** (each owned + gated by that team):

```text
RH · Juridique · Underwriting · Claims · Pricing & Portfolio · Risk Engineering ·
Reinsurance & Captive · Finance & Actuarial · Compliance & Governance ·
IT / Security / DORA · International Programmes · Corporate / Direction
```

Inside each shelf, the **documentation hierarchy** (the key distinction):

```text
POLICY     = What / Why / mandatory principle        (Group/Enterprise, approved by the board/CUO)
STANDARD   = Mandatory requirements                  (what must hold)
GUIDELINE  = How you should normally operate         (the day-to-day métier reference)
PROCEDURE  = The exact process                       (step-by-step)
RUNBOOK    = Operational execution                   (the hands-on steps)
```

## 7. The 12 governance families (the corpus map)

```text
01 Corporate Governance      05 Policy Administration     09 Finance & Actuarial
02 Risk Management (+ORSA)    06 Claims                    10 Compliance & Legal (sanctions/AML/conduct/POG)
03 Underwriting (+appetite,   07 Risk Engineering (+CAT)   11 Data / IT / Cyber / DORA (+InfoSec/BCP/incident/change)
   DoA, referral)            08 Reinsurance & Captive     12 AI & Model Governance
04 Pricing & Portfolio
```

These absorb the ~40 guideline types (Underwriting, Risk Appetite, DoA, Referral, Pricing, POG, Claims,
Reserving, Reinsurance, Risk Engineering, CAT, Portfolio, Sanctions, AML, Conflict-of-Interest, Conduct,
Policy-Admin, International-Programme, Captive/Fronting, Finance, Investment, Actuarial, ORSA, Operational-Risk,
Internal-Control, Four-Eyes, SoD, Data-Governance, Data-Quality, InfoSec, DORA, Third-Party/Outsourcing, BCP,
Incident, Change, AI-Governance, Model-Risk, Records-&-Retention, Audit).

## 8. The executable complement

Every capability in the registry (Backstage catalog) gains the columns:

```text
Applicable Policy · Applicable Standard · Applicable Guideline · Applicable Procedure ·
Required Controls · Approval Authority · Evidence Required
```

So **when an underwriter opens a submission**, the workbench surfaces the applicable guidelines (Property UW
Guideline FR · CAT Exposure Standard · Sanctions Policy · Referral Authority Matrix · Pricing Standard · Risk
Engineering Standard · Reinsurance Guideline) and **enforces** referral triggers / DoA caps / pricing floors /
four-eyes / SoD in the app + Temporal. ktayl-underwriting already has the appetite/eligibility/referral hooks —
it is the natural **pilot**.

## 9. Governance of the corpus (approval · review · audit) — owned by Compliance #15

- **Approval = four-eyes + approval authority**, recorded. Two acceptable mechanisms: (a) BookStack roles +
  a review/approval step + page history; (b) for the **critical Solvency-II policies** that need a hard,
  timestamped four-eyes trail — keep them in **git + CODEOWNERS** and **link** them from the intranet.
- **Review cadence** per family; **audit log** (who/what/when/why/approval) — the platform's append-only
  audit pattern. Feeds the internal-control library (Risk→Control→Owner→Evidence→Testing→Finding→Remediation→Audit).

## 10. Phasing

| Phase | Deliverable |
|---|---|
| **0 — Stand up the intranet** | Deploy BookStack (Helm/ArgoCD, MariaDB, Authentik OIDC, backup, netpol) — Digital Workplace #10; ADR for the MySQL deviation |
| **1 — Structure + pilot content** | Create the shelves + the hierarchy; seed **3 pilot shelves** (RH, Juridique, **Underwriting**) + 2–3 governance families; add the 7 columns to the capability registry |
| **2 — Make the high-value UW rules executable** | Wire appetite/referral/DoA/pricing-floors in the UW workbench to the registry↔guideline link (builds on ktayl-underwriting) |
| **3 — Extend** | Roll out the remaining families / business lines; control library + ORSA under #15 |

## 11. Compliance & certification mapping

Solvency II Pillar 2 (governance system, written policies, DoA, four-eyes, ORSA) · IDD (POG / target market) ·
DORA (ICT governance family) · EU AI Act (AI-governance family) · ACPR (written policies, four-eyes). Cert:
**BC01 (piloter)** + **BC03 (déployer & sécuriser)**; the AI-governance family also feeds **BC02**.

## 12. Open decisions (owner)

1. **Exposure:** internal-only (Tailscale/nip.io) **or** public behind Authentik forward-auth (`intranet.devandre.sbs`)?
2. **Critical-policy corpus:** all content in BookStack, **or** keep Solvency-II policies in git+CODEOWNERS (strict four-eyes) and link them?
3. **MariaDB:** dedicated small instance (recommended) vs reuse an existing MySQL.
4. **Scope of Phase 1 pilot shelves** — confirm RH + Juridique + Underwriting, or a different first set.
