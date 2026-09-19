---
id: hr-tooling
title: HR / Human Resources Tooling
sidebar_label: HR Tooling
---

# HR / Human Resources Tooling

The ktayl-solution IS manages employees with a **best-of-breed, self-hosted** stack (not a
commercial HR SaaS) — consistent with the rest of the digital workplace. The HRIS is
**ERPNext / Frappe HR**, with custom French-compliance payroll modules, plus identity and
(planned) training tools around it.

:::note Status honesty — "installed" ≠ "operational"
This page distinguishes **installed** (the software has the feature) from **operational**
(the org is actually using it, with data). Record counts below are from the **live**
ERPNext (verified 2026-09-19). The IS currently has **1 employee** (it is a simulated
insurer), so most HR modules are *installed but empty* — a deliberate state, not a defect.
:::

## The HR tool stack

| Function | Tool | Status | Verified reality |
|---|---|---|---|
| **Employee data / source of truth** | ERPNext **Frappe HR** (`hrms`) | 🟡 installed, skeleton | `hrms` app installed; **1 Employee** record |
| **Payroll** | ERPNext Payroll + custom **`erpnext_dsn`** (French DSN → URSSAF) + **`erpnext_sepa`** (salary transfers) | ✅ **built + tested** | Custom modules built + unit-tested (`test_dsn_generator.py`, `test_sepa_pain008.py`); **1 Salary Slip** generated |
| **Hiring / Recruitment** | Frappe HR Recruitment | 🟡 installed, unused | **Job Openings: 0** |
| **Performance** | Frappe HR Appraisal | 🟡 installed, unused | **Appraisals: 0** |
| **Leave / Attendance** | Frappe HR Leave + Attendance | 🟡 installed, unused | **Leave: 0, Attendance: 0** |
| **Working-time (non-cadre) + alternance** | Frappe HR **Employee Checkin + Shift + Attendance**; alternance via Employment Type + "Formation/École" Leave Type + shared calendar | 🟡 installed, needs config | capability present in `hrms`; config task (`minicloud-erpnext#7`) |
| **Employee engagement** (recognition/rewards + pulse/feedback) | **Frappe HR Energy Points** + **LimeSurvey** (eNPS/pulse); comms via Matrix/Jitsi/Nextcloud | 📋 backlog (need-first hold) | no mature FOSS all-in-one exists (category is SaaS) — see below |
| **Mandatory training (IDD CPD)** | **Moodle** LMS | 📋 backlog (need-first hold) | not deployed — see below |
| **Identity lifecycle (joiner/mover/leaver + access)** | **Authentik** SSO (live) + **MidPoint** IGA (planned #17) | ✅ SSO live · 📋 IGA planned | every app is SSO-gated |
| **Employee IT support** | **GLPI** ITSM (planned #16) | 📋 planned | helpdesk/tickets |
| **Workforce analytics** | ERPNext built-in reports (+ Metabase/BI planned) | 🟡 partial | capability exists; ~no data to analyse yet (1 employee) |

**The honest summary:** the HRIS is *installed and wired* (Frappe HR + SSO), and **payroll**
is the one genuinely-built piece (the DSN/SEPA custom modules are real engineering — French
social-declaration + SEPA salary transfers). Hiring, performance, leave, and attendance are
**available but not operated** — there is no real workforce yet. This is expected for a
simulated IS; it becomes operational when there are real employees.

## Payroll — the real work (DSN + SEPA)

The custom Frappe apps in `minicloud-erpnext` are the substantive HR engineering:
- **`erpnext_dsn`** — generates the French **DSN** (Déclaration Sociale Nominative), the
  monthly mandatory social-declaration to URSSAF (S10/S20/S90 blocks, CRLF, UTF-8). Unit-tested.
- **`erpnext_sepa`** — **SEPA pain.008** direct-debit / salary-transfer generation.

These are Tier-A tested code (see the [testing standard](../engineering-standards/testing-strategy)),
not just ERPNext configuration.

## Moodle LMS — planned, on a need-first hold

**Driver:** the **IDD** (Insurance Distribution Directive) / ACPR requires insurance
distributors to complete **15 h/year Continuing Professional Development**, tracked and
evidenced per employee for audit.

**Planned scope (when built):** self-hosted Moodle on k8s (GAP wrapper-chart) + Authentik
SSO + **ERPNext-HR integration** (roster → auto-enrollment; completion → HR record) + DDA/IDD
course tracks + completion reporting → the 15 h/year evidence + certificates feeding the
[compliance obligations register](../insurance-platform/regulatory-operating-model) (IDD Art. 10 control).

**Why it is NOT deployed (need-first gate):** the IS has 1 employee — standing up a
heavyweight LMS to track "mandatory workforce training" with no workforce would consume
scarce cluster resources for no operational value. It is tracked as a **design / cert-evidence
capability** (demonstrates the IDD-CPD control for RNCP/interviews), with a **revisit trigger**:
real employees + PII at volume, a real audit, or a production compliance claim — the same
logic as the [BYOD scope boundary](../insurance-platform/regulatory-operating-model).
Tracked: `ktayl-workplace#10` (board #10, Digital Workplace).

## Employee engagement — planned, on a need-first hold

**Goal:** keep employees motivated/satisfied/committed — communication + recognition/rewards +
feedback/pulse (the Culture Amp / Lattice / Officevibe category).

**Honest landscape:** dedicated engagement platforms are **overwhelmingly commercial SaaS**;
there is **no mature drop-in FOSS all-in-one**. The self-hosted, on-model composition is:
- **Recognition / rewards** → **Frappe HR Energy Points** (gamified points/leaderboard) +
  Employee Feedback (already installed in `hrms`, unused).
- **Feedback / pulse / eNPS** → **LimeSurvey** (self-hosted; anonymous, longitudinal, reporting).
- **Communication / social / meetings** → **Matrix + Element, Jitsi, Nextcloud** (already live).

This is as close to a Culture-Amp-equivalent as FOSS offers while staying self-hosted; a
commercial SaaS would break the self-hosted model + €-cap and send data off-cluster.

**Why it is NOT deployed (need-first gate):** 1 employee → an engagement platform has no
operational value without a workforce. Tracked as a **design/portfolio capability**, revisit
when there's a real workforce (same logic as Moodle + the BYOD boundary). Tracked:
`ktayl-workplace#11` (board #10).

## Working-time (non-cadre) & alternance — Frappe HR config, on a need-first hold

Two French-labour-law functions — **both covered by the installed Frappe HR (`hrms`), needing
configuration, not new tools:**

- **Working-time for non-cadre.** French law requires *actual hours* recorded for non-cadre (and
  cadres not au forfait-jours); cadres au forfait-jours count days. Config: **Employee Checkin**
  (badgeuse/pointage) → **Shift Type / Assignment** (35h schedule, late/overtime flags) →
  **Attendance** → heures supplémentaires as a **Salary Slip** component (via `erpnext_dsn`).
  Model non-cadre = Shift-based (hourly, checkin-driven); cadre-forfait-jours = attendance-by-day.
- **Alternance rhythm** (know when at university). No dedicated FOSS tool — model via
  **Employment Type "Alternant/Apprenti"** + a **Leave Type "Formation/École"** for school
  periods (visible in the team calendar, not counted as absence) + a shared calendar
  (Nextcloud/ERPNext) + alternance payroll specifics (% SMIC by age/year) in the Salary Structure/DSN.

**Need-first hold:** these are configuration/operational tasks with no value until a real
workforce exists (1 employee today). Tracked: `minicloud-erpnext#7` (board #8).

## Related
- ERPNext deployment + Frappe HR (source of truth): board #8, repo `minicloud-erpnext`.
- Identity: Authentik SSO (live) · Access Governance / MidPoint IGA (board #17).
- Regulatory tie (IDD CPD, obligations register): [Regulatory Operating Model](./regulatory-operating-model).
