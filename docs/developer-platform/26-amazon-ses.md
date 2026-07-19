---
id: amazon-ses
title: Phase 80 — Amazon SES (Outbound Email Relay)
sidebar_label: Phase 80 — Amazon SES
---

# Phase 80 — Amazon SES Outbound Email Relay

Phase 80 configures Stalwart v0.16.13 as an SMTP relay through Amazon Simple Email Service (SES). All outbound email from `devandre.sbs` is now routed via SES, providing enterprise-grade deliverability, DKIM signing, SPF alignment, and a DMARC-compliant sending pipeline — with no open relay exposed to the internet.

---

## Solution Architecture

```mermaid
flowchart TB
    subgraph cluster["k3s Cluster — mail namespace"]
        stalwart["Stalwart v0.16.13\nmail/stalwart-0\n(fast-skunk:587/25/143/993)"]
    end

    subgraph platform["Platform Services"]
        alertmanager["Alertmanager\n(monitoring ns)"]
        backstage["Backstage\n(scaffolder actions)"]
        erpnext["ERPNext\n(erp ns)"]
    end

    subgraph aws["AWS — eu-west-1"]
        ses["Amazon SES\nemail-smtp.eu-west-1.amazonaws.com:587\n(STARTTLS)"]
        route53["Route 53 / DNS\nSPF · DKIM · DMARC\nfor devandre.sbs"]
    end

    subgraph secrets["Secret Management"]
        vault["Vault\nsecret/platform/mail"]
        eso["External Secrets Operator\nstalwart-secret (k8s)"]
    end

    alertmanager -->|"SMTP STARTTLS\nkanmegnea@devandre.sbs"| stalwart
    backstage -->|"JMAP Email/set\n+ EmailSubmission/set"| stalwart
    erpnext -->|"SMTP (future)"| stalwart

    stalwart -->|"SMTP STARTTLS :587\nSASL LOGIN\nIAM SMTP creds"| ses
    ses -->|"delivers via\nauthenticated relay"| internet(["Internet\ninboxes"])

    vault -->|"smtp-relay-*\nstalwart-admin-secret"| eso
    eso -->|"env vars\nSMTP_RELAY_*"| stalwart

    route53 -.->|"SPF include:amazonses.com\nDKIM _domainkey\nDMARC p=none"| ses

    style cluster fill:#1e3a5f,color:#fff
    style aws fill:#ff9900,color:#1a1a1a
    style secrets fill:#2d4a2d,color:#fff
    style platform fill:#3a1e5f,color:#fff
```

---

## Key Components

| Component | Role |
|-----------|------|
| **Stalwart v0.16.13** | MTA + JMAP mail server; receives mail from internal services, relays outbound via SES |
| **Amazon SES (eu-west-1)** | SMTP relay; enforces DKIM, SPF, DMARC; provides delivery metrics |
| **IAM user `ses-smtp-minicloud`** | Least-privilege SES sending identity; SMTP credentials distinct from API keys |
| **Vault `secret/platform/mail`** | Single source of truth for all Stalwart secrets including SES SMTP credentials |
| **ESO ExternalSecret `stalwart-secret`** | Syncs Vault keys to pod environment variables at runtime |

---

## DNS Configuration (devandre.sbs)

Three DNS records form the email authentication chain:

| Record | Type | Value |
|--------|------|-------|
| `devandre.sbs` SPF | TXT | `v=spf1 include:amazonses.com -all` |
| `*._domainkey.devandre.sbs` | CNAME | SES DKIM selector (AWS-managed rotation) |
| `_dmarc.devandre.sbs` | TXT | `v=DMARC1; p=none; rua=mailto:admin@devandre.sbs` |

SES verifies domain ownership and signs outgoing messages with DKIM. The `p=none` DMARC policy allows monitoring without rejecting mail — upgrade to `p=quarantine` after confirming clean delivery for 30 days.

---

## Stalwart Relay Configuration

All Stalwart configuration is stored in **RocksDB** (not TOML files). Routes and outbound strategy are managed via the JMAP admin API at `/jmap/` or the React admin SPA at `/admin/`.

### MTA Route: `ses-relay`

| Field | Value |
|-------|-------|
| Type | Relay Host |
| Address | `email-smtp.eu-west-1.amazonaws.com` |
| Port | `587` |
| Protocol | SMTP |
| Implicit TLS | Off (STARTTLS negotiated) |
| Auth username | `AKIAZDNTLNEA6EFN6LKW` (literal) |
| Auth password | env var `SMTP_RELAY_PASSWORD` |

The password is injected at runtime from the Kubernetes secret `stalwart-secret` — never stored in the container image or RocksDB.

### Outbound Routing Strategy

```
IF is_local_domain(rcpt_domain)  →  'local'
ELSE                              →  'ses-relay'
```

Local mail (e.g. `admin@devandre.sbs` → `kanmegnea@devandre.sbs`) is delivered directly. Everything else hits SES.

---

## Secret Management

Credentials are stored in **Vault** and never touch the filesystem directly:

```
Vault: secret/platform/mail
  stalwart-admin-secret  → STALWART_ADMIN_SECRET   (pod recovery admin)
  smtp-relay-host        → SMTP_RELAY_HOST          (email-smtp.eu-west-1.amazonaws.com)
  smtp-relay-port        → SMTP_RELAY_PORT          (587)
  smtp-relay-user        → SMTP_RELAY_USER          (IAM SMTP username)
  smtp-relay-password    → SMTP_RELAY_PASSWORD      (IAM SMTP password)
```

ESO syncs these into the `stalwart-secret` Kubernetes Secret in the `mail` namespace. The StatefulSet reads them as environment variables via `envFrom`.

---

## Alertmanager Integration

Alertmanager's SMTP config targets Stalwart directly (cluster-internal):

```yaml
# kube-prometheus-stack values
alertmanager:
  config:
    global:
      smtp_smarthost: 'stalwart.mail.svc.cluster.local:587'
      smtp_from: 'kanmegnea@devandre.sbs'
      smtp_require_tls: true
      smtp_tls_config:
        insecure_skip_verify: true   # internal self-signed cert
```

Stalwart relays Alertmanager emails outbound via SES.

---

## Deployment Steps

### 1. IAM Setup (AWS Console)

1. Create IAM user `ses-smtp-minicloud` with policy `AmazonSESFullAccess` (scoped to send only).
2. In IAM → Security credentials → **Create SMTP credentials** (these differ from API keys).
3. Verify domain `devandre.sbs` in SES → add the 3 DNS records above.
4. Add `kanmegneandre@gmail.com` as a verified identity (sandbox mode).

### 2. Store Credentials in Vault

```bash
# On controller — use patch to avoid overwriting other keys
vault kv patch secret/platform/mail \
  smtp-relay-host=email-smtp.eu-west-1.amazonaws.com \
  smtp-relay-port=587 \
  smtp-relay-user=<SMTP_USERNAME> \
  smtp-relay-password=<SMTP_PASSWORD>
```

### 3. Force ESO Re-sync

```bash
kubectl annotate externalsecret stalwart-secret -n mail \
  force-sync=$(date +%s) --overwrite
kubectl rollout restart statefulset/stalwart -n mail
```

### 4. Configure Stalwart via Admin UI

Navigate to `https://mail.10.0.0.200.nip.io/admin/`:

1. **Settings → MTA → Routes** → Create route named `ses-relay` (Relay Host, port 587, STARTTLS, env-var password).
2. **Settings → MTA → Outbound Strategy** → Set the `else` branch to `'ses-relay'`.

### 5. Test

Send via JMAP from the user account:

```javascript
// JMAP Email/set + EmailSubmission/set
// accountId: 'b' (kanmegnea), identityId: 'b'
// mailboxIds: { e: true }  // Sent Items
```

Verify: Tasks → Scheduled = empty, Tasks → Failed = empty → delivered.

---

## Gotchas

### Stalwart uses JMAP exclusively for config (no REST management API)

Stalwart v0.16 stores all configuration in RocksDB. There is no `/api/settings` endpoint. All config mutations go through:
- **Admin SPA** at `/admin/` (React Hook Form, PKCE OAuth2)
- **JMAP API** at `/jmap/` with `Authorization: Bearer <token>` extracted from `sessionStorage['stalwart-auth']`

### JMAP EmailSubmission/set requires both `emailId` and `identityId`

`identityId` is mandatory — omitting it returns `invalidProperties`. Fetch the identity list first:

```javascript
methodCalls: [['Identity/get', { accountId: 'b', ids: null }, '0']]
// returns id: 'b' for kanmegnea@devandre.sbs
```

### SES sandbox — recipient must be verified

In SES sandbox mode, both sender and recipient domains must be verified. Request production access via AWS Console → SES → Account dashboard → "Request production access". Approval takes 2–8 hours.

### Stalwart relay auth password: env var, not literal

In the `ses-relay` route config, the password field must reference the environment variable name as a Stalwart secret reference, not the literal value. The env var `SMTP_RELAY_PASSWORD` is read at startup.

### Vault `vault kv put` overwrites all keys — use `vault kv patch`

`vault kv put secret/platform/mail smtp-relay-host=...` destroys all other keys at that path. Always use `vault kv patch` to add/update individual keys on shared secret paths.

### multipathd claims Longhorn iSCSI volumes (fast-heron / fast-skunk)

On nodes where `multipathd` is running, it can claim Longhorn iSCSI devices (`IET VIRTUAL-DISK`) as multipath devices (`mpatha`), blocking kubelet CSI mounts. Symptom: pod stuck in `ContainerCreating` for 80+ minutes. Fix:

```bash
# /etc/multipath.conf on the affected node
defaults {
    user_friendly_names yes
}
blacklist {
    device {
        vendor "IET"
        product "VIRTUAL-DISK"
    }
}
```

```bash
sudo multipath -f mpatha
sudo systemctl reload-or-restart multipathd
# then delete and let the pod reschedule
```

Apply this to all worker nodes with `multipathd` running.

---

## Verification Checklist

- [ ] `kubectl get externalsecret stalwart-secret -n mail` → `SecretSynced: True`
- [ ] `kubectl exec -n mail stalwart-0 -- env | grep SMTP_RELAY` → shows 4 vars
- [ ] Stalwart admin → Settings → MTA Routes → `ses-relay` visible
- [ ] Stalwart admin → Settings → MTA Outbound Strategy → else branch = `ses-relay`
- [ ] Send test email via JMAP → Tasks → Scheduled = empty, Failed = empty
- [ ] AWS SES Console → Sending Statistics → message count increments
