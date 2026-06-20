---
id: temporal
title: Phase 17 — Temporal
sidebar_position: 2
---

:::caution Deferred — not deployed on this cluster
Temporal was the original Phase 16 automation plan. Phase 16 was **replaced by Harbor as Sovereign Registry**. This doc is kept as a planning reference.
:::


# Phase 17 — Temporal — Code-Based Workflow Orchestration

Temporal is a workflow orchestration engine for developers. You write workflows in real code (Python, Go, TypeScript, Java) — Temporal handles retries, timeouts, state persistence, and failure recovery automatically. Think of it as a durable, distributed function runner.

---

## n8n vs Temporal

| | n8n | Temporal |
|---|---|---|
| Interface | Visual (no-code / low-code) | Code (Python, Go, TypeScript) |
| Audience | Ops, non-developers | Developers |
| Complexity | Simple automations | Complex long-running workflows |
| Retries | Basic | Sophisticated (exponential backoff, deadlines) |
| State | Limited | Full — survives restarts and crashes |
| Best for | API integrations, notifications | Business logic, sagas, data pipelines |

**Use both:** n8n for simple event-driven automations, Temporal for complex business workflows.

---

## Key Concepts

```text
Workflow  → A durable function that can run for minutes, hours, or months
Activity  → A single step (call API, send email, run script)
Worker    → A process that executes workflows and activities
Signal    → Send data into a running workflow
Query     → Read state from a running workflow
```

---

## Deploy Temporal in k3s

```bash
helm repo add temporalio https://charts.temporal.io

helm install temporal temporalio/temporal \
  --namespace temporal \
  --create-namespace \
  --set server.replicaCount=1 \
  --set cassandra.config.cluster_size=1 \
  --set elasticsearch.enabled=false \
  --set prometheus.enabled=false \
  --set grafana.enabled=false
```

Access the Temporal UI:

```bash
kubectl port-forward -n temporal svc/temporal-web 8088:8088
```

Open: `http://localhost:8088`

---

## Example Workflow — Node Provisioning Pipeline

This is the kind of workflow Temporal excels at — long-running, multi-step, with retries:

```python
# workflows/provision_node.py
from temporalio import workflow, activity
from datetime import timedelta

@activity.defn
async def trigger_maas_deploy(node_name: str) -> str:
    # Call MAAS API to deploy node
    import httpx
    resp = httpx.post(
        "http://10.0.0.1:5240/MAAS/api/2.0/machines/",
        data={"hostname": node_name, "distro_series": "noble"}
    )
    return resp.json()["system_id"]

@activity.defn
async def wait_for_deployment(system_id: str) -> bool:
    import httpx, asyncio
    for _ in range(60):  # 30 minutes max
        status = httpx.get(
            f"http://10.0.0.1:5240/MAAS/api/2.0/machines/{system_id}/"
        ).json()["status_name"]
        if status == "Deployed":
            return True
        await asyncio.sleep(30)
    return False

@activity.defn
async def run_ansible(node_ip: str) -> None:
    import subprocess
    subprocess.run([
        "ansible-playbook",
        "-i", f"{node_ip},",
        "playbooks/configure-nodes.yml"
    ], check=True)

@workflow.defn
class ProvisionNodeWorkflow:
    @workflow.run
    async def run(self, node_name: str, node_ip: str) -> str:
        system_id = await workflow.execute_activity(
            trigger_maas_deploy,
            node_name,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=workflow.RetryPolicy(maximum_attempts=3)
        )

        deployed = await workflow.execute_activity(
            wait_for_deployment,
            system_id,
            start_to_close_timeout=timedelta(minutes=35)
        )

        if deployed:
            await workflow.execute_activity(
                run_ansible,
                node_ip,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=workflow.RetryPolicy(maximum_attempts=3)
            )

        return f"Node {node_name} provisioned and configured"
```

---

## Example Workflow — CI/CD Saga

```python
@workflow.defn
class DeployWorkflow:
    @workflow.run
    async def run(self, app: str, version: str) -> str:
        # Build image
        await workflow.execute_activity(build_docker_image, app, version)

        # Scan for vulnerabilities
        scan_ok = await workflow.execute_activity(scan_image_harbor, app, version)
        if not scan_ok:
            await workflow.execute_activity(notify_slack, f"❌ {app}:{version} failed security scan")
            return "aborted"

        # Deploy to staging
        await workflow.execute_activity(argocd_sync, app, "staging")

        # Run integration tests
        tests_ok = await workflow.execute_activity(run_integration_tests, app)
        if not tests_ok:
            await workflow.execute_activity(argocd_rollback, app, "staging")
            return "rolled back"

        # Promote to production
        await workflow.execute_activity(argocd_sync, app, "production")
        await workflow.execute_activity(notify_slack, f"✅ {app}:{version} deployed to production")
        return "deployed"
```

If any step fails, Temporal retries it. If the worker crashes mid-workflow, Temporal resumes from where it left off. This is impossible to replicate reliably with bash scripts or CI pipelines alone.

---

## Use Cases on This Cluster

```text
✔ Node provisioning pipeline (MAAS → Ansible → Kubernetes join)
✔ Full CI/CD saga (build → scan → stage → test → promote)
✔ ML training pipeline (data prep → train → evaluate → register)
✔ Scheduled cleanup (old images, expired tokens, stale namespaces)
✔ Multi-step incident response (detect → diagnose → remediate → report)
```

---

## Done When

```text
✔ Temporal server Running in temporal namespace
✔ Temporal UI accessible
✔ First workflow registered and executed
✔ Worker running and processing activities
✔ Workflow visible in UI with event history
```
