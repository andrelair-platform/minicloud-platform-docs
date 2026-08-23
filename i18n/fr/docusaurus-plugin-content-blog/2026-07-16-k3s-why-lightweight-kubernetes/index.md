---
slug: k3s-why-lightweight-kubernetes-bare-metal
title: "Pourquoi k3s ? Installer Kubernetes sur 5 laptops avec une seule commande curl"
authors: [andre]
description: >
  Comment k3s a été installé sur un cluster bare-metal de 5 nœuds — une commande curl par machine —
  et pourquoi k3s a battu kubeadm, microk8s, RKE2 et k0s pour ce matériel spécifique.
tags: [kubernetes, k3s, bare-metal, platform-engineering, devops, homelab]
date: 2026-07-16
image: /img/docusaurus-social-card.jpg
---

Le matériel était provisionné. MAAS avait démarré quatre ThinkPads en PXE et cloud-init avait écrit les clés SSH et les noms d'hôte. La question suivante était : **comment faire tourner concrètement Kubernetes sur cinq laptops ?**

Il existe plus de façons d'installer Kubernetes qu'il n'y a de parcours de certification Kubernetes. J'ai fini avec k3s. Voici pourquoi — et exactement à quoi ressemblait l'installation.

{/* truncate */}

## La contrainte qui a tranché la décision

Choisir une distribution Kubernetes pour ce cluster n'était pas un débat philosophique. Le matériel a décidé à ma place.

Le cluster inclut un **MacBook Pro 13" (fin 2012)** — un Intel Core i5-3210M (bicœur, millésime 2012), 8 Go de RAM DDR3. Cette machine est devenue `swift-mac`, exécutant Ubuntu 22.04 comme worker de stockage Longhorn. Le MacBook ne peut pas être provisionné en PXE (le firmware EFI d'Apple ne supporte pas le démarrage réseau), donc Ubuntu a été installé manuellement depuis une clé USB. Après cela, il rejoint le cluster exactement comme n'importe quel autre nœud.

Si le MacBook peut faire tourner un agent k3s sans être privé de RAM, n'importe quel nœud de ce cluster le peut. C'est le critère de sélection.

## Les options et pourquoi elles n'ont pas convaincu

| Distribution | Pourquoi non |
|---|---|
| **kubeadm** | La méthode « officielle » — mais elle vous oblige à installer containerd, un plugin CNI et etcd séparément avant même de pouvoir initialiser le plan de contrôle. Le plan de contrôle seul consomme 2 Go+ au repos. Trop lourd, trop de pièces mobiles, 40 pages de documentation avant le hello world. |
| **minikube / kind** | Mononœud, conçu pour le développement local et les runners CI. Ne peut pas former un vrai cluster bare-metal multi-nœuds. |
| **microk8s** | Dépendant de Snap. Fortement couplé au gestionnaire de paquets d'Ubuntu, surcharge non triviale du runtime snap, moins portable entre distributions. |
| **RKE2** | La distribution durcie de Rancher — conforme CIS par défaut, excellente pour la production d'entreprise réglementée. Plus gourmande en ressources que k3s et sur-dimensionnée pour un homelab. À revisiter si un second cluster est un jour construit aux specs d'entreprise. |
| **k0s** | Comparable en poids à k3s, mais l'écosystème était moins mature au démarrage de ce projet — moins d'exemples communautaires, moins d'outillage, moins de documentation. |

## Pourquoi k3s

k3s l'emporte sur quatre critères qui comptent vraiment pour ce matériel :

**1. Binaire unique, tout inclus.**  
containerd, CoreDNS, flannel (CNI), kube-proxy et un provisionneur de chemin local sont tous regroupés dans un binaire unique d'environ 70 Mo. Rien à installer séparément, rien à épingler en version sur plusieurs paquets, rien à casser dans un écart entre versions de composants.

**2. Empreinte mémoire minimale.**  
Le plan de contrôle k3s démarre autour de 300 Mo de RAM sur un cluster calme. Les 8 Go du MacBook Pro ne sont pas un plafond — c'est de la marge. Sous charge, le même nœud fait tourner des répliques Longhorn, des daemonsets système et un agent k3s sans être privé.

**3. Kubernetes certifié CNCF.**  
C'est l'argument qui compte pour un portfolio. k3s expose exactement les mêmes API que GKE, EKS et AKS. Chaque concept appris ici — Deployments, Services, PersistentVolumes, RBAC, Admission Webhooks — se transfère directement au Kubernetes cloud managé. Ce n'est pas un jouet de homelab ; c'est du Kubernetes, dépouillé des composants non pertinents à cette échelle.

**4. Mises à jour progressives sans étape manuelle.**  
Une fois [system-upgrade-controller](https://github.com/rancher/system-upgrade-controller) déployé, mettre à jour tout le cluster est un seul changement YAML : mettez à jour le champ `version:` dans le manifeste du Plan et committez. Le contrôleur gère cordon → drain → mise à jour → uncordon sur chaque nœud, le serveur avant les agents. Le cluster est passé de v1.33 à v1.36.2+k3s1 de cette façon avec zéro interruption sur les cinq nœuds.

## L'installation

Les quatre nœuds ThinkPad du cluster (set-hog, fast-skunk, fast-heron, star-kitten) tournaient déjà sous Ubuntu 22.04 LTS, provisionnés par MAAS. `swift-mac` avait Ubuntu installé manuellement. À partir de là, l'installation tient en trois étapes.

**Étape 1 — Plan de contrôle sur `set-hog` (10.0.0.2) :**

```bash
ssh ubuntu@10.0.0.2
curl -sfL https://get.k3s.io | sh -
```

Le script détecte l'architecture, télécharge le binaire unique, enregistre une unité systemd et démarre le serveur k3s. Le serveur d'API complet, le scheduler, le controller-manager et l'etcd embarqué sont opérationnels en 30 secondes.

**Étape 2 — Récupérer le token de jonction :**

```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

**Étape 3 — Joindre chaque worker (fast-skunk, fast-heron, star-kitten, swift-mac) :**

```bash
curl -sfL https://get.k3s.io | \
  K3S_URL=https://10.0.0.2:6443 \
  K3S_TOKEN=<token> \
  sh -
```

Quatre sessions SSH. Quatre commandes curl. Le cluster apparaît dans `kubectl get nodes` quelques secondes après chaque jonction.

```
NAME          STATUS   ROLES                  AGE   VERSION
set-hog       Ready    control-plane,master   5m    v1.36.2+k3s1
fast-skunk    Ready    <none>                 4m    v1.36.2+k3s1
fast-heron    Ready    <none>                 3m    v1.36.2+k3s1
star-kitten   Ready    <none>                 2m    v1.36.2+k3s1
swift-mac     Ready    <none>                 1m    v1.36.2+k3s1
```

Le nœud `swift-mac` a rejoint via le maillage Tailscale (le contrôleur MAAS fait office de NAT). Le SMC d'Apple ne supporte pas le Wake-on-AC, donc `swift-mac` ne redémarre pas automatiquement après une coupure de courant — tous les autres nœuds si. C'est la seule asymétrie d'infrastructure introduite par le matériel.

## L'analogie

La relation entre kubeadm et k3s est la même que celle entre installer manuellement un serveur Linux paquet par paquet et utiliser MAAS pour le provisionner. Le résultat est identique. Le chemin est radicalement différent. Kubeadm vous donne un contrôle maximal sur chaque composant. k3s vous donne un cluster fonctionnel sur lequel bâtir immédiatement.

Pour un projet dont le but est de démontrer des compétences en platform engineering — pas de démontrer la capacité à configurer etcd de zéro — k3s est le bon choix. Le cluster en est désormais à sa 75e phase opérationnelle. La distribution n'a jamais été le goulot d'étranglement.

## L'automatiser avec Ansible

Quatre sessions SSH conviennent pour un amorçage unique. Mais après que le cluster était en route et que `minicloud-ansible` s'est établi comme couche d'automatisation, l'étape naturelle suivante était d'écrire un playbook capable de reproduire l'installation complète de zéro — pour que la prochaine reconstruction du cluster prenne une commande, pas quatre.

Le playbook se trouve à `playbooks/install-k3s.yml` dans [minicloud-ansible](https://github.com/andrelair-platform/minicloud-ansible). Il a trois plays :

**Play 1 — Plan de contrôle (`set-hog`) :**  
Installe le serveur k3s, attend que le port 6443 soit prêt, attend que le nœud atteigne l'état `Ready`, puis lit le token de jonction dans une variable Ansible.

**Play 2 — Workers (`fast-skunk`, `fast-heron`, `star-kitten`, `swift-mac`) :**  
Joint un worker à la fois (`serial: 1`) avec le token récupéré depuis `hostvars`. Chaque worker doit être `Ready` avant que le suivant ne démarre.

**Play 3 — Kubeconfig :**  
Récupère `/etc/rancher/k3s/k3s.yaml` depuis le plan de contrôle, remplace l'adresse serveur de `127.0.0.1` par l'IP réelle, et renomme le contexte en `minicloud`. Enregistre le résultat dans `/tmp/minicloud.yaml` sur le contrôleur Ansible.

```bash
# Simulation
ansible-playbook playbooks/install-k3s.yml --check

# Installation complète (épingle la version actuelle du cluster)
ansible-playbook playbooks/install-k3s.yml

# Épingler une version différente
ansible-playbook playbooks/install-k3s.yml -e k3s_version=v1.37.0+k3s1

# Workers uniquement (plan de contrôle déjà en route)
ansible-playbook playbooks/install-k3s.yml --tags workers

# Après le playbook — copier le kubeconfig vers le contrôleur
scp /tmp/minicloud.yaml controller:~/.kube/minicloud.yaml
```

Le playbook est **idempotent** — il vérifie la présence de `/usr/local/bin/k3s` avant d'installer. Le relancer sur un cluster existant saute les tâches d'installation et ne fait que revalider l'état `Ready`.

### Pourquoi l'installation n'a pas été automatisée dès le premier jour

Deux raisons. Premièrement, l'installation de k3s est une opération de Jour-0 — elle s'exécute une fois par durée de vie du cluster. L'effort d'écrire et de tester un playbook l'emportait sur le coût de quatre commandes SSH. Deuxièmement, `swift-mac` ne peut pas démarrer en PXE, donc Ubuntu a été installé manuellement via USB de toute façon. Tant qu'une étape est manuelle, toute la séquence d'amorçage est de fait manuelle pour ce nœud.

Ce qui a été automatisé dès le premier jour, c'est la partie qui se répète réellement : `system-upgrade-controller` gère chaque futur bump de version k3s comme un seul commit YAML. Le playbook Ansible couvre le cas limite — reconstruire de zéro — qui vaut la peine d'être automatisé même s'il n'arrive qu'une ou deux fois dans la vie du cluster.

## La suite

Avec cinq nœuds exécutant k3s, la couche suivante est le réseau et l'équilibrage de charge : MetalLB pour les services `LoadBalancer` bare-metal, un contrôleur ingress wildcard, et une CA privée pour que chaque service interne obtienne un vrai TLS. C'est couvert dans le prochain article.

---

*Les runbooks complets de chaque phase, y compris les modèles cloud-init exacts utilisés pour le provisioning MAAS, se trouvent dans la section [Documentation](/platform-roadmap/roadmap-overview).*
