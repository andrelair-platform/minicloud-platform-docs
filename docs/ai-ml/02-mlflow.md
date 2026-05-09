---
id: mlflow
title: MLflow (Deferred)
sidebar_position: 2
---

# MLflow — ML Experiment Tracking & Model Registry

:::caution Status: Deferred to a future phase
The original Phase 19 plan called for **Ollama + MLflow + Kubeflow**.
We deliberately scoped Phase 19 down to **Ollama + Open WebUI only** —
same pattern as Phase 11 (deferred Crossplane), Phase 13 (deferred
GitLab), Phase 15 (deferred Vault), Phase 16 (deferred
n8n/Temporal/Airflow), Phase 18 (deferred Backstage plugins).

**Why MLflow is deferred:**

1. **No active ML training workload.** MLflow's value is tracking
   experiments + registering trained models. We have no model training
   on this cluster. Installing MLflow without a real workload to feed
   it = "MLflow exists" theatre.
2. **Pairs naturally with a real ML pipeline.** The right time to
   install MLflow is alongside an actual training workload (e.g.,
   fine-tuning a model from Ollama, an RL training loop, a Jupyter
   notebook with sklearn experiments).

The likely future home is a dedicated "ML pipeline" phase when there's
a real training/experimentation workload to track.

This page is kept as conceptual reference. The implementation has not
been done.
:::

MLflow tracks your machine learning experiments — hyperparameters, metrics, model artifacts — and provides a model registry where you promote models from experimentation to production. It gives your ML work the same discipline as software engineering.

---

## What MLflow Tracks

```text
Each ML experiment run records:
  ✔ Hyperparameters (learning rate, batch size, epochs...)
  ✔ Metrics (accuracy, loss, F1 score per epoch)
  ✔ Artifacts (model weights, plots, confusion matrices)
  ✔ Environment (Python version, dependencies)
  ✔ Code version (git commit hash)
```

---

## Architecture on Your Cluster

```text
ML Training Job (pod or local machine)
        │ logs metrics + artifacts
        ▼
MLflow Tracking Server (k3s pod)
        │ stores
        ├── Metadata → PostgreSQL
        └── Artifacts → MinIO (S3-compatible)
        │
        ▼
MLflow UI (browser)
  → Compare runs, promote models to registry
```

---

## Deploy MLflow

```bash
kubectl create namespace mlflow
```

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlflow
  namespace: mlflow
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mlflow
  template:
    metadata:
      labels:
        app: mlflow
    spec:
      containers:
        - name: mlflow
          image: ghcr.io/mlflow/mlflow:latest
          command:
            - mlflow
            - server
            - --host=0.0.0.0
            - --port=5000
            - --backend-store-uri=postgresql://mlflow:password@postgres-svc/mlflow
            - --default-artifact-root=s3://mlflow-artifacts/
          env:
            - name: MLFLOW_S3_ENDPOINT_URL
              value: http://minio.minio.svc:9000
            - name: AWS_ACCESS_KEY_ID
              value: minioadmin
            - name: AWS_SECRET_ACCESS_KEY
              value: minioadmin
          ports:
            - containerPort: 5000
---
apiVersion: v1
kind: Service
metadata:
  name: mlflow
  namespace: mlflow
spec:
  type: LoadBalancer
  selector:
    app: mlflow
  ports:
    - port: 5000
      targetPort: 5000
```

```bash
kubectl apply -f mlflow.yaml
```

---

## Log an Experiment (Python)

```python
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

mlflow.set_tracking_uri("http://10.0.0.202:5000")
mlflow.set_experiment("iris-classification")

X, y = load_iris(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

with mlflow.start_run():
    n_estimators = 100
    mlflow.log_param("n_estimators", n_estimators)

    model = RandomForestClassifier(n_estimators=n_estimators)
    model.fit(X_train, y_train)

    accuracy = accuracy_score(y_test, model.predict(X_test))
    mlflow.log_metric("accuracy", accuracy)

    mlflow.sklearn.log_model(model, "random-forest-model")
    print(f"Accuracy: {accuracy:.3f}")
```

---

## Model Registry Workflow

```text
1. Train multiple runs with different hyperparameters
2. Compare in MLflow UI → pick best run
3. Register model: "iris-classifier" → version 1
4. Transition: Staging → Production
5. Serving layer loads model from registry
```

In MLflow UI:
- **Models** tab → register from any run
- Set stage: `None → Staging → Production → Archived`

---

## Serve a Model

```bash
mlflow models serve \
  -m "models:/iris-classifier/Production" \
  --host 0.0.0.0 \
  --port 8888
```

REST API:

```bash
curl http://10.0.0.202:8888/invocations \
  -H "Content-Type: application/json" \
  -d '{"dataframe_split": {"columns": ["sl","sw","pl","pw"], "data": [[5.1,3.5,1.4,0.2]]}}'
```

---

## Done When

```text
✔ MLflow tracking server Running
✔ MinIO bucket mlflow-artifacts created
✔ First experiment logged via Python client
✔ Model registered in model registry
✔ UI accessible at MetalLB IP
```
