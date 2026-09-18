---
id: dns-naming-externaldns
title: DNS Naming Convention & ExternalDNS
sidebar_label: DNS Naming & ExternalDNS
---

# DNS Naming Convention & ExternalDNS

> **Map page** — the summary + the reference table live here; the full decision record lives with the
> infrastructure code. **Full ADR:**
> [`minicloud-gitops/docs/dns-naming-and-externaldns.md`](https://github.com/andrelair-platform/minicloud-gitops/blob/main/docs/dns-naming-and-externaldns.md).

The platform has one enterprise-wide DNS convention and automates org DNS through **ExternalDNS**. The
organisation (**ktayl-solution IS**) is namespaced under **`ktayl.devandre.sbs`** so it never collides
with the owner's **portfolio** (`www` / apex `devandre.sbs`) or with **Retrieva** (`retrieva.online`,
its own domain — the two-layer model). Access control is identity-first: public via Cloudflare Tunnel +
WAF + Authentik SSO; internal via Tailscale.

## The convention (four planes)

| Plane | Convention | Reached via | Examples |
|---|---|---|---|
| **Personal (not org)** | `devandre.sbs`, `www.devandre.sbs` | Cloudflare | the portfolio — **off-limits to org automation** |
| **Retrieva (cert product)** | `retrieva.online` | Cloudflare | separate layer |
| **Public — org** | `<app>.ktayl.devandre.sbs` (prod) · `<app>.<env>.ktayl.devandre.sbs` (non-prod) | Cloudflare Tunnel + WAF + SSO | `broker.ktayl.devandre.sbs`, `broker.dev.ktayl.devandre.sbs` |
| **Corp — internal apps** | `<app>.10.0.0.200.nip.io` (today) → target `<app>.corp.ktayl.devandre.sbs` | Tailscale only | `underwriting.10.0.0.200.nip.io` |
| **Platform — ops tooling** | `<tool>.10.0.0.200.nip.io` (**Tailscale-only, default**) | Tailscale | `argocd`, `grafana`, `vault` |
| **Kubernetes-internal** | `<svc>.<ns>.svc.cluster.local` | in-cluster | `stalwart.mail.svc.cluster.local` |

**Rules:** environment is a subdomain **prefix** (`broker.dev.…`), prod is the clean name; microservices
are **not** hostnames (internal on `svc.cluster.local` behind default-deny egress); platform tooling
defaults to Tailscale-only.

## ExternalDNS (Cloudflare) — automated, fail-safe

An org app's Ingress creates its own DNS record (the GitOps `Ingress → DNS` flow). Because the public
plane rides Cloudflare Tunnel, ExternalDNS publishes **CNAMEs to the tunnel**, not A-records. It is
scoped so it cannot misfire: **`--domain-filter=ktayl.devandre.sbs`** (can't touch the portfolio or
`retrieva.online`) and **`policy=upsert-only`** (never deletes). The **hostname is the opt-in** — an app
is managed only when its Ingress host is under `ktayl.devandre.sbs` (a deliberate act; internal apps use
nip.io), plus the `external-dns.alpha.kubernetes.io/target` (tunnel) annotation to make it a CNAME. No
custom label is used (the shared library ingress emits only standard labels). It is idle until an org app
adopts a `ktayl.devandre.sbs` host — the scaffold (`services/_template-helm`) carries the ready block.

**Companion (follow-up):** a wildcard `*.ktayl.devandre.sbs` `cloudflared` ingress rule + wildcard cert
for fully zero-touch public onboarding (controller-side, outside GitOps). Full design, guard table, and
phased-migration plan are in the ADR linked above.

## Related
- Delivery / wrapper-chart golden path: [Delivery Workflow](./delivery-workflow)
- Mail auth on the same zone (custom MAIL FROM): [Amazon SES](./amazon-ses)
