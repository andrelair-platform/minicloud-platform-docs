---
id: onboarding-a-colleague
title: Onboarding a Colleague (Access Guide)
sidebar_label: Onboarding a Colleague
sidebar_position: 5
---

# Onboarding a Colleague — how a collaborator reaches the apps

The platform has **three access tiers**. Which steps a colleague needs depends entirely on *which apps
they must reach*. Figure out their tier first, then follow only that section.

| Tier | Apps | What the colleague needs |
|---|---|---|
| ① **Internal / operator tools** (Tailscale-only) | ArgoCD, Grafana, Prometheus, Alertmanager, Harbor, Vault, Kargo, Backstage, Temporal, NATS, Loki, Hubble, Polaris, LiteLLM, Langfuse, Flowise, MLflow, Open WebUI, the agents, ktayl-policy-service, platform-demo | **Tailscale + CA cert + Authentik** (all 3) |
| ② **Business / employee apps** (public + SSO) | Chat, Mail, Nextcloud, ERPNext, Plane, n8n, OnlyOffice, Jitsi Meet, Matrix/Element, Vaultwarden, Docuseal | **Authentik only** — just a browser |
| ③ **Public** | Homer, the demo, retrieva.online, sign | nothing — open URLs |

> **The rule:** operator/infra tools are **Tailscale-only** (3-tier hardening, gitops#1180) — they have
> **no public route**, only `*.10.0.0.200.nip.io`. Business apps are public behind SSO at `*.devandre.sbs`.

---

## The short version

- **Colleague only needs business apps (tier ②)?** → give them an **Authentik account + MFA**, send them
  the `*.devandre.sbs` URL. Done. No Tailscale, no CA.
- **Colleague needs internal tools (tier ①)?** → **Tailscale (reach) → CA cert (trust) → Authentik
  (identity)**, in that order. The three steps below.

---

## Tier ② — business apps (the easy path)

1. **Create their Authentik account** at `https://auth.devandre.sbs` (admin) or
   `https://auth.10.0.0.200.nip.io` (internal) — add them to the appropriate group, enroll TOTP/MFA.
2. Send them the app URL, e.g. `https://chat.devandre.sbs`, `https://cloud.devandre.sbs`,
   `https://erp.devandre.sbs`. They log in with SSO from any browser, anywhere. **That's it.**

No VPN and no certificate install — the public edge (Cloudflare Tunnel) terminates a real Let's Encrypt
cert and Authentik gates access.

---

## Tier ① — internal / operator tools (the full path)

Internal apps require **three** things: network reach, TLS trust, and identity. Skipping any one fails in a
recognisable way (see *Troubleshooting*).

### Step 1 — Network reach: add them to the Tailnet + approve the subnet route

The internal apps live on the `10.0.0.0/24` cluster network, which the **controller** (`100.88.123.8`)
advertises as a Tailscale **subnet route**. A colleague reaches it by joining your tailnet and being
granted that route.

1. **Invite them** — Tailscale admin console → **Users** → *Invite external user* → their email. They accept
   and install the Tailscale client on their machine (`https://tailscale.com/download`).
2. **Approve their use of the subnet route** — Tailscale admin → the controller node → **Subnet routes** →
   ensure `10.0.0.0/24` is approved, and that your **ACL policy** permits this user to use it. (If your ACL
   is default-open, joining is enough; if you restrict routes by user/tag, add a grant for them.)
3. They confirm reach: `tailscale status` shows the tailnet, and `ping 10.0.0.200` works.

> **Why this and not a public URL?** Operator tools expose the cluster's control plane, catalog, secrets and
> CI. Keeping them off the public internet and behind the VPN is the whole point of the tier-① decision —
> identity alone (SSO) isn't a sufficient perimeter for these.

*(Alternative for a shared/CI machine: issue a Tailscale **auth key** (admin → Settings → Keys) and run
`tailscale up --authkey=…` on that box instead of a personal invite. Prefer the per-user invite for a real
person — it's tied to their identity and easy to revoke.)*

### Step 2 — TLS trust: install the minicloud root CA

Internal apps use certificates from the **private minicloud root CA**, so browsers/tools will reject them
until that CA is trusted. Send the colleague **`minicloud-ca.crt`** (the same file at `~/minicloud-ca.crt`)
over a secure channel and have them install it:

- **macOS:** Keychain Access → *System* → *File ▸ Import Items* → select `minicloud-ca.crt` → set it to
  *Always Trust*.
- **Linux:** copy to `/usr/local/share/ca-certificates/minicloud-ca.crt` → `sudo update-ca-certificates`.
- **Windows:** `certlm.msc` → *Trusted Root Certification Authorities* → *Import*.
- **Firefox** keeps its own store: *Settings ▸ Privacy & Security ▸ Certificates ▸ View Certificates ▸
  Authorities ▸ Import*.

### Step 3 — Identity: Authentik account + MFA

Same as tier ②, but they'll reach Authentik at the **internal** URL: create their account at
`https://auth.10.0.0.200.nip.io`, add them to the right group, enroll TOTP. Every internal app is gated by
Authentik SSO, so one login carries across all of them.

### Step 4 — They're in

They open any internal URL and SSO logs them in. The full internal set:

| App | Internal URL (Tailscale-only) |
|---|---|
| Backstage | `https://backstage.10.0.0.200.nip.io` |
| ArgoCD | `https://argocd.10.0.0.200.nip.io` |
| Grafana | `https://grafana.10.0.0.200.nip.io` |
| Prometheus | `https://prometheus.10.0.0.200.nip.io` |
| Alertmanager | `https://alertmanager.10.0.0.200.nip.io` |
| Harbor | `https://harbor.10.0.0.200.nip.io` |
| Vault | `https://vault.10.0.0.200.nip.io` |
| Kargo | `https://kargo.10.0.0.200.nip.io` |
| Temporal | `https://temporal.10.0.0.200.nip.io` |
| NATS monitor | `https://nats.10.0.0.200.nip.io` |
| Loki | `https://loki.10.0.0.200.nip.io` |
| Hubble (Cilium) | `https://hubble.10.0.0.200.nip.io` |
| Polaris | `https://polaris.10.0.0.200.nip.io` |
| LiteLLM | `https://litellm.10.0.0.200.nip.io` |
| Langfuse | `https://langfuse.10.0.0.200.nip.io` |
| Flowise | `https://flowise.10.0.0.200.nip.io` |
| MLflow | `https://mlflow.10.0.0.200.nip.io` |
| Open WebUI (chat) | `https://chat.10.0.0.200.nip.io` |
| minicloud-agent · crew-agent | `https://agent.10.0.0.200.nip.io` · `https://crew-agent.10.0.0.200.nip.io` |
| ktayl-policy-service | `https://ktayl-policy.10.0.0.200.nip.io` |
| platform-demo | `https://platform-demo.10.0.0.200.nip.io` |

The one-stop launcher is **Homer** — internally `https://homer.10.0.0.200.nip.io` (also public at
`homer.devandre.sbs`).

---

## Troubleshooting (which of the 3 layers failed)

| Symptom | Failed layer | Fix |
|---|---|---|
| `This site can't be reached` / DNS or timeout on `*.10.0.0.200.nip.io` | **Tailscale** | not on the tailnet, or subnet route `10.0.0.0/24` not approved for them |
| **404** at a `*.devandre.sbs` operator URL (e.g. `grafana.devandre.sbs`) | **by design** | that host was pulled from the public tunnel — use the `*.10.0.0.200.nip.io` URL over Tailscale |
| **Certificate warning / `NET::ERR_CERT_AUTHORITY_INVALID`** | **CA cert** | `minicloud-ca.crt` not installed/trusted in their OS or Firefox store |
| Reaches the login page but **can't authenticate** | **Authentik** | no account, wrong group, or MFA not enrolled |
| Authentik **`redirect_uri` mismatch** after login | app config | the app's OIDC provider must whitelist the callback host (usually already set) |

## Revoking access

- **Tailscale:** admin console → remove the user / revoke their node or auth key.
- **Authentik:** disable/delete the account (cuts SSO to *all* apps at once — the value of a single IdP).
- The CA cert on their machine is harmless without the other two (it grants no access by itself).

## Related

- [Tailscale VPN](./tailscale) · [Cloudflare Tunnel](./cloudflare-tunnel) · [Homer Dashboard](./homer-dashboard)
