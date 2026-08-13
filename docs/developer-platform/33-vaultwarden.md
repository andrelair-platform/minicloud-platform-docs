---
id: vaultwarden
title: Vaultwarden — Password Management
sidebar_label: Vaultwarden (Passwords)
---

# Vaultwarden — Password Management

Self-hosted Bitwarden-compatible password manager for the ktayl-solution IS. All IS credentials (service accounts, API keys, admin passwords) are stored in Vaultwarden — not in Slack, email, or shared spreadsheets.

## Access

| URL | Audience |
|---|---|
| https://vault-pw.devandre.sbs | Public (Cloudflare Tunnel) |
| https://vault-pw.10.0.0.200.nip.io | Internal (Tailscale only) |

Login: **Authentik SSO button** on the login page. Direct email/password login is disabled.

:::warning SSO-only access
Vaultwarden uses the Timshel fork (`timshel/vaultwarden:1.34.1-6`) which adds the Authentik SSO button. Standard `vaultwarden/server` image does not support SSO login — do not upgrade to it without checking fork compatibility.
:::

## Deployment

| Parameter | Value |
|---|---|
| Namespace | `vaultwarden` |
| Image | `ghcr.io/timshel/vaultwarden:1.34.1-6` |
| Managed by | ArgoCD |
| Storage | Longhorn PVC |
| Auth | Authentik OIDC SSO |
| Backup | Velero (daily Longhorn snapshot) |

```bash
kubectl --context minicloud get pods -n vaultwarden
kubectl --context minicloud get ingress -n vaultwarden
```

## Credential Inventory

15 IS credentials managed across these folders:

| Folder | Contents |
|---|---|
| **Platform infra** | Harbor admin, ArgoCD admin, Grafana admin, MinIO root, Vault root token |
| **External services** | Cloudflare API token, AWS SES credentials, Tailscale OAuth |
| **Business apps** | ERPNext admin, Docuseal API token, Plane admin |
| **Mail** | Stalwart admin, SES SMTP credentials |
| **k3s cluster** | MAAS admin, controller SSH keypair |

## CLI access (controller)

A pinned `bw` CLI version is installed on the controller for scripted access:

```bash
BW=~/.local/share/bw-compat/bw   # v2024.6.0 — v2026+ incompatible with this Vault version

$BW config server https://vault-pw.devandre.sbs
BW_SESSION=$($BW unlock --passwordenv BW_PASSWORD --raw)
$BW --session $BW_SESSION list items --folderid <folder-id>
$BW --session $BW_SESSION get item "Harbor admin"
$BW lock
```

:::caution CLI version lock
The `bw` CLI v2025+ changed the API format in a way that breaks against this Vaultwarden version. Use only `~/.local/share/bw-compat/bw` (v2024.6.0). Do not `brew upgrade bw`.
:::

## Relation to Vault (HashiCorp)

Vaultwarden and HashiCorp Vault serve different purposes:

| | Vaultwarden | HashiCorp Vault |
|---|---|---|
| **Users** | Humans (password manager UI) | Services (ESO, k3s pods) |
| **Access** | Browser / Bitwarden app | API / Vault Agent |
| **Stored** | Credentials humans need to log in | Dynamic secrets, PKI, app secrets |
| **Auth** | Authentik SSO | Kubernetes SA, AppRole |

Platform secrets (CI tokens, app secrets) live in HashiCorp Vault at `vault.devandre.sbs`. Human credentials live in Vaultwarden.

## Related issues

- [Vaultwarden SSO deployment (completed 2026-07-10)](https://github.com/andrelair-platform/platform-backlog/issues/121)
