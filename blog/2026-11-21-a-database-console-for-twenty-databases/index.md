---
slug: a-database-console-for-twenty-databases
title: "A Database Console for Twenty Databases — Why I Deleted Adminer and Picked DBeaver"
authors: [andrelair]
tags: [databases, postgresql, mariadb, clickhouse, kubernetes, cnpg, security, tooling, dbeaver]
date: 2026-11-21
description: "The platform grew to ~20 PostgreSQL instances plus MariaDB and ClickHouse across many namespaces. A single in-cluster web SQL console (Adminer) stopped being the right answer. Here is the tool comparison I ran, why a local client beat a hosted one, and the three Kubernetes-specific details that make it safe."
---

The platform quietly crossed a line: it now runs **~20 PostgreSQL instances** (CloudNativePG clusters with
dev/prod pairs, plus a few plain StatefulSets), **3 MariaDB** databases, and a **ClickHouse** store — spread
across a couple of dozen namespaces. The question stopped being *"how do I open a SQL console?"* and became
*"how do I give myself a console over twenty-plus databases without turning that console into a liability?"*

I had been using **Adminer** — a single in-cluster web SQL UI behind SSO. It was fine at three databases.
At twenty-three, across dev and prod, it was the wrong shape. This post is the comparison I actually ran
and the decision I landed on.

{/* truncate */}

## What was wrong with the thing I already had

Adminer is a lovely 400 KB PHP file. But as *the* database cockpit for a multi-namespace cluster it has
three structural problems:

1. **It's a standing attack surface.** A web UI that can reach several databases' namespaces is, by
   definition, a permanent pod + ingress + a set of NetworkPolicy holes into DB namespaces. One
   misconfiguration and every database it can see is a browser tab away.
2. **Every tab looks identical.** There is no visual difference between `claims (dev)` and
   `claims (PROD)`. The only thing standing between a careless `DELETE` and production is your own
   attention. That is not a control.
3. **Two engines only.** Adminer does PostgreSQL and MySQL/MariaDB. It does not speak ClickHouse — so it
   was never going to be the *one* tool anyway.

None of these are Adminer's fault. They're what happens when you ask a single-file web console to be an
enterprise-wide database cockpit.

## The field I compared

I wanted one tool for every SQL engine, dev/prod safety I could *see*, and — the part that matters on a
self-hosted cluster — **no new thing to run and secure**. Here's how the candidates scored against *this*
setup (not in the abstract):

| Tool | Shape | Engines it covers here | Dev/Prod guardrail | Cluster footprint | Cost | Verdict |
|---|---|---|---|---|---|---|
| **Adminer** | in-cluster web UI | PostgreSQL, MariaDB | none (identical tabs) | **permanent** pod + ingress + netpol holes | FOSS | **retired** |
| pgAdmin / phpMyAdmin | web or desktop, single-engine | one engine each | per-tool | web = footprint; desktop = none | FOSS | one tool *per engine* — wrong for 4 engines |
| **DBeaver CE** | local desktop | **PostgreSQL, MariaDB, ClickHouse, SQLite** (+ any JDBC) | **connection-type colour + read-only default** | **zero** (runs on my laptop) | free (Apache-2.0) | **chosen** |
| DBeaver PRO | local desktop | + Redis, MongoDB, Cassandra… | same | zero | paid | not needed yet — free companions cover those |
| TablePlus | local desktop | many | per-connection colour | zero | paid | polished, but no edge over CE *for this* |
| Beekeeper Studio | local desktop | PostgreSQL, MySQL… | some | zero | FOSS + paid tier | lighter, but no native ClickHouse |

Two columns decided it: **"engines it covers here"** and **"cluster footprint."** DBeaver CE is the only
free tool that speaks all three of my SQL engines in one window *and* adds nothing to the cluster — it's a
desktop app that talks over my own `kubectl`. TablePlus and Beekeeper are genuinely nice; they just didn't
beat *free + all-my-engines + zero-footprint* on this particular board.

### Head-to-head: Adminer vs DBeaver, factor by factor

Zooming into the two that actually ran here — the incumbent and its replacement:

| Factor | Adminer (in-cluster web app) | DBeaver (local desktop + k8s tunnel) |
|---|---|---|
| **Security & attack surface** | runs inside Kubernetes, exposed via Ingress + SSO; one misconfiguration puts every database it can reach behind a browser tab | **zero cluster footprint** — nothing deployed; access is strictly my own kubeconfig RBAC |
| **Prod vs dev safety** | every tab looks identical — easy to run a `DELETE` on `ktayl-core-prod` thinking it's dev | **Production connections render red, open read-only**, and confirm on execute |
| **Managing 23+ instances** | retype host/user/secret on each login, or hardcode creds into config | connections saved in **Production / Development folders**; passwords pulled from each DB's Secret per session, kept in the encrypted local store |
| **ClickHouse support** | none — can't open `langfuse-clickhouse` at all | full, in the same window as Postgres and MariaDB |
| **Feature depth** | table browser + a raw SQL box | autocomplete, ER diagrams, visual `EXPLAIN` plans, cross-DB export, multi-tab query history |

### The one case where Adminer would still make sense

To be fair to the 400 KB file: there *is* a scenario it wins — **emergency, browser-only access from a
device with no `kubectl` and no laptop** (say, a non-developer teammate reaching a database behind Authentik
SSO from a phone). If that need ever becomes real, the right answer is a *scoped* Adminer pointed at
**non-prod only** — not the cluster-wide console it had drifted into being. Today that need doesn't exist,
so the standing attack surface wasn't worth keeping on the bet that it might.

### The non-SQL stores go to purpose-built companions

The honest limit: DBeaver CE does not cover **Redis/Valkey** (~11 of them), **OpenSearch** (sanctions
screening), or **Qdrant** (RAG vectors). Rather than buy PRO for Redis, I let each specialist tool do its
job — **RedisInsight**, **OpenSearch Dashboards** (already web-based), and **Qdrant's** built-in
`:6333/dashboard`. A "single pane of glass" that's worse at every pane isn't worth the licence.

## The decision: move the console to the client

The reframing that made it click: **a database console is an attack surface, and the cheapest attack
surface is the one that doesn't exist.** A local client over `kubectl port-forward` has *zero* standing
footprint. Access is bounded by my own kubeconfig RBAC — there is no shared, always-on service with broad
database reach for anyone to find. Deleting Adminer didn't just swap tools; it removed a permanent pod, an
ingress, an SSO integration, and a fistful of cross-namespace NetworkPolicy holes.

## Three Kubernetes details that make it actually safe

Pointing a desktop client at in-cluster databases is only as good as the wiring. Three things matter:

**1. Tunnel to the `-rw` Service, never a pod.** CloudNativePG clusters expose `<cluster>-rw`, which always
tracks the current primary. Forward to that and a failover is invisible to you; forward to a pod and you'll
be reading a replica — or nothing — after the next switchover.

```bash
kubectl --context minicloud-oidc -n ktayl-core-prod \
  port-forward svc/ktayl-core-cnpg-rw 55438:5432
```

**2. Credentials are pulled per session — never stored in the connection file.** The generated connection
set carries hosts, ports and database names, but **no passwords**. Each password is read from the
database's own Kubernetes Secret at connect time, into the client's encrypted store:

```bash
kubectl --context minicloud-oidc -n ktayl-core-prod get secret ktayl-core-cnpg-app \
  -o jsonpath='{.data.password}' | base64 -d
```

A connection file that leaks is a map, not a key.

**3. Production is red and read-only by default.** This is the control Adminer couldn't give. Every `*-prod`
connection is tagged `Production` — the client paints its tabs **red** and opens them **read-only**, with a
confirm prompt on execute. Writing to production is a deliberate toggle, not an accident of which tab had
focus. Dev connections stay plain.

The whole thing is generated from one source-of-truth table (port · namespace · `-rw` service · engine ·
env · secret), so the tunnels, the connection file, and the docs never drift.

## What I'd tell myself three databases ago

Not *"pick DBeaver."* The transferable lesson is the question order: **start from the attack surface and the
blast radius, not the feature list.** The best console for twenty databases turned out to be the one that
runs nowhere, stores no passwords, and makes production visibly dangerous to touch. The feature comparison
only mattered *after* those constraints had already thrown out most of the field.
