---
id: phase-10-ansible
title: Phase 10 — Ansible (Post-MAAS Bootstrap)
sidebar_position: 10
---

# Phase 10 — Ansible (Post-MAAS Bootstrap & Day-2 Ops)

The first nine phases of the platform built the *running* cluster:
provisioning, k3s, Tailscale, MetalLB, Longhorn, Ingress, Harbor, monitoring,
podinfo. Each one needed a small, manual node-level tweak (an `apt install`,
an `iscsid enable`, a config file dropped into `/etc/`). Those tweaks
worked, but they live as prose in `CLAUDE.md` rather than as code on disk.
If a node's SSD dies tomorrow, every one of them is a chance to forget
something.

Phase 10 codifies the **post-MAAS, pre-k3s node bootstrap** as Ansible
roles. The proof that the codification is correct is `ansible-playbook
--check --diff`: when it returns `changed=0` against the live cluster, our
roles match reality. When it doesn't, we've found drift — which is exactly
what happened on this run.

Ansible is **not** used to install k3s itself. The cluster is live and
stateful (etcd, Longhorn replicas, Harbor data, Prometheus TSDB); rerunning
a curl-pipe-sh installer against a healthy node is risk without reward. The
roles cover only the OS-level prerequisites that need to be re-applied if a
node is reimaged.

A second playbook (`upgrade.yml`) demonstrates rolling Day-2 maintenance —
`kubectl drain` → `apt upgrade` → reboot if needed → wait for Ready →
`kubectl uncordon`, one node at a time.

---

## Architecture

```text
                    Controller (this machine)
                   ┌─────────────────────────┐
                   │  ansible-core 2.20      │
                   │  pipx-installed         │
                   │  ssh keys to ubuntu@    │
                   │  10.0.0.{2,4,7}         │
                   └────────────┬────────────┘
                                │ SSH (key auth, NOPASSWD sudo)
            ┌───────────────────┼────────────────────┐
            ▼                   ▼                    ▼
       set-hog            fast-skunk           fast-heron
     (control plane)       (worker)             (worker)

   roles applied to every node:
     ▸ common              base utilities
     ▸ longhorn-prereq     open-iscsi + iscsid enabled
     ▸ k3s-registries      /etc/rancher/k3s/registries.yaml
     ▸ network             /etc/netplan/99-default-gateway.yaml
```

---

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Install method | `pipx install --include-deps ansible` (ansible-core 2.20) | `apt install ansible` ships an older 9.x release; pipx isolates ansible's Python deps from system Python and gives us the modern release |
| Repo location | `~/minicloud-ktaylorganisation/ansible/` | Sibling of the chart values files; not a separate git repo (yet) |
| Role boundary | One role per concern — `common`, `longhorn-prereq`, `k3s-registries`, `network` | Each manual config from Phases 0–7 becomes its own role; clean isolation |
| **No k3s install task** | Documented in Phase 1; not in any playbook | Cluster is live and stateful; running a curl-pipe-sh installer adds risk without value. New nodes get the install command run *once* manually, then `site.yml`. |
| First verification | `--check --diff` against live nodes | Standard Ansible idempotency proof. The receipt is `changed=0` on a *second* run. |
| Day-2 ops | `serial: 1` rolling upgrade with `kubectl drain` / `uncordon` delegated to `localhost` | Real production pattern; ensures workloads relocate before any node is upgraded |
| Secrets | None in scope | OS config only — no API keys, no passwords. Ansible Vault arrives in Phase 15. |

---

## Pre-flight

```bash
# Install ansible-core via pipx (no sudo for the ansible binary itself)
sudo apt install -y pipx python3-venv
pipx ensurepath
pipx install --include-deps ansible
ansible --version | head -1
# → ansible [core 2.20.x]

# SSH key auth must already work — Phase 0 set this up
ssh ubuntu@10.0.0.2 echo ok        # set-hog
ssh ubuntu@10.0.0.4 echo ok        # fast-skunk
ssh ubuntu@10.0.0.7 echo ok        # fast-heron
```

---

## Repo layout

```
ansible/
├── ansible.cfg            # inventory path, callback format, ssh pipelining
├── inventory.yml          # 3 nodes grouped: control_plane / workers / cluster
├── README.md
├── playbooks/
│   ├── site.yml           # bootstrap: common + longhorn-prereq + k3s-registries + network
│   └── upgrade.yml        # Day-2: rolling apt upgrade with drain/uncordon
└── roles/
    ├── common/            # tasks/main.yml + defaults/main.yml
    ├── longhorn-prereq/   # tasks/main.yml
    ├── k3s-registries/    # tasks/main.yml + files/registries.yaml
    └── network/           # tasks/main.yml + files/99-default-gateway.yaml + handlers/main.yml
```

### `ansible.cfg`

```ini
[defaults]
inventory = inventory.yml
host_key_checking = False
retry_files_enabled = False
callback_result_format = yaml
deprecation_warnings = False
roles_path = roles
forks = 5

[ssh_connection]
pipelining = True
ssh_args = -o ControlMaster=auto -o ControlPersist=60s -o ForwardAgent=no
```

> Note: in older docs you'll see `stdout_callback = yaml`. That callback was
> removed in `community.general` 12. The modern equivalent is
> `callback_result_format = yaml` on the built-in `default` callback.

### `inventory.yml`

```yaml
all:
  vars:
    ansible_user: ubuntu
    ansible_python_interpreter: /usr/bin/python3
  children:
    control_plane:
      hosts:
        set-hog:    {ansible_host: 10.0.0.2}
    workers:
      hosts:
        fast-skunk: {ansible_host: 10.0.0.4}
        fast-heron: {ansible_host: 10.0.0.7}
    cluster:
      children:
        control_plane:
        workers:
```

---

## Roles

### `common` — base utilities

Codifies a single declarative list of utilities every node should have.

`roles/common/defaults/main.yml`:

```yaml
common_packages:
  - htop
  - vim
  - curl
  - jq
  - net-tools
  - traceroute
  - rsync
```

`roles/common/tasks/main.yml`:

```yaml
- name: Install base utilities
  ansible.builtin.apt:
    name: "{{ common_packages }}"
    state: present
    update_cache: true
    cache_valid_time: 3600
  become: true
```

### `longhorn-prereq` — iSCSI

`roles/longhorn-prereq/tasks/main.yml`:

```yaml
- name: Install open-iscsi (provides iscsid + iscsi_tcp module)
  ansible.builtin.apt:
    name: open-iscsi
    state: present
  become: true

- name: Ensure iscsid service is enabled and started
  ansible.builtin.systemd:
    name: iscsid
    enabled: true
    state: started
  become: true
```

### `k3s-registries` — Harbor mirror config

`roles/k3s-registries/files/registries.yaml`:

```yaml
configs:
  "harbor.10.0.0.200.nip.io":
    tls:
      insecure_skip_verify: true
mirrors:
  "harbor.10.0.0.200.nip.io":
    endpoint:
      - "http://harbor.10.0.0.200.nip.io"
```

`roles/k3s-registries/tasks/main.yml`:

```yaml
- name: Ensure /etc/rancher/k3s directory exists
  ansible.builtin.file:
    path: /etc/rancher/k3s
    state: directory
    owner: root
    group: root
    mode: "0755"
  become: true

- name: Install /etc/rancher/k3s/registries.yaml
  ansible.builtin.copy:
    src: registries.yaml
    dest: /etc/rancher/k3s/registries.yaml
    owner: root
    group: root
    mode: "0644"
  become: true
```

> The k3s/`/v2`-suffix mirror issue documented in Phase 7 is *not* fixed by
> this role — the role only preserves the current state. The proper fix
> arrives in Phase 15 with TLS.

### `network` — explicit default gateway

`roles/network/files/99-default-gateway.yaml`:

```yaml
network:
  version: 2
  ethernets:
    enp0s31f6:
      routes:
        - to: default
          via: 10.0.0.1
```

`roles/network/tasks/main.yml`:

```yaml
- name: Install /etc/netplan/99-default-gateway.yaml
  ansible.builtin.copy:
    src: 99-default-gateway.yaml
    dest: /etc/netplan/99-default-gateway.yaml
    owner: root
    group: root
    # netplan refuses world-readable files (since 24.04) — must be 0600
    mode: "0600"
  become: true
  notify: Apply netplan
```

`roles/network/handlers/main.yml`:

```yaml
# `netplan generate` validates the YAML and produces the systemd-networkd
# config without applying it — a cheap safety check before `netplan apply`
# tears down interfaces. If `generate` fails, `apply` will not be invoked
# and the node keeps its current networking.
- name: Apply netplan
  ansible.builtin.shell:
    cmd: |
      set -e
      netplan generate
      netplan apply
  become: true
  changed_when: true
```

---

## The receipt — `--check --diff` against live nodes

```bash
cd ansible/
ansible-playbook playbooks/site.yml --check --diff
```

On *this* cluster, the first check revealed real drift in `common`:

```
TASK [common : Install base utilities] *********
The following NEW packages will be installed:
  net-tools traceroute
changed: [set-hog]                ← would install net-tools + traceroute
The following NEW packages will be installed:
  traceroute
changed: [fast-heron]              ← would install traceroute only
The following NEW packages will be installed:
  net-tools traceroute
changed: [fast-skunk]              ← would install net-tools + traceroute

PLAY RECAP
fast-heron  : ok=7 changed=1
fast-skunk  : ok=7 changed=1
set-hog     : ok=7 changed=1
```

Every other task (`longhorn-prereq`, `k3s-registries`, `network`) reported
`ok` — the codified state of those three concerns matched reality on every
node. The drift was confined to base utilities: `net-tools` had been
installed on `fast-heron` but not on the other two; `traceroute` was missing
everywhere.

This is a more interesting outcome than "no drift at all." It shows that
Ansible *finds* drift you didn't know existed, before it bites you in an
incident.

---

## Apply + idempotency

Apply the playbook:

```bash
ansible-playbook playbooks/site.yml --diff
```

```
TASK [common : Install base utilities] *********
changed: [set-hog]    (installed: net-tools traceroute)
changed: [fast-skunk] (installed: net-tools traceroute)
changed: [fast-heron] (installed: traceroute)

PLAY RECAP — all hosts: ok=7 changed=1
```

Run it a second time, immediately:

```
PLAY RECAP — all hosts: ok=7 changed=0
```

`changed=0` on every host. The playbook is idempotent. That's the receipt.

---

## Day-2: rolling apt upgrade

`playbooks/upgrade.yml` does a `serial: 1` rolling upgrade, draining
workloads before each node is touched and waiting for Ready before moving
on.

```yaml
- name: Rolling apt upgrade across the cluster
  hosts: cluster
  serial: 1
  become: true
  pre_tasks:
    - name: Cordon and drain the node from the controller
      delegate_to: localhost
      become: false
      ansible.builtin.command:
        cmd: >
          kubectl drain {{ inventory_hostname }}
          --ignore-daemonsets
          --delete-emptydir-data
          --timeout=5m
  tasks:
    - name: apt update
      ansible.builtin.apt:
        update_cache: true
    - name: apt upgrade (safe upgrade — never removes packages)
      ansible.builtin.apt:
        upgrade: safe
    - name: Check whether a reboot is required
      ansible.builtin.stat:
        path: /var/run/reboot-required
      register: reboot_required
    - name: Reboot the node if required
      ansible.builtin.reboot:
        reboot_timeout: 600
        post_reboot_delay: 30
      when: reboot_required.stat.exists
    - name: Wait for kubelet to mark the node Ready
      delegate_to: localhost
      become: false
      ansible.builtin.command:
        cmd: kubectl wait --for=condition=Ready node/{{ inventory_hostname }} --timeout=5m
  post_tasks:
    - name: Uncordon the node
      delegate_to: localhost
      become: false
      ansible.builtin.command:
        cmd: kubectl uncordon {{ inventory_hostname }}
```

Pre-flight before running for real:

* Every workload should have ≥ 2 replicas with anti-affinity across workers
  (Phase 9's podinfo HPA satisfies this).
* Longhorn volumes should have ≥ 2 healthy replicas — drain fail-safes if
  it cannot relocate them.
* Always `--check` and `--syntax-check` first.

```bash
ansible-playbook playbooks/upgrade.yml --syntax-check
ansible-playbook playbooks/upgrade.yml --list-tasks
ansible-playbook playbooks/upgrade.yml --limit fast-heron   # one node first
ansible-playbook playbooks/upgrade.yml                      # all 3, rolling
```

---

## Troubleshooting

### `community.general.yaml callback plugin has been removed`

`stdout_callback = yaml` was removed in `community.general` 12. Replace
with `callback_result_format = yaml` on the built-in `default` callback.

### `--check` reports drift you didn't expect

Either the role doesn't match reality (rewrite the task) or a node has
drifted from the others (apply and reconcile, or update the role to match
what's on the node). The `--diff` output tells you which.

### Netplan task ran on every node despite the file already existing

Probably a permission-bit mismatch — netplan files must be `0600` on
24.04+. The `mode:` parameter on the `copy` task ensures every run lands on
the right permissions; if you delete the line, the first run after a fresh
node will report `changed` because file mode differs from the default
(`0644`).

### `sudo: a password is required`

The `ubuntu` user on the target node lacks passwordless sudo. Fix the node
(`/etc/sudoers.d/90-ubuntu` with `NOPASSWD:ALL`) or run with
`--ask-become-pass`.

---

## Done When

```text
✔ ansible-core 2.18+ installed via pipx, ansible/ binaries on PATH
✔ ansible -m ping all returns "pong" from set-hog, fast-skunk, fast-heron
✔ ansible-playbook playbooks/site.yml --check --diff has been run and any
  drift it found is documented (drift on first run is expected and useful)
✔ Apply + second run shows changed=0 (idempotency proven)
✔ playbooks/upgrade.yml passes --syntax-check and --list-tasks
✔ README.md committed
✔ Cluster is still healthy (kubectl get nodes, podinfo, grafana all reachable)
```

---

## Real-world skills demonstrated

| Skill | Where it applies in industry |
|---|---|
| **Codification of "tribal knowledge"** | Every team has a mental list of "things you have to remember to do on a fresh node." Turning that list into roles is what separates a one-engineer hobby project from a real platform. |
| **`--check --diff` as drift audit** | Same workflow real teams use to detect config drift before it causes an incident — Puppet's `--noop`, Chef's `--why-run`, Terraform's `plan` are all the same idea. |
| **Idempotency as a first-class quality** | The "second run reports zero changes" rule is non-negotiable for production playbooks. Anything else is a foot-gun. |
| **Risk-aware scope** | Choosing not to install k3s through Ansible — codifying *prerequisites* but leaving the cluster bootstrap manual — is exactly the call senior engineers make on live, stateful systems. |
| **Rolling upgrades with drain/uncordon** | Standard production-maintenance pattern. Same shape on EKS, GKE, AKS, OpenShift, and bare metal. |
| **`delegate_to: localhost` for control-plane tasks** | Useful any time you need to coordinate Kubernetes operations alongside SSH-based maintenance — `kubectl drain` runs from where kubeconfig lives, not from inside the node being drained. |
| **Pipx + venv hygiene** | Modern way to install Python CLIs on PEP 668 systems (Ubuntu 24.04+, Debian 12+) without polluting system Python. |
