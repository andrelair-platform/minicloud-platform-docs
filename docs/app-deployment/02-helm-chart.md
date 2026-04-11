---
id: helm-chart
title: Standard Helm Chart
sidebar_position: 2
---

# Standard Helm Chart Structure

Every application deployed on this platform uses a Helm chart. This page defines the **platform-approved standard chart layout** — what goes in it, how it is structured, and how `values.yaml` is organized for multi-environment support.

---

## Scaffold a New Chart

```bash
helm create myapp
```

This generates the baseline. Clean it up to match the standard:

```text
myapp/
├── Chart.yaml             ← chart metadata + dependencies
├── values.yaml            ← default values (production-safe defaults)
├── values-staging.yaml    ← staging overrides
├── values-prod.yaml       ← production overrides
└── templates/
    ├── _helpers.tpl        ← named templates (labels, selectors)
    ├── deployment.yaml
    ├── service.yaml
    ├── ingress.yaml
    ├── hpa.yaml
    ├── pvc.yaml            ← optional, for stateful apps
    ├── configmap.yaml      ← optional
    └── serviceaccount.yaml
```

---

## Chart.yaml

```yaml
apiVersion: v2
name: myapp
description: My Application — Payments API
type: application
version: 1.2.0          # chart version (bumped in CI)
appVersion: "1.2.0"     # app version (matches Docker image tag)

dependencies:
  - name: postgresql
    version: "15.5.0"
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled

  - name: redis
    version: "19.1.0"
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled
```

---

## values.yaml (Platform Standard)

```yaml
# ── Image ──────────────────────────────────────────────────────────
image:
  repository: harbor.local/myteam/myapp
  tag: "1.2.0"
  pullPolicy: IfNotPresent

imagePullSecrets:
  - name: harbor-registry-secret

# ── Replicas & Scaling ─────────────────────────────────────────────
replicaCount: 2

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

# ── Resources (mandatory — no defaults omitted) ────────────────────
resources:
  requests:
    cpu: "250m"
    memory: "256Mi"
  limits:
    cpu: "1"
    memory: "512Mi"

# ── Health Probes ──────────────────────────────────────────────────
livenessProbe:
  httpGet:
    path: /health/live
    port: 3000
  initialDelaySeconds: 15
  periodSeconds: 20
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/ready
    port: 3000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3

# ── Service ────────────────────────────────────────────────────────
service:
  type: ClusterIP
  port: 80
  targetPort: 3000

# ── Ingress ────────────────────────────────────────────────────────
ingress:
  enabled: true
  className: nginx
  host: myapp.yourdomain.com
  tls: true
  tlsSecret: myapp-tls

# ── Environment Variables ──────────────────────────────────────────
env:
  NODE_ENV: production
  LOG_LEVEL: info

# ── Secrets (injected from Vault) ─────────────────────────────────
vault:
  enabled: true
  role: myapp
  secretPath: secret/myteam/myapp

# ── Storage ────────────────────────────────────────────────────────
persistence:
  enabled: false
  storageClass: longhorn
  size: 10Gi
  mountPath: /data

# ── Dependencies ──────────────────────────────────────────────────
postgresql:
  enabled: false

redis:
  enabled: false
```

---

## values-staging.yaml

```yaml
replicaCount: 1

image:
  tag: "latest-main"      # staging tracks latest main build

resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "256Mi"

autoscaling:
  enabled: false          # fixed replicas in staging

ingress:
  host: myapp.staging.yourdomain.com
  tls: false              # no TLS in staging

env:
  NODE_ENV: staging
  LOG_LEVEL: debug
```

---

## values-prod.yaml

```yaml
replicaCount: 3

image:
  tag: "1.2.0"            # pinned explicit version

resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "2"
    memory: "1Gi"

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10

ingress:
  host: myapp.yourdomain.com
  tls: true

env:
  NODE_ENV: production
  LOG_LEVEL: warn
```

---

## templates/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "myapp.fullname" . }}
  labels:
    {{- include "myapp.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "myapp.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "myapp.selectorLabels" . | nindent 8 }}
      annotations:
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        {{- if .Values.vault.enabled }}
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: {{ .Values.vault.role }}
        vault.hashicorp.com/agent-inject-secret-env: {{ .Values.vault.secretPath }}
        {{- end }}
    spec:
      imagePullSecrets:
        {{- toYaml .Values.imagePullSecrets | nindent 8 }}
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: {{ .Values.service.targetPort }}
          env:
            {{- range $key, $val := .Values.env }}
            - name: {{ $key }}
              value: {{ $val | quote }}
            {{- end }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          livenessProbe:
            {{- toYaml .Values.livenessProbe | nindent 12 }}
          readinessProbe:
            {{- toYaml .Values.readinessProbe | nindent 12 }}
          {{- if .Values.persistence.enabled }}
          volumeMounts:
            - name: data
              mountPath: {{ .Values.persistence.mountPath }}
          {{- end }}
      {{- if .Values.persistence.enabled }}
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: {{ include "myapp.fullname" . }}-pvc
      {{- end }}
```

---

## templates/ingress.yaml

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "myapp.fullname" . }}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    {{- if .Values.ingress.tls }}
    cert-manager.io/cluster-issuer: letsencrypt-prod
    {{- end }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  {{- if .Values.ingress.tls }}
  tls:
    - hosts:
        - {{ .Values.ingress.host }}
      secretName: {{ .Values.ingress.tlsSecret }}
  {{- end }}
  rules:
    - host: {{ .Values.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ include "myapp.fullname" . }}
                port:
                  number: {{ .Values.service.port }}
{{- end }}
```

---

## templates/hpa.yaml

```yaml
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "myapp.fullname" . }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "myapp.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetMemoryUtilizationPercentage }}
{{- end }}
```

---

## Push Chart to Harbor OCI Registry

```bash
# Login to Harbor
helm registry login harbor.local -u admin -p Admin12345

# Package
helm package ./myapp

# Push
helm push myapp-1.2.0.tgz oci://harbor.local/charts
```

Pull later:

```bash
helm pull oci://harbor.local/charts/myapp --version 1.2.0
```

---

## Done When

```text
✔ Chart scaffolded with all standard templates
✔ values.yaml, values-staging.yaml, values-prod.yaml defined
✔ Chart pushed to Harbor OCI registry
✔ helm template ./myapp renders without errors
✔ Chart installs cleanly with helm install --dry-run
```
