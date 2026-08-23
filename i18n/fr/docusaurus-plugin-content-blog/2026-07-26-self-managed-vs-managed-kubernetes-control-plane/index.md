---
slug: self-managed-vs-managed-kubernetes-control-plane
title: "Kubernetes auto-géré vs managé : à quoi ressemble vraiment l'exploitation de son propre plan de contrôle"
authors: [andre]
description: >
  Une comparaison concrète entre l'exploitation d'un plan de contrôle k3s sur un ThinkPad et EKS/GKE/AKS —
  ancrée dans un vrai cluster bare-metal, pas dans la théorie. Ce que vous possédez, ce qui casse, et ce que vous apprenez.
tags: [kubernetes, k3s, bare-metal, platform-engineering, devops, control-plane, eks, gke]
date: 2026-07-26
image: /img/docusaurus-social-card.jpg
---

La plupart des comparatifs Kubernetes sont écrits par des gens qui n'ont utilisé que des services managés. Celui-ci est écrit par quelqu'un qui a un ThinkPad nommé `set-hog` posé sur un bureau, en train de faire tourner le serveur d'API en ce moment même.

Voici à quoi ressemble vraiment l'auto-gestion d'un plan de contrôle Kubernetes — comparé ligne par ligne à EKS, GKE et AKS.

{/* truncate */}

## Le décor

Le cluster est **minicloud** : cinq machines, toutes bare-metal, exécutant k3s v1.36.2+k3s1 sur Ubuntu 22.04.

| Nœud | IP | Rôle |
|------|----|------|
| set-hog | 10.0.0.2 | **plan de contrôle k3s** |
| fast-skunk | 10.0.0.4 | worker k3s |
| fast-heron | 10.0.0.7 | worker k3s |
| star-kitten | 10.0.0.8 | worker k3s |
| swift-mac | 10.0.0.10 | worker k3s (MacBook Pro 2012) |

`set-hog` est l'endroit où tournent le serveur d'API, le scheduler et le controller-manager. C'est un ThinkPad. Il est sur un bureau. Quand il tombe, plus aucun pod n'est ordonnancé — exactement ce contre quoi la documentation des clouds managés vous met en garde quand vous lisez les schémas d'architecture qu'ils publient mais n'ont pas à exploiter eux-mêmes.

## Le comparatif

| Aspect | minicloud (auto-géré) | Managé (EKS / GKE / AKS) |
|--------|--------------------------|---------------------------|
| **Où ça tourne** | ThinkPad physique sur votre bureau (`set-hog`) | Infrastructure du fournisseur cloud, cachée |
| **Qui l'installe** | Vous avez lancé `k3s server` via Ansible | Le fournisseur s'en charge — un simple `terraform apply` |
| **HA / redondance** | Plan de contrôle mononœud — si `set-hog` meurt, plus d'ordonnancement jusqu'à sa reprise | Réplicas etcd + serveur d'API multi-AZ, SLA fournisseur 99,9 %+ |
| **etcd** | Kine/SQLite (remplacement léger de k3s — pas de `--cluster-init`) | Vrai cluster etcd, géré et sauvegardé par le fournisseur |
| **Serveur d'API** | Exposé sur `set-hog`, accédé via Tailscale | Exposé sur un endpoint fournisseur (p. ex. `*.eks.amazonaws.com`) |
| **Accès kubectl** | Contexte `minicloud-oidc` via Tailscale → `set-hog` | Intégration IAM/OIDC, pas de VPN nécessaire |
| **Accès break-glass** | Contexte `minicloud-break-glass` (certificat statique, urgence uniquement) | Console fournisseur / rôles IAM d'urgence |
| **Mises à jour** | Plans system-upgrade-controller : le Plan serveur d'abord (cordon), puis le Plan agent, vous fixez la version cible | Bouton fournisseur ou mise à jour auto, ils gèrent la migration etcd |
| **Métriques scheduler + ctrl-mgr** | DaemonSet socat sur `set-hog` proxifiant `:10259 → :10269` et `:10257 → :10267` car k3s les lie uniquement à `127.0.0.1` | Le fournisseur les expose nativement, ou pas du tout (opaque) |
| **Durcissement CIS** | kube-bench k3s-CIS-1.7 appliqué manuellement via Ansible — **16/16 PASS** sur tous les workers | Le fournisseur gère la plupart des contrôles CIS par défaut |
| **Coût** | Électricité + matériel (déjà possédé) | 70–150 $/mois par cluster rien que pour le plan de contrôle (EKS : 0,10 $/h) |
| **Impact d'une panne** | Crash de `set-hog` → serveur d'API HS → plus d'ordonnancement (les pods en cours continuent) | Le fournisseur restaure automatiquement, généralement invisible |

## Ce dont personne ne parle : les métriques du scheduler

Sur tout cluster Kubernetes managé, vous pouvez scraper directement les métriques du scheduler et du controller-manager depuis l'intégration de supervision du fournisseur. Sur k3s, ces deux composants se lient uniquement à `127.0.0.1` — la boucle locale, non joignable depuis Prometheus.

Le correctif est un DaemonSet socat épinglé sur `set-hog` avec `hostNetwork: true` :

```yaml
# proxy scheduler : 127.0.0.1:10259 → 0.0.0.0:10269
socat TCP-LISTEN:10269,fork TCP:127.0.0.1:10259

# proxy controller-manager : 127.0.0.1:10257 → 0.0.0.0:10267
socat TCP-LISTEN:10267,fork TCP:127.0.0.1:10257
```

Deux Services Kubernetes pointent vers les pods socat. Deux ServiceMonitors avec `scheme: https` et `insecureSkipVerify: true` disent à Prometheus de les scraper. Résultat : 60 séries de scheduler et 93 séries de workqueue du controller-manager, exactement ce que vous voyez dans le dashboard Grafana « Kubernetes / Scheduler ».

Sur EKS, vous cliquez sur « activer les logs du plan de contrôle » et CloudWatch fait le reste. Sur k3s bare-metal, vous apprenez à quoi sert socat.

## Ce que vous possédez vraiment vs ce que possède le fournisseur

```
Auto-géré (votre responsabilité)         Managé (responsabilité du fournisseur)
────────────────────────────────────    ──────────────────────────────────────
Installation + config initiale k3s       Provisionné automatiquement
Durcissement CIS kubelet (Ansible)       Appliqué par défaut
Plans system-upgrade-controller          Mise à jour en un clic dans la console
Proxy socat pour métriques plan-contrôle Métriques exposées nativement
Ordre de boot : contrôleur d'abord (30s) Toujours disponible, aucune dépendance
  puis nœuds (2 min), puis Tailscale        d'ordre
Restauration NAT iptables après coupure  Le réseau fournisseur ne casse jamais
  de courant (iptables-restore manuel)      au redémarrage
Gestion des certificats break-glass      Rôles IAM d'urgence
Root CA minicloud + PKI cert-manager     CA du fournisseur, pas la vôtre
```

### Le problème de l'ordre de boot

Le Kubernetes managé n'a pas d'ordre de boot. Votre cluster, si.

Après une coupure de courant totale, la séquence de redémarrage correcte est :

1. **Contrôleur MAAS** (ThinkPad X390, le routeur NAT pour `10.0.0.0/24`) — attendre 30 secondes
2. **Nœuds du cluster** — attendre 2 minutes que k3s démarre
3. **Tailscale sur le Mac** — ensuite `kubectl` refonctionne

Sautez l'étape 1 et les nœuds du cluster ne peuvent pas joindre internet. Les nœuds démarrent, k3s se lance, ArgoCD tente de se synchroniser depuis GitHub, et chaque repo-server reçoit `context deadline exceeded`. La raison : le contrôleur exécute le NAT (`MASQUERADE` via iptables pour `10.0.0.0/24`), et après un redémarrage, `netfilter-persistent` ne restaure pas les règles car son unité systemd est un lien symbolique cassé.

La procédure de reprise :

```bash
sudo sh -c 'iptables-restore < /etc/iptables/rules.v4'
sudo iptables -I FORWARD -s 10.0.0.0/24 -j ACCEPT
sudo iptables -I FORWARD -d 10.0.0.0/24 -j ACCEPT
sudo iptables -I FORWARD -s 10.42.0.0/16 -j ACCEPT
sudo iptables -I FORWARD -d 10.42.0.0/16 -j ACCEPT
```

EKS n'a pas ce problème. Mais les ingénieurs EKS ne savent pas non plus ce que font ces commandes.

## La différence etcd

Le Kubernetes standard utilise etcd comme magasin de stockage — un magasin clé-valeur distribué tournant en cluster de 3 ou 5 nœuds, avec consensus Raft.

k3s remplace etcd par **Kine** — une couche de traduction qui parle l'API etcd mais écrit dans SQLite sous le capot. SQLite est un fichier unique sur le disque de `set-hog`. Pas de cluster, pas de Raft, pas de quorum. Si le disque tombe, l'état du cluster est perdu.

Côté sauvegarde : Velero sauvegarde les objets Kubernetes (mais pas directement le fichier etcd/SQLite). Pour un vrai cluster de production, c'est l'écart le plus significatif par rapport au Kubernetes managé.

Pour un homelab et un projet de portfolio, SQLite convient. Mais il vaut la peine de savoir ce à quoi vous avez renoncé.

## Mettre à jour le plan de contrôle

Sur EKS, mettre à jour le plan de contrôle est un clic ou un changement de ressource Terraform. Le fournisseur gère la migration etcd, le redémarrage du serveur d'API et la matrice de compatibilité.

Sur k3s bare-metal, les mises à jour passent par **system-upgrade-controller** via des Plans :

```yaml
# Plan serveur (s'exécute en premier, concurrency 1, cordon le nœud)
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: k3s-server
spec:
  version: v1.36.2+k3s1
  nodeSelector:
    matchLabels:
      node-role.kubernetes.io/control-plane: "true"
  concurrency: 1
  cordon: true
  upgrade:
    image: rancher/k3s-upgrade

---
# Plan agent (attend la fin du Plan serveur)
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: k3s-agent
spec:
  version: v1.36.2+k3s1
  prepare:
    image: rancher/k3s-upgrade
    args: ["prepare", "k3s-server"]
  nodeSelector:
    matchLabels:
      kubernetes.io/os: linux
```

Le cluster est passé de v1.30 à v1.36.2 de cette façon — les 5 nœuds, zéro interruption sur les workloads, un seul commit dans le dépôt gitops.

## Le benchmark CIS

Les fournisseurs managés gèrent la plupart du CIS Kubernetes Benchmark par défaut. Ils configurent les flags du serveur d'API, verrouillent le kubelet et imposent des valeurs par défaut sécurisées.

Sur k3s bare-metal, vous le faites vous-même. La configuration kubelet de chaque nœud est déployée via Ansible :

```yaml
# /var/lib/kubelet/config.yaml (déployé par cis-kubelet-hardening.yml)
protectKernelDefaults: true
eventRecordQPS: 0
rotateCertificates: true
serverTLSBootstrap: true
tlsCipherSuites:
  - TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256
  - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
```

En lançant `kube-bench` contre le profil k3s-CIS-1.7 après avoir appliqué le playbook :

```
== Summary node ==
16 checks PASS
0 checks FAIL
0 checks WARN
```

Sur un cluster managé, vous ne voyez jamais cette sortie. Le fournisseur l'a exécutée pour vous avant même que vous ne provisionniez le premier nœud.

## Le vrai compromis

**Ce que vous gagnez en auto-géré :**
- Pleine appropriation opérationnelle — vous comprenez chaque composant parce que vous l'avez installé
- Coût de plan de contrôle nul (EKS facture 0,10 $/h ≈ 73 $/mois rien que pour le plan de contrôle)
- Capacité d'air-gap — le cluster fonctionne sans internet si nécessaire
- Votre propre PKI — root CA minicloud reconnue dans l'OS, le navigateur et chaque service
- La capacité d'expliquer la différence entre le serveur d'API et le scheduler en entretien, parce que vous avez débogué les deux

**Ce que vous cédez :**
- Plan de contrôle HA — une seule panne de disque de `set-hog` met fin au cluster
- Les sauvegardes etcd managées
- Les ~2 heures passées après une coupure de courant à restaurer les règles iptables et à attendre le retour de `set-hog` avant que `kubectl` refonctionne

## Pourquoi c'est important pour les postes de Platform Engineering

Quand vous vous retrouverez devant un cluster Kubernetes managé au travail — et cela arrivera, car EKS est le défaut partout — vous comprendrez ce que le fournisseur fait pour vous au lieu de le traiter comme de la magie.

Vous saurez :
- Ce qu'est Kine/SQLite, et pourquoi la vraie production utilise etcd
- Pourquoi l'endpoint de métriques du scheduler est sur `127.0.0.1` et comment l'exposer
- Ce que fait `iptables-restore` et pourquoi le NAT compte pour le réseau des pods
- Ce que le durcissement CIS configure réellement, pas seulement qu'il devrait être activé
- Ce que signifie l'accès break-glass et pourquoi il faut le séparer de l'OIDC

Pouvoir dire « j'ai exploité le plan de contrôle moi-même » n'est pas une histoire de homelab. C'est une histoire de profondeur de compréhension — celle qui vient de l'avoir cassé, réparé, et compris pourquoi.

---

*minicloud est un projet continu de plateforme Kubernetes bare-metal. L'architecture complète, les runbooks et la documentation phase par phase sont sur [andrelair-platform.github.io/minicloud-platform-docs](https://andrelair-platform.github.io/minicloud-platform-docs).*
