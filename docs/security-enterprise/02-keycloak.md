---
id: keycloak
title: Keycloak (SSO / IAM)
sidebar_position: 2
---

# Keycloak — Single Sign-On for the Entire Platform

Keycloak is the identity backbone of the platform. Every tool — ArgoCD, Grafana, Superset, OpenMetadata, Harbor, Backstage — uses Keycloak as its OIDC provider. Developers log in once and access everything. No per-tool passwords.

---

## What Keycloak Manages

```text
Developer Browser
       │
       │  Login once
       ▼
  ┌──────────────────────────────────────┐
  │         Keycloak (OIDC/OAuth2)       │
  │                                      │
  │  Users  │  Groups  │  Roles  │  MFA  │
  └──────────────────────────────────────┘
       │
       │  Issues tokens (JWT)
       ▼
 ArgoCD  │  Grafana  │  Superset  │  Harbor
 OpenMetadata  │  Backstage  │  Vault
```

---

## Deploy Keycloak on Kubernetes

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

### values-keycloak.yaml

```yaml
# values-keycloak.yaml
auth:
  adminUser: admin
  existingSecret: keycloak-admin-secret
  passwordSecretKey: admin-password

production: true
proxy: edge

replicaCount: 2

resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "1"
    memory: "2Gi"

postgresql:
  enabled: true
  auth:
    username: keycloak
    password: "KeycloakDbPass123!"
    database: keycloak

extraEnvVars:
  - name: KC_HOSTNAME
    value: "keycloak.yourdomain.com"
  - name: KC_HOSTNAME_STRICT
    value: "false"

ingress:
  enabled: true
  ingressClassName: nginx
  hostname: keycloak.yourdomain.com
  tls: true
  selfSigned: false
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
```

```bash
kubectl create namespace identity

kubectl create secret generic keycloak-admin-secret \
  --from-literal=admin-password=$(openssl rand -base64 32) \
  --namespace identity

helm upgrade --install keycloak bitnami/keycloak \
  --namespace identity \
  --values values-keycloak.yaml \
  --wait
```

---

## Create the Platform Realm

```bash
# Get admin password
ADMIN_PASS=$(kubectl get secret keycloak-admin-secret -n identity -o jsonpath='{.data.admin-password}' | base64 -d)

# Create realm via Keycloak CLI (exec into pod)
kubectl exec -n identity deploy/keycloak -- \
  /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 \
    --realm master \
    --user admin \
    --password $ADMIN_PASS

# Create platform realm
kubectl exec -n identity deploy/keycloak -- \
  /opt/keycloak/bin/kcadm.sh create realms \
    -s realm=platform \
    -s enabled=true \
    -s displayName="Mini Cloud Platform" \
    -s sslRequired=external
```

---

## Create Platform Roles

```bash
KCADM="kubectl exec -n identity deploy/keycloak -- /opt/keycloak/bin/kcadm.sh"

# Realm roles
$KCADM create roles -r platform -s name=platform-admin
$KCADM create roles -r platform -s name=platform-developer
$KCADM create roles -r platform -s name=platform-viewer
$KCADM create roles -r platform -s name=data-analyst
$KCADM create roles -r platform -s name=data-engineer
```

---

## Register OIDC Clients

### ArgoCD Client

```bash
$KCADM create clients -r platform -f - << 'EOF'
{
  "clientId": "argocd",
  "enabled": true,
  "protocol": "openid-connect",
  "publicClient": false,
  "secret": "argocd-client-secret-change-me",
  "redirectUris": ["https://argocd.yourdomain.com/auth/callback"],
  "webOrigins": ["https://argocd.yourdomain.com"],
  "standardFlowEnabled": true,
  "defaultClientScopes": ["openid", "profile", "email", "roles"]
}
EOF
```

### Grafana Client

```bash
$KCADM create clients -r platform -f - << 'EOF'
{
  "clientId": "grafana",
  "enabled": true,
  "protocol": "openid-connect",
  "secret": "grafana-client-secret-change-me",
  "redirectUris": ["https://grafana.yourdomain.com/login/generic_oauth"],
  "standardFlowEnabled": true
}
EOF
```

Repeat similarly for: `superset`, `harbor`, `backstage`, `openmetadata`, `vault`

---

## Configure ArgoCD to Use Keycloak

```yaml
# argocd-cm ConfigMap patch
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-cm
  namespace: argocd
data:
  oidc.config: |
    name: Keycloak
    issuer: https://keycloak.yourdomain.com/realms/platform
    clientID: argocd
    clientSecret: $oidc.keycloak.clientSecret
    requestedScopes: ["openid", "profile", "email", "roles"]
    requestedIDTokenClaims:
      groups:
        essential: true
```

```yaml
# argocd-rbac-cm ConfigMap patch
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-rbac-cm
  namespace: argocd
data:
  policy.csv: |
    g, platform-admin, role:admin
    g, platform-developer, role:editor
    g, platform-viewer, role:readonly
  policy.default: role:readonly
  scopes: '[roles]'
```

---

## Configure Grafana SSO

```ini
# grafana.ini OAuth section (in Helm values)
[auth.generic_oauth]
enabled = true
name = Keycloak
allow_sign_up = true
client_id = grafana
client_secret = ${KEYCLOAK_GRAFANA_SECRET}
scopes = openid profile email roles
auth_url = https://keycloak.yourdomain.com/realms/platform/protocol/openid-connect/auth
token_url = https://keycloak.yourdomain.com/realms/platform/protocol/openid-connect/token
api_url = https://keycloak.yourdomain.com/realms/platform/protocol/openid-connect/userinfo
role_attribute_path = contains(roles[*], 'platform-admin') && 'Admin' || contains(roles[*], 'platform-developer') && 'Editor' || 'Viewer'
```

---

## Multi-Factor Authentication (MFA)

```text
Keycloak Admin UI → platform realm → Authentication → Required Actions
  → Enable: Configure TOTP (required for platform-admin role)

Keycloak Admin UI → Authentication → Flows → Browser
  → Add: Conditional OTP
  → Condition: User role = platform-admin
```

All admin-role users must set up TOTP (Google Authenticator / Authy) on first login.

---

## User Federation (LDAP / Active Directory)

```text
platform realm → User Federation → Add LDAP Provider
  → Vendor: Active Directory
  → Connection URL: ldap://ad.yourdomain.com
  → Bind DN: cn=keycloak-svc,dc=yourdomain,dc=com
  → Bind Credential: {{ LDAP_PASSWORD }}
  → User DN: ou=employees,dc=yourdomain,dc=com
  → UUID attribute: objectGUID
  → Sync: Periodic changed users sync (every 10 min)
```

---

## Service Account Tokens (Machine-to-Machine)

For CI pipelines that need API access:

```bash
# Create client credential flow client
$KCADM create clients -r platform -f - << 'EOF'
{
  "clientId": "gitlab-ci",
  "enabled": true,
  "protocol": "openid-connect",
  "publicClient": false,
  "serviceAccountsEnabled": true,
  "standardFlowEnabled": false,
  "secret": "gitlab-ci-secret-change-me"
}
EOF

# Get token in CI pipeline
TOKEN=$(curl -s -X POST \
  https://keycloak.yourdomain.com/realms/platform/protocol/openid-connect/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=client_credentials&client_id=gitlab-ci&client_secret=${KEYCLOAK_CI_SECRET}' \
  | jq -r '.access_token')
```

---

## Done When

```text
✔ Keycloak running at keycloak.yourdomain.com
✔ Platform realm created with roles (admin, developer, viewer, analyst)
✔ ArgoCD, Grafana, Superset, Harbor login via Keycloak SSO
✔ MFA required for platform-admin role
✔ Role → ArgoCD RBAC mapping working
✔ Service account tokens issued to CI pipeline
```
