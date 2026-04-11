---
id: airflow
title: Phase 17 — Apache Airflow
sidebar_position: 3
---

# Phase 17 — Apache Airflow — Data Pipeline Orchestration

Apache Airflow is the standard tool for scheduling and orchestrating data pipelines. Workflows are defined as Python DAGs (Directed Acyclic Graphs) — each node is a task, edges define execution order and dependencies.

---

## When to Use Airflow vs Temporal vs n8n

| Tool | Best For |
|---|---|
| **n8n** | Event-driven API automations, quick integrations |
| **Temporal** | Long-running business workflows, retries, sagas |
| **Airflow** | Scheduled data pipelines, ETL, batch jobs, ML workflows |

On this cluster, Airflow primarily handles **data and ML workloads** — scheduled batch jobs, training pipelines, data ingestion — complementing Temporal and n8n.

---

## Core Concepts

```text
DAG      → A workflow definition (Python file)
Task     → A single unit of work (run SQL, call API, train model)
Operator → Pre-built task types (PythonOperator, BashOperator, KubernetesPodOperator)
Schedule → Cron expression or interval
XCom     → Pass data between tasks
```

---

## Deploy Airflow via Helm

```bash
helm repo add apache-airflow https://airflow.apache.org

helm install airflow apache-airflow/airflow \
  --namespace airflow \
  --create-namespace \
  --set executor=KubernetesExecutor \
  --set dags.gitSync.enabled=true \
  --set dags.gitSync.repo="https://gitlab.yourdomain.com/platform/airflow-dags.git" \
  --set dags.gitSync.branch=main \
  --set data.metadataConnection.host=postgres-svc \
  --set data.metadataConnection.db=airflow \
  --set redis.enabled=false \
  --set postgresql.enabled=false
```

`KubernetesExecutor` runs each task as a separate pod — scales to cluster capacity, no idle workers.

`gitSync` pulls DAGs directly from your GitLab repo — push a DAG, it appears in Airflow automatically.

---

## Access Airflow UI

```bash
kubectl port-forward svc/airflow-webserver -n airflow 8080:8080
```

Open: `http://localhost:8080`

Default credentials: `admin / admin`

---

## Example DAG — Nightly Data Ingestion

```python
# dags/nightly_ingest.py
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator

def extract_data(**context):
    import requests
    data = requests.get("https://api.example.com/data").json()
    context["ti"].xcom_push(key="raw_data", value=data)
    return len(data)

def transform_data(**context):
    raw = context["ti"].xcom_pull(key="raw_data")
    transformed = [
        {"id": r["id"], "value": r["value"] * 1.2}
        for r in raw if r["value"] > 0
    ]
    context["ti"].xcom_push(key="transformed", value=transformed)

with DAG(
    "nightly_ingest",
    schedule_interval="0 2 * * *",    # 02:00 UTC every night
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
) as dag:

    extract = PythonOperator(
        task_id="extract",
        python_callable=extract_data,
    )

    transform = PythonOperator(
        task_id="transform",
        python_callable=transform_data,
    )

    load = PostgresOperator(
        task_id="load",
        postgres_conn_id="postgres_cluster",
        sql="INSERT INTO data_table VALUES (%s, %s)",
    )

    extract >> transform >> load
```

---

## Example DAG — ML Training Pipeline

```python
# dags/ml_training.py
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
from datetime import datetime

with DAG("ml_training", schedule_interval="@weekly",
         start_date=datetime(2026, 1, 1)) as dag:

    prepare_data = KubernetesPodOperator(
        task_id="prepare_data",
        name="data-prep",
        namespace="airflow",
        image="harbor.local/ml/data-prep:latest",
        cmds=["python", "prepare.py"],
    )

    train_model = KubernetesPodOperator(
        task_id="train_model",
        name="training",
        namespace="airflow",
        image="harbor.local/ml/trainer:latest",
        cmds=["python", "train.py", "--epochs", "50"],
        resources={"request_cpu": "6", "request_memory": "12Gi"},
    )

    register_model = KubernetesPodOperator(
        task_id="register_model",
        name="mlflow-register",
        namespace="airflow",
        image="harbor.local/ml/trainer:latest",
        cmds=["python", "register.py"],
        env_vars={"MLFLOW_TRACKING_URI": "http://mlflow.mlflow.svc:5000"},
    )

    prepare_data >> train_model >> register_model
```

Each step runs as a Kubernetes pod — using your cluster's full CPU for training.

---

## GitSync — Automatic DAG Deployment

```text
You write a new DAG → git push to GitLab
        │
Airflow gitSync pulls every 60s
        │
New DAG appears in Airflow UI automatically
        │
No restart, no manual upload
```

---

## Done When

```text
✔ Airflow pods Running with KubernetesExecutor
✔ GitSync pulling from GitLab DAG repo
✔ First DAG visible in UI and triggerable
✔ KubernetesPodOperator launching pods successfully
✔ ML training DAG running on cluster resources
```
