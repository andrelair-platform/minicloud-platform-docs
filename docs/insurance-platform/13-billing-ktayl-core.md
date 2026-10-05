---
id: billing-ktayl-core
title: Billing — ktayl-core (insurance-LOB modular monolith) · as-built
sidebar_label: 💶 Billing (ktayl-core)
sidebar_position: 13
---

# Billing — ktayl-core (insurance-LOB modular monolith)

:::note Status
🏗️ **Tier-1 money-chain kickoff (2026-10-05).** `ktayl-core` is the ktayl-solution **insurance-LOB
modular monolith** (Spring Boot + Spring Modulith, Java 21), board **#28**. Its first module is
**Billing** — the *premium → cash → GL* link the operating spine couldn't do. Live so far: **BILL-010**
(app skeleton, image published + signed) and **BILL-011** (bound-premium ingest + the durable
`UNDERWRITING_EVENTS` JetStream stream). The Billing **workload** is not yet deployed (BILL-016); the
stream is already live and capturing. Detailed design (PRD, architecture, ADR-001/002/003, SPEC) lives
in the **`ktayl-core` repo** `docs/`; this page is the org-site map.
:::

## Why ktayl-core exists (and why a modular monolith)

The insurance operating spine runs **Submission → Underwriting (live) → Policy bind (live) → Billing →
Claims (live)**. A policy could be **bound** but there was **no way to turn it into cash** — no premium
invoice, no payment, no ledger posting. Billing is that missing link.

Per the platform's **modular-monolith-first** rule, a new insurance business domain is a **module inside
`ktayl-core`** — *not* a new repo/service/board/pipeline. Boundaries are designed from day one (own
interface + own Postgres schema) so a module can later be *extracted* if it earns it, but it is not
deployed as a separate service by default. For a solo platform this avoids the per-service tax (CI +
Kargo + CNPG + Helm + netpols + QA gate × N) while keeping clean domain seams — and the boundaries are
**enforced by tooling** (a Spring Modulith `ApplicationModules.verify()` test fails the build on any
violation), not by discipline.

## Architecture (the Billing money thread)

```
Authentik SSO ─▶ Ingress ─▶ ktayl-core (Spring Boot, one deployable)
   Underwriting ──bound-risk event──▶ NATS JetStream (UNDERWRITING_EVENTS)
                                            │ durable consumer (ingest the premium)
   ┌─────────────────────────────────────────┼──────────────────────────┐
   ▼ ingests (premium)        ▼ posts                ▼ pays (ext)          ▼ owns
 UW bound-risk event    ERPNext GL (`erp` ns)   Stripe (test, SEPA DD)  PostgreSQL (schema `billing`)
 {policy_number,        Journal Entries         PaymentIntent + signed  one DB, schema-per-module
  premium_minor, …}     (double-entry)          webhook
```

| Decision | Choice | ADR |
|---|---|---|
| Stack | **Java 21 + Spring Boot 3.5 + Spring Modulith 1.4** (transactional-insurance fit; enforced module boundaries) | [ADR-001](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/architecture/adr/ADR-001-stack-spring-modulith.md) |
| Payment PSP | **Stripe test mode + SEPA Direct Debit**, webhook-driven async capture (domain-correct EU premium channel; DORA third-party) | [ADR-002](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/architecture/adr/ADR-002-payment-psp-stripe-sepa.md) |
| Premium source | **the Underwriting `bound-risk` event**, made durable by a JetStream stream — **not** the PAS (which has no premium) | [ADR-003](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/architecture/adr/ADR-003-ingest-underwriting-event.md) |
| GL | **adopt ERPNext** (post Journal Entries; never rebuild a ledger) | PRD |

**The grounding lesson (BILL-011):** the plan assumed Billing reads the premium from the PAS. Confirming
the real contract showed the **PAS is a thin registry with no premium** ("bound" = status `active`); the
premium lives in **Underwriting**, which already emits a `bound-risk` event. So Billing ingests that event
via a durable JetStream consumer — zero Underwriting change — and an **L3 contract test** pins the payload
(`premium_minor` stays an integer eurocents; dates parse as `LocalDate`) so a future drift fails pre-merge.

## As-built — epic BILL-01 (premium → cash → GL)

| Story | What's live |
|---|---|
| **BILL-010** scaffold | Spring Boot + Spring Modulith skeleton; `billing` (CLOSED) + `shared` (OPEN) modules; `ModularityTests` boundary guard (green); Authentik OIDC security; Flyway schema-per-module; non-root Dockerfile; CI (build → Harbor+ghcr → Trivy CRITICAL → cosign + SBOM). Image **published + signed**. |
| **BILL-011** ingest | `UnderwritingEventConsumer` (durable JetStream, ack/term/nak) → `PolicyIngestService` (idempotent by `policy_number`, validated, audited) → `ingested_policy` + `audit_log` (Flyway V2). The **`UNDERWRITING_EVENTS`** stream (gitops) durably captures the UW bind event. L1 + **L3 contract** tests green. |
| BILL-012 invoice+installments | 🔜 next — raise the premium invoice + installment schedule (reconcile to Σ installments, idempotent). |
| BILL-013a/b Stripe | planned — SEPA-DD PaymentIntent + signature-verified idempotent webhook capture. |
| BILL-014 GL post | planned — balanced Journal Entries to ERPNext via a transactional outbox. |
| BILL-015 / BILL-016 | planned — who-owes-what; GAP wrapper chart + **Kargo git-Warehouse** deploy (the consumer goes live). |

## Security by design
- **AuthN/AuthZ:** Authentik OIDC resource-server; `/api/**` authenticated + Finance-group (the Stripe
  webhook is the one non-SSO path, guarded by signature verification). Actor from the token, never a payload.
- **Money invariant:** eurocents integers (never floats); the GL post goes through a **transactional
  outbox** so billing-state and the external ledger never share a distributed transaction — no
  half-committed money move.
- **Secrets:** ESO → Vault (DB, ERPNext, Stripe test key + webhook secret). **No PCI scope** (Stripe
  tokenises; ktayl-core never sees card/IBAN).
- **Egress:** default-deny → DNS + NATS + ERPNext + Postgres + `api.stripe.com` (the one governed external
  exception). Governance gate (SA+SEC) signed off 2026-10-05.

## Operate / verify
```bash
# the durable stream that captures the UW bound-risk event (live):
ssh controller "kubectl exec -n messaging <nats-box> -- nats -s nats://nats:4222 stream info UNDERWRITING_EVENTS"
#   → Subjects: insurance.underwriting.>  · File · Limits   (verified 2026-10-05)
ssh controller "kubectl get application ktayl-core-infra -n argocd"      # Synced / Healthy
# the signed, Trivy-clean image (BILL-010 main build):
#   ghcr.io/andrelair-platform/ktayl-core:66a5b17   (cosign-signed + CycloneDX SBOM)
# build + the module-boundary guard locally:
cd ktayl-core && ./mvnw verify      # Tests: ModularityTests (ApplicationModules.verify) + L1 + L3 → BUILD SUCCESS
```

## Compliance mapping
**Solvency II / IFRS 17** (premium recognition → technical provisions; MVP records receivable/income
cleanly for a later measurement slice) · **GDPR** (policyholder PII minimised + audited) · **DORA**
(billing↔ERPNext↔Stripe ICT interdependency; **Stripe = a third-party ICT register entry**; resilience =
durable JetStream ingest + retried async GL post + idempotency) · **ACPR/EIOPA** (premium accounting via
the ERPNext GL). Certification: **BC02 (concevoir/développer)** + **BC03 (déployer & sécuriser)**.

## Status honesty — what's not done yet
- **The Billing workload isn't deployed** (BILL-016). The stream captures events now; the consumer goes
  live with the GAP wrapper chart + Kargo git-Warehouse. **Prod is the authoritative consumer** (dev's
  `BILLING_NATS_URL` blank → one consumer, no double-invoice).
- **No invoice/payment/GL yet** — BILL-012→014. The money chain is wired at the ingest end only.
- **Stripe** needs a test account (free) → keys to Vault at BILL-013a.
- **holder_name** enrichment from the PAS is deferred (display-only; the premium mechanics don't need it).

Full detail + rationale: `ktayl-core` repo `docs/`
([PRD](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/prd.md) ·
[architecture](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/architecture.md) ·
[ADR-001/002/003](https://github.com/andrelair-platform/ktayl-core/tree/main/docs/architecture/adr) ·
[SPEC](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/specs/spec-billing-mvp/SPEC.md)).
