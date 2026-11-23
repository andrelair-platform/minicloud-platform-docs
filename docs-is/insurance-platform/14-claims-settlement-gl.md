---
id: claims-settlement-gl
title: Claims settlement, reserving & GL (CLM-FIN) · as-built
sidebar_label: 🧾 Claims settlement & GL (CLM-FIN)
sidebar_position: 14
---

# Claims settlement, reserving & GL — four-eyes controls + double-entry (CLM-FIN)

:::note Status
✅ **LIVE on dev AND prod, proven end-to-end with a real reserve (2026-11-22).** The claim money controls +
general-ledger posting. The **four-eyes workflow** (reserve approve · payment request→approve→execute ·
large-loss review) lives in **`ktayl-claims`** (which owns the claim over the frozen GlobalCore legacy); the
**GL posting** lives in a new **`ktayl-core` `claimsgl` module**, consuming a published
`insurance.claims.financial` event one-way. **Not** the ADR-014 fold. Detailed design + the full case study
live in the repos (ADR-021 + `ktayl-core/docs/evidence/`); this page is the org-site map.
:::

## Why it's split this way (ADR-021)
`ktayl-claims` is a **Strangler/ACL over the frozen Oracle GlobalCore legacy** — it owns the claim and its
reserve/settle state machine. `ktayl-core` is the **modular monolith** that already runs the ERPNext GL for
premiums (BILL-014). So the claim money **workflow** stays with the claim (keeping it whole — no split-brain,
no premature fold), and `ktayl-core` gets **only** the GL seam it's best at, fed by an async event. The
alternative (a full claims-finance module in core) would split a claim's money from its state across two
services — rejected.

## Architecture (the claim money thread)

```
ktayl-claims (ACL over the frozen Oracle legacy)              ktayl-core (claimsgl module)
  reserve / settle  ─────────────► GlobalCore (Oracle, SOAP)
        │ above authority / large-loss → FOUR-EYES              ▲  insurance.claims.financial
        ▼ (approve ≠ requester; payment: request→approve→execute)│  (CLAIMS_EVENTS, durable consumer)
  applied to the legacy                                          │
        │                                                        │
        ▼ Debezium CDC → claim_read projection                   │
  projector computes the MOVEMENT (new − prior)                  │
        └── transactional outbox → publisher ────────────────────┘
                                                        outbox → ERPNext Journal Entry (double-entry)
```

| Decision | Choice | Ref |
|---|---|---|
| Ownership split | **workflow in ktayl-claims · GL-only seam in ktayl-core**, one-way async event | [ADR-021](https://github.com/andrelair-platform/ktayl-core/blob/main/docs/architecture/adr/ADR-021-claims-gl-seam.md) |
| Emission | **CDC-driven** (the projector computes the reserve/settlement movement) — not the command path | ADR-021 |
| GL | **adopt ERPNext** — balanced Journal Entries (never rebuild a ledger) | BILL-014 pattern |
| Controls | **four-eyes** (approver ≠ requester) + **SoD** on payments (request ≠ approve ≠ execute) + large-loss review | ADR-021 |

## As-built — the CLM-FIN epic

| Slice | What's live |
|---|---|
| **CLM-FIN-01** GL seam | `claimsgl` CLOSED module (ktayl-core): durable JetStream consumer of `insurance.claims.financial` → transactional outbox → ERPNext JE. Mapping (French PCG): reserve↑ → DR `6561 Charges de sinistres` / CR `4675 Sinistres à payer`; downward adj → the reverse; payment → DR `4675` / CR `5121 Cash`. Balance enforced at construction. |
| **CLM-FIN-02** emitter | ktayl-claims emits `insurance.claims.financial` when a reserve/settlement **moves** — the CDC projector computes `new − prior` and writes it to a transactional outbox (atomic with the `claim_read` upsert) → a scheduled publisher drains it to the `CLAIMS_EVENTS` stream. Deterministic `event_id` → end-to-end idempotency. **Prod-only producer** (dev stays off — one producer, no dev→prod-GL leak). |
| **CLM-FIN-03a** reserve four-eyes | Above-authority **or** large-loss reserve ⇒ `202 PENDING` (held in a claims-side store, legacy untouched) → a *different*, higher-authority person approves ⇒ applied to the legacy. Self-approve 403, already-decided 409. Below authority ⇒ applied directly. |
| **CLM-FIN-03b** payment workflow | A settlement above authority / large-loss ⇒ **request → approve (four-eyes) → execute (a non-requester executor)**; **only execute disburses** (`legacy.settle`) — approval alone never pays (segregation of duties). |
| **CLM-FIN-04** deploy + live proof | `CLAIMS_EVENTS` stream (gitops), ktayl-core prod consumer active, ktayl-claims prod producer promoted (Kargo). Proven: a real reserve → GL JE. |

## Operate / verify
```bash
# the claims GL consumer is bound (prod):
ssh controller "kubectl exec -n messaging deploy/nats-box -- nats consumer ls CLAIMS_EVENTS"   # → claimsgl-ingest
# end-to-end (a real reserve on the prod claims API → a balanced claims JE in ERPNext):
#   POST https://claims-prod.10.0.0.200.nip.io/api/claims/<CLM>/reserve  (X-Claims-Authority: SENIOR)  {"amount":30000}
#   → 200 RESERVED → Debezium CDC → emitter → claimsgl → ERPNext JE (DR 6561 / CR 4675), balanced.
# the four-eyes queues:
#   GET /api/claims/reserve-approvals   ·   GET /api/claims/payment-requests
```

## Compliance mapping
**Solvency II / IFRS 17** (claims reserves → technical provisions; loss payments → claims-paid — recorded
cleanly for a later measurement slice) · **DORA** (claims↔legacy↔ERPNext ICT interdependency; resilience =
durable CDC + retried async GL post + idempotency) · **governance** (four-eyes + SoD + append-only approval
audit = the threat-T7 control, a payout above authority can't be self-applied). Certification: **BC02/BC03**.

## Status honesty — what's proven, what's gated
- **Proven live on prod (real, not synthetic):** a reserve through the live SOAP Oracle legacy → CDC →
  emitter → `claimsgl` → **JE `ACC-JV-2026-00010`** balanced €30,000. The four-eyes controls are active on
  prod (above-authority reserve/settle now returns `202`, not `403`).
- **The lesson captured in the case study:** the claims *producer* was initially merged + dev-live but not
  promoted to prod — "merged ≠ live"; each side of a cross-service chain needs its own promotion. Fixed +
  re-proven with a real transaction.
- **Deferred:** real Authentik OIDC on the claims API (header-based today, ADR-005); the proactive large-loss
  *review board* UI (the control + queue exist; a dedicated screen is a follow-up).

Detailed design: **ADR-021** + the case study `ktayl-core/docs/evidence/case-studies/clm-fin-claims-money-control.md`
(both in the `ktayl-core` repo). Related: the [Billing as-built](./13-billing-ktayl-core.md) (the premium chain)
and the [legacy-core modernization](./06-legacy-core-modernization.md) (the claims Strangler).
