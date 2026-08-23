---
slug: container-registry-architecture-harbor-k3s-proxy-cache
title: "Un registre pour les gouverner tous : Harbor comme point d'entrée unique des images pour un cluster k3s bare-metal"
authors: [andrelair]
tags: [harbor, kubernetes, docker, registry, k3s, self-hosted, devops, supply-chain, rate-limiting, containerd]
date: 2026-08-16
description: "Comment une instance Harbor auto-hébergée, configurée en proxy pull-through pour docker.io, ghcr.io, quay.io et registry.k8s.io, devient le point d'entrée unique de tout le trafic d'images d'un cluster k3s bare-metal — éliminant les limites de débit Docker Hub, centralisant le scan de vulnérabilités, et préservant la capacité d'air-gap sans aucun changement de code dans vos manifestes."
---

Si vous exploitez sérieusement un cluster Kubernetes, vous finissez par heurter le mur Docker Hub. Un matin, votre pipeline CI se met à échouer avec `toomanyrequests: You have reached your pull rate limit`. Ou pire — il échoue pendant une reprise de cluster à 2 h du matin, quand vos nœuds tirent des images pour redémarrer des workloads critiques et que Docker Hub décide que vous avez dépassé votre quota anonyme de 100 pulls par 6 heures.

Le conseil standard est d'ajouter de l'authentification. Mais cela ne fait qu'augmenter la limite — cela n'élimine pas la dépendance à un service externe pendant vos moments les plus vulnérables. La réponse de production est un cache proxy pull-through, et sur un cluster k3s auto-hébergé, Harbor + les miroirs k3s font que chaque nœud se comporte comme si Docker Hub était local.

{/* truncate */}

## Le tableau complet : cinq registres, un point d'entrée

Sur la plateforme minicloud — un cluster k3s bare-metal de 5 nœuds exécutant plus de 70 workloads — le trafic d'images implique cinq registres distincts :

| Registre | Type | Ce qu'il sert |
|---|---|---|
| `harbor.10.0.0.200.nip.io` | Auto-hébergé (Harbor 2.14) | **Tout** — images construites par CI + cache proxy pour tous les registres publics |
| `docker.io` | Public amont | Docker Hub par défaut — nginx, postgres, redis, alpine, ubuntu... |
| `ghcr.io` | Public amont | GitHub Container Registry — Authentik, Longhorn, Velero, la plupart de l'outillage CNCF |
| `quay.io` | Public amont | Quay de Red Hat — Prometheus, AlertManager, Grafana, OPA |
| `registry.k8s.io` | Public amont | Images du projet Kubernetes — pause, kube-proxy, CoreDNS, metrics-server |

Mais « cinq registres » n'est vrai que du point de vue de l'origine du pull. Du point de vue de chaque nœud du cluster, il y a exactement **un** registre : Harbor.

---

## Comment k3s rend Harbor transparent

La clé est `registries.yaml` — un fichier de configuration de miroir containerd que k3s lit au démarrage. Il dit au runtime de conteneur : « quand un pod demande une image de X, essaie Y d'abord, replie sur X ».

```yaml
# /etc/rancher/k3s/registries.yaml (sur chaque nœud k3s)
mirrors:
  "docker.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/docker-hub"
      - "https://registry-1.docker.io"
  "ghcr.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/ghcr"
      - "https://ghcr.io"
  "quay.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/quay"
      - "https://quay.io"
  "registry.k8s.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io/v2/k8s-registry"
      - "https://registry.k8s.io"
  "harbor.10.0.0.200.nip.io":
    endpoint:
      - "https://harbor.10.0.0.200.nip.io"
configs:
  "harbor.10.0.0.200.nip.io":
    tls:
      ca_file: /etc/rancher/k3s/minicloud-ca.crt
```

Quand une spec de pod dit `image: nginx:alpine`, containerd ne contacte pas `docker.io`. Il essaie `harbor.10.0.0.200.nip.io/v2/docker-hub` d'abord. Si Harbor a l'image en cache, il la renvoie immédiatement. Sinon, Harbor la récupère depuis `registry-1.docker.io`, la met en cache, et la sert — le nœud ne communique jamais qu'avec Harbor.

L'endpoint de repli (`"https://registry-1.docker.io"`) est là comme mécanisme de résilience : si Harbor lui-même est en panne, containerd peut toujours tirer directement. En pratique, ce repli ne se déclenche que pendant les redémarrages ou les fenêtres de maintenance de Harbor.

**Rien dans vos manifestes Kubernetes ne change.** Un Deployment qui dit `image: ghcr.io/goauthentik/server:2024.12.0` continue de dire exactement cela. Le miroir intercepte le pull au niveau containerd, avant toute analyse de manifeste.

---

## Projets de cache proxy Harbor

Côté Harbor, chaque registre amont devient un **projet de cache proxy**. Un projet de cache proxy n'a aucune image stockée dans git ni poussée par quiconque — c'est purement un cache pull-through. Quand Harbor reçoit une requête pour `docker-hub/nginx:alpine`, il :

1. Vérifie son stockage local pour `nginx:alpine` (même digest que celui de Docker Hub)
2. Si trouvé et que le manifeste n'a pas expiré : sert depuis le stockage local
3. Si non trouvé : tire depuis le registre amont configuré, le stocke, le sert

Les quatre projets de cache proxy sur minicloud :

| Nom du projet Harbor | Registre amont | Type de registre dans Harbor |
|---|---|---|
| `docker-hub` | `https://registry-1.docker.io` | Docker Hub |
| `ghcr` | `https://ghcr.io` | Docker Registry (compatible OCI) |
| `quay` | `https://quay.io` | Docker Registry (compatible OCI) |
| `k8s-registry` | `https://registry.k8s.io` | Docker Registry (compatible OCI) |

Le nom du projet dans Harbor **doit correspondre exactement** au segment de chemin dans `registries.yaml`. L'endpoint miroir `harbor.10.0.0.200.nip.io/v2/docker-hub` route vers le projet Harbor nommé `docker-hub`. Si vous créez le projet comme `proxy-docker` mais que le chemin miroir dit `docker-hub`, chaque pull rate le cache et va au repli — vous n'avez ni protection contre les limites de débit ni scan de vulnérabilités.

Un piège à documenter : Harbor liste `quay` comme type de registre supporté, mais quand vous tentez de créer un projet de cache proxy contre un registre de type `quay`, l'API renvoie `400: unsupported registry type quay`. Le correctif est d'enregistrer l'amont Quay comme `docker-registry` (OCI générique) plutôt que `quay` — l'API V2 de Quay est entièrement compatible OCI et le proxy OCI générique de Harbor fonctionne correctement avec.

---

## Pourquoi cela compte au-delà des limites de débit

Les limites de débit Docker Hub sont la motivation évidente, mais l'architecture offre plusieurs autres propriétés qui comptent en production :

**Scan de vulnérabilités au point d'étranglement.** Harbor exécute Trivy. Chaque image qui transite par le cache proxy est scannée. Si vous activez « Empêcher les images vulnérables » au niveau projet, aucune image avec un CVE Critical ne peut être tirée dans le cluster — même s'il s'agit d'une image amont publique qu'un manifeste référence directement. Le scheduler Kubernetes voit un 403 de Harbor et le pod reste Pending au lieu d'exécuter du code vulnérable.

**Reproductibilité sous partition réseau.** Un cluster bare-metal dans un homelab ou un bureau n'a pas de SLA internet d'entreprise. Si votre cluster peut survivre à une coupure internet de 4 heures, c'est parce que chaque image dont vos workloads ont besoin est déjà dans le cache de Harbor depuis le dernier pull. Pendant une reprise après coupure de courant sur minicloud — où les 5 nœuds redémarrent simultanément et tentent de tirer des images en même temps — Harbor sert tout depuis le stockage local. Aucun échec de pull d'image, aucun pod bloqué en `ImagePullBackOff`.

**Piste d'audit pour tous les pulls d'images.** Harbor journalise chaque requête de pull : quelle image, quel tag, quel digest, à quelle heure, authentifié comme quel utilisateur ou compte de service. Sur un cluster avec 70 workloads en route, savoir que `set-hog` a tiré `quay.io/prometheus/prometheus:v2.54.0` à 03:47 le 2026-08-02 est parfois utile pour une investigation d'incident.

**Intégrité de la supply chain pour les images construites par CI.** La cinquième entrée de la liste de miroirs `registries.yaml` — `harbor.10.0.0.200.nip.io` pointant vers lui-même — garantit que les images construites par CI (vos propres services, image Backstage personnalisée, Open WebUI personnalisé) sont aussi servies via Harbor sans traitement spécial. Les signatures cosign sont stockées comme artefacts Harbor aux côtés de l'image. Trivy scanne vos propres images avec la même politique que les images amont. La provenance des images de toute la flotte transite par un seul système.

---

## Le flux de pull, étape par étape

Voici exactement ce qui se passe quand k3s ordonnance `harbor-core` sur un nœud après un effacement à froid de la base Harbor (ce qui oblige Harbor à retirer ses propres images) :

```
1. Le scheduler assigne le pod au nœud fast-skunk
2. kubelet demande à containerd : tirer goharbor/harbor-core:v2.14.0
3. containerd vérifie registries.yaml : "docker.io" → miroir harbor.10.0.0.200.nip.io/v2/docker-hub
4. containerd envoie : GET harbor.10.0.0.200.nip.io/v2/docker-hub/goharbor/harbor-core/manifests/v2.14.0
5. Harbor : vérifie le cache du projet docker-hub → cache miss (base fraîche)
6. Harbor : s'authentifie auprès de registry-1.docker.io (avec identifiants stockés si configuré)
7. Harbor : tire le manifeste + les couches depuis Docker Hub
8. Harbor : stocke les couches dans le PVC harbor-registry (20Gi Longhorn)
9. Harbor : renvoie le manifeste à containerd
10. containerd : tire les couches depuis Harbor (même requête, désormais cache hit)
11. Nœud : image dépaquetée, pod démarre
```

Sur les pulls suivants de la même image (même digest), les étapes 6–8 sont entièrement sautées. Harbor répond depuis son propre stockage. Docker Hub n'est jamais contacté.

---

## Ce qui casse quand Harbor tombe

Cette architecture crée un point unique de défaillance : si Harbor est en panne et qu'une image n'est pas déjà sur le nœud, le pod ne peut pas démarrer. Les endpoints de repli dans `registries.yaml` atténuent cela, mais ils vous exposent de nouveau aux limites de débit et requièrent un accès internet sortant qui peut ne pas toujours être disponible.

La réponse opérationnelle est de traiter Harbor avec la même posture de fiabilité que votre contrôleur ingress ou le DNS : le garder sur un nœud stable (`fast-skunk`, épinglé via nodeSelector), utiliser Longhorn avec 3 répliques pour ses PVC, et alerter sur les redémarrages du pod Harbor. Pendant une maintenance planifiée de Harbor, pré-tirez toute image que vous savez nécessaire.

Sur minicloud, cela s'est produit une fois quand le PVC Longhorn de harbor-database a subi une panne et que Harbor est resté indisponible ~40 minutes. Pendant cette fenêtre, les nœuds qui avaient déjà des images en cache local n'ont pas été affectés. Les pods qui avaient besoin de pulls d'images sont restés bloqués en `ImagePullBackOff` — ils se sont repliés sur Docker Hub et ont heurté les limites de débit car le quota de pull anonyme était déjà consommé plus tôt dans la journée. La leçon : un cache pull-through n'est pas la même chose qu'un registre local. Containerd ne pré-remplit pas les nœuds ; il ne met en cache qu'après le premier pull. Pour les workloads critiques, `imagePullPolicy: IfNotPresent` avec des images pré-tirées sur chaque nœud est la seule vraie garantie hors-ligne.

---

## Référence de configuration

**Créer un registre de cache proxy dans Harbor (API) :**

```bash
HARBOR_PASS=$(ssh controller "cat ~/.harbor-admin")

# Enregistrer l'amont (exemple : ghcr.io)
curl -sk --cacert ~/minicloud-ca.crt \
  -u "admin:${HARBOR_PASS}" \
  -X POST "https://harbor.10.0.0.200.nip.io/api/v2.0/registries" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "ghcr-upstream",
    "type": "docker-registry",
    "url": "https://ghcr.io",
    "insecure": false
  }'

# Récupérer l'ID du registre dans la réponse, puis créer le projet proxy
curl -sk --cacert ~/minicloud-ca.crt \
  -u "admin:${HARBOR_PASS}" \
  -X POST "https://harbor.10.0.0.200.nip.io/api/v2.0/projects" \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name": "ghcr",
    "registry_id": <ID_CI_DESSUS>,
    "public": true
  }'
```

**Vérifier que le miroir fonctionne :**

```bash
# Sur n'importe quel nœud, observer containerd tirer via Harbor :
ssh controller "journalctl -u k3s -f | grep 'pulling from'"

# Ou vérifier le nombre de pulls de Harbor via l'API :
curl -sk --cacert ~/minicloud-ca.crt \
  -u "admin:${HARBOR_PASS}" \
  "https://harbor.10.0.0.200.nip.io/api/v2.0/projects/ghcr" \
  | python3 -c "import sys,json; p=json.load(sys.stdin); print('pulls:', p['metadata'].get('pull_count', 0))"
```

**Critique : les noms de projets doivent correspondre aux chemins de miroir.** La config miroir `harbor.10.0.0.200.nip.io/v2/docker-hub` requiert un projet Harbor nommé exactement `docker-hub`. Le préfixe `/v2/` et le nom du projet forment l'URL de pull containerd.

---

## Résumé

L'architecture de registre de minicloud est délibérément simple : une instance Harbor, quatre projets de cache proxy, un `registries.yaml` sur chaque nœud. Aucun secret d'authentification de pull d'image dans les namespaces. Aucun traitement spécial dans les valeurs Helm ou les overlays Kustomize. Chaque nœud tire chaque image depuis Harbor, Harbor récupère depuis l'amont si nécessaire, et les limites de débit Docker Hub sont un problème qui n'existe plus au quotidien.

La propriété la plus intéressante est la consolidation de la supply chain : chaque image, qu'elle ait été construite par CI et poussée vers `library/my-service`, ou tirée via le cache depuis `ghcr.io/someproject/tool`, transite par la même instance Harbor, est scannée par la même politique Trivy, et apparaît dans le même journal d'audit. Pour une plateforme qui exécute des workloads d'assurance où la provenance des images compte pour la conformité réglementaire, ce point d'étranglement unique vaut plus que le correctif des limites de débit Docker Hub.
