---
id: docuseal
title: Docuseal — e-Signature Platform
sidebar_label: Docuseal (e-Signature)
---

# Docuseal — e-Signature Platform

Self-hosted electronic signature platform for the ktayl-solution IS. Every insurance contract, claims settlement, broker mandate, and SEPA mandate requires a legally traceable signature — Docuseal provides eIDAS-compatible e-signature without SaaS dependency.

## Access

| URL | Audience |
|---|---|
| https://sign.devandre.sbs | Public (Cloudflare Tunnel) |
| https://sign.10.0.0.200.nip.io | Internal (Tailscale only) |

Login: Authentik OIDC SSO (`kanmegnea` + TOTP).

## Deployment

| Parameter | Value |
|---|---|
| Namespace | `sign` |
| Image | `docuseal/docuseal:1.8.3` |
| Managed by | ArgoCD |
| Storage | Longhorn PVC |
| Auth | Authentik OIDC |

```bash
kubectl --context minicloud get pods -n sign
kubectl --context minicloud get ingress -n sign
```

## Document Templates

Four insurance templates configured:

| Template | Use case |
|---|---|
| **Contrat de police** | Policy binding signature at underwriting |
| **Règlement de sinistre** | Claims settlement agreement |
| **Mandat courtier** | Broker mandate / letter of authority |
| **Mandat SEPA** | SEPA direct debit authorisation for premium collection |

## Integration Points

```
ERPNext CRM (devis → accept)
    ↓  send-for-signature API call
Docuseal (signature request created)
    ↓  signed PDF webhook
ktayl-claims-service (settlement confirmation)
    ↓  audit trail
Paperless-ngx DMS (#76) — long-term compliant archive
```

## API Usage

Docuseal exposes a REST API for programmatic signature requests:

```bash
# Create a signature request from a template
curl -X POST https://sign.devandre.sbs/api/v1/submissions \
  -H "X-Auth-Token: $DOCUSEAL_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": 1,
    "send_email": true,
    "submitters": [
      {"role": "Souscripteur", "email": "client@example.com"},
      {"role": "Courtier", "email": "broker@example.com"}
    ]
  }'
```

The API token is stored in Vault at `secret/platform/docuseal` key `api-token`.

## Why self-hosted

- **ACPR compliance**: audit trail under French jurisdiction, not a US SaaS provider
- **Cost**: zero per-signature fee (DocuSign: €0.80–2.00/envelope)
- **Integration**: direct API access from ktayl microservices without webhook relay
- **Data sovereignty**: signed PDFs never leave the on-premises cluster

## Regulatory context

Docuseal produces signatures compliant with **eIDAS Regulation (EU 910/2014)** at the **Simple Electronic Signature** level. For ACPR-regulated operations requiring Advanced or Qualified signatures, a qualified Trust Service Provider (TSP) integration would be required — not in scope for this IS.

## Related issues

- [#75 — e-Signature platform: Docuseal](https://github.com/andrelair-platform/platform-backlog/issues/75) ✅ Done
- [#76 — Paperless-ngx DMS (signed document archive)](https://github.com/andrelair-platform/platform-backlog/issues/76)
