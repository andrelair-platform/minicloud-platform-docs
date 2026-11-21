---
id: db-credentials
title: Where database credentials live (the storage map + discipline)
sidebar_label: 🔑 DB credentials
---

# Where database credentials live

:::note Verified against the live cluster (2026-11-21)
The companion to the [DBeaver DB cockpit](/platform/developer-platform/dbeaver-db-access): that page is
*how you connect*; this one is *where the password comes from*. The **discipline** behind it is the
auto-loaded rule [`db-credentials.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/db-credentials.md).
:::

Credentials live in **three places, by role** — never conflate them.

## 1. Runtime copy — a Kubernetes Secret in each DB's namespace (always)
What the pods, and the DBeaver `kubectl … get secret … | base64 -d` one-liner, actually read.

- **CNPG clusters** → `<cluster>-app` (`kubernetes.io/basic-auth`: `username`/`password`/`dbname`), owned
  by the CNPG `Cluster`. e.g. `ktayl-core-cnpg-app`.
- **Plain / vendor DBs** → a named Opaque Secret: `ai-postgresql-secret`, `backstage-postgres-secret`,
  `temporal-db-secret`, `bookstack-db-secret`, `ktayl-itsm-db`, `erpnext`, …

## 2. Source of truth — where the password *comes from*

| Source | Databases | Rotate by |
|---|---|---|
| **Vault `secret/platform/*` → ESO** *(authoritative — the standard)* | all plain/vendor DBs (ai, backstage, temporal, bookstack, itsm, erp, ktayl-iam-dev, langfuse-clickhouse) **+** the CNPG clusters with a `*-role` ExternalSecret: **authentik · synapse (chat) · data-platform · ktayl-iam (prod) · langfuse · nextcloud · retrieva · ktayl-core (prod) · claims (prod) · underwriting (prod) · paperless** *(last 4 backfilled 2026-11-21)* | edit Vault → ESO re-renders the k8s Secret → CNPG reconciles |
| **CNPG operator-generated** *(the `-app` secret is the only store — acceptable for dev)* | the **dev** instances of claims · ktayl-core · underwriting (regenerable, low-stakes) | via CNPG |

How the Vault-sourced CNPG case works: the cluster's `spec.managed.roles[].passwordSecret` points at an
ESO-rendered secret (e.g. `retrieva-cnpg-role`), so the role password **traces to Vault**; the operator
keeps `<cluster>-app` reconciled to it. Reference clusters: `retrieva-cnpg`, `langfuse-postgres`.

## 3. Human break-glass — Vaultwarden (emergency, SSO down)
Emergency **admin** logins live in the Vaultwarden `controller-break-glass` folder; Vault's own
crown-jewels are age-encrypted on the controller. These are **not** the per-DB runtime creds (most DB app
passwords are in Vault/CNPG, not individually in Vaultwarden). Vault auto-unseals via AWS KMS, so a reboot
needs no human key.

## The discipline (the standard for every NEW database)
> **Vault is the source of truth for every database credential; the in-namespace k8s Secret is a rendered
> copy; human break-glass is Vaultwarden; nothing else.**

- **CNPG** → source the role password from Vault via an ESO `ExternalSecret` referenced by
  `managed.roles[].passwordSecret`. Do **not** ship a cluster whose only store is the operator `-app` secret.
- **Plain/vendor DB** → credential via ESO from Vault; never a chart default, never a literal in values,
  never committed (the `guard-write` hook blocks secret material).
- **Former gap — now closed (2026-11-21):** the 4 operator-generated-only prod clusters (ktayl-core,
  claims, underwriting, paperless) were backfilled — Vault seeded with the current `-app` password, then
  `managed.roles` + a `-role` ExternalSecret wired (no-outage: CNPG re-applied the identical value).
  Only the **dev** instances remain operator-generated (acceptable — regenerable).

Full rule (authoritative): [`db-credentials.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/.claude/rules/db-credentials.md).

## Retrieve any DB password (works in every case — reads the runtime Secret)
```bash
# CNPG:
kubectl --context minicloud-oidc -n <ns> get secret <cluster>-app \
  -o jsonpath='{.data.password}' | base64 -d; echo
# plain/vendor — discover the key first:
kubectl --context minicloud-oidc -n <ns> get secret <name> \
  -o go-template='{{range $k,$v := .data}}{{$k}}{{"\n"}}{{end}}'
```
The `*-cnpg-r2` secrets alongside a CNPG cluster are **R2 backup** credentials, not a DB login.
