---
id: phase-9-ansible
title: Phase 19 — Ansible (Backstage Integration)
sidebar_position: 10
---

# Phase 9 — Ansible Automation

Automate node configuration, cluster setup, and app deployment with Ansible.

---

## Why Ansible?

```text
✔ Idempotent — run multiple times safely
✔ Agentless — uses SSH
✔ YAML playbooks — readable and version-controlled
✔ Can rebuild entire cluster from scratch
```

---

## Install Ansible

```bash
sudo apt install ansible
```

---

## Inventory File

```ini
# inventory.ini
[control_plane]
set-hog ansible_host=10.0.0.2 ansible_user=ubuntu

[workers]
fast-skunk ansible_host=10.0.0.4 ansible_user=ubuntu
fast-heron ansible_host=10.0.0.7 ansible_user=ubuntu

[cluster:children]
control_plane
workers
```

---

## Use Cases

### k3s cluster install

```yaml
- name: Install k3s control plane
  hosts: control_plane
  tasks:
    - name: Run k3s installer
      shell: curl -sfL https://get.k3s.io | sh -
```

### Node configuration

```yaml
- name: Configure all nodes
  hosts: cluster
  tasks:
    - name: Install base packages
      apt:
        name: [curl, vim, htop, net-tools]
        state: present
```

### Cluster rebuild

```text
✔ Tear down cluster
✔ Re-provision via MAAS
✔ Re-install k3s via Ansible
✔ Re-deploy apps via ArgoCD
```

---

## Done When

```text
✔ Full cluster deployable from a single ansible-playbook command
✔ Node configs reproducible
```
