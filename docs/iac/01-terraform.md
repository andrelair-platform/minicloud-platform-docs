---
id: terraform
title: Phase 11 — OpenTofu (MAAS)
sidebar_position: 1
---

# Phase 11 — OpenTofu — Infrastructure as Code

Phase 10 codified what runs *on* a node (Ansible roles for packages,
iSCSI, k3s registries, netplan). Phase 11 codifies the layer **below**
that: the **MAAS-managed infrastructure itself** — cluster subnet, DHCP
range, and the 3 machines registered by `system_id`.

On bare metal, MAAS is "the cloud API". Using OpenTofu against MAAS
demonstrates exactly the same skill as Terraform against AWS, Azure, or
GCP — just running on local hardware. After this phase the question "if
my MAAS controller's SSD dies tomorrow, can I rebuild the inventory?" has
a code-based answer: `tofu apply` against a fresh MAAS install.

:::info OpenTofu vs Terraform
OpenTofu is the Apache 2.0 community fork of Terraform after HashiCorp
relicensed under BSL in 2023. Commands and provider ecosystem are
compatible (`tofu` instead of `terraform`). For new work in 2025+,
OpenTofu is the conservative choice. The provider used here
(`canonical/maas`) is on the OpenTofu Registry as well as the Terraform
Registry.
:::

---

## What this phase manages

| Resource | Why it's codified | Source of truth |
|---|---|---|
| `maas_subnet.cluster` (10.0.0.0/24) | Cluster network, gateway, fabric, vlan | `maas admin subnet read 3` |
| `maas_subnet_ip_range.cluster_dhcp` (10.0.0.10–100) | DHCP pool MAAS hands out to PXE-booting nodes | `maas admin ipranges read` |
| `maas_machine.cluster["set-hog"]` (system_id `nbc6cx`) | Control-plane node | `maas admin machine read nbc6cx` |
| `maas_machine.cluster["fast-skunk"]` (`sby3w7`) | Worker | `maas admin machine read sby3w7` |
| `maas_machine.cluster["fast-heron"]` (`q6m3px`) | Worker | `maas admin machine read q6m3px` |

The state file (`terraform.tfstate`) is **gitignored** — it contains the
MAAS API key in resource attributes. Remote backends (Vault, S3, Consul)
arrive in Phase 15.

---

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Tool | **OpenTofu** 1.10.6 | Apache 2.0 fork, no BSL concerns, compatible CLI |
| Install method | Tarball into `~/.local/bin/tofu` (no sudo) | Avoids the apt-repo dance; trivial to upgrade |
| Provider | `canonical/maas` ~> 2.5 | The older `maas/maas` source is now a redirect — use the new name to silence the deprecation warning |
| Repo location | `~/minicloud-ktaylorganisation/opentofu/` | Sibling of `ansible/`, same convention |
| State file | Local `terraform.tfstate`, mode-protected, gitignored | API key lives in here; remote backend deferred to Phase 15 |
| API key handling | `~/.maas-api-key` (mode 600) → `TF_VAR_maas_api_key` env var | Same out-of-band pattern as Harbor / Grafana passwords |
| Apply against live MAAS | **Never (yet)** | Cluster is in `Deployed` state; `tofu apply` could trigger machine commission/reboot. `plan` is used purely as a drift detector. |
| **Crossplane** | **Deferred to a later phase** | Different paradigm (IaC inside Kubernetes vs outside). Doing both shallowly is worse than doing one well. See `02-crossplane.md`. |

---

## The "import-plan" loop

The cluster is brownfield — every resource already exists in MAAS. The
correct workflow is:

1. Write `.tf` describing what you *think* MAAS contains.
2. `tofu import` each resource by its MAAS ID, populating state without
   touching live MAAS.
3. `tofu plan` — this will almost certainly report drift (provider
   default values you didn't set, fields the API returns that aren't in
   your `.tf`).
4. **Update the `.tf` to match what plan says — never `tofu apply` to
   "fix" the drift on a live system.**
5. Re-plan. Repeat 3-4 until plan reports "No changes".

For this cluster the loop took **one iteration**. The first plan
reported `fabric = "0" -> null` and `vlan = "0" -> null` on the subnet.
Adding `fabric = "0"` and `vlan = "0"` to `subnet.tf` made the next plan
clean.

---

## Pre-flight

```bash
# OpenTofu binary (no sudo)
curl -sLO https://github.com/opentofu/opentofu/releases/download/v1.10.6/tofu_1.10.6_linux_amd64.tar.gz
tar -xzf tofu_1.10.6_linux_amd64.tar.gz tofu
mv tofu ~/.local/bin/tofu && chmod +x ~/.local/bin/tofu
tofu version

# MAAS API key (mode 600)
maas list | awk '$1=="admin" {print $3}' > ~/.maas-api-key && chmod 600 ~/.maas-api-key
```

---

## Repo layout

```
opentofu/
├── versions.tf       # required_version + canonical/maas provider
├── provider.tf       # provider "maas" — reads url + key from variables
├── variables.tf      # maas_api_url (default), maas_api_key (sensitive)
├── env.sh            # source-able: exports TF_VAR_maas_api_key from ~/.maas-api-key
├── subnet.tf         # maas_subnet.cluster — 10.0.0.0/24
├── ip_ranges.tf      # maas_subnet_ip_range.cluster_dhcp — 10.0.0.10..100
├── machines.tf       # maas_machine.cluster (for_each over 3 hosts)
├── outputs.tf        # subnet_id, machines map, set_hog_ip, fast_*_ip
└── .gitignore        # .terraform/, *.tfstate, *.tfvars
```

### `versions.tf`

```hcl
terraform {
  required_version = ">= 1.10.0"
  required_providers {
    maas = {
      source  = "canonical/maas"   # the older maas/maas source is now a redirect
      version = "~> 2.5"
    }
  }
}
```

### `provider.tf` and `variables.tf`

```hcl
# variables.tf
variable "maas_api_url" {
  type    = string
  # IMPORTANT: provider appends /api/2.0/ itself — do NOT include it here
  default = "http://localhost:5240/MAAS"
}

variable "maas_api_key" {
  type      = string
  sensitive = true
}

# provider.tf
provider "maas" {
  api_url = var.maas_api_url
  api_key = var.maas_api_key
}
```

### `env.sh`

```bash
#!/usr/bin/env bash
# source ./env.sh before running tofu commands
export TF_VAR_maas_api_key="$(cat "$HOME/.maas-api-key")"
```

### `subnet.tf` (after the import-plan loop converges)

```hcl
resource "maas_subnet" "cluster" {
  name       = "10.0.0.0/24"
  cidr       = "10.0.0.0/24"
  gateway_ip = "10.0.0.1"
  fabric     = "0"   # added on iteration 2 of the import-plan loop
  vlan       = "0"   # added on iteration 2 of the import-plan loop
}
```

### `ip_ranges.tf`

```hcl
resource "maas_subnet_ip_range" "cluster_dhcp" {
  subnet   = maas_subnet.cluster.id
  type     = "dynamic"
  start_ip = "10.0.0.10"
  end_ip   = "10.0.0.100"
  comment  = "Added via 'Provide DHCP...' in Web UI."
}
```

### `machines.tf`

```hcl
locals {
  cluster_machines = {
    set-hog    = { hostname = "set-hog",    ip = "10.0.0.2", role = "control-plane" }
    fast-skunk = { hostname = "fast-skunk", ip = "10.0.0.4", role = "worker" }
    fast-heron = { hostname = "fast-heron", ip = "10.0.0.7", role = "worker" }
  }
}

resource "maas_machine" "cluster" {
  for_each = local.cluster_machines

  hostname         = each.value.hostname
  power_type       = "manual"
  power_parameters = jsonencode({})
  pxe_mac_address  = "00:00:00:00:00:00"   # placeholder — overwritten on import

  lifecycle {
    ignore_changes = [pxe_mac_address, power_parameters]
  }
}
```

### `outputs.tf`

```hcl
output "subnet_id"      { value = maas_subnet.cluster.id }
output "subnet_cidr"    { value = maas_subnet.cluster.cidr }
output "subnet_gateway" { value = maas_subnet.cluster.gateway_ip }
output "dhcp_range"     {
  value = "${maas_subnet_ip_range.cluster_dhcp.start_ip}–${maas_subnet_ip_range.cluster_dhcp.end_ip}"
}
output "machines" {
  value = {
    for k, m in maas_machine.cluster :
    k => {
      hostname  = m.hostname
      system_id = m.id
      ip        = local.cluster_machines[k].ip
      role      = local.cluster_machines[k].role
      pxe_mac   = m.pxe_mac_address
    }
  }
}
output "set_hog_ip"   { value = local.cluster_machines["set-hog"].ip }
```

---

## Run

```bash
cd opentofu/
source ./env.sh
tofu init                                                  # downloads canonical/maas provider

# Bring existing resources under management (one-time)
tofu import maas_subnet.cluster 3
tofu import maas_subnet_ip_range.cluster_dhcp 1
tofu import 'maas_machine.cluster["set-hog"]'    nbc6cx
tofu import 'maas_machine.cluster["fast-skunk"]' sby3w7
tofu import 'maas_machine.cluster["fast-heron"]' q6m3px

# The receipt
tofu plan
# → "No changes. Your infrastructure matches the configuration."

tofu output set_hog_ip
# → "10.0.0.2"
```

---

## Verification roadmap (results)

| Test | Expected | Actual |
|---|---|---|
| Tooling | `tofu version` ≥ 1.10 | OpenTofu v1.10.6 ✓ |
| State | `tofu import` succeeds for all 5 resources | ✓ subnet, IP range, 3 machines |
| Idempotency | `tofu plan` returns no changes | ✓ "No changes. Your infrastructure matches the configuration." |
| Output | `tofu output set_hog_ip` | `"10.0.0.2"` ✓ |

---

## Troubleshooting

### `Unable to get MAAS version: 404 (.../api/2.0/api/2.0/version/.)`

The `maas_api_url` was set to include `/api/2.0` — the provider appends
it itself. Use `http://localhost:5240/MAAS` (no `/api/2.0`).

### `Provider has moved to canonical/maas`

The `maas/maas` source still works as a redirect, but you should update
`versions.tf` to `source = "canonical/maas"` and re-run `tofu init`.

### Plan reports drift on `fabric`, `vlan`, or other fields after import

Update the `.tf` to declare what the provider returns. Don't `apply` the
diff to "reset" them — that's destructive on a live system. This is the
import-plan loop in action.

### `tofu output` returns empty

Run `tofu refresh` first to populate state with computed outputs, then
`tofu output`.

---

## What this repo deliberately does NOT manage

* **k3s itself.** Phase 1's docs install k3s; Ansible's Phase 10 keeps the
  prereqs in shape. OpenTofu is for the layer below.
* **Kubernetes resources.** That's helm-chart values files (Phases 5–9)
  and ArgoCD (Phase 12). Mixing IaC tools per layer keeps each focused.
* **DNS records, fabrics, VLAN config.** MAAS already manages these and
  we haven't needed to mutate them. Add as needed.
* **Crossplane.** Different paradigm — see `02-crossplane.md`.

---

## Real-world skills demonstrated

| Skill | Where it applies in industry |
|---|---|
| **Importing brownfield infrastructure** | Every shop that adopted Terraform after their cloud accounts were already populated. Same workflow on AWS, Azure, GCP. |
| **The import-plan loop** | The only safe way to reconcile code with live state without destroying anything. Real teams enforce "plan must be empty" as a CI check. |
| **OpenTofu adoption** | Awareness of the BSL→Apache 2.0 fork is a 2024+ industry-pulse signal. |
| **Provider-specific gotchas** | The "`/api/2.0` doubling" issue, the `canonical/maas` move — same shape as every cloud provider has its own quirks. |
| **Sensitive state handling** | API key in state → gitignore + 0600 → remote backend later. Standard escalation path. |
| **Risk-aware scope** | Choosing not to `apply` against a live, stateful system, even when the tool offers it, is the senior-engineer move. Same call as Phase 10's "no k3s install via Ansible." |
| **Layered IaC** | OpenTofu for the cloud-API layer (MAAS), Ansible for the OS layer, Helm/kubectl for the cluster layer — each tool focused on what it's best at. |
