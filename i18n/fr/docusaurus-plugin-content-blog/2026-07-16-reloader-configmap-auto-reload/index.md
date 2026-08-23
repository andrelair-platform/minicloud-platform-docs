---
slug: kubernetes-configmap-auto-reload-stakater-reloader
title: "Automatiser les rechargements de ConfigMap : pourquoi nous avons ajouté Stakater Reloader"
authors: [andre]
description: >
  Kubernetes ne redémarre pas automatiquement les pods quand un ConfigMap monté change — surtout
  avec des montages subPath. Nous avons ajouté Stakater Reloader pour éliminer les appels manuels
  kubectl rollout restart sur Homer, LiteLLM, SearXNG et Backstage. Voici le problème, le correctif,
  et une investigation bonus d'OOMKill ArgoCD découverte en chemin.
tags: [kubernetes, gitops, argocd, platform-engineering, reloader, configmap, devops]
date: 2026-07-16
---

Chaque fois que je mettais à jour la config du dashboard Homer, je devais lancer `kubectl rollout restart deployment/homer -n homer` après qu'ArgoCD ait fini de synchroniser. Pareil pour LiteLLM quand le routage changeait. Pareil pour Backstage après toute mise à jour de catalogue ou de proxy. Le motif était identique à chaque fois : pousser vers git, attendre la synchronisation ArgoCD, puis déclencher manuellement un redémarrage de pod.

C'est une odeur opérationnelle. Si git est le seul chemin d'écriture, le redémarrage devrait être automatique aussi.

{/* truncate */}

## Pourquoi Kubernetes ne recharge pas automatiquement les ConfigMaps

Kubernetes *met bien* à jour les données de ConfigMap sur place — mais seulement pour les montages de volume qui utilisent le répertoire complet. Quand vous montez un ConfigMap avec `subPath` (montant un seul fichier plutôt que tout le répertoire), Kubernetes [saute intentionnellement la mise à jour automatique](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically).

Homer monte sa config avec `subPath` :

```yaml
volumeMounts:
  - mountPath: /www/assets/config.yml
    name: config
    subPath: config.yml   # ← ceci désactive la propagation automatique
```

C'est par conception. `subPath` vous donne un contrôle fin sur l'endroit où un fichier atterrit dans un conteneur, mais il casse la surveillance inotify que Kubernetes utiliserait sinon pour propager les mises à jour de ConfigMap. Le fichier que le pod voit est figé au moment du montage.

Le contournement courant — que j'avais en place — est un bump d'annotation manuel sur le template de pod :

```yaml
template:
  metadata:
    annotations:
      config-checksum: "v17-star-kitten-polaris"  # bumper ceci manuellement après chaque changement de config
```

Changer l'annotation force un nouveau pod-template-hash, ce qui déclenche un redémarrage progressif. Mais c'est du bruit : cela encombre l'historique git, c'est facile à oublier, et cela n'a rien à voir avec le changement réel effectué.

## Le motif plus large

Ce n'était pas que Homer. Chaque déploiement adossé à un ConfigMap dans le cluster avait le même problème :

| Déploiement | ConfigMaps | Action requise après changement |
|---|---|---|
| `homer` | `homer-config` | `kubectl rollout restart` manuel |
| `litellm` | `litellm-config`, `langfuse-prompt-handler`, `phi3-financial-prompt` | `kubectl rollout restart` manuel |
| `searxng` | `searxng-config` | `kubectl rollout restart` manuel |
| `backstage` | `backstage-app-config`, `backstage-session-config` | `kubectl rollout restart` manuel |

Le CLAUDE.md avait même une note me rappelant de lancer le redémarrage après chaque push de config Backstage. L'existence de cette note est le problème — si un humain doit se souvenir de faire quelque chose après un push git, ce sera finalement oublié.

## Le correctif : Stakater Reloader

[Stakater Reloader](https://github.com/stakater/reloader) est un contrôleur Kubernetes qui surveille les ConfigMaps et les Secrets, et déclenche des redémarrages progressifs sur tout Deployment (ou StatefulSet, DaemonSet) qui y adhère via une seule annotation.

Le déploiement est un unique chart Helm dans son propre namespace :

```yaml
# apps/reloader.yaml
sources:
  - repoURL: https://stakater.github.io/stakater-charts
    chart: reloader
    targetRevision: "2.2.14"   # app v1.4.19
```

Et y adhérer est une ligne sur les métadonnées de n'importe quel Deployment :

```yaml
metadata:
  annotations:
    reloader.stakater.com/auto: "true"
```

Reloader détecte tous les ConfigMaps et Secrets référencés par le Deployment (via `volumes`, `envFrom` et `env.valueFrom`) et les surveille. Quand ArgoCD synchronise un changement de ConfigMap, Reloader voit la mise à jour en quelques secondes et déclenche automatiquement un redémarrage progressif.

Le flux est désormais entièrement automatisé :

```
push git → ArgoCD synchronise le ConfigMap → Reloader détecte le changement → redémarrage progressif du pod
```

Aucune étape humaine. Aucun bump d'annotation. Aucune entrée de runbook vous rappelant de vous souvenir.

## Supprimer le contournement manuel

Avec Reloader installé, l'annotation `config-checksum` dans le déploiement de Homer était du bruit :

```yaml
# avant — contournement manuel
template:
  metadata:
    annotations:
      config-checksum: "v17-star-kitten-polaris"

# après — propre
template:
  metadata:
    labels:
      app: homer
      backstage.io/kubernetes-id: homer
```

Les métadonnées du déploiement obtiennent l'annotation Reloader à la place :

```yaml
metadata:
  name: homer
  namespace: homer
  annotations:
    reloader.stakater.com/auto: "true"
```

## Une investigation bonus : les OOMKills d'ArgoCD

En implémentant Reloader, j'ai remarqué que le contrôleur d'application ArgoCD était en CrashLoopBackOff — 183 redémarrages sur 44 heures :

```
argo-cd-argocd-application-controller-0   0/1   CrashLoopBackOff   183 (4m ago)   44h
```

Cela expliquait pourquoi les synchronisations prenaient une éternité et pourquoi Reloader lui-même ne pouvait pas terminer sa synchronisation initiale. Le code de sortie était 137 — `SIGKILL` du tueur OOM :

```
Last State: Terminated
  Reason:    OOMKilled
  Exit Code: 137
```

Le contrôleur avait une limite mémoire de 1Gi, fixée quand le cluster gérait environ 10 applications. Il en gère désormais ~40, dont des applications Helm multi-sources avec de gros manifestes (Harbor, Authentik, kube-prometheus-stack). La boucle de réconciliation pour 40 apps a simplement dépassé 1Gi.

Le correctif est dans `helm-values/argocd-values.yaml` :

```yaml
controller:
  resources:
    requests: { cpu: 100m, memory: 512Mi }
    limits:   { cpu: 1000m, memory: 2Gi }   # était 1Gi
```

Appliqué immédiatement via `kubectl patch statefulset` sans attendre qu'ArgoCD s'auto-synchronise (il ne pouvait pas, puisque le contrôleur était celui qui plantait). Après le patch, le contrôleur est monté proprement : `1/1 Running 0`.

La leçon : la mémoire du contrôleur ArgoCD croît avec le nombre d'applications et la complexité de leurs manifestes. Si vous ajoutez beaucoup d'apps Helm, gardez-le à l'œil. Un `CrashLoopBackOff` sur le contrôleur d'application signifie que plus rien ne se synchronise — c'est le pod le plus critique du cluster après le serveur d'API.

## Ce qui est déployé

```
Namespace :  reloader
App :        reloader (ArgoCD)
Chart :      stakater/reloader 2.2.14 (app v1.4.19)
Sécurité :   runAsNonRoot, runAsUser 65534, seccompProfile RuntimeDefault,
             capabilities.drop ALL, pas d'escalade de privilèges
Ressources : 10m/32Mi demandé — 100m/128Mi limite
```

Déploiements qui se rechargent désormais automatiquement au changement de ConfigMap :
- `homer` — mise en page du dashboard
- `litellm` — routage de modèles de l'AI Gateway, gestionnaire de prompts, garde-fous financiers
- `searxng` — réglages du moteur de recherche
- `backstage` — emplacements de catalogue, endpoints de proxy, config d'auth

Tout futur déploiement qui monte un ConfigMap obtient le même comportement avec une ligne d'annotation. Le motif passe à l'échelle gratuitement.

## Un piège : le versionnage du chart

La version du chart Stakater Reloader ne **correspond pas** à la version de l'application. Quand j'ai d'abord épinglé `targetRevision: "1.4.3"` (correspondant au format de version de l'app), ArgoCD a échoué :

```
error fetching chart: failed to fetch chart: helm pull --version 1.4.3 --repo https://stakater.github.io/stakater-charts
```

La version correcte à utiliser est la version du chart, trouvée via :

```bash
helm repo add stakater https://stakater.github.io/stakater-charts
helm search repo stakater/reloader
# NAME                  CHART VERSION   APP VERSION
# stakater/reloader     2.2.14          v1.4.19
```

Chart `2.2.14` = app `v1.4.19`. Toujours chercher avant d'épingler.
