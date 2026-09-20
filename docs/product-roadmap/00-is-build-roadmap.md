---
id: is-build-roadmap
title: ktayl IS — Build Roadmap (start here)
sidebar_label: 🧭 IS Build Roadmap (start here)
sidebar_position: 0
---

# ktayl IS — Build Roadmap (the single place)

> **If you're ever unsure what to build next, read this.** Everything on the ktayl-solution IS sits in
> **one of three parallel tracks** (plus the live foundations). This page is the map of the tracks, their
> order, and — crucially — **how they interlock**, so nothing feels scattered.

```
 FOUNDATIONS (live) ──────────────────────────────────────────────────────────
   platform #3 · AI platform #4 · digital workplace #10 · Policy Admin #6 · ERPNext #8

 TRACK A — BUSINESS BUILD (the insurance value chain — sequenced)
   Distribution #13 → UNDERWRITING #12 → Policy Admin #6 → Claims #11 → Billing #14 → Reinsurance #22
                                     (live)
        every domain is built the same way, and passes ↓

 TRACK B — GOVERNANCE & COMPLIANCE (continuous — the gate every Track-A build clears)
   regulatory layer · AI-Act gate · obligations register   (framework built ✅, applied per domain)

 TRACK C — MODERNIZATION PRACTICE LAB (parallel skills cadence, feeds real integration skill into Track A)
   GlobalCore ✅ · GenApp modernization M1–M4
```

**All three are valuable and all three stay on the roadmap.** Track A delivers the business; Track B keeps
it compliant *by design*; Track C builds the legacy/integration muscle real insurers need. They are not
competing — they interlock (see *How they interlock*).

---

## Track A — Business build (the value chain)

Build **outward from what's already live** (Policy Admin #6). Sequenced by value + dependency:

| Phase | Build | Why here |
|---|---|---|
| **1** | **Underwriting & Pricing #12** ← *recommended start* | highest value; FDE playbook ready; feeds the live Policy Admin |
| **1** | Distribution / broker portal #13 | where submissions come *in* (feeds #12) |
| **1** | Claims #11 | the other half of the policy lifecycle |
| **1** | Billing #14 | premium in |
| **2** | Reinsurance #22 · Risk Engineering #21 · International #23 · Compliance #15 | specialty + control |
| **3** | Data/Actuarial #5; Documents #24 / Integration #25 / MDM #20 **as a domain needs them** | insight + layers-on-demand |
| **4** | AI/automation capstone: Knowledge Assistant #18 · AI Ops Copilot #19 | **LAST** — automates *over* real systems |

:::warning Live-deadline item — Facturation électronique (jump the queue)
The French **e-invoicing reform is already in effect (1 Sep 2026)** — a **deadline-driven compliance
capability**, not deferrable like the rest of Phase 2/3. It's a **Finance #14** capability (extending
ERPNext's existing `erpnext_facturx`), backed by an obligation in the register (Compliance #15) and PDP
connectivity (Integration #25). Minimum immediate piece = **receiving** e-invoices via a PDP (universal,
regardless of insurance's VAT-exemption). Scope needs Compliance confirmation (premiums are VAT-exempt →
receiving + e-reporting apply; taxable B2B services must issue). See the obligations register.
:::

**Opportunistic quick win** (Enterprise-IT, not the value chain): GLPI/ITSM #16 — do when convenient.

## Track B — Governance & compliance (continuous, not a phase)

The framework is **built** — it now **applies to every Track-A domain** as a gate, not a separate project:
- **Regulatory layer** (compliance-by-design) — each capability declares its triggered frameworks + controls.
- **AI-Act gate** — every AI use case gets a risk tier → proportionate controls.
- **Obligations register** (RC-05) — the single map of what applies.

→ docs: *Regulatory Operating Model*, *AI-Act Gate*; register in `ktayl-compliance`.

## Track C — Modernization practice lab (parallel cadence)

A **skills track** that builds the wrap / strangler / legacy-comprehension muscle — then feeds it back
into Track A whenever a domain integrates with something legacy:
- **GlobalCore** — a deliberately-legacy Java/SOAP core, **built ✅** (`globalcore-legacy`).
- **GenApp modernization (M1–M4)** — recover the real IBM COBOL app's rules → reimplement on the cluster
  (`cics-genapp/docs/business-rules-catalog.md`).

→ full plan: `ktayl-integration/docs/legacy-wrapper-initiative-spec.md`.

---

## How they interlock (one repeatable recipe per domain)

Building **any** Track-A domain is the *same loop* — and that loop is where B and C plug in:

```
1. FDE playbook        (understand the domain: process, users, pain, data, KPIs)
2. BMAD spec + stories (the implementation contract)
3. Build a thin end-to-end slice   ──uses Track-C patterns when it touches legacy/integration
4. Pass the governance gate        ──Track-B: regulatory impact + AI-Act tier + controls by design
5. Deploy (GAP wrapper chart) + iterate
```

So Underwriting #12 = its FDE playbook (done) → spec → thin slice (submission→quote→bind→PAS) → clears the
governance gate (any AI in it gets an AI-Act tier) → deploy → next slice. Every domain repeats it.

## The one open decision
**Where to start Track A.** Recommended: **Underwriting #12** (value + playbook ready + feeds the live
PAS). Once chosen, the recipe above repeats per domain and the roadmap stops feeling ad-hoc.

## Alignment check — the "Enterprise Claims & Risk Intelligence" reference blueprint

A widely-circulated portfolio blueprint (*"Atlas Insurance — Enterprise Claims & Risk Intelligence
Platform"*) describes the **exact** pattern this IS is built on: an **Oracle legacy core you must not
replace**, modernized *around* with domain APIs, CDC/events, a modern data + AI platform, and
enterprise-grade identity / observability / DevOps. It is **not a new project** — it's a checklist we can
grade ourselves against. Below: what we already support, what the Claims build delivers, the genuinely new
items it adds to the roadmap, and where we **deliberately differ** (our stack ≠ the blueprint's defaults).

### What we already support (live foundations)
| Blueprint capability (§) | Our equivalent | Status |
|---|---|---|
| Kubernetes platform (§17) | k3s, 6-node | ✅ live |
| CI/CD (§18) | GitHub Actions + Argo CD + Kargo | ✅ live |
| IaC (§19) | OpenTofu (MAAS/AWS) + Helm/Kustomize | ✅ live |
| Observability (§16) | OTel + Prometheus + Grafana + Loki + Tempo | ✅ live |
| OAuth/OIDC + RBAC (§14) | **Authentik** (not Keycloak/Entra) | ✅ live |
| Audit (§15) | change-records + app audit + Langfuse AI traces | ✅ live |
| Event bus (§7) | **NATS** (not Kafka) | ✅ live |
| Modern app DB (§6) | PostgreSQL | ✅ live |
| RAG pipeline (§10–11) | markitdown / rag-ingest → **Qdrant** → LiteLLM | ✅ live |
| Structured-vs-document AI split (§12) | RAG for docs · SQL-tools for data | ✅ pattern set |
| Secrets / least-privilege (§14) | Vault + ESO + default-deny netpols | ✅ live |

### What the Claims build delivers (Track A — Claims #11, planned; PR #6 merged)
| Blueprint capability (§) | Where in our plan |
|---|---|
| Oracle legacy core, don't replace (§2, §4) | **GlobalCore** on Oracle Free (ADR-002) |
| Controlled domain APIs around Oracle (§5) | the ACL — stories S003 / S004 |
| Oracle CDC → events (§7) | **Debezium → NATS** — S005 (not GoldenGate/Kafka) |
| CQRS read-model (§6) | Postgres read-model — S006 |
| Structured AI tool (§12) + identity propagation (§14) | governed SQL-tool — S007, threat-model **T8** |
| Claims Copilot agent (§13) | v1 = read-only tool; **full multi-tool agent = AI Ops Copilot #19 (capstone, parked)** |
| Bounded Oracle→Postgres migration (§20) | ADR-007 footnote (later, non-critical only) |

### Net-new items this blueprint adds to the roadmap
- **Event-driven Risk / Fraud scoring service (§8)** — a NATS consumer of `CLAIM_CREATED` / `…_CHANGED`
  writing a `risk_assessment` table in Postgres → a **Claims #11 post-v1 capability** (fraud/SIU lane),
  **not** a new board. (Distinct from **Risk Engineering #21**, which is *physical* risk/prevention on the
  underwriting side.)
- **Analytics warehouse + BI (§9)** — OLTP → CDC/ETL → warehouse → **Metabase** (not Power BI) → the
  **Data / Actuarial #5** track. The **warehouse layer is the main not-yet-built piece** this surfaces.
- **Semantic / metrics layer on the data platform (§9 extension)** — a governed metrics layer
  (self-hosted **Cube** or the **dbt semantic layer**) over the warehouse, so **one** definition of each
  business metric (loss ratio · claim frequency · open high-value claims · average settlement) is consumed
  **identically** by **Metabase** *and* the **Claims Copilot AI tools**. The AI then queries **governed
  metrics, not raw SQL** — which reinforces §12 (structured-vs-document split) and closes the "the LLM
  invents its own numbers" risk. → **Data / Actuarial #5** (build alongside the warehouse).
- **Resilience drills (§21)** — retries / DLQ / idempotency / circuit-breakers → fold into each domain's
  **NFR gate** (Track B), not a standalone project.

### Deliberate divergences (our stack, not the blueprint's)
| Blueprint default | We use | Why |
|---|---|---|
| Kafka | **NATS** | already the platform backbone; lighter, sufficient here |
| GoldenGate | **Debezium** | open-source, zero licence |
| Power BI | **Metabase** (+ Grafana for ops) | self-hosted, no SaaS |
| Keycloak / Entra ID | **Authentik** | already the org IdP |
| pgvector | **Qdrant** (pgvector available) | our RAG store |
| Policy on Oracle | **Policy already modern** (`ktayl-policy-service` #6) | only **Claims** wraps the Oracle legacy |
| "Atlas Insurance Group" | **ktayl-solution** | one fictional carrier — don't introduce a second brand |

**Maturity ladder (§22) → our tracks:** L1–L2 (core + modern platform + auth) = **foundations, live**;
L3 (CDC→events) + L5 (RAG/agent) = **Claims #11**; L4 (warehouse/BI + semantic layer) = **Data #5**;
L6 (K8s/IaC/CI/obs) = **live**; L7 (enterprise hardening) = **already the platform's standing posture**
(table below), applied per domain at the Track-B gate.

### Level 7 — Enterprise hardening (§22 L7) — mostly already live
The point where "a project becomes portfolio-level enterprise-architecture work" — and for us it's **not
future work**, it's the standing posture every new domain inherits and re-proves at its NFR/security gate.
| Hardening capability | Our implementation | Status |
|---|---|---|
| **Audit** | change-records (ITIL/DORA, one per prod PR) + app audit trails + Langfuse AI traces | ✅ live |
| **Secrets management** | Vault + External Secrets Operator (ESO); no secrets in Git | ✅ live |
| **Data masking** | Presidio PII masking (pre-LLM) + gateway/app DLP + default-deny egress netpols | ✅ live (per domain) |
| **Resilience** | canary/BlueGreen Rollouts + health-gate auto-abort; retries / idempotency / DLQ in services; Longhorn replicas | ✅ live / per-service |
| **Load testing** | k6 in CI (smoke + load) | ✅ live (extend per domain) |
| **Backup / recovery** | Velero + MinIO; kine/SQLite control-plane backup; Longhorn volume backups | ✅ live |
| **Security testing** | Trivy image scan · cosign + SBOM · Gatekeeper / Polaris policy · CSPM IAM audit · SAST | ✅ live |
| **Architecture documentation** | Docusaurus (org + per-repo) · C4 · ADR logs · threat models · NFR registers | ✅ live |

**Bottom line:** the blueprint validates that the three-track IS *is* an enterprise-modernization platform.
The only genuinely new backlog it surfaces is the **warehouse/BI + semantic layer (#5)** and the
**event-driven risk/fraud service (#11 post-v1)** — **everything else, including all of Level 7, is already
live or already planned.**

---

## Where the detail lives
- **Domain map (what exists):** [EA Blueprint](../insurance-platform/enterprise-architecture-blueprint)
- **Per-domain deep-dive:** FDE playbooks (e.g. [Underwriting](../insurance-platform/underwriting-fde-playbook))
- **Governance:** [Regulatory Operating Model](../insurance-platform/regulatory-operating-model) · [AI-Act Gate](../ai-ml/ai-act-gate)
- **Practice lab:** `ktayl-integration/docs/legacy-wrapper-initiative-spec.md`
- **Detailed backlog / quarter view:** [Product Roadmap (detail)](./overview)
