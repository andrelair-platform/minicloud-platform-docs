---
id: kubeflow
title: Phase 20 — Kubeflow
sidebar_position: 3
---

# Kubeflow — Full ML Platform on Kubernetes

Kubeflow is the Kubernetes-native ML platform. It orchestrates end-to-end ML pipelines — data prep, training, evaluation, serving — as reproducible, versioned DAGs running directly on your cluster.

---

## What Kubeflow Provides

| Component | Purpose |
|---|---|
| **Pipelines** | DAG-based ML workflow orchestration |
| **Notebooks** | JupyterHub — collaborative notebooks in the browser |
| **Training Operator** | Distributed training (PyTorch, TensorFlow, JAX) |
| **KServe** | Model serving with autoscaling |
| **Katib** | Hyperparameter tuning (AutoML) |
| **Tensorboard** | Training visualization |

---

## Architecture

```text
Data Scientist (browser)
        │
        ▼
Kubeflow Central Dashboard (k3s)
  ├── Notebooks (JupyterHub)
  ├── Pipelines UI (DAG editor)
  └── Models (KServe endpoints)
        │
        ▼
  Pipeline Run (k8s pods)
  ├── Step 1: Data ingestion (pod)
  ├── Step 2: Feature engineering (pod)
  ├── Step 3: Training (pod — uses all available CPUs)
  ├── Step 4: Evaluation (pod)
  └── Step 5: Model registration → MLflow
```

---

## Install Kubeflow

### Using kustomize (official method)

```bash
# Install kustomize
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
sudo mv kustomize /usr/local/bin/

# Clone the manifests
git clone https://github.com/kubeflow/manifests.git
cd manifests

# Install (takes 5–10 minutes)
while ! kustomize build example | kubectl apply -f -; do
  echo "Retrying..."; sleep 10
done
```

### Verify all components

```bash
kubectl get pods -n kubeflow --watch
```

Wait for all pods to be `Running` (may take 10+ minutes on first install).

---

## Access the Dashboard

```bash
kubectl port-forward svc/istio-ingressgateway -n istio-system 8080:80
```

Open: `http://localhost:8080`

Default credentials: `user@example.com / 12341234`

---

## Create a Pipeline (Python SDK)

```python
import kfp
from kfp import dsl

@dsl.component(base_image="python:3.11")
def load_data(output_path: str) -> str:
    import json
    data = {"X": [[1,2],[3,4]], "y": [0,1]}
    with open(output_path, "w") as f:
        json.dump(data, f)
    return output_path

@dsl.component(base_image="python:3.11",
               packages_to_install=["scikit-learn"])
def train_model(data_path: str) -> float:
    import json
    from sklearn.linear_model import LogisticRegression
    with open(data_path) as f:
        data = json.load(f)
    model = LogisticRegression()
    model.fit(data["X"], data["y"])
    return 0.95  # accuracy

@dsl.pipeline(name="simple-ml-pipeline")
def ml_pipeline():
    data_task = load_data(output_path="/tmp/data.json")
    train_task = train_model(data_path=data_task.output)

# Compile and submit
client = kfp.Client(host="http://localhost:8080/pipeline")
client.create_run_from_pipeline_func(ml_pipeline, arguments={})
```

The pipeline creates Kubernetes pods for each step — fully reproducible and auditable.

---

## Distributed Training

Run PyTorch training across all 3 nodes simultaneously:

```yaml
apiVersion: kubeflow.org/v1
kind: PyTorchJob
metadata:
  name: distributed-training
  namespace: kubeflow
spec:
  pytorchReplicaSpecs:
    Master:
      replicas: 1
      template:
        spec:
          containers:
            - name: pytorch
              image: pytorch/pytorch:2.0.0-cuda11.7-cudnn8-runtime
              command: ["python", "train.py", "--distributed"]
              resources:
                requests:
                  cpu: "6"
                  memory: "12Gi"
    Worker:
      replicas: 2   # fast-skunk + fast-heron
      template:
        spec:
          containers:
            - name: pytorch
              image: pytorch/pytorch:2.0.0-cuda11.7-cudnn8-runtime
              command: ["python", "train.py", "--distributed"]
              resources:
                requests:
                  cpu: "6"
                  memory: "12Gi"
```

This uses 18 cores and 36 GiB RAM across all 3 nodes in parallel.

---

## Katib — Hyperparameter Tuning

Automatically search for the best hyperparameters:

```yaml
apiVersion: kubeflow.org/v1beta1
kind: Experiment
metadata:
  name: hp-tuning
  namespace: kubeflow
spec:
  objective:
    type: maximize
    goal: 0.99
    objectiveMetricName: accuracy
  algorithm:
    algorithmName: bayesianoptimization
  parallelTrialCount: 3
  maxTrialCount: 12
  parameters:
    - name: learning_rate
      parameterType: double
      feasibleSpace:
        min: "0.001"
        max: "0.1"
    - name: batch_size
      parameterType: int
      feasibleSpace:
        min: "16"
        max: "128"
  trialTemplate:
    primaryContainerName: training
    trialParameters:
      - name: learningRate
        reference: learning_rate
      - name: batchSize
        reference: batch_size
    trialSpec:
      apiVersion: batch/v1
      kind: Job
      spec:
        template:
          spec:
            containers:
              - name: training
                image: my-training-image:latest
```

Kubeflow runs 3 trials in parallel, picks the best, and converges automatically.

---

## Resource Requirements

| Component | CPU | RAM |
|---|---|---|
| Kubeflow core | 4 cores | 8 GiB |
| Istio service mesh | 2 cores | 4 GiB |
| JupyterHub notebooks | 1–4 per user | 2–8 GiB per user |
| Training jobs | Up to cluster capacity | Up to cluster capacity |

Kubeflow is the heaviest component in this stack — ensure Longhorn storage is set up first.

---

## Done When

```text
✔ All Kubeflow pods Running
✔ Dashboard accessible
✔ First pipeline submitted and completed
✔ JupyterHub notebook spawning successfully
```
