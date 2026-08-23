---
slug: kubernetes-upgrades-self-managed-vs-managed
title: "Mises à jour Kubernetes : ce que les fournisseurs managés gèrent pour vous et ce que vous possédez vous-même"
authors: [andre]
description: >
  Un regard concret sur la mise à jour de Kubernetes — comparant les mises à jour en un clic d'EKS, GKE et AKS
  aux Plans system-upgrade-controller et à l'automatisation GitHub Actions que j'ai construits pour mon
  cluster k3s bare-metal de 5 nœuds. Chaque décision documentée, chaque piège inclus.
tags: [kubernetes, k3s, upgrades, platform-engineering, devops, eks, gke, aks, system-upgrade-controller, gitops]
date: 2026-07-28
image: /img/docusaurus-social-card.jpg
---

Une mise à jour Kubernetes n'est jamais un simple changement de numéro de version. Il y a un drain de nœud, un échange de binaire, une migration de plan de contrôle, une séquence d'éviction de pods, et — si vous êtes en bare-metal — personne à appeler quand ça tourne mal.

Les fournisseurs Kubernetes managés gèrent l'essentiel de cela pour vous. Les clusters auto-gérés vous font tout posséder. Cet article documente les deux côtés concrètement : ce qu'EKS, GKE et AKS font réellement lors d'une mise à jour, et ce que j'ai construit pour automatiser le même processus sur mon cluster k3s de 5 nœuds tournant sur des ThinkPads.

{/* truncate */}

## Le décor

**minicloud** est un cluster k3s de 5 nœuds sur Ubuntu 22.04 bare-metal :

| Nœud | IP | Rôle |
|------|----|------|
| `set-hog` | 10.0.0.2 | plan de contrôle k3s (ThinkPad X390) |
| `fast-skunk` | 10.0.0.4 | worker |
| `fast-heron` | 10.0.0.7 | worker |
| `star-kitten` | 10.0.0.8 | worker |
| `swift-mac` | 10.0.0.10 | worker (MacBook Pro 2012, Ubuntu 22.04) |

k3s remplace etcd par Kine/SQLite sur `set-hog`. Pas de cloud. Pas de plan de contrôle managé. Quand `set-hog` doit être mis à jour, je possède le séquencement, le drain et la reprise.

---

## Comment le Kubernetes managé gère les mises à jour

### EKS (Amazon)

EKS scinde la mise à jour en deux étapes indépendantes, et cette scission est intentionnelle.

**La mise à jour du plan de contrôle** est un appel d'API :
```bash
aws eks update-cluster-version \
  --name my-cluster \
  --kubernetes-version 1.31
```

AWS gère la migration etcd, remplace les pods du serveur d'API sur plusieurs AZ, et gère la transition de l'ancienne version à la nouvelle sans interruption côté plan de contrôle. Vous ne voyez jamais les machines sur lesquelles il tourne.

**La mise à jour du groupe de nœuds** est séparée. Les groupes de nœuds managés font un remplacement progressif : une nouvelle instance EC2 démarre avec la nouvelle AMI, s'enregistre, l'ancien nœud est cordonné et drainé, puis terminé. Vous pouvez régler le nombre max de nœuds indisponibles. Les groupes de nœuds spot demandent plus de soin — la course éviction + remplacement peut vous laisser brièvement en sous-capacité.

L'auto-mise à jour EKS existe (`enableAutoUpgrade`) mais la plupart des équipes de production la désactivent et gèrent les mises à jour sur un planning de maintenance. La raison : la compatibilité des add-ons. Les clusters EKS portent VPC CNI, kube-proxy et CoreDNS comme add-ons managés, chacun avec son propre chemin de mise à jour à séquencer avec la version du plan de contrôle. AWS vous avertit du décalage de version mais ne bloquera pas une mise à jour qui le crée.

**Ce que vous possédez encore sur EKS :** les mises à jour d'add-ons (VPC CNI, CoreDNS, kube-proxy), la conception des PodDisruptionBudget, la tolérance au drain des workloads, la validation post-mise à jour.

### GKE (Google)

Le modèle de mise à jour de GKE est le plus automatisé des trois. Les **canaux de release** (Rapid, Regular, Stable) gèrent les mises à jour automatiquement sur un planning aligné aux releases Kubernetes amont — typiquement 2–4 semaines après qu'une release atteint l'amont.

Quand GKE met à jour un pool de nœuds, il utilise par défaut des **surge upgrades** : il provisionne un nœud supplémentaire avant de drainer l'ancien, pour maintenir la pleine capacité tout du long. Le nombre de nœuds surge et le max indisponible sont réglables via `--max-surge` et `--max-unavailable`.

GKE a aussi des **fenêtres de maintenance** — vous définissez une plage horaire où les mises à jour automatiques sont autorisées. Pour les clusters de production, c'est ainsi que les équipes empêchent le churn de nœuds inattendu pendant les heures de bureau.

La mise à jour du plan de contrôle sur GKE est totalement opaque. Google la gère, elle est couverte par leur SLA, et vous ne pouvez pas observer les étapes individuelles. Pour la plupart des équipes, c'est une fonctionnalité, pas un manque.

**Ce que vous possédez encore sur GKE :** la configuration de la fenêtre de maintenance, les définitions de PDB, s'assurer que les workloads tolèrent l'éviction, valider le comportement des add-ons sur les nouvelles versions mineures.

### AKS (Azure)

Les mises à jour AKS sont les plus proches du manuel parmi les trois options managées. Pas de mise à jour automatique par défaut — vous la planifiez :

```bash
az aks upgrade \
  --resource-group my-rg \
  --name my-cluster \
  --kubernetes-version 1.31.0
```

AKS effectue une mise à jour progressive : le plan de contrôle d'abord, puis les pools de nœuds un nœud surge à la fois. Comme GKE, AKS utilise une approche de nœud surge — il provisionne un nouveau nœud, déplace les workloads, puis retire l'ancien nœud.

AKS supporte aussi les **mises à jour d'image de nœud** séparément des mises à jour de version Kubernetes. Vous pouvez mettre à jour l'image OS (correctifs noyau, versions containerd) sans changer la version mineure Kubernetes — utile pour le patch de CVE entre mises à jour.

**Ce que vous possédez encore sur AKS :** déclencher les mises à jour (ou configurer les politiques d'auto-mise à jour), la conception des PDB, le séquencement des pools de nœuds si vous en avez plusieurs avec des taints différents.

### Le motif commun

Les trois fournisseurs partagent la même séquence de mise à jour sous le capot :

1. Mettre à jour le plan de contrôle (invisible pour vous, géré par le fournisseur)
2. Pour chaque nœud worker : cordon → drain → remplacer le binaire ou l'AMI → uncordon
3. Vérifier la readiness du nœud avant de passer au suivant

Ce qu'ils retirent de votre assiette : gérer la migration des données etcd, séquencer la version du serveur d'API entre les réplicas, gérer la fenêtre d'indisponibilité du plan de contrôle, et récupérer des pannes partielles en plein milieu d'une mise à jour.

Ce qu'ils ne peuvent pas retirer de votre assiette : concevoir des workloads qui tolèrent l'éviction.

---

## Comment je gère les mises à jour sur k3s bare-metal

### L'outil : system-upgrade-controller

Le mécanisme de mise à jour de k3s est [system-upgrade-controller](https://github.com/rancher/system-upgrade-controller) — un contrôleur Kubernetes qui lit des CRD `Plan` et exécute des Jobs de mise à jour sur les nœuds correspondants.

La CRD Plan est déclarative. Vous committez une version cible, ArgoCD la synchronise, le contrôleur gère le reste :

```yaml
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: k3s-server
  namespace: system-upgrade
spec:
  concurrency: 1
  nodeSelector:
    matchExpressions:
      - key: node-role.kubernetes.io/control-plane
        operator: Exists       # pas matchLabels: "true" — la valeur varie selon les versions
  cordon: true
  drain:
    force: true
    ignoreDaemonSets: true     # requis : le DaemonSet Longhorn bloquerait sinon le drain
    deleteEmptydirData: true
    timeout: 120
  version: v1.36.2+k3s1
  upgrade:
    image: rancher/k3s-upgrade
  tolerations:
    - key: CriticalAddonsOnly
      operator: Exists
    - effect: NoExecute
      operator: Exists
    - effect: NoSchedule
      operator: Exists
---
apiVersion: upgrade.cattle.io/v1
kind: Plan
metadata:
  name: k3s-agent
  namespace: system-upgrade
spec:
  concurrency: 1
  nodeSelector:
    matchExpressions:
      - key: node-role.kubernetes.io/control-plane
        operator: DoesNotExist
  cordon: true
  drain:
    force: true
    ignoreDaemonSets: true
    deleteEmptydirData: true
    timeout: 120
  prepare:
    image: rancher/k3s-upgrade
    args: [prepare, k3s-server]   # bloque jusqu'à la fin du Plan serveur
  version: v1.36.2+k3s1
  upgrade:
    image: rancher/k3s-upgrade
  tolerations:
    - key: CriticalAddonsOnly
      operator: Exists
    - effect: NoExecute
      operator: Exists
    - effect: NoSchedule
      operator: Exists
```

**Séquence de mise à jour imposée par ces Plans :**

1. Le Plan `k3s-server` s'exécute sur `set-hog` (plan de contrôle) — cordon, drain, installer le nouveau binaire k3s, uncordon
2. L'étape `prepare` du Plan `k3s-agent` attend la fin du Plan serveur
3. Les workers se mettent à jour un à la fois (`concurrency: 1`) — fast-skunk, fast-heron, star-kitten, swift-mac

Cela reflète ce qu'EKS, GKE et AKS font tous en interne. La différence est qu'ici c'est du YAML visible, auditable, versionné dans git.

### Les pièges (non documentés)

Trois problèmes qui ne sont pas dans la doc de system-upgrade-controller et que j'ai rencontrés en écrivant ces Plans :

**1 — `matchLabels: "true"` casse sur certaines versions k3s**

Le label `node-role.kubernetes.io/control-plane` existe sur toutes les versions k3s, mais sa valeur (`""` vs `"true"`) varie. `matchLabels: "true"` ne correspond silencieusement à rien sur les clusters où la valeur est vide. Le correctif est `operator: Exists` — correspondre sur la clé quelle que soit la valeur.

**2 — `cordon: true` seul n'évince pas les pods**

`cordon: true` empêche l'ordonnancement de nouveaux pods sur le nœud. Il n'évince pas les pods existants. Sans le bloc `drain:`, les pods en cours restent sur le nœud pendant la mise à jour, y compris les StatefulSets avec PVC — ce qui peut causer une corruption de données si le binaire k3s redémarre sous eux.

**3 — `ignoreDaemonSets: true` est obligatoire avec Longhorn**

Longhorn exécute un DaemonSet (`longhorn-manager`) sur chaque nœud. Un drain sans `ignoreDaemonSets: true` attendra que ce pod DaemonSet se termine avant de continuer — mais les pods DaemonSet sont immédiatement replanifiés, donc l'attente ne se termine jamais. Le drain se bloque jusqu'au déclenchement du `timeout`, puis échoue.

**4 — Le `selfHeal` d'ArgoCD entre en conflit avec les Jobs de mise à jour de SUC**

system-upgrade-controller crée des pods Job sur les nœuds cibles pendant la mise à jour. ArgoCD, si `selfHeal: true` est actif sur la synchronisation, voit ces pods Job comme des ressources « hors synchronisation » (elles ne sont pas dans git) et peut les supprimer en plein milieu de la mise à jour. La pratique sûre : mettre en pause l'auto-synchronisation ou ajouter une entrée `ignoreDifferences` pour les ressources Job avant de déclencher une mise à jour.

### L'automatisation : GitHub Actions hebdomadaire

Committer une nouvelle version à la main fonctionne, mais requiert de se souvenir de vérifier. J'ai construit un workflow GitHub Actions qui tourne chaque lundi à 08:00 UTC, récupère la dernière release k3s depuis l'API GitHub, et ouvre une PR s'il trouve une version plus récente :

```yaml
name: k3s upgrade PR

on:
  schedule:
    - cron: '0 8 * * 1'
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: false

jobs:
  check-and-bump:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITOPS_TOKEN }}

      - name: Get latest k3s release
        id: latest
        run: |
          LATEST=$(curl -sf \
            -H "Authorization: Bearer ${{ secrets.GITHUB_TOKEN }}" \
            "https://api.github.com/repos/k3s-io/k3s/releases/latest" \
            | jq -r '.tag_name')
          echo "latest=$LATEST" >> "$GITHUB_OUTPUT"

      - name: Get current version from Plan YAML
        id: current
        run: |
          # grep '^ *version:' saute les lignes de commentaire contenant aussi le mot 'version:'
          CURRENT=$(grep -m1 '^ *version:' manifests/system-upgrade/01-k3s-plans.yaml \
            | awk '{print $2}')
          echo "current=$CURRENT" >> "$GITHUB_OUTPUT"

      - name: Compare and bump
        run: |
          if [[ "${{ steps.latest.outputs.latest }}" != "${{ steps.current.outputs.current }}" \
             && "${{ inputs.dry_run }}" != "true" ]]; then
            # bump de version dans les deux Plans (serveur + agent partagent la même ligne de version)
            sed -i "s/${{ steps.current.outputs.current }}/${{ steps.latest.outputs.latest }}/g" \
              manifests/system-upgrade/01-k3s-plans.yaml
            # ... puis ouvrir une PR
          fi
```

Le corps de la PR inclut une checklist de pré-fusion :

- Lire les notes de release k3s pour les dépréciations d'API
- Vérifier le bump de version de containerd (le `socketPath` de Chaos Mesh est couplé au chemin du socket containerd — un bump majeur de containerd peut casser les expériences de chaos)
- Vérifier qu'aucun PodDisruptionBudget ne bloque le drain
- Vérifier le nombre de répliques de volumes Longhorn
- Prendre une sauvegarde kine/SQLite **avant** la mise à jour

Le dernier point est ce qu'un fournisseur managé fait silencieusement avant chaque mise à jour. Sur bare-metal, la checklist l'impose.

---

## Comparaison côte à côte

| Dimension | minicloud (k3s bare-metal) | EKS | GKE | AKS |
|-----------|---------------------------|-----|-----|-----|
| **Qui déclenche la mise à jour** | Développeur — PR pour bumper `version:` dans git | Développeur ou politique d'auto-mise à jour | Canal de release (automatique) ou développeur | Développeur (ou politique d'auto-mise à jour) |
| **Migration du plan de contrôle** | system-upgrade-controller sur `set-hog` — visible | AWS — opaque, zéro interruption | Google — opaque, garanti par SLA | Azure — progressif, progression visible dans le portail |
| **Séquencement des workers** | `concurrency: 1`, Plan serveur d'abord, puis Plan agent | Groupe de nœuds managé : surge + drain par nœud | Surge upgrade : nouveau nœud avant de drainer l'ancien | Surge : nouveau nœud avant de drainer l'ancien |
| **Sauvegarde pré-mise à jour** | Sauvegarde kine/SQLite manuelle via checklist PR | AWS sauvegarde etcd automatiquement | Google sauvegarde etcd automatiquement | Azure sauvegarde etcd automatiquement |
| **Rollback** | Restaurer la sauvegarde kine + réinstaller l'ancien binaire sur chaque nœud | Rollback du groupe de nœuds possible ; rollback du plan de contrôle non supporté | Non supporté (pas de rollback vers la version mineure précédente) | Non supporté |
| **Séquencement des add-ons** | Manuel (les versions d'apps ArgoCD sont indépendantes) | Les add-ons managés requièrent une étape de mise à jour séparée | Géré automatiquement par GKE | Manuel pour la plupart des add-ons |
| **Décalage de version** | Vous choisissez quand ; les releases k3s suivent l'amont à ~1–2 semaines | N-2 versions supportées ; nouvelles versions disponibles ~2 mois post-amont | Canaux de release : Rapid (~2 semaines), Regular (~4 semaines), Stable (~6 semaines) | ~2 mois post-amont pour le support GA |
| **Observabilité** | `kubectl get nodes -w`, statut de sync ArgoCD, santé Longhorn | CloudWatch Container Insights, dashboard EKS upgrade insights | Cloud Logging, notifications de mise à jour GKE | Azure Monitor, événements de mise à jour AKS |
| **Ce qui casse silencieusement** | Blocage de drain DaemonSet, selfHeal ArgoCD supprimant les Jobs SUC, `swift-mac` requiert un power-cycle manuel après figement OS | Décalage de version d'add-on après mise à jour du plan de contrôle | Rare — GKE gère la plupart de la compatibilité en interne | Décalage de version de pool de nœuds si vous en avez plusieurs |
| **Coût** | Électricité (matériel déjà possédé) | 0,10 $/h par cluster (73 $/mois rien que le plan de contrôle) | Plan de contrôle gratuit en Standard ; Autopilot ajoute un coût par workload | Plan de contrôle gratuit ; on paie les VM des nœuds |

---

## Le compromis honnête

Les fournisseurs managés retirent les parties mécaniques : installation du binaire, migration etcd, provisioning de nœuds surge, vérifications de readiness post-mise à jour. Ils ne retirent pas le travail de conception : PodDisruptionBudgets, tolérance au drain, limites de ressources permettant l'éviction, et sondes de santé des workloads.

k3s auto-géré ne retire aucune des parties mécaniques. Vous écrivez les CRD Plan. Vous réglez la spec de drain. Vous construisez l'automatisation. Vous possédez la sauvegarde. Mais l'avantage est que chaque étape est dans git, chaque décision est auditable, et vous comprenez ce qui se passe réellement quand vous lancez `kubectl get nodes -w` et voyez un nœud disparaître puis revenir.

Le workflow GitHub Actions que j'ai construit ouvre une PR une fois par semaine si k3s sort quelque chose de nouveau. Le corps de la PR est une checklist en six points. La fusionner prend deux minutes. La mise à jour elle-même prend environ vingt minutes sur cinq nœuds, sans surveillance.

Voilà le marché de l'auto-gestion : plus de travail en amont pour comprendre le système, moins de mystère quand quelque chose tourne mal.

---

## Ce qui est automatisé vs ce qui reste manuel

**Automatisé :**
- Détection hebdomadaire des nouvelles releases k3s (GitHub Actions)
- PR avec la version bumpée dans les deux Plans (serveur + agent)
- Séquence de drain et de mise à jour des nœuds (system-upgrade-controller)
- Synchronisation ArgoCD des Plans mis à jour

**Toujours manuel :**
- Lire les notes de release pour les changements cassants
- Sauvegarde kine/SQLite avant la fusion
- Validation post-mise à jour (`kubectl get nodes`, `kubectl get pods -A`, santé des volumes Longhorn)
- Intervention manuelle sur `swift-mac` si la mise à jour se bloque (le SMC d'Apple ne supporte pas le power-cycle à distance)

Les éléments manuels le sont intentionnellement. Une mise à jour entièrement autonome qui saute la vérification des notes de release et la sauvegarde est un chemin rapide vers un incident de production. La PR n'est pas une barrière pour ralentir les choses — c'est le moment où un humain lit les notes de release et décide que la mise à jour est sûre à appliquer.

C'est la même décision qu'une équipe plateforme prend quand elle dé-met en pause une fenêtre de maintenance GKE ou approuve une mise à jour de groupe de nœuds EKS. La différence est que sur bare-metal, la décision et ses conséquences sont entièrement les vôtres.
