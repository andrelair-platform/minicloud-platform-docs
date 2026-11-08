"""Data Platform — TARGET architecture (system-design view, mingrammer `diagrams`).

The hybrid lakehouse decided in ktayl-data-platform ADR-006/007/008:
  Source OLTP DBs → S3 RAW LAKE (replayable Parquet) → DuckDB transform (reads S3 directly,
  dbt-duckdb) → CNPG serving marts (fact/dim, MDM-keyed) → Metabase BI.
S3 = lake (storage) · DuckDB = transform engine · CNPG = serving store · dbt docs + YAML registry
= catalog/lineage. AWS provisioned by OpenTofu (minicloud-cloud); runtime by ArgoCD. No static AWS keys.

Run via the central venv:  python src/data_platform_target.py   (see Makefile `make generate`).
Output → static/img/architecture/data-platform-target.{svg,png} (base64-inlined afterwards).
"""
from __future__ import annotations

from diagrams import Cluster, Diagram
from diagrams.aws.storage import S3
from diagrams.aws.cost import Budgets
from diagrams.aws.security import IAMRole
from diagrams.onprem.iac import Terraform
from diagrams.onprem.analytics import Dbt, Metabase
from diagrams.onprem.database import Postgresql
from diagrams.onprem.compute import Server
from diagrams.onprem.client import User

from _theme import OUT, GRAPH_ATTR, NODE_ATTR, EDGE_ATTR, cluster_attr, node, FLOW, WIRE, DASH
from _theme import GREEN, AMBER, SLATE, CYAN, MUTED

OUTFILE = str(OUT / "data-platform-target")

with Diagram(
    "Data Platform — Target Architecture  (S3 lake · DuckDB transform · CNPG serving)",
    filename=OUTFILE,
    outformat=["svg", "png"],
    show=False,
    direction="TB",
    graph_attr={**GRAPH_ATTR, "ranksep": "1.05", "nodesep": "0.6", "splines": "spline"},
    node_attr=NODE_ATTR,
    edge_attr=EDGE_ATTR,
):
    # ---- 1. Source systems (OLTP · per-domain · in-cluster) -------------------
    with Cluster("1 · Source systems  (OLTP · per-domain silos · in-cluster)",
                 graph_attr=cluster_attr(SLATE)):
        src_pol = node(Postgresql, "Policy (PAS)\nktayl-policy-service", icon="postgresql.png")
        src_clm = node(Postgresql, "Claims read-model\nktayl-claims (CNPG)", icon="cnpg.png")
        src_uw = node(Postgresql, "Underwriting\nktayl-underwriting", icon="postgresql.png")
        src_bill = node(Postgresql, "Billing · GL\nktayl-core · ERPNext", icon="postgresql.png")

    # ---- 2. AWS cloud — raw data lake (OpenTofu-provisioned) ------------------
    with Cluster("2 · AWS Cloud — raw data lake  (OpenTofu / minicloud-cloud · ~$10/mo budget)",
                 graph_attr=cluster_attr(AMBER)):
        s3 = S3("S3 RAW LAKE\nParquet · versioned · manifest\nchecksums · REPLAYABLE archive")
        tf = Terraform("OpenTofu\nbudget · bucket · IAM")
        budget = Budgets("AWS Budget\nalerts $5 / $8 / $10")
        iam = IAMRole("Scoped IAM · short-lived STS\n(NO static keys)")

    # ---- 3. Transform (ephemeral · columnar · reads S3 directly) --------------
    with Cluster("3 · Transform  (ephemeral Job · columnar · reads S3 Parquet directly)",
                 graph_attr=cluster_attr(CYAN)):
        duck = node(Server, "DuckDB + dbt-duckdb\nstaging → curated → marts\n(NO custom loader)", icon="k3s.png")
        ingctrl = node(Postgresql, "ingestion-control table\nbatch idempotency · replay", icon="cnpg.png")

    # ---- 4. Serving (conformed · MDM-keyed · concurrent) ---------------------
    with Cluster("4 · Serving  (CNPG · conformed marts · Metabase-friendly)",
                 graph_attr=cluster_attr(GREEN)):
        cnpg = node(Postgresql, "CNPG serving marts\nfact_* / dim_* · MDM-keyed\n(Combined Ratio · RoRAC)", icon="cnpg.png")
        mb = Metabase("Metabase\ndashboards · KPIs")

    # ---- 5. Catalog / governance (cross-cutting) -----------------------------
    with Cluster("5 · Catalog & governance", graph_attr=cluster_attr(MUTED)):
        dbtdocs = Dbt("dbt docs\nmodel catalog + lineage")
        registry = node(Server, "YAML dataset registry\nowner · source · PII · retention")
        vault = node(Server, "Vault\ndynamic AWS creds (STS)", icon="vault.png")

    # ============================= relationships ==============================
    # sources → raw lake (extract as Parquet)
    for s in (src_pol, src_clm, src_uw, src_bill):
        s >> FLOW("extract → Parquet") >> s3

    # raw lake → DuckDB transform (reads S3 Parquet natively — no loader)
    s3 >> FLOW("DuckDB reads Parquet (httpfs)") >> duck
    duck >> DASH("tracks batches") >> ingctrl

    # transform → serving (materialize conformed marts into CNPG)
    duck >> WIRE("materialize marts") >> cnpg
    cnpg >> FLOW("query") >> mb

    # provisioning + guardrails (backing / dashed)
    tf >> DASH("provisions") >> s3
    budget >> DASH("cost alerts", color=AMBER) >> s3
    vault >> DASH("short-lived STS creds") >> iam
    iam >> DASH("read-only") >> duck

    # catalog / lineage (backing / dashed)
    duck >> DASH("models + lineage") >> dbtdocs
    s3 >> DASH("documented in") >> registry
