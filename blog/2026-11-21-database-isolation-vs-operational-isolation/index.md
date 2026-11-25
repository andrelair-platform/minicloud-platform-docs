---
slug: database-isolation-vs-operational-isolation
title: "Database Isolation Is Not Operational Isolation — When Postgres Apps Should Share a Cluster"
authors: [andrelair]
tags: [databases, postgresql, cnpg, backup, disaster-recovery, architecture, dora, carnets]
date: 2026-11-21
description: "Browsing the platform's databases, I noticed two Postgres servers host many databases — Backstage 13, the AI server 6. That raised the real design question: when should apps share a Postgres cluster, and when should they get their own? The answer turns on a distinction that's easy to miss — separate databases isolate access, not operations, and especially not recovery."
---

While wiring up a desktop SQL client across the platform's ~20 Postgres instances, I hit a small surprise:
two servers host **many** databases at once. **Backstage** keeps **13** of them (one per plugin —
`backstage_plugin_catalog`, `_auth`, `_scaffolder`, …); the shared **AI** server keeps **6** (one per tool
— `openwebui`, `litellm`, `ragdb`, `vaultwarden`, `flowise`, `mlflow`). Everything else uses one database
per server.

That's a UI curiosity. But it forced the actual design question behind it: **when should apps share a
Postgres cluster, and when should each get its own?** The answer rests on a distinction that's easy to
collapse — and expensive when you do.

{/* truncate */}

## One server, many databases

First, the mental model, because it trips people up. A Postgres **server** (one running instance, one
host:port, one login) is a *container* for many **databases**:

```
Server/instance   (one pod, one host:port, one superuser login)
   └── Databases          ← there can be many
         └── Schemas
               └── Tables
```

The server is an apartment building; each database is an apartment. The `postgres` superuser is the master
key — but you still choose **which apartment** to walk into. (Connect to the wrong one — the empty default
`postgres` database — and you'll swear the data is gone. It isn't; you're in the wrong room.)

Backstage and the AI server hold many apartments on purpose: Backstage runs in *database-per-plugin* mode,
and the AI server consolidates several small tools onto one instance instead of running six separate
Postgres deployments on a resource-tight cluster. Consolidation is a *good* instinct here. The question is
how far to take it — and that's where the two kinds of isolation matter.

## The distinction: database isolation ≠ operational isolation

Putting two apps on one cluster with separate databases and roles gives you **database isolation**. It does
**not** give you **operational isolation**. They are different things:

| | **Database isolation** (separate DB + role) | **Operational isolation** (separate cluster) |
|---|---|---|
| What it controls | **access** — what each app can read/write | **blast radius** — CPU, memory, storage I/O, a cluster-wide outage or upgrade |
| Apps on one cluster still share | — | all of the above, **plus one backup/PITR recovery boundary** |

A role scoped to its own database means LiteLLM can't read Open WebUI's rows. Good. But both still contend
for the same CPU, memory and disk I/O, both go down in the same cluster outage, both move together on an
upgrade — and, the part that bites hardest, **both live inside the same physical-backup boundary.**

## The recovery boundary is the one people miss

A CloudNativePG physical backup + point-in-time recovery restores the **whole cluster** — not a single
database. So "restore only `litellm` to yesterday 14:00" is not a one-liner. It's:

1. restore the **entire** cluster to a **temporary** instance at that timestamp,
2. `pg_dump` the `litellm` database out of it,
3. load it back into the live cluster.

Separate databases do **not** buy you separate recovery. A **dedicated cluster** does. That single fact
reorders a lot of "just put it on the shared one" decisions.

## So where does each app go?

The rule I landed on: **consolidate low-risk workloads, isolate the recovery-critical ones.**

| Workload | Placement | Why |
|---|---|---|
| Open WebUI · Flowise · LiteLLM · MLflow | **Shared** cluster, DB + role per app | low-risk; share capacity and maintenance; isolate *access*, not operations |
| Retrieva · `ragdb` | Shared if indexing is light; **dedicated** if it contends | bulk ingest + vector-index builds fight interactive queries for CPU/disk |
| Backstage (13 plugin DBs) | **One** cluster for all of them | keep separate only if the dev portal must survive an AI/workplace DB incident |
| **Authentik** | **Dedicated** | an auth outage blocks many services and complicates every other recovery |
| **Vaultwarden** | **Dedicated**, off the AI cluster | break-glass credentials need a recovery path independent of AI workloads |

Two of those are non-negotiable on a platform you have to *recover*: the thing that authenticates everything
(Authentik) and the thing that holds break-glass credentials (Vaultwarden) must not share a failure or
recovery boundary with a pile of experimental AI tools.

## A correction to the usual hand-wave

"One database per server" is a simplification. One Postgres **instance accepts many logins**, and a CNPG
cluster runs a **primary plus replicas**. For shared hosting the discipline is: **one role per app, scoped
to its own database, with a per-role `connectionLimit`** so one chatty app can't exhaust the cluster's
connections. Use the superuser as a *separate admin login* only when you deliberately want to browse across
databases.

## Don't argue it — measure it

The honest move isn't to declare a policy; it's to prove one. Before migrating more workloads onto the
shared cluster, I'd:

1. **Consolidate the lightweight *dev* databases** first (lowest stakes).
2. **Run one restore drill:** recover `litellm` into a *temporary* cluster **while the live shared cluster
   keeps serving** the other tools. That's the whole thesis under test — can you recover one app without
   taking down its neighbours?
3. **Measure the Longhorn PVC + replica footprint actually eliminated.** On a cluster whose real
   bottleneck is storage-replica rebuilds, that number — not the count of databases DBeaver shows — is what
   tells you whether to consolidate further.

## The line worth keeping

**Separate databases isolate access. Only a separate cluster isolates operations — and recovery.** Decide
placement on the second one: *if I had to restore this app alone, at 3am, while everything else kept
running, would today's layout let me?* If yes, share freely. If no, it has earned its own cluster.
