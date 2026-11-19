---
id: billing-ktayl-core
title: Billing — ktayl-core (insurance-LOB modular monolith) · as-built
sidebar_label: 💶 Billing (ktayl-core)
sidebar_position: 13
---

# Billing — ktayl-core (insurance-LOB modular monolith)

:::note Status
✅ **LIVE on dev AND prod (2026-11-14).** `ktayl-core` is the ktayl-solution **insurance-LOB modular
monolith** (Spring Boot + Spring Modulith, Java 21), board **#28**. The Billing **workload is deployed**
(GAP wrapper chart + Kargo git-Warehouse; ArgoCD `ktayl-core-dev` + `ktayl-core-prod`, both Synced/Healthy,
prod 2/2 + R2 PITR backup). The **full premium → cash → ledger chain is proven end-to-end in prod**: a
`bound-risk` event → **invoice** → **payment** (Stripe test SEPA) → **double-entry Journal Entries in
ERPNext**. **Prod is the authoritative NATS consumer** (dev keeps it dormant → one consumer, no double-invoice). Two more modules are
live in prod: **Complaints** (the hexagonal exemplar, ADR-013) and **Finance** (2026-11-19) — the period-end
**GL reconciliation** + an **auditable period close**, see *As-built — epic FINCLOSE* below. Detailed design
(PRD, architecture, ADRs) lives in the **`ktayl-core` repo** `docs/`; this page is the org-site map.
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
| **BILL-012** invoice+installments | ✅ **live (prod-proven)** — `InvoiceService.raiseFor` raises the premium invoice + installment schedule (total reconciles to Σ installments, idempotent per `policy_number`); `InvoiceOnIngestListener` auto-chains it `AFTER_COMMIT` of the ingest. End-to-end verified in prod: `bound-risk → ingested_policy → invoice(issued) → installment(open)`. |
| **BILL-016** deploy | ✅ **live** — GAP wrapper chart (`services/ktayl-core/helm/`) on `minicloud-app-deployment` + a `templates/` **CNPG** (prod: 2 instances + R2 PITR) + **Kargo git-Warehouse**; ArgoCD `ktayl-core-dev` + `ktayl-core-prod`. Phase-5 egress-netpol hardened (default-deny + allow-list). The consumer is **active in prod**. |
| **BILL-013a/b** Stripe | ✅ **LIVE on prod — premium→cash proven end-to-end** — `POST /api/billing/payments` (Finance-gated) creates an idempotent SEPA-DD PaymentIntent (`payment=pending`, rejects a paid installment with 409 before the PSP); `POST /webhooks/stripe` (M2M, `Stripe-Signature`-verified) captures on `payment_intent.succeeded` → payment `succeeded`, installment `paid`, invoice `settled` when all paid, idempotent by event id, parks-not-drops. **Verified live:** a real Stripe test PaymentIntent (`pi_…`) + a signed webhook on the public `billing.devandre.sbs/webhooks/stripe` route → DB payment=succeeded/installment=paid/invoice=settled. Keys in Vault (`secret/platform/ktayl-core`) via ESO; the webhook uses the path-scoped tunnel pattern (no new ingress/cert). L1+L2+L3 green. |
| **BILL-014** GL post | ✅ **LIVE on prod — money→ledger proven end-to-end** — a **transactional outbox** (`ledger_outbox`, V8): a plain `@EventListener` writes the GL intent **in the same transaction** as the business fact (`PremiumInvoiced`→DR Receivable/CR Income; `PaymentCaptured`→DR Bank/CR Receivable) — never a half-post (proven by a publish-in-rollback test); balance (Σdr=Σcr) enforced at construction; a `@Scheduled` drainer posts to the live **ERPNext** (`https://erp.devandre.sbs`, Frappe token auth, idempotent by `cheque_no`), a GL outage leaves rows pending→retried (billing never blocked). **Verified live:** a bound-risk → invoice → pay produced two **submitted, balanced Journal Entries** in ERPNext (French PCG CoA, company Ktayl Solutions: 4111/706/5121, a Customer party on the receivable). L1+L2 green. |
| **BILL-013c** dunning | ✅ **LIVE on prod — non-payment path verified** — the webhook handles `payment_intent.payment_failed`: payment→`failed`, **installment stays open**, a **`dunning_case` per installment** (V9) opens/increments; at the lapse threshold (default 3) → `lapse_pending` + emits **`PolicyLapseRecommended`** (a recommendation for human/regulatory review — IDD notice rules — not auto-cancellation); a later success **resolves** the case. Idempotent + parks-not-drops. **Verified live:** 3 signed failure webhooks → dunning `lapse_pending` (attempts 3), installment open. L1+L2+L3 green. |
| BILL-015 | planned — who-owes-what read model. |

## As-built — epic FINCLOSE (period close & GL reconciliation)

The **`finance` module** is the period-end layer on top of Billing — the *auditable close*. Billing already
posts each premium/payment to the GL (BILL-014); Finance answers **"does the ledger agree, and is the period
locked?"** It is a **read/close layer, never a second ledger**, consuming Billing only through a published
Spring-Modulith named interface (`ledger-view`) — the boundary is enforced by `ModularityTests`.

| Story | What's live (prod, 2026-11-19) |
|---|---|
| **FINCLOSE-01** reconciliation + register | ✅ **LIVE on prod** — `GET /api/finance/periods/{YYYY-MM}/reconciliation` (billing subledger POSTED vs the ERPNext GL total → **drift** + stuck-count) and `/register` (gross premium invoiced · cash received · receivable outstanding). `GROUP_Finance`-gated; GL unconfigured → `glStatus=UNAVAILABLE` (never a 5xx); single-currency EUR guard; period attribution = outbox `created_at` (UTC). Flyway **V14** (`finance` schema + `accounting_period`). Added Billing's `ledger-view` published interface. |
| **FINCLOSE-02** close/reopen + audit | ✅ **LIVE on prod** — `POST …/close` locks a period behind preconditions (each a 409: period **ended** · subledger **settled** · GL **reconciled**, or `force`+reason), `POST …/reopen` (reason-gated → 422), `GET …/close` history. An **immutable append-only closing audit** (Flyway **V15**) records who/when + the attested figures. **ADR-019 — the close is a CONTROL/attestation + detection, NOT a physical lock on billing** (a `billing→finance` lock would be a module cycle `ModularityTests` rejects); a `postCloseMovement` flag detects any GL movement after close. Lifecycle `OPEN ⇄ CLOSED` only. |
| **FINCLOSE-03** | planned (#77) — a close **dashboard** (recent periods × status/drift/stuck in one call) + GL **outbox-drift** metrics & a Prometheus alert + a Grafana panel. |

**Verified live (prod):** pods on the finance build, **`V14`+`V15` applied in the prod CNPG**
(`accounting_period` + `period_close_audit`), `/actuator/health` 200, all finance routes SSO +
`GROUP_Finance`-gated (401 without a token), `ktayl-core-prod` ArgoCD `Synced/Healthy`. CI **222 tests green**
(L1 · L2 real-Postgres full close lifecycle · L3 web; `ModularityTests` + `HexagonalArchitectureTests`).
Design: ADR-018 (read-layer, not a second ledger) + ADR-019 (control-not-lock) in the `ktayl-core` repo.

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
# prod app + DB healthy:
ssh controller "kubectl get application ktayl-core-prod -n argocd"        # Synced / Healthy
ssh controller "kubectl get cluster ktayl-core-cnpg -n ktayl-core-prod"   # healthy, 2 instances
# the prod Billing consumer is bound (durable billing-ingest on the UW stream):
ssh controller "kubectl exec -n messaging deploy/nats-box -- nats -s nats://nats.messaging.svc:4222 consumer ls UNDERWRITING_EVENTS"
#   → billing-ingest   (verified 2026-11-14)
# end-to-end money thread (publish a synthetic bound-risk → invoice appears):
#   nats pub insurance.underwriting.bound-risk '{"policy_number":"...","premium_minor":360000,"currency":"EUR",...}'
#   → billing.ingested_policy + billing.invoice(issued) + billing.installment(open), total == Σ installments
# build + the module-boundary guard locally:
cd ktayl-core && ./mvnw verify      # ModularityTests + HexagonalArchitectureTests + L1 + L3 → BUILD SUCCESS
```

## Compliance mapping
**Solvency II / IFRS 17** (premium recognition → technical provisions; MVP records receivable/income
cleanly for a later measurement slice) · **GDPR** (policyholder PII minimised + audited) · **DORA**
(billing↔ERPNext↔Stripe ICT interdependency; **Stripe = a third-party ICT register entry**; resilience =
durable JetStream ingest + retried async GL post + idempotency) · **ACPR/EIOPA** (premium accounting via
the ERPNext GL). Certification: **BC02 (concevoir/développer)** + **BC03 (déployer & sécuriser)**.

## Status honesty — what's done, what's not
- **Deployed + proven:** the workload is live on dev AND prod; the **ingest → invoice** thread is verified
  end-to-end in prod (BILL-012 + BILL-016).
- **Payment (Stripe BILL-013a/b): LIVE on prod, premium→cash proven end-to-end.** Initiate creates a real
  Stripe test PaymentIntent; the signature-verified webhook (public `billing.devandre.sbs/webhooks/stripe`,
  path-scoped tunnel) captures it → installment `paid`, invoice `settled`. Test-mode only (no real money).
  Honest scope: the success event in the live verify was self-signed with the real `whsec_` (validates our
  signature-verify + capture exactly as prod); the ultimate test (confirm a test SEPA IBAN so Stripe itself
  sends `succeeded`) needs a payment frontend — deferred.
- **Not done yet:** **GL post (ERPNext BILL-014)** — ledger posting via a transactional outbox is the next
  slice (it listens for the `PaymentCaptured` event BILL-013 already emits). **holder_name** enrichment from
  the PAS is deferred (display-only).
- **Three first-exercised-in-prod bugs were found + fixed during the prod go-live** — all in the
  consumer chain that is *dormant on dev*, so neither CI mocks nor the dev QA gate could catch them:
  (1) wrong NATS address (`nats.nats.svc`→`nats.messaging.svc`); (2) `@ConditionalOnBean` silently
  dropping the consumer bean (→ deterministic `@ConditionalOnExpression` property gate); (3) the
  `AFTER_COMMIT` auto-invoice listener not committing (→ `@Transactional(REQUIRES_NEW)`). The systemic
  gate owed is an **L2 integration test** (testcontainers NATS + Postgres) of publish→ingest→invoice,
  which would have caught all three pre-merge.

Full detail + rationale: `ktayl-core` repo `docs/`
([PRD](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/prd.md) ·
[architecture](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/architecture.md) ·
[ADR-001/002/003](https://github.com/andrelair-platform/ktayl-core/tree/main/docs/architecture/adr) ·
[SPEC](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/specs/spec-billing-mvp/SPEC.md)).
