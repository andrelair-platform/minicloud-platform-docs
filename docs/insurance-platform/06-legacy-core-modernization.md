---
id: legacy-core-modernization
title: Legacy-Core Modernization (GlobalCore + the strangler)
sidebar_label: Legacy-Core Modernization
---

# Legacy-Core Modernization — the Oracle legacy (GlobalCore) & the strangler

:::note Status — direction aligned; build gated
This is the **documentation alignment** for the legacy spine of the ktayl IS. The legacy engine
(**GlobalCore**) is already built (Java 8 / SOAP / batch); it is **evolving to Oracle + the Claims
domain**. No Claims wrap is built yet. Gates: **align docs → validate → Claims Path-C planning
([`ktayl-claims/docs/`](https://github.com/andrelair-platform/ktayl-claims/tree/main/docs)) → validate →
build.** This is **ktayl-solution IS** work (business/org context), **not** the Retrieva certification.
:::

## 1. Why a legacy core — and where it sits

A real IARD insurer's IS is **not** all greenfield. It runs a **legacy core that still works** (old,
authoritative, stored-procedure-heavy, SOAP/batch) and grows a **modern platform around it** that wraps,
intercepts and *strangles* it — but rarely replaces it (**Strangler Fig + Anti-Corruption Layer**). This is
the ktayl IS's **Track C (Modernization Practice Lab)** on the
[IS Build Roadmap](../product-roadmap/is-build-roadmap), and — crucially — it is pointed at a **real,
needed domain** so the wrapping *delivers value*, not a throwaway.

**Two deliberate choices:**
1. **Policy is already modern** (the live `ktayl-policy-service`, #6), so **the legacy is NOT policy** —
   wrapping a legacy policy core would just re-deliver what we already have.
2. **The legacy delivers a domain we NEED but haven't built — Claims (#11).** Wrapping the legacy *is* how
   we deliver modern Claims. The practice lab (Track C) and the real business domain (Track A) reinforce
   each other instead of competing.

## 2. GlobalCore — the legacy engine (on Oracle)

The legacy is **GlobalCore** (`globalcore-legacy`) — a deliberately-legacy carrier we own and **freeze**,
so wrapping it teaches the real modernization architecture. Its authentic-legacy traits are the point:

| Trait | How it shows up | Why it matters |
|---|---|---|
| **Oracle** | the system-of-record runs on **Oracle** (Free edition) with **PL/SQL** stored procedures | real Oracle experience — the HDI-relevant skill; rules live in the DB, not the app |
| **SOAP/XML only** | the only API is `/ws` (WSDL) — no REST, no JSON | forces an ACL translator (SOAP→JSON) |
| **Batch, not real-time** | a create lands `pending`; a **nightly batch** activates it | you design around async issuance (batch→events) |
| **Cryptic shared schema** | ≤8-char columns, codes not enums (`STATCD` P/A/L/C…) | the ugly representation the ACL must hide |
| **Outside k8s** | plain Docker container on the controller | legacy isn't cloud-native; the modern platform reaches *out* to it |
| **FROZEN** | you never add modern capability *inside* it | the constraint that forces a real wrap, not an edit |

**Evolution (from the current build):** GlobalCore v0 is Java 8 / SOAP / batch on **PostgreSQL-pretending-
to-be-Oracle**, domain = Policy. It evolves to (a) **real Oracle** (Free edition + PL/SQL), and (b) the
**Claims domain** (claims · reserves · payments + supporting refs) — the needed, unbuilt capability. Policy
data stays as a supporting reference (coverage lookups), but the **wrapped/delivered domain is Claims**.

## 3. How Oracle runs — the image & placement

**No standalone Oracle infrastructure** — one Free-edition container (the old XE lineage; zero licence).

- **Image:** `container-registry.oracle.com/database/free:latest-lite` (community mirror `gvenzl/oracle-free`
  as fallback). GlobalCore (Java 8 / Spring) connects via Oracle JDBC.
- **Placement — OUTSIDE Kubernetes**, as Docker containers on the controller (GlobalCore + its Oracle,
  like MinIO). Realistic ("legacy on traditional infra, modern platform on k8s") and keeps Oracle off the
  constrained k3s cluster (no Longhorn). The modern ACL reaches GlobalCore's SOAP + Oracle at
  `controller-ip`.
- **Sizing gate:** the controller disk is tight (98 G, MinIO ~33 G, prior disk-full cascades). Oracle Free
  needs a few GB — size + gate it, or place the containers on a worker node's local disk (still outside k3s).
- Oracle creds → **Vault** (`secret/platform/oracle-legacy`) → ESO → the ACL; a **least-privilege app
  user**, never SYS/SYSTEM, never in Git.

## 4. The wrap — how Claims #11 delivers the domain

`ktayl-claims` (#11) is the modern Claims capability, built **as the ACL/strangler** over GlobalCore. Three
seams, matching GlobalCore's authentic-legacy interfaces:

1. **SOAP → JSON translation (the ACL API).** The modern claims API calls GlobalCore's SOAP for writes
   (create claim → `pending`), translating the cryptic XML (codes, ≤8-char fields) into clean JSON. No app,
   portal or AI speaks SOAP or touches Oracle directly.
2. **Batch → events.** A create is only official after the nightly batch flips it active. The ACL models
   this async issuance and, via **CDC (Debezium on Oracle → NATS)**, turns legacy changes into domain events
   (`CLAIM_CREATED`, `CLAIM_STATUS_CHANGED`, `RESERVE_ADJUSTED`) so consumers react instead of polling.
3. **Read-model + governed AI.** A **Postgres read-model** (CQRS-lite) projects the events to power a modern
   claims workbench (reads never hit the legacy). AI reaches claims **only via approved SQL-tools behind the
   ACL** (identity-propagated, PII-masked) + **RAG** for documents — never the LLM on Oracle.

## 5. How it fits the roadmap (Track A × Track C)

| Piece | Track | State |
|---|---|---|
| **GlobalCore** (`globalcore-legacy`) — Oracle/SOAP/batch legacy | C (practice lab) | built ✅, evolving to Oracle + Claims |
| **ktayl-claims #11** — the modern wrap that delivers Claims | A (business) | scaffold → Path-C planning done |
| **ktayl-integration #25** — the ACL/CDC wrapper capability | foundations | wrapper spec authored |
| **GenApp (M1–M4)** — the *real* IBM COBOL core, optional advanced track | C | forked, study-now |
| Policy #6, Underwriting #12, distribution, finance… | A | modern greenfield (NOT wrapped) |

The wrapping skill built here (SOAP→JSON, batch→events, ACL, CDC, legacy comprehension) **feeds back into
Track A** whenever a real domain must integrate with something legacy — the whole point of Track C.

## 6. Build sequence (gated)

```
now      Underwriting #12 thin slice (greenfield, in flight — don't interrupt)
  →      align docs (EA §2b + this + the wrapper spec)         ← YOU VALIDATE HERE
  →      ktayl-claims Path-C planning set (brief/PRD/arch/threat/ADRs) aligned to GlobalCore+Oracle+Claims  ← validate
  →      evolve GlobalCore: Oracle (Free) + PL/SQL + the Claims domain (frozen, outside k8s)
  →      build ktayl-claims: ACL (SOAP→JSON) → CDC(Debezium→NATS) → read-model → workbench
  →      governed AI read-tools · then the AI Ops Copilot (#19) LAST
```

**Validation gates before any Oracle/Claims build.** No Oracle is stood up and no Claims code is written
until this alignment + the Claims Path-C set are validated — same discipline as Underwriting #12.

## 7. Governance & compliance

Path-C (a legacy datastore, CDC, cross-boundary AI) → **architecture + security review gates**.
Compliance-by-design in the Claims threat model: legacy creds (Vault/ESO), least-privilege Oracle user,
default-deny egress to the controller only, PII masking before AI, identity propagation, audit on every ACL
+ AI action. Evidence → **Regulatory & Compliance #15** control library. Cert: BC01 (spine) / BC02–BC03 (wrap).

## References

- [Enterprise Architecture Blueprint §2b](./enterprise-architecture-blueprint) — the spine in the IS model
- [IS Build Roadmap](../product-roadmap/is-build-roadmap) — Track C (Modernization Practice Lab)
- Wrapper initiative spec: `ktayl-integration/docs/legacy-wrapper-initiative-spec.md`
- Legacy engine: `globalcore-legacy` · Claims wrap: `ktayl-claims` (#11)
