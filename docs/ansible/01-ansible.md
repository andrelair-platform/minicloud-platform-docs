---
id: ansible
title: Phase 10 — Ansible
sidebar_position: 1
---

# Phase 10 — Ansible — Infrastructure Automation

Ansible automates everything you would otherwise do by hand over SSH — installing k3s, configuring nodes, deploying apps, rebuilding the cluster from scratch. It is agentless (uses SSH), idempotent (safe to run multiple times), and YAML-based.

---

## Why Ansible at This Stage

By Phase 10 you have a working cluster. Without Ansible, everything you built is a collection of commands you ran once and may not remember. Ansible turns those commands into **repeatable, version-controlled playbooks** — run them again and the result is identical.

```text
Without Ansible:
  → Manual SSH to each node
  → Different config per node over time
  → Cluster rebuild = hours of work

With Ansible:
  → ansible-playbook cluster.yml
  → All nodes configured identically
  → Cluster rebuild = minutes
```

---

## Install Ansible

```bash
# On your local machine or MAAS controller
sudo apt install -y ansible

ansible --version
```

---

## Inventory File

Describes your cluster to Ansible:

```ini
# inventory.ini
[control_plane]
set-hog ansible_host=10.0.0.2 ansible_user=ubuntu

[workers]
fast-skunk ansible_host=10.0.0.4 ansible_user=ubuntu
fast-heron  ansible_host=10.0.0.7 ansible_user=ubuntu

[cluster:children]
control_plane
workers
```

Test connectivity:

```bash
ansible all -i inventory.ini -m ping
```

All 3 nodes should return `pong`.

---

## Playbook 1 — Configure All Nodes

```yaml
# playbooks/configure-nodes.yml
---
- name: Configure all cluster nodes
  hosts: cluster
  become: true
  tasks:

    - name: Install base packages
      apt:
        name:
          - curl
          - vim
          - htop
          - net-tools
          - ca-certificates
          - nfs-common
          - open-iscsi
        state: present
        update_cache: true

    - name: Disable IPv6
      sysctl:
        name: "{{ item }}"
        value: "1"
        state: present
        sysctl_file: /etc/sysctl.d/99-disable-ipv6.conf
      loop:
        - net.ipv6.conf.all.disable_ipv6
        - net.ipv6.conf.default.disable_ipv6
        - net.ipv6.conf.lo.disable_ipv6

    - name: Set timezone to UTC
      timezone:
        name: UTC

    - name: Enable iscsid (required for Longhorn)
      systemd:
        name: iscsid
        enabled: true
        state: started
```

Run:

```bash
ansible-playbook -i inventory.ini playbooks/configure-nodes.yml
```

---

## Playbook 2 — Install k3s Cluster

```yaml
# playbooks/install-k3s.yml
---
- name: Install k3s control plane
  hosts: control_plane
  become: true
  tasks:
    - name: Install k3s server
      shell: curl -sfL https://get.k3s.io | sh -
      args:
        creates: /usr/local/bin/k3s

    - name: Get node token
      slurp:
        src: /var/lib/rancher/k3s/server/node-token
      register: node_token

    - name: Save token to local file
      local_action:
        module: copy
        content: "{{ node_token.content | b64decode | trim }}"
        dest: /tmp/k3s-node-token

- name: Join worker nodes
  hosts: workers
  become: true
  vars:
    k3s_token: "{{ lookup('file', '/tmp/k3s-node-token') }}"
    k3s_url: "https://10.0.0.2:6443"
  tasks:
    - name: Install k3s agent
      shell: |
        curl -sfL https://get.k3s.io | \
          K3S_URL={{ k3s_url }} \
          K3S_TOKEN={{ k3s_token }} \
          sh -
      args:
        creates: /usr/local/bin/k3s
```

Run:

```bash
ansible-playbook -i inventory.ini playbooks/install-k3s.yml
```

---

## Playbook 3 — Full Cluster Rebuild

The most powerful playbook — provision from scratch after a MAAS redeploy:

```yaml
# playbooks/rebuild-cluster.yml
---
- import_playbook: configure-nodes.yml
- import_playbook: install-k3s.yml
```

```bash
ansible-playbook -i inventory.ini playbooks/rebuild-cluster.yml
```

Full cluster up from a freshly MAAS-deployed node in under 5 minutes.

---

## Playbook 4 — Rolling Updates

Update all nodes without cluster downtime:

```yaml
# playbooks/update-nodes.yml
---
- name: Rolling update cluster nodes
  hosts: cluster
  become: true
  serial: 1          # one node at a time
  tasks:
    - name: Drain node
      local_action:
        module: shell
        cmd: kubectl drain {{ inventory_hostname }} --ignore-daemonsets --delete-emptydir-data
      ignore_errors: true

    - name: Update packages
      apt:
        upgrade: dist
        update_cache: true

    - name: Reboot if required
      reboot:
        reboot_timeout: 300
      when: ansible_facts.get('reboot_required', false)

    - name: Uncordon node
      local_action:
        module: shell
        cmd: kubectl uncordon {{ inventory_hostname }}
```

---

## Project Structure

```text
ansible/
├── inventory.ini
├── group_vars/
│   ├── all.yml          # shared variables
│   └── workers.yml
├── playbooks/
│   ├── configure-nodes.yml
│   ├── install-k3s.yml
│   ├── rebuild-cluster.yml
│   └── update-nodes.yml
└── roles/
    ├── base/            # common node setup
    ├── k3s-server/      # control plane install
    └── k3s-agent/       # worker install
```

---

## Done When

```text
✔ ansible all -m ping returns pong for all 3 nodes
✔ configure-nodes.yml runs clean (idempotent)
✔ install-k3s.yml builds the cluster from scratch
✔ rebuild-cluster.yml tested end to end
```
