---
slug: high-availability-bare-metal-kubernetes
title: "Concevoir la haute disponibilité sur Kubernetes bare-metal — couche par couche"
authors: [andre]
description: >
  La HA sur un cluster k3s auto-géré n'est pas un seul réglage — ce sont six couches indépendantes,
  chacune avec un compromis concret. Cet article parcourt chaque couche de minicloud, ce qui a été
  validé par un chaos game day en conditions réelles, et comment les mêmes préoccupations se retrouvent
  sur EKS, GKE et AKS.
tags: [kubernetes, k3s, high-availability, bare-metal, platform-engineering, longhorn, argo-rollouts, nginx, metallb, chaos-engineering, eks, gke, aks]
date: 2026-07-28
image: /img/docusaurus-social-card.jpg
---

« Haute disponibilité » est l'un de ces termes dont tout le monde s'accorde à dire qu'il compte et que presque personne ne définit précisément. Sur un fournisseur Kubernetes managé, vous cochez une case pour le multi-AZ et vous passez à autre chose. Sur un cluster auto-géré, vous prenez six décisions d'architecture indépendantes, chacune avec son propre mode de défaillance, son compromis et son coût opérationnel.

Cet article documente chaque couche de HA sur **minicloud** — un cluster k3s de 5 nœuds sur des ThinkPads — explique le raisonnement derrière chaque compromis, et associe chaque couche à la façon dont EKS, GKE et AKS résolvent le même problème.

{/* truncate */}

## Le cluster

Cinq machines :

| Nœud | IP | Rôle |
|------|----|------|
| `set-hog` | 10.0.0.2 | plan de contrôle k3s (ThinkPad X390) |
| `fast-skunk` | 10.0.0.4 | worker |
| `fast-heron` | 10.0.0.7 | worker |
| `star-kitten` | 10.0.0.8 | worker |
| `swift-mac` | 10.0.0.10 | worker + stockage Longhorn (MacBook Pro 2012, Ubuntu 22.04) |

Chaque décision de HA ci-dessous a été prise pour ce contexte spécifique. Le raisonnement est transférable ; les chiffres ne le sont pas.

---

## Couche 1 — Plan de contrôle : délibérément mononœud

C'est la décision de HA la plus importante du cluster, et la réponse est : pas de HA sur cette couche.

`set-hog` exécute le serveur d'API k3s, le scheduler, le controller-manager et le datastore Kine/SQLite. C'est un seul ThinkPad. S'il plante, le plan de contrôle disparaît jusqu'à son redémarrage — environ 90 secondes.

**Ce qui se passe réellement quand le plan de contrôle tombe :**
- Les pods en cours sur les quatre workers **continuent de tourner**. kubelet est un processus local ; il n'a pas besoin du serveur d'API pour gérer les pods existants.
- Aucun nouvel ordonnancement. Aucun Deployment ne se déploie. Aucun ConfigMap ne se met à jour. Aucun secret ne tourne.
- La reprise est automatique quand `set-hog` redémarre et que k3s se lance.

**Pourquoi pas de plan de contrôle HA ?** La HA k3s nécessite `--cluster-init` sur le premier nœud serveur plus deux nœuds serveur supplémentaires avec `--server`. Cela bascule le datastore de Kine/SQLite vers etcd embarqué avec consensus Raft entre trois nœuds. Pour un cluster de 5 nœuds, trois machines en rôle plan de contrôle est un mauvais ratio — et la charge opérationnelle de gérer un cluster Raft est réelle. Étant donné que l'indisponibilité du plan de contrôle ne met pas à terre les workloads en cours et que la reprise prend 90 secondes, le compromis est clair.

**Ce que font les fournisseurs managés à la place :**
- **EKS :** serveur d'API répliqué sur plusieurs AZ. etcd est un cluster multi-AZ qu'AWS gère entièrement. Le plan de contrôle tombe → vous ne le remarquez jamais.
- **GKE :** même modèle. Le plan de contrôle est si opaque que GKE Standard ne le facture même pas séparément ; il fait partie du SLA du cluster.
- **AKS :** même modèle. Azure gère la HA du plan de contrôle ; vous ne payez que les VM des workers.

L'approche managée élimine entièrement ce mode de défaillance. Le coût sur EKS est de 0,10 $/h (73 $/mois) avant tout worker — rien que pour le plan de contrôle. Sur minicloud, `set-hog` tourne sur du matériel déjà possédé.

---

## Couche 2 — Workers : quatre nœuds, distribution inter-nœuds

Tous les pods de workload tournent sur quatre workers. Le scheduler k3s distribue les répliques par défaut avec la sémantique `PodTopologySpread` — les Deployments multi-répliques atterrissent sur des nœuds différents sans configuration explicite.

**L'exception swift-mac :** `swift-mac` est un MacBook Pro 2012. Il n'a ni IPMI, ni BMC, ni capacité de power-cycle à distance (le SMC d'Apple ne répond qu'aux pressions physiques de bouton). Si l'OS se fige, une intervention manuelle est requise. Les StatefulSets qui exigent une reprise automatisée garantie sont écartés de `swift-mac` via des règles d'affinité de nœud :

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: NotIn
              values: [swift-mac]
```

`swift-mac` exécute des workloads sans état et des répliques de stockage Longhorn (où il ajoute de la capacité, pas de la disponibilité en chemin critique).

**Ce que font les fournisseurs managés à la place :** les nœuds workers cloud sont des VM avec un contrôle d'alimentation complet au niveau hyperviseur. Si une instance AWS EC2 se fige, le groupe de nœuds la termine et la remplace automatiquement. L'auto-réparation de nœud est disponible sur GKE (par défaut sur Autopilot). Sur bare-metal, les nœuds figés requièrent une attention humaine.

---

## Couche 3 — Applications : répliques, PDB et Argo Rollouts

C'est là que réside l'essentiel du travail de HA. Les couches plan de contrôle et stockage définissent le plafond ; la couche applicative détermine si les workloads survivent réellement aux pannes sous ce plafond.

### Nombre de répliques

Les workloads de production tournent avec un minimum de 3 répliques, réparties sur les workers. Le chiffre 3 est délibéré : il tolère 1 panne de pod et continue de servir le trafic pendant que le remplaçant démarre. Avec 2 répliques, un kill de pod plus un démarrage lent vous laisse à 1 réplique — plus de redondance.

### PodDisruptionBudgets

Chaque workload de production a un PDB qui empêche Kubernetes d'évincer plus d'une réplique simultanément lors des perturbations volontaires (drains de nœud, mises à jour de cluster) :

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: platform-demo-pdb
spec:
  minAvailable: 2        # au moins 2 répliques doivent être Ready en permanence
  selector:
    matchLabels:
      app: platform-demo
```

Sans PDB, le drain de mise à jour k3s pourrait évincer les trois répliques d'un nœud simultanément, provoquant une brève interruption. Le PDB l'empêche — le drain attend qu'un remplaçant devienne Ready avant d'évincer le pod suivant.

### Argo Rollouts : déploiements sans interruption

Les Deployments Kubernetes classiques utilisent la stratégie `RollingUpdate`, qui offre une HA basique pendant les déploiements. Les services de production sur minicloud utilisent **Argo Rollouts** pour plus de contrôle :

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: platform-demo
spec:
  replicas: 3
  strategy:
    canary:
      stableService: platform-demo-stable
      canaryService: platform-demo-canary
      trafficRouting:
        nginx:
          stableIngress: platform-demo
      steps:
        - setWeight: 20      # envoyer 20% vers la nouvelle version
        - pause: {}          # attendre l'analyse
        - setWeight: 50
        - pause: {duration: 60s}
        - setWeight: 100
      analysis:
        templates:
          - templateName: success-rate
        startingStep: 1
        args:
          - name: service-name
            value: platform-demo-canary
```

La propriété de HA clé : le ReplicaSet stable reste entièrement en ligne tout au long du rollout. Une nouvelle version qui échoue à son analyse de taux de succès est automatiquement rétrogradée — le jeu stable absorbe tout le trafic, et le canary est démonté. Aucune intervention humaine nécessaire, aucune fenêtre d'interruption.

### Ce qu'a prouvé le Chaos Game Day de la Phase 81

En Phase 81, trois expériences de chaos ont été menées contre les workloads de production :

**Expérience 1 — Kill de pod (PodChaos) :**
- Tué 1 des 3 répliques `platform-demo`
- La surveillance des EndpointSlice de NGINX a exclu le pod avant la fin du kill
- Pod de remplacement : `Ready` en 16 secondes
- Disponibilité HTTP : **100 %** (mesurée, pas estimée)

**Expérience 2 — Latence de base de données (NetworkChaos) :**
- Délai artificiel de 200 ms sur le trafic `backstage → postgresql`
- Requêtes DB chemin froid : +200 ms de latence (attendu)
- Requêtes chemin cache : non affectées
- Backstage est resté fonctionnel tout du long

**Expérience 3 — Stress CPU (StressChaos) :**
- 2 workers à 80 % de charge sur les pods `platform-demo-staging`
- La limite CPU cgroup (200m) a bridé le stresseur — impact au niveau du nœud : zéro
- Latence HTTP p95 : restée dans le SLO

Ce sont des résultats mesurés sur de vrais workloads de production, pas des simulations sur des services de test jetables.

**Ce que font les fournisseurs managés à la place :** les fournisseurs cloud offrent nativement des stratégies de Deployment similaires (Deployment EKS, Rollout GKE), mais Argo Rollouts ajoute le contrôle de poids de trafic et la promotion conditionnée par métrique que les fournisseurs managés n'incluent pas d'emblée. Argo Rollouts fonctionne à l'identique sur EKS/GKE/AKS — c'est un motif au niveau workload, pas au niveau fournisseur.

---

## Couche 4 — Stockage : réplication Longhorn

La HA du stockage persistant est la couche la plus difficile à réussir sur bare-metal. Les fournisseurs cloud vous donnent EBS Multi-AZ (EKS), Persistent Disk (GKE) ou Azure Disk (AKS) — tous avec une réplication intégrée gérée par le backend de stockage.

Sur bare-metal, cette réplication est votre responsabilité. La réponse est **Longhorn** : un système de stockage bloc distribué cloud-native qui tourne entièrement à l'intérieur de Kubernetes.

### Comment fonctionne la réplication Longhorn

Chaque PVC Longhorn est configuré avec `numberOfReplicas: 2` (le défaut). Longhorn maintient deux copies de réplique des données du volume sur deux nœuds distincts :

```
PVC (16 Gi)
├── Réplique A → fast-heron  /var/lib/longhorn/replicas/...
└── Réplique B → star-kitten /var/lib/longhorn/replicas/...
```

Si `fast-heron` tombe, le volume se dégrade sur la Réplique B (saine). Kubernetes replanifie le pod vers un nœud où la Réplique B est accessible. Le volume revient en ligne. Aucune donnée n'est perdue.

Si `fast-heron` et `star-kitten` tombent simultanément, le volume est inaccessible. C'est le mode de défaillance que `numberOfReplicas: 2` accepte. Avec 4 workers, une double panne de nœud simultanée est considérée comme acceptable.

### swift-mac comme nœud de stockage

`swift-mac` a le plus grand disque disponible du cluster. Son stockage Longhorn est utilisé pour la capacité, mais toujours avec une réplique sur un worker ThinkPad — `swift-mac` n'est jamais le point unique de stockage d'un volume.

### HA Longhorn pendant les mises à jour

Pendant une mise à jour de nœud k3s, le Plan de mise à jour draine le nœud. Un nœud en cours de drain perd sa réplique Longhorn. Les volumes se dégradent temporairement à 1 réplique (toujours accessibles, mais sans redondance pendant le drain). C'est pourquoi les Plans de mise à jour tournent avec `concurrency: 1` — un seul nœud draine à la fois, réduisant la dégradation de réplique à une fenêtre minimale.

**Ce que font les fournisseurs managés à la place :**

| | Longhorn (bare-metal) | EBS (EKS) | Persistent Disk (GKE) | Azure Disk (AKS) |
|---|---|---|---|---|
| Réplication | Logicielle entre nœuds | Au niveau matériel dans l'AZ | Au niveau matériel, option multi-zone | Au niveau matériel dans l'AZ |
| Multi-AZ | Non (site unique) | EBS Multi-Attach (limité) | PD régional (disponible) | Disque redondant par zone (disponible) |
| Snapshot | Snapshots Longhorn vers MinIO/S3 | Snapshots EBS vers S3 | Snapshots Persistent Disk | Snapshots Azure Disk |
| Restauration | UI Longhorn ou PVC depuis snapshot | Restauration EBS vers nouveau volume | Restauration de volume GKE | Restauration AKS |
| Coût opérationnel | Vous gérez la santé des répliques, l'affinité de nœud, les plannings de sauvegarde | Nul — AWS le gère | Nul — Google le gère | Nul — Azure le gère |

L'histoire du stockage managé est convaincante : les disques des fournisseurs cloud répliquent au niveau matériel, entièrement sous Kubernetes. Les caractéristiques de performance sont garanties, la réplication est invisible, et les snapshots sont un seul appel d'API. Le compromis est le coût (0,10–0,20 $/Go/mois pour les SSD managés) et le fait d'être lié à l'abstraction de stockage du fournisseur.

---

## Couche 5 — Ingress et réseau : DaemonSet NGINX + MetalLB

### NGINX en DaemonSet

Le contrôleur ingress NGINX tourne en **DaemonSet** — un pod par nœud worker. Les quatre workers (`fast-skunk`, `fast-heron`, `star-kitten`, `swift-mac`) exécutent un pod NGINX à l'écoute du trafic.

```
Trafic externe → 10.0.0.200 (VIP MetalLB) → n'importe quel pod NGINX → pod cible
```

Si un worker tombe, son pod NGINX tombe avec lui — mais les pods NGINX des trois workers restants continuent de servir toutes les routes. La VIP se réannonce en quelques secondes.

### Bascule MetalLB niveau 2

MetalLB en mode L2 assigne `10.0.0.200` comme VIP du cluster. En mode L2, un nœud « possède » la VIP à un instant donné et répond aux requêtes ARP pour cette IP. Le nœud propriétaire est élu par les pods speaker de MetalLB.

Si le nœud propriétaire tombe :
1. Le cache ARP du routeur expire (typiquement 30–60 secondes, configurable)
2. Les speakers MetalLB élisent un nouveau propriétaire parmi les nœuds sains restants
3. Le nouveau propriétaire commence à répondre à l'ARP pour `10.0.0.200`
4. Le trafic reprend

Temps de bascule en pratique : moins de 30 secondes. C'est le maillon de HA le plus faible de la couche réseau — l'expiration du cache ARP est le goulot d'étranglement. Le mode BGP (MetalLB le supporte) donnerait une bascule sous la seconde, mais requiert un routeur compatible BGP.

### Surveillances EndpointSlice de NGINX

NGINX surveille les objets EndpointSlice pour chaque Service. Quand un pod est tué (lors d'expériences de chaos, d'évictions de pod ou de mises à jour), Kubernetes met à jour l'EndpointSlice avant que le pod ne se termine. NGINX retire le pod de son pool amont avant que le moindre trafic ne l'atteigne.

C'est pourquoi l'expérience de kill de pod de la Phase 81 a montré 100 % de disponibilité HTTP : NGINX avait déjà cessé de router vers le pod tué au moment où le signal de kill est arrivé.

### Cloudflare Tunnel : HA publique

Les services publics (`backstage.devandre.sbs`, `homer.devandre.sbs`, etc.) passent par un Cloudflare Tunnel tournant en systemd sur le contrôleur. Le réseau de Cloudflare gère l'équilibrage de charge global et la protection DDoS en amont du cluster. Le tunnel lui-même est un point unique de défaillance sur le contrôleur — mais :

- `cloudflared` tourne avec `Restart=always` et `StartLimitIntervalSec=0`
- Les redémarrages du contrôleur récupèrent le tunnel automatiquement
- La périphérie de Cloudflare met en cache les réponses récentes, absorbant les brèves interruptions du tunnel pour le contenu statique

**Ce que font les fournisseurs managés à la place :**

- **EKS :** l'AWS Load Balancer Controller provisionne des ALB directement depuis les objets Ingress. Multi-AZ, auto-scaling, terminaison TLS native au niveau du load balancer. La complexité MetalLB et DaemonSet NGINX disparaît.
- **GKE :** l'Ingress GKE provisionne un Google Cloud Load Balancer. Équilibrage HTTP(S) global, IP Anycast, intégration WAF Cloud Armor — le tout depuis une seule annotation Ingress.
- **AKS :** Azure Load Balancer ou Application Gateway via le contrôleur AGIC. Modèle comparable à GKE.

L'approche managée déplace l'équilibrage de charge entièrement hors de Kubernetes — le load balancer lui-même a une HA de niveau fournisseur, pas de niveau pod. Le compromis est le coût (tarif ALB, tarif GLB) et le verrouillage fournisseur sur la couche load balancer.

---

## Couche 6 — Observabilité : la HA de la pile HA

Une architecture HA que vous ne pouvez pas observer n'est pas une architecture HA — c'est une supposition. La pile d'observabilité est ce qui transforme les couches ci-dessus en quelque chose de mesurable.

**Ce qui tourne :**
- **Prometheus + Grafana :** SLO du cluster et des applications, dashboards de ressources des nœuds, alerte personnalisée `ChaosGameDayActive`
- **Loki :** agrégation de logs des 5 nœuds via OTel Collector (DaemonSet), avec Promtail comme agent de collecte
- **Tempo :** traçage distribué pour les services instrumentés (platform-demo, backstage)
- **AlertManager :** route les alertes vers les canaux de notification avec des règles d'inhibition pour supprimer les faux positifs connus pendant les tests de chaos

**La règle d'inhibition qui rend les tests de chaos honnêtes :**

```yaml
inhibit_rules:
  - source_matchers: ['alertname = "ChaosGameDayActive"']
    target_matchers: ['alertname =~ "KubePodCrashLooping|KubePodNotReady"']
```

Quand une expérience de chaos tourne, `ChaosGameDayActive` se déclenche (les métriques du contrôleur de chaos montrent `status=Injecting`). Cela inhibe les alertes `KubePodCrashLooping` et `KubePodNotReady` — pour que les kills de pod intentionnels n'inondent pas Slack de fausses alertes. Quand l'expérience se termine, l'inhibition se lève et l'alerting reprend son fonctionnement normal.

**Ce que font les fournisseurs managés à la place :**
- EKS : CloudWatch Container Insights, métriques d'add-on EKS, AWS Managed Grafana (payant)
- GKE : Cloud Monitoring avec intégration GKE, Cloud Logging
- AKS : Azure Monitor for Containers, workspace Log Analytics

L'observabilité managée est plus rapide à démarrer (quelques clics vs. charts helm et ServiceMonitors) mais moins flexible — vous ne pouvez pas ajouter de règles Prometheus personnalisées ni ajuster la logique d'inhibition d'alerte sans contournements significatifs. Sur bare-metal, vous possédez tout le pipeline d'observabilité : plus de travail, contrôle total.

---

## La carte complète de la HA

| Couche | Décision minicloud | Mode de défaillance accepté | Équivalent fournisseur managé |
|---|---|---|---|
| **Plan de contrôle** | `set-hog` unique | Interruption d'ordonnancement de 90s au redémarrage | Multi-AZ, géré par le fournisseur, invisible |
| **Datastore** | Kine/SQLite, sauvegarde nocturne | RPO ~23h | etcd avec réplication sous la minute |
| **Workers** | 4 nœuds, `swift-mac` isolé pour les StatefulSets | Figement de `swift-mac` = reprise manuelle | Auto-réparation, contrôle d'alimentation au niveau VM |
| **Pods** | 3 répliques, PDB, canary Argo Rollouts | — | Mêmes motifs sur k8s managé |
| **Stockage** | Volumes Longhorn 2 répliques | Perte de double nœud = volume inaccessible | Disque fournisseur avec réplication matérielle |
| **Ingress** | DaemonSet NGINX + MetalLB L2 | Expiration cache ARP = bascule VIP ~30s | ALB/GLB fournisseur, bascule sous la seconde |
| **Observabilité** | Prometheus + Loki + Tempo + AlertManager | Vous exploitez la pile | CloudWatch / Cloud Monitoring managé |

---

## Ce que cela enseigne et que le Kubernetes managé n'enseigne pas

Exploiter la HA sur bare-metal vous force à comprendre chaque couche indépendamment, car chacune peut défaillir indépendamment.

Sur EKS, vous fixez `--node-count 3` et obtenez d'un coup la redondance des workers, la réplication du stockage, la bascule du load balancer et la HA du plan de contrôle — depuis un seul appel d'API. Le système fonctionne, les modes de défaillance sont rares, et vous n'avez jamais à penser à l'expiration du cache ARP de MetalLB ni au nombre de répliques Longhorn pendant les drains de nœud.

Ce que vous perdez : le modèle mental du *pourquoi* ça marche. Quand quelque chose tourne mal sur un cluster managé — et ça arrive — les ingénieurs qui ne connaissent que le chemin « cocher la case HA » peinent à diagnostiquer si la panne est à la couche plan de contrôle, à la couche stockage ou à la couche réseau.

Sur bare-metal, vous ne pouvez pas éviter de construire ce modèle mental. Les six couches ci-dessus ne sont pas des abstractions. Ce sont des décisions que j'ai prises, configurées, testées avec des expériences de chaos en conditions réelles, et documentées. Chacune correspond directement à un concept qui apparaît dans les incidents de Kubernetes managé en production.

Le même Argo Rollout qui protège les déploiements de production sur minicloud fonctionne à l'identique sur EKS. Le même PDB qui empêche le drain de mise à jour k3s d'évincer toutes les répliques fonctionne à l'identique sur GKE. La même règle d'inhibition Prometheus qui supprime les fausses alertes pendant les tests de chaos fonctionne à l'identique sur AKS.

La différence, c'est que sur bare-metal, vous ne pouvez pas sauter la compréhension pour arriver au résultat.
