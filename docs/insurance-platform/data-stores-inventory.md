---
id: data-stores-inventory
title: Data stores inventory (as-built)
sidebar_label: 🗄️ Data stores inventory
---

# Data stores inventory — the ktayl-solution IS

:::note Verified, live
Produced by querying the **running cluster** (CNPG clusters + StatefulSets + Deployments + NATS + the
control-plane store), not from memory. Snapshot date: **2026-10-06**. Reproduce with the commands in
*Operate / verify* below. This is the companion to [Canonical data model](canonical-data-model) (the
*logical* model) — this page is the *physical* "what engine runs where."
:::

The data layer is **PostgreSQL-standard with vendor-forced exceptions**, plus purpose-built stores for
vectors, analytics, cache, events, secrets, objects and observability.

## Relational

### PostgreSQL — the house standard (~20 instances, 3 deployment styles)
| Style | Image | Where (ns / service) |
|---|---|---|
| **CNPG operator** (preferred) | `cloudnative-pg/postgresql:17.4` | authentik (2) · claims (dev 1 / prod 1) · underwriting (dev 1 / **prod 2**) · nextcloud · data-platform (`dp-postgres`) |
| **Custom base** `postgresql:18.4.0-noavx512` (+ pgvector) | Harbor | `postgresql-ai` (RAG) · `postgresql-synapse` (Matrix) |
| **Plain / vendor StatefulSet** | `postgres:16/15-alpine`, bitnami | ktayl-iam (dev+prod) · ktayl policy-service (dev+prod) · retrieva (dev+dev) · backstage (bitnami 15.4) · plane (15.7) · temporal (15) · **harbor-database** (goharbor) |
| **External** (points elsewhere via `DATABASE_URL`) | — | **langfuse** (no Postgres in-ns — metadata DB is external) |

> ⚠️ **Consolidation debt:** Postgres is universal but deployed **three inconsistent ways** (CNPG vs raw
> StatefulSet vs vendor-bundled). CNPG is the intended standard (backup/HA/PITR) — the raw/vendor ones are
> candidates to migrate. See [Database backup](../backup-dr/database-backup) and the custom base image note below.

### MariaDB — the vendor-forced exception (3 — the old "one deviation" note is stale)
`mariadb:10.6.27` **ERPNext** · `mariadb:11.4` **BookStack** · `mariadb:11.4` **GLPI**. All three because
the *adopted* app (Frappe/ERPNext, BookStack, GLPI) is **MariaDB-native** — adopt-vs-build drives the
engine, not a platform preference.

### MySQL / Oracle — legacy simulation only
`globalcore-legacy` ships `docker-compose.yml` (**MySQL**) + `docker-compose.oracle.yml` (**Oracle**) — the
Java/SOAP legacy the Claims ACL strangles. Local-dev / ACL target, **not on-cluster**.

### SQLite — the cluster's own state
**k3s control-plane datastore = kine → SQLite** (on the control-plane node; backed up by the kine-backup
CronJob + a controller systemd timer). Nextcloud was on SQLite historically → migrated to CNPG.

## Vector / search
- **Qdrant** `v1.11.0` (ai) — the RAG vector DB (retrieva · open-webui · rag-ingest).
- **pgvector** — vector search *inside* Postgres (the `-noavx512` base; ai + synapse). → two coexisting
  vector approaches (Qdrant vs pgvector) — a deliberate split (ADR-worthy).

## Analytics (OLAP) & BI
- **ClickHouse** `25.2.1` + **Zookeeper** (langfuse) — columnar store for LLM traces.
- **Metabase** `v0.50.26` (data-platform) — BI; queries the `dp-postgres` medallion.

## Cache / KV / broker
- **Redis / Valkey** (~9): litellm-cache · langfuse-redis · nextcloud-redis · plane-redis · harbor-redis ·
  argocd-redis · matrix-synapse-redis · erpnext-valkey (cache + queue) · retrieva-redis.
- **RabbitMQ** `3.13.6` (plane) — AMQP broker.

## Specialised stores
| Store | Engine | Role |
|---|---|---|
| **Vault** | Raft (integrated storage) | secrets KV (AWS-KMS auto-unseal) |
| **NATS JetStream** | file-backed streams | event store: `JOBS · POLICY_EVENTS · UNDERWRITING_EVENTS · HR_LIFECYCLE · CLAIMS_CDC(_PROD)` |
| **MinIO** | S3 object | `plane-ce-minio` (in-cluster) + **controller MinIO** (Docker, backup target) + **Cloudflare R2** (off-site CNPG barman) |
| **Prometheus / Loki / Tempo** | TSDB / logs / traces | observability datastores |
| **Stalwart** | RocksDB (embedded) | mail store (Longhorn PVC) |

## Headline observations
1. **Postgres = standard; MariaDB = vendor-forced** (ERPNext/GLPI/BookStack). The "one MySQL deviation"
   claim is outdated — it's 3, all adopted-app-driven.
2. **Postgres deployment is inconsistent** (CNPG / raw STS / vendor) — the biggest cleanup target; migrate
   load-bearing ones onto CNPG for backup/PITR parity.
3. **Two vector approaches** (Qdrant + pgvector) coexist deliberately.
4. **The custom `postgresql-noavx512` base is a single point of fragility** — it lives only in Harbor and
   was once GC'd out; protected by an always-retain rule. See the registry retention runbook.

## Operate / verify
```bash
# CNPG Postgres clusters
ssh controller "kubectl --context minicloud get cluster.postgresql.cnpg.io -A"
# every stateful datastore (image per workload)
ssh controller "kubectl --context minicloud get sts -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image"
# DBs that run as Deployments (metabase, redis/valkey…)
ssh controller "kubectl --context minicloud get deploy -A -o wide | grep -iE 'postgres|maria|redis|valkey|clickhouse|qdrant|metabase|rabbit|minio'"
# NATS JetStream streams
ssh controller "kubectl exec -n messaging <nats-box> -- nats -s nats://nats:4222 stream ls"
```

## See also
- Logical model → [Canonical data model](canonical-data-model) · System of record → [System of record](system-of-record)
- Backup/DR → [DR runbook](../backup-dr/dr-runbook) · Custom base image + the SIGILL story → the Docker course
  (`ktayl-docker-course`, Module 0 + the registry retention troubleshooting).
