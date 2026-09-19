---
slug: ansible-bare-metal-node-bootstrap
title: "La couche sous le GitOps : comment ~200 lignes d'Ansible gardent un cluster bare-metal reproductible"
authors: [andrelair]
tags: [ansible, bare-metal, kubernetes, k3s, gitops, longhorn, harbor, cis, automation, platform-engineering, idempotency]
date: 2026-09-19
description: "Le GitOps réconcilie tout ce qui est à l'intérieur du cluster — mais pas le système d'exploitation en dessous. Voici comment minicloud-ansible codifie les prérequis au niveau des nœuds (iSCSI, multipath, miroirs de registre, routes par défaut, durcissement CIS) pour qu'un nœud puisse être réinstallé ou ajouté avec un seul playbook idempotent."
---

ArgoCD réconcilie tout ce qui est *à l'intérieur* de mon cluster : 95 applications, de Vault à la passerelle IA, toutes déclarées dans Git et synchronisées en continu. Mais ArgoCD ne peut pas formater un disque, installer `open-iscsi` ni corriger une route par défaut. Il existe une couche **en dessous** du GitOps — le système d'exploitation de chaque nœud bare-metal — et si cette couche n'est pas codifiée, « l'infrastructure reproductible » n'est qu'une demi-vérité.

Pour le système d'information ktayl-solution, cette couche appartient à un petit dépôt : **[`minicloud-ansible`](https://github.com/andrelair-platform/minicloud-ansible)**. Environ 200 lignes de tâches réparties en quatre rôles, qui font une seule chose et la font bien : rendre les prérequis OS d'un cluster k3s à 6 nœuds **reproductibles et auditables**. Cet article explique comment je l'utilise pour exploiter la plateforme de l'organisation.

{/* truncate */}

## La frontière de périmètre : ce qu'Ansible possède, et ce qu'il refuse délibérément

La plateforme tourne sur des ThinkPad reconditionnés (plus un MacBook Pro de 2012) provisionnés par MAAS. Le modèle de livraison est du GitOps trunk-based : la CI construit les artefacts, Kargo les promeut, ArgoCD les déploie. Alors où se situe Ansible ? Exactement dans l'espace que les autres outils ne peuvent pas atteindre :

| Couche | Propriétaire | Exemple |
|---|---|---|
| Bare-metal / cycle de vie des machines | MAAS + OpenTofu | enrôler et commissionner un ThinkPad comme nœud |
| **Prérequis OS des nœuds** | **Ansible (ce dépôt)** | **`open-iscsi`, blacklist multipath, miroir de registre, route par défaut, config kubelet CIS** |
| Cluster k3s & workloads | GitOps (ArgoCD + Kargo) | 95 Applications, valeurs Helm, promotion |

La décision de conception la plus importante de ce dépôt est un **non-objectif** : il **n'installe pas** k3s. Le cluster est vivant et stateful — répliques Longhorn, données du registre Harbor, TSDB de monitoring, store kine/SQLite du control-plane. Relancer un installeur k3s `curl | sh` sur un nœud sain n'apporte aucun bénéfice et présente un vrai risque de corruption de l'état du cluster si quoi que ce soit dérive dans l'installeur. Le dépôt couvre donc **uniquement les prérequis au niveau OS qui doivent être ré-appliqués si un nœud est réinstallé** — et l'installation de k3s reste une étape manuelle documentée et délibérée. Savoir ce qu'il ne faut **pas** automatiser fait partie d'une exploitation sûre.

## Les quatre rôles qui gardent un nœud correct

Le playbook de bootstrap, `site.yml`, tient en quatre lignes — il compose quatre rôles sur le groupe d'inventaire `cluster` :

```yaml
- name: Bootstrap minicloud cluster nodes (post-MAAS, pre-k3s)
  hosts: cluster
  roles:
    - common
    - longhorn-prereq
    - k3s-registries
    - network
```

Chaque rôle encode une leçon.

### `common` — les utilitaires de base, et un qui n'est pas évident

`htop`, `vim`, `curl`, `jq`, `rsync`… et `sqlite3`. Ce dernier n'est pas là pour le confort : le nœud control-plane exécute une sauvegarde en ligne de la base d'état de k3s avec `sqlite3 .backup`, qui est WAL-safe sur une base vivante. Il est inoffensif sur les workers, donc il est déployé sur tous les nœuds plutôt que traité comme un cas spécial. Petit, mais c'est la différence entre « j'ai une sauvegarde » et « j'ai une sauvegarde qui ne se corrompt pas sous charge ».

### `longhorn-prereq` — le rôle qui a mérité sa blacklist multipath

C'est le rôle avec une histoire de guerre. Longhorn expose chaque volume comme une cible iSCSI (vendor `IET`, produit `VIRTUAL-DISK`). Si `multipathd` tourne, il *réclame* ces périphériques `/dev/sdX` en tant que `mpathN` et les retient au niveau device-mapper — le montage kubelet échoue alors avec `already mounted or mount point busy`, et les pods restent bloqués indéfiniment en `ContainerCreating`.

Les nœuds plus anciens portaient une blacklist ajoutée à la main. Puis j'ai ajouté `loving-gannet`, le nœud le plus récent — et il a rencontré le bug immédiatement, parce qu'il *n'avait jamais la blacklist que les autres avaient*. C'est exactement le mode de défaillance qu'Ansible existe pour empêcher : des correctifs manuels, par nœud, non documentés, qu'un nouveau nœud ne possède pas silencieusement. Le correctif est donc entré dans le rôle :

```yaml
- name: Blacklist Longhorn iSCSI devices from multipath
  ansible.builtin.copy:
    dest: /etc/multipath.conf
    content: |
      blacklist {
          device {
              vendor "IET"
              product "VIRTUAL-DISK"
          }
      }
  when: multipathd_unit.stat.exists
  notify: Flush and restart multipathd
```

Désormais, la blacklist est une propriété du fait *d'être un nœud de ce cluster*, pas quelque chose que je me suis souvenu de faire. Tout nœud futur l'obtient dès son premier passage de `site.yml`. (Le rôle installe aussi `open-iscsi` et active `iscsid`, l'autre exigence stricte de Longhorn.)

### `k3s-registries` — Harbor en miroir, avec un fallback qui évite les pannes auto-infligées

Chaque pull d'image sur le cluster passe par le Harbor in-cluster en miroir proxy-cache — `docker.io`, `ghcr.io`, `quay.io`, `registry.k8s.io`. Ce rôle dépose `/etc/rancher/k3s/registries.yaml` (plus le certificat root-CA interne, pour que les pulls soient vérifiés en HTTPS) sur chaque nœud.

La subtilité est dans le fallback. Chaque miroir liste Harbor **en premier** et l'upstream public **en second** :

```yaml
mirrors:
  "docker.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/docker-hub"
      - "https://registry-1.docker.io"
```

Cet ordre est tout l'intérêt : si Harbor est indisponible — un redémarrage de pod, une mise à jour — k3s bascule vers le registre public au lieu que le cluster entier perde la capacité de puller des images. Cela évite le piège classique « le redémarrage du registre a cassé le cluster ». Un miroir de registre n'est une bonne idée que s'il échoue en mode ouvert.

### `network` — un rôle d'un seul fichier pour le problème ennuyeux qui met un cluster à terre

Un unique fichier netplan fixe la route par défaut via `10.0.0.1`. C'est trivial — jusqu'à ce qu'un nœud redémarre sans passerelle par défaut et disparaisse du réseau. Le rôle porte aussi un vrai piège dans ses métadonnées : depuis Ubuntu 24.04, netplan **refuse les fichiers world-readable**, donc le fichier doit être en `0600`. Le handler exécute `netplan generate` (pour valider la syntaxe) *avant* `netplan apply` — car la seule chose pire qu'une mauvaise route est d'appliquer une mauvaise route à un nœud que vous ne pouvez ensuite plus joindre.

## Day-2 : mises à jour progressives sans interruption

Le bootstrap est unique par nœud. L'autre mission du dépôt, c'est la maintenance continue, et `upgrade.yml` est là où l'organisation obtient un patching sans interruption. Il tourne en `serial: 1` — strictement un nœud à la fois — et pour chaque nœud :

1. `kubectl drain` (délégué au contrôleur) — cordon + éviction, en respectant les PodDisruptionBudgets
2. `apt update` + `apt upgrade` (upgrade **safe** — ne supprime jamais de paquets)
3. redémarrage **uniquement si** `/var/run/reboot-required` existe (c.-à-d. un noyau a atterri)
4. attente que le nœud repasse `Ready`
5. `kubectl uncordon`

Le pré-vol est codifié dans les commentaires du playbook comme un contrat d'exploitation : chaque workload doit avoir ≥2 répliques avec anti-affinité entre workers, et chaque volume Longhorn ≥2 répliques saines — pour que le drain puisse *échouer en sécurité* s'il ne peut pas relocaliser un volume plutôt que de risquer les données. C'est ainsi qu'une plateforme exploitée en solo patche son OS sur un cluster vivant sans mettre les services de l'organisation hors ligne.

## Au-delà du bootstrap : durcissement et migrations sous forme de playbooks

Le même modèle idempotent s'étend à des changements plus lourds, conservés comme playbooks séparés et relisibles :

- **`cis-kubelet-hardening.yml`** écrit un `/var/lib/kubelet/config.yaml` conforme CIS (port read-only à `0`, rotation des certificats, suites de chiffrement TLS fortes uniquement, limites de PID par pod) et configure k3s pour le charger — puis déploie `kube-bench` pour le prouver. Résultat : **16/16 PASS** sur les contrôles kubelet k3s-cis-1.7, sur chaque worker. La posture de sécurité comme code, avec sa propre preuve.
- **`cilium-migration.yml`** a réalisé le remplacement progressif du CNI Flannel→Cilium eBPF sur un cluster vivant.
- **`fix-grub-timeout.yml`** est le genre de petit correctif réel qui devient un playbook répétable au lieu d'une session SSH oubliée.

## La discipline qui le rend digne de confiance : `changed=0`

Rien de tout cela ne compte si le code ne correspond pas à la réalité. Le workflow qui les garde honnêtes est un **audit de dérive** — une exécution en mode check qui ne change rien et signale ce qui *changerait* :

```bash
ansible-playbook playbooks/site.yml --check --diff
```

Lisez le `PLAY RECAP`. Si chaque hôte rapporte `changed=0`, l'état codifié **est** la réalité. Si un hôte rapporte `changed > 0`, c'est de la dérive — soit un rôle qui ne correspond plus au nœud, soit un nœud que quelqu'un a modifié à la main. Dans les deux cas, on investigue le diff *avant* d'appliquer. Et chaque rôle doit rapporter `changed=0` à une seconde exécution consécutive — la définition de l'idempotence, et la barre pour qu'un rôle soit « terminé ».

Pour un contexte réglementé (le SI ktayl-solution simule un assureur français, avec DORA dans le périmètre), cette propriété vaut autant que l'automatisation elle-même : à tout moment je peux *prouver*, de façon non destructive, que la couche OS de la flotte correspond à une intention versionnée et relue — et reconstruire n'importe quel nœud à partir de là.

## Pourquoi ce petit dépôt compte pour l'organisation

Il est tentant de voir 200 lignes d'Ansible à côté de 95 applications GitOps et de le prendre pour un détail. Ce n'en est pas un. C'est le **socle** sur lequel toute la plateforme repose :

- **Reproductibilité.** Un nœud réinstallé ou tout neuf devient un membre correct du cluster en un seul passage de `site.yml` — pas de savoir tribal, pas de nœuds « flocons de neige » (la leçon `loving-gannet`, rendue permanente).
- **Sécurité.** Le miroir Harbor-avec-fallback et l'upgrade drain-first échouent tous deux en mode *ouvert*, pour que les opérations de routine ne cascadent pas en pannes.
- **Auditabilité.** `--check --diff` transforme « les serveurs sont configurés correctement » d'une affirmation en un fait vérifiable et reproductible.
- **Une frontière de périmètre nette.** MAAS provisionne le métal, Ansible rend l'OS correct, GitOps fait tourner le cluster. Chaque outil fait le travail pour lequel il est le meilleur, et les coutures sont explicites.

Le GitOps est sous les projecteurs parce qu'il fait tourner les applications que l'entreprise voit. Mais ces applications ne tournent que parce que, en dessous, chaque nœud est ennuyeusement, prouvablement correct — et c'est le travail que ce petit dépôt fait pour l'organisation, à chaque fois qu'un nœud arrive ou repart.

*Le dépôt est public : [`andrelair-platform/minicloud-ansible`](https://github.com/andrelair-platform/minicloud-ansible).*
