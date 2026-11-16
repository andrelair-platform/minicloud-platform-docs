---
id: ktayl-dms-paperless
title: ktayl DMS — Paperless-ngx (Documents)
sidebar_label: ktayl DMS (Paperless)
---

# ktayl DMS — Paperless-ngx

The **Documents & DMS transversal layer** (board [#24](https://github.com/orgs/andrelair-platform/projects/24)) for the ktayl-solution IS. An insurer drowns in documents — policy schedules, endorsements, claim evidence (invoices, photos, expert reports), broker mandates, SEPA mandates, KYC/AML records. The DMS is the **capture · OCR · full-text search · archival** capability the business domains consume; it does **not** own the business meaning of a document (a claim owns its own claim-number), it makes every document **findable and retained**.

:::note Role (ADR-001): the DMS is a *transversal capability*, not a domain
Domains (Claims, Policy, Underwriting…) remain the system-of-record for *their* documents. The DMS is the shared **capture/OCR/search/e-sign** layer they plug into (role B). It complements **Docuseal** (e-signature) and **Nextcloud/OnlyOffice** (collaborative file editing) — Paperless is the **ingest-OCR-archive-search** half. See `ktayl-dms/docs/architecture/adr/ADR-001`.
:::

## Access

| URL | Audience |
|---|---|
| https://paperless.10.0.0.200.nip.io | Internal (Tailscale only) |

Login: **Authentik OIDC SSO** (`kanmegnea` + TOTP) via django-allauth. A break-glass local `admin` exists (password in Vault `secret/platform/paperless`) for recovery when SSO is down.

## Deployment (Phase 1 — live on dev)

| Parameter | Value |
|---|---|
| Namespace | `ktayl-dms` |
| App image | `ghcr.io/paperless-ngx/paperless-ngx:2.20.15` |
| Database | **CNPG** `paperless-cnpg` (`ghcr.io/cloudnative-pg/postgresql:17.4`), 1 instance (dev) |
| Broker | `redis:7.4-alpine` (task queue / celery) |
| Storage | Longhorn PVCs — media 5Gi · data 2Gi · consume 1Gi (RWO) |
| OCR | built-in **Tesseract** (`fra+eng`) — no external OCR service |
| Search | built-in **Whoosh** full-text index — no Elasticsearch |
| Managed by | ArgoCD (`apps/is/dms/ktayl-dms-dev.yaml`), standalone Helm chart `services/ktayl-dms/helm` |
| Auth | Authentik OIDC (django-allauth), callback `/accounts/oidc/authentik/login/callback/` |

```bash
kubectl --context minicloud get pods -n ktayl-dms
kubectl --context minicloud get ingress -n ktayl-dms
```

## Why Paperless-ngx (the adopt decision)

A **DMS was an adopt-candidate, not a build** (`architecture-strategy.md` adopt-vs-build). Paperless-ngx wins on the tight-cluster constraint: its OCR (**Tesseract**) and search (**Whoosh**) are **built into the one app container** — no Elasticsearch, no separate OCR sidecar — so the full capture→OCR→search→archive capability is ~3 pods idle (app + CNPG + Redis). Office-doc OCR (Gotenberg/Tika) is deliberately **off in Phase 1** (`PAPERLESS_TIKA_ENABLED=false`); PDF/image OCR is the 80% case and is native.

## Architecture (how it works)

```
User ─(SSO)→ nginx Ingress ─→ Paperless (Django + gunicorn + celery)
                                   │  ├─ CNPG Postgres  (metadata, tags, correspondents)
                                   │  ├─ Redis          (celery task queue)
                                   │  ├─ Tesseract      (OCR, in-process)
                                   │  └─ Whoosh         (full-text index, on the data PVC)
                                   └─(OIDC back-channel, CA-trusted)→ Authentik
```

- **s6-overlay image** → the container **must start as root** to set up `/run`, then drops the app to `USERMAP_UID/GID 1000`. The namespace is therefore exempt from the `require-non-root` Gatekeeper constraint (identical to BookStack); every other control is kept (no SA token, `NET_RAW` dropped, no-priv-esc, seccomp, resource limits, default-deny-ingress NetworkPolicies).
- **CA-trust initContainer** appends the minicloud CA to the base bundle so Paperless's OIDC discovery back-channel to `auth.devandre.sbs` (split-horizon → 10.0.0.200, minicloud-CA) verifies.
- **Network posture** — default-deny **ingress** netpols (allow ingress-nginx:8000, same-ns, CNPG operator, monitoring scrape); egress is left open to avoid the Cilium default-deny-egress trap that hangs CNPG/apiserver traffic (same pattern as underwriting).

## Operate / verify

```bash
# pod health (dev)
kubectl --context minicloud get pods -n ktayl-dms
# → paperless 1/1, paperless-cnpg-1 1/1, paperless-redis 1/1

# login page served through the ingress
/usr/bin/curl --cacert ~/minicloud-ca.crt -s -o /dev/null -w "%{http_code}\n" \
  https://paperless.10.0.0.200.nip.io/accounts/login/        # → 200

# OIDC discovery back-channel (run in-pod) reaches Authentik over CA trust
# → issuer https://auth.devandre.sbs/application/o/paperless/
```

Verified on dev 2026-11-15: pod `1/1 Ready`, celery worker connected to Redis, login page `HTTP 200` in-pod **and** through the ingress, the Authentik `authentik` provider registered in allauth, the OIDC discovery reachable over the CA-trusted channel, and the Authentik provider `redirect_uris` a **STRICT** match to Paperless's callback.

## Phase 2 — the document brain (dms-classifier, live on dev)

When a scanned claim invoice / policy schedule / KYC doc lands, an **AI worker** reads the OCR text, infers the **claim# / policy# / client** it belongs to, validates it against the real systems of record, and auto-files it as Paperless custom fields — with a **human-in-the-loop** gate on low-confidence matches. This is what links a loose document to its business record.

```
Paperless (post-consume) ──publish {doc_id}──▶ NATS JetStream  DMS_DOC / dms.doc.consumed
                                                      │ (durable, never drops a doc)
                              KEDA (NATS lag) ──wakes──▶ dms-classifier 0→1
                                                      │
   indra OCR ──▶ Presidio PII-mask ──▶ LiteLLM extract ──▶ validate (claims + ktayl-core lookups)
                                                      │
   confident + validated → PATCH the Paperless custom field + `filed` tag
   low-confidence / not-found / client-mismatch → `needs-review` tag (HITL, never auto-filed)
```

| Aspect | As-built |
|---|---|
| Service | **Python 3.12 + FastAPI**, a NATS JetStream durable consumer. Repo `ktayl-dms/classifier/`, image `ghcr.io/andrelair-platform/dms-classifier`, deployed via `services/dms-classifier/helm` + `apps/is/dms/dms-classifier-dev.yaml` |
| OCR | the self-hosted **indra** service (CPU-only, ~76 MB model, in-ns) — quality drives match accuracy |
| Governed AI | **Presidio** PII-masking **before** the LLM; LiteLLM team key; starts on an on-cluster model |
| Decision gates | confidence threshold · the candidate must **exist** in the SoR · a **confused-deputy** check (a number that validates but belongs to a *different* client → HITL) |
| Idempotency | a doc already carrying `filed`/`needs-review` is skipped (NATS redelivery is a no-op) |

### M2M auth to the systems of record (SEC-03)

The classifier's **policy** lookup calls `ktayl-core` (`/api/billing/policies/{n}`), which **requires authentication**. The worker mints an **OAuth2 client-credentials** token from Authentik (provider `dms-classifier`) and sends it; `ktayl-core` validates it against the shared Authentik **JWKS** signature + a **trusted-issuer allowlist** (ADR-016). The claims lookup is open on dev. Creds flow Vault `secret/platform/dms-classifier` → ESO → the pod (optional env → unauthenticated fallback until populated, zero churn).

> **Two live gotchas worth knowing** (both caught by end-to-end verification, not unit tests):
> 1. **Consumer-side NetworkPolicy** — `ktayl-core` only allowed `underwriting` on `:8080`; the classifier (`ns ktayl-dms`) timed out until `ktayl-dms` was added to the allow.
> 2. **Issuer exact-match drops `:80`** — Authentik stamps `iss` from the request Host header, which omits the default port, so the token's iss is `…authentik.svc/application/o/dms-classifier/` (no `:80`). An exact-match allowlist entry **with** `:80` 401's a valid token. Match the empirical iss.

**Verified live (2026-11-16):** token mints (1464-char JWT), unauthenticated lookup → `401`, authenticated → `404` (policy-not-found — i.e. **auth accepted**, no longer `401`). The reusable provisioner is `minicloud-ops/scripts/authentik/oidc-m2m-provider.sh`.

### KEDA scale-to-zero + Kargo (#13)

- **KEDA** `ScaledObject` (NATS JetStream consumer-lag trigger, `minReplicaCount: 0`) — the worker **sleeps at 0 replicas** until a document lands, then wakes 0→1 and drains. Verified: `deploy replicas=0`, ScaledObject `Ready=True Active=False` idle.
- **Kargo** (dev-only, git-Warehouse on the public `ktayl-dms` repo, `includePaths: [classifier]`) auto-promotes the `main` build into the dev overlay — no manual `image.tag` bump. A prod Stage is deferred until a prod DMS exists. Verified: Kargo auto-promoted a build live.

## Phase 3 — office-OCR, retention, e-sign

### Office-document OCR (live) — Gotenberg + Tika

Word/Excel/PowerPoint/ODF documents become full-text searchable via the **Paperless-native** office pipeline: **Gotenberg** (render office→PDF) + **Apache Tika** (text extract), two Gatekeeper-compliant stateless Deployments (`PAPERLESS_TIKA_ENABLED=true`, gated on `tika.enabled`). Scans/images keep the built-in Tesseract (and the indra OCR for the classifier). This **supersedes** the Phase-1 "`PAPERLESS_TIKA_ENABLED=false`" note above.

### Document retention — **archive-only**, offsite preservation

A daily CronJob (`python -m app.retention`, runs the classifier image — 12-factor #12) gives every DMS document a durable **offsite R2 copy** classified by its legal retention class + keep-until year (DORA Art. 11-12 business-continuity). It is **archive-only — it has no delete path at all** and ships **DRY-RUN by default**; it's **gated off** until the owner reviews the policy + a dry-run.

The retention standard (French/EU insurer — full matrix in [`ktayl-dms/docs/retention-policy.md`](https://github.com/andrelair-platform/ktayl-dms/blob/main/docs/retention-policy.md)):

| Class | Window | Basis |
|---|---|---|
| policy · claim · financial · regulatory | **10 years** | Code des assurances · Code de commerce L123-22 · ACPR/DORA |
| kyc / AML | **5 years** | CMF L561-12 (AMLD) |
| correspondence | 5 years · internal 3 years · marketing 1 year | civil prescription / operational |
| **default (unclassified)** | **10 years** (conservative) | never under-retain an unknown record |

It encodes both the **regulatory minimum** (how long we *must* keep) and the **GDPR storage-limitation maximum** (when personal data becomes *purge-eligible*) — but **purge is out of scope**: destroying a regulated record is a separate, human-approved, logged step, never a cron. **Verified live:** the dry-run ran the full path (auth → classify → report) with **0 uploads, 0 deletes, 0 errors**.

### E-signature (design sketch) — Docuseal

The DMS↔Docuseal e-sign flow (a document flagged for signature → Docuseal submission → completion webhook → NATS → the signed PDF captured back into Paperless) is a **design sketch** ([`ktayl-dms/docs/esign-flow.md`](https://github.com/andrelair-platform/ktayl-dms/blob/main/docs/esign-flow.md)), **not built** — it crosses a service + legal-evidence boundary (signed-record assurance level, eIDAS), so it's a scoped Path-B epic for board #24, not a blind build.

## Status & roadmap

- **Phase 1 (live):** capture, Tesseract OCR (`fra+eng`), Whoosh search, Authentik SSO, CNPG-backed.
- **Phase 2 (live):** the **dms-classifier** — AI document↔record matching with HITL, M2M auth to the SoR (verified), KEDA scale-to-zero + Kargo (verified).
- **Phase 3:** office-OCR (**live** — Gotenberg/Tika) · retention archival (**live, archive-only, dry-run, gated off**) · e-signature (**design sketch**, not built).

Detailed design + decisions live with the code: [`ktayl-dms/docs`](https://github.com/andrelair-platform/ktayl-dms) — ADR-001 (DMS role), `retention-policy.md`, `esign-flow.md`; the M2M wiring is in `services/dms-classifier/helm` + the ktayl-core issuer/netpol.
