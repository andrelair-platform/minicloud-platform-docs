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

## Status & roadmap

- **Phase 1 (live on dev):** capture (upload + `consume/` folder), Tesseract OCR (`fra+eng`), Whoosh full-text search, Authentik SSO, CNPG-backed.
- **Phase 2 (future):** document↔business matching — tags + a KEDA-scaled AI worker that reads a scanned claim/policy document and proposes the claim#/policy# it belongs to (reuses the AI platform).
- **Phase 3 (future):** office-doc OCR (Gotenberg/Tika), retention/archival policies, doc generation, deeper e-sign (Docuseal) hand-off.

Detailed design + the adopt decision live with the code: [`ktayl-dms/docs/architecture/adr/ADR-001`](https://github.com/andrelair-platform/ktayl-dms).
