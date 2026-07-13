---
slug: platform-engineering-bare-metal-kubernetes
title: "L'ingénierie de plateforme sans budget illimité : Kubernetes en production sur 5 ThinkPads"
authors: [andre]
description: >
  Comment j'ai construit une plateforme Kubernetes de qualité production sur cinq ThinkPads bare-metal —
  avec provisioning MAAS, GitOps, SSO, observabilité et services IA — et ce que j'ai appris
  sur l'ingénierie de plateforme réelle en chemin.
tags: [kubernetes, platform-engineering, devops, k3s, gitops, bare-metal]
date: 2026-07-13
image: /img/docusaurus-social-card.jpg
---

La plupart des plateformes cloud vous cachent l'infrastructure. Provisioning MAAS, séquences de boot PXE, agrégation de cartes réseau, backends de stockage, chaînes de certificats — tout est abstrait derrière quelques flags CLI ou un tableau de bord. Cette abstraction a de la valeur en production, mais elle peut aussi tenir les ingénieurs à distance des systèmes qu'ils sont censés comprendre en profondeur.

Ce projet est né d'une question simple : **qu'est-ce qu'il faut vraiment pour construire une plateforme Kubernetes de qualité production from scratch ?**

{/* truncate */}

## La configuration

Le matériel : cinq laptops. Quatre Lenovo ThinkPad X390 servent de nœuds de cluster, et un MacBook Pro 2012 fonctionne comme worker de stockage. Un cinquième ThinkPad X390 fait office de contrôleur MAAS — gérant le boot PXE, le DHCP, le DNS et le NAT Tailscale pour toute la baie. Coût total : bien en dessous de la facture mensuelle d'un cloud provider pour une puissance de calcul équivalente.

```
Contrôleur (MAAS) :  ktayl-ThinkPad-X390  — endpoint Tailscale, NAT, kubectl
Plan de contrôle :   set-hog              — master k3s, 10.0.0.2
Workers :            fast-skunk           — 10.0.0.4
                     fast-heron           — 10.0.0.7
                     star-kitten          — 10.0.0.8
                     swift-mac            — 10.0.0.10 (MacBook Pro 2012, stockage Longhorn)
```

Chaque nœud est provisionné par MAAS via PXE : le contrôleur diffuse une offre de boot, les nœuds la récupèrent, et Ubuntu 22.04 est déployé avec un cloud-init pré-configuré. N'importe quel nœud peut être effacé et re-provisionné en moins de 10 minutes — la même discipline qu'on appliquerait dans un vrai service bare-metal d'un cloud provider.

## Ce que "qualité production" signifie concrètement

Faire tourner un home lab, c'est facile. Le faire tourner comme une équipe plateforme ferait tourner la production, c'est une tout autre discipline. Les contraintes que je me suis imposées :

- **Pas de `kubectl apply` manuel** — toutes les charges de travail vivent dans Git et se synchronisent via ArgoCD (pattern app-of-apps, Kustomize base+overlays, flux de promotion CI à 3 branches)
- **Réseau zero-trust** — politiques d'admission OPA Gatekeeper en mode deny sur les 23 namespaces, NetworkPolicy appliquée partout, Vault auto-unseal via AWS KMS
- **Observabilité dès le départ** — Prometheus + Grafana + Loki + Tempo déployés avant toute charge applicative ; node_exporter sur le contrôleur lui-même pour que les alertes disque se déclenchent avant que MinIO ne crashe
- **SSO OIDC sur chaque service** — Authentik comme fournisseur d'identité, OIDC/PKCE protégeant ArgoCD, Grafana, Harbor, Backstage, Open WebUI et Vaultwarden
- **Tests de régression automatisés** — 62 vérifications couvrant infra, GitOps, sécurité, stockage, IA et observabilité, exécutées après chaque changement significatif

## Ce qui m'a surpris

**Le stockage est la partie la plus difficile du bare-metal.** Longhorn sur le MacBook Pro 2012 (swift-mac) a nécessité un réglage manuel du mount propagation, du nombre de réplicas et des tolérances de scheduling. Quand le nœud tombe inopinément — et ça arrive, parce que le SMC d'Apple ne supporte pas Wake-on-AC — la récupération des réplicas Longhorn a besoin d'une marge que l'on ne comprend vraiment qu'après l'avoir vu échouer deux fois.

**Les chaînes de certificats cassent de manière non évidente.** Je fais tourner une CA privée (`minicloud-ca.crt`) pour tous les endpoints HTTPS internes. Le Keychain système macOS lui fait confiance, mais `/opt/anaconda3/bin/curl` utilise OpenSSL et l'ignore silencieusement. Deux heures de débogage d'un échec de push vers Harbor m'ont appris à toujours vérifier quel binaire `curl` est dans le `$PATH`.

**GitOps et la synchronisation des StatefulSets ArgoCD ont des cas limites.** Quand le `VolumeClaimTemplate` d'un StatefulSet est défini sans `apiVersion`, `kind` et `volumeMode` explicites, ArgoCD v3.4.1 affiche en permanence un diff — même après synchronisation. La correction consiste à écrire le spec complet dans le manifeste ; `ignoreDifferences` ne fonctionne pas pour ces champs.

**Les timeouts de backup Velero doivent être ajustés par charge de travail.** Le `itemOperationTimeout` par défaut de 4 heures du plugin kopia de Velero n'était pas suffisant pour un PV ClickHouse de 4,5 Go (données de traces LLM Langfuse). Kopia avait transféré ~2,5 Go et le backup a été annulé. Passer à 8 heures a résolu le problème — mais la leçon est que les SLO de backup dépendent de la taille des données, pas seulement de la configuration de l'infrastructure.

## Ce qui tourne aujourd'hui

Après plus de 35 phases de construction incrémentale, la plateforme actuelle fait tourner :

| Service | Objectif |
|---|---|
| ArgoCD | Livraison GitOps — 8 dépôts applicatifs custom, 23 namespaces |
| Harbor | Registry de conteneurs privée avec signature d'images cosign |
| Backstage | Portail développeur interne avec catalogue, TechDocs, scaffolder |
| Authentik | Fournisseur d'identité OIDC/SSO |
| Grafana + Prometheus | Métriques, tableaux de bord, alerting |
| Loki + Tempo | Agrégation de logs et tracing distribué |
| Vault | Gestion des secrets avec auth Kubernetes |
| Longhorn | Stockage bloc distribué sur le cluster |
| Open WebUI + Ollama | Chat LLM auto-hébergé avec modèles locaux |
| Pipeline RAG | Ingestion de documents → découpage → embeddings → pgvector |
| Velero | Backups planifiés vers MinIO (quotidien, TTL 7 jours) |
| Vaultwarden | Gestionnaire de mots de passe auto-hébergé avec SSO |
| Cloudflare Tunnel | Accès HTTPS public sans port-forwarding |

Tout est accessible publiquement sur `*.devandre.sbs` via Cloudflare Tunnel, protégé par Authentik SSO.

## Pourquoi ça compte pour un ingénieur

L'objectif n'a jamais été de faire tourner Kubernetes à la maison pour le plaisir. L'objectif était de développer le type d'instinct plateforme qui ne vient qu'en opérant une infrastructure à travers les pannes : le disque se remplit et MinIO reste bloqué en mémoire sans alerte ; le SMC d'un nœud ne répond pas au WoL et un cron job doit compenser ; un job de mise à jour de CRD Velero ne renseigne jamais `status.succeeded` à cause d'un bug du contrôleur Job de k3s.

Ces incidents — et leurs corrections — c'est ce à quoi ressemble vraiment l'ingénierie de plateforme sous les abstractions. Les prochains articles de cette série iront plus en profondeur sur des composants spécifiques : l'architecture du pipeline RAG, le workflow de promotion GitOps et l'ensemble de politiques OPA Gatekeeper.

---

*Les runbooks complets pour chaque phase se trouvent dans la section [Documentation](/platform-roadmap/roadmap-overview) de ce site.*
