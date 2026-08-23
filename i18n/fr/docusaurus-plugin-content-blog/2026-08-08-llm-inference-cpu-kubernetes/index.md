---
slug: llm-inference-cpu-kubernetes
title: "Nous avons remplacé Ollama par vLLM sur du Kubernetes CPU-only — voici ce qui a changé"
authors: [andrelair]
tags: [ai, llm, vllm, ollama, inference, kubernetes, cpu, self-hosted, mlops, enterprise, data-sovereignty]
date: 2026-08-08
description: "Nous avons fait tourner Ollama en production sur des ThinkPads bare-metal sans GPU. Puis nous l'avons remplacé par vLLM. Voici le compte-rendu honnête de ce qui a cassé, de ce qui s'est amélioré, et de quel est réellement le bon outil pour l'inférence CPU-only dans un vrai cluster."
---

La plupart des articles comparant vLLM et Ollama présument que vous avez un GPU. Les benchmarks montrent une utilisation impressionnante de la VRAM. Les schémas d'architecture incluent des pilotes CUDA. La recommandation — vLLM gagne — vient avec un astérisque implicite : *à condition d'avoir le matériel pour*.

Nous ne l'avions pas. Notre cluster d'inférence, c'est quatre ThinkPads, chacun avec un i7-8565U (4 cœurs, 8 threads, jusqu'à 4,6 GHz en turbo), 16 Go de RAM, et aucun GPU d'aucune sorte. Nous avons d'abord utilisé Ollama. Puis nous l'avons remplacé par vLLM. Voici le compte-rendu honnête de cette migration : ce qui a cassé, ce qui s'est amélioré, et à quoi ressemblent réellement les compromis quand vous faites tourner de l'inférence LLM sur des CPU x86 grand public.

{/* truncate */}

## Pourquoi nous avons commencé avec Ollama

L'attrait d'Ollama est réel. Vous tirez un modèle en une commande, vous obtenez une API compatible OpenAI, et ça marche immédiatement. Pour un développeur seul interrogeant un modèle localement, ou pour une petite équipe validant si un modèle auto-hébergé est utile ou non, rien n'est plus rapide pour démarrer.

Nous avons déployé Ollama en deux instances — primaire sur un ThinkPad, secondaire sur un autre — et placé LiteLLM devant elles en proxy. Cela nous a donné le routage de modèles, les clés d'API virtuelles et le traçage Langfuse dès le premier jour, sans qu'Ollama n'ait à fournir aucune de ces fonctionnalités lui-même. La configuration était intentionnelle : nous savions qu'Ollama n'était pas un serveur de production, alors nous avons compensé à la couche proxy.

Pour une faible concurrence, ça fonctionnait. Un utilisateur seul posant une question sur un document financier obtenait une réponse en 15–25 secondes pour un modèle 4B. Acceptable pour un outil interne où les utilisateurs comprenaient la latence.

Puis nous avons essayé de l'utiliser pour quoi que ce soit au-delà.

---

## Ce qui a cassé sous charge réelle

### Le traitement séquentiel n'est pas un problème de configuration

Ollama traite une requête à la fois. Quand une deuxième requête arrive alors que la première génère encore, elle attend. Pas dans une file qui alimente en continu — elle attend que toute la première réponse soit terminée avant qu'un seul token ne soit généré pour le second utilisateur.

Sur un CPU avec un modèle 4B mettant 20 secondes à répondre, deux utilisateurs simultanés signifient que l'un d'eux attend 40 secondes. Cinq utilisateurs simultanés signifient que le dernier attend près de deux minutes avant que sa réponse ne commence. Ce n'est pas quelque chose que l'on règle. C'est l'architecture.

Pour un pipeline RAG qui appelle le modèle en boucle — un appel pour reclasser les chunks, un pour synthétiser une réponse, un pour générer une question de suivi — vous sérialisez ce qui devrait être un travail parallèle. Trois appels séquentiels sur un modèle à 20 secondes, c'est une minute de temps réel pour une seule requête utilisateur.

### Pas de métriques, pas de visibilité

Ollama n'expose rien à Prometheus. Pas de profondeur de file. Pas de time-to-first-token. Pas de débit de tokens. Pas de taux d'erreurs.

Quand un modèle a commencé à répondre lentement — ce qui arrivait régulièrement car le modèle chargé se disputait la mémoire avec d'autres workloads du cluster — nous n'avions aucun signal d'Ollama lui-même. Nous voyions des pics de latence dans les traces Langfuse (parce que chaque appel LiteLLM était tracé), mais nous ne pouvions pas distinguer entre « Ollama est lent », « le modèle fait quelque chose de coûteux en calcul » ou « le nœud est contraint en mémoire ». L'absence de métriques internes rendait la planification de capacité impossible.

### Pression mémoire sans visibilité

Un modèle 4B en quantification 4-bit fait environ 2,5 Go en mémoire. Charger deux modèles simultanément — ce qu'Ollama fera si `OLLAMA_MAX_LOADED_MODELS` est réglé au-dessus de un — consomme 5 Go+ de RAM système rien que pour les poids des modèles. Sur un nœud de 16 Go exécutant k3s, l'iSCSI Longhorn et divers autres pods, cela laisse peu de marge.

Ollama ne vous indique pas son usage mémoire actuel de façon structurée. Vous pouvez voir la mémoire du processus dans `kubectl top`, mais vous ne pouvez pas voir la répartition entre poids du modèle, cache KV et tampons de requêtes en attente. Quand le nœud a commencé à évincer des pods à cause de la pression mémoire, nous l'avons appris par les événements Kubernetes plutôt que par Ollama.

---

## La migration vers vLLM

vLLM v0.6.6 supporte l'inférence CPU via `--device=cpu`. Ce n'est pas le cas d'usage principal — l'équipe vLLM optimise fortement pour NVIDIA CUDA — mais le backend CPU est fonctionnel et reçoit la même logique de batching continu et de PagedAttention que le chemin GPU.

Notre déploiement cible le même nœud fast-heron (i7-8565U, 16 Go de RAM) qui exécutait précédemment Ollama primaire :

```yaml
containers:
  - name: vllm
    image: docker.io/vllm/vllm-openai:v0.6.6
    args:
      - --model=microsoft/Phi-3-mini-4k-instruct
      - --device=cpu
      - --dtype=float16
    env:
      - name: VLLM_CPU_KVCACHE_SPACE
        value: "2"
    resources:
      requests:
        cpu: 2000m
        memory: 6Gi
      limits:
        cpu: 7000m
        memory: 14Gi
```

Quelques décisions méritant explication :

**`--dtype=float16` sur CPU.** L'inférence CPU en float16 fonctionne sur x86 moderne via les instructions AVX-512 ou AVX2. L'i7-8565U supporte AVX2. Utiliser float16 plutôt que float32 divise par deux la taille du modèle en mémoire et réduit le coût arithmétique par token.

**`VLLM_CPU_KVCACHE_SPACE=2`.** Cela réserve 2 Go de RAM pour le cache KV. Sur CPU, PagedAttention gère cette allocation entre requêtes concurrentes. Sans ce réglage, vLLM utilise par défaut une allocation conservatrice qui limite inutilement la concurrence.

**7 cœurs CPU alloués.** Nous laissons un cœur pour l'OS, l'agent k3s et les autres processus système. vLLM utilise tous les cœurs alloués pour le calcul d'attention parallèle et les opérations tensorielles à travers les couches du modèle.

---

## Ce qui s'est réellement amélioré

### Les requêtes concurrentes fonctionnent

C'est la raison principale de la migration. Le batching continu de vLLM signifie que dès qu'une requête termine une étape de décodage, la requête suivante de la file est ordonnancée. Plusieurs utilisateurs peuvent recevoir activement des tokens simultanément plutôt que d'attendre dans une file strictement séquentielle.

Pour un pipeline RAG faisant plusieurs appels de modèle par requête utilisateur, cela compte énormément. Le proxy LiteLLM peut dispatcher trois appels et recevoir les réponses au fur et à mesure de leur achèvement, plutôt que d'attendre que chacun se termine avant d'émettre le suivant.

### Les métriques Prometheus sont réelles

L'endpoint `/metrics` de vLLM fournit tout le nécessaire pour exploiter correctement le service :

```
vllm:num_requests_running          # requêtes concurrentes actives en ce moment
vllm:num_requests_waiting          # profondeur de file — indicateur avancé de saturation
vllm:gpu_cache_usage_perc          # utilisation du cache KV (même métrique, fonctionne pour CPU)
vllm:time_to_first_token_seconds   # histogrammes p50/p99 du TTFT
vllm:request_success_total         # taux de succès des requêtes par modèle
vllm:num_tokens_generated          # débit total
```

Nous avons ajouté un ServiceMonitor et Prometheus scrape désormais ces valeurs toutes les 15 secondes. Quand la latence grimpe, nous avons la profondeur de file et l'utilisation du cache pour diagnostiquer si la cause est le volume de requêtes, la pression mémoire ou le comportement du modèle. C'était simplement impossible avec Ollama.

### Service de modèle affiné

Nous avons lancé un job de fine-tuning QLoRA dans Google Colab pour produire un adaptateur phi3-financial — une base Phi-3-mini-4k-instruct avec un adaptateur LoRA entraîné sur des données du domaine financier. vLLM peut charger des adaptateurs LoRA et les servir comme modèles nommés aux côtés de la base :

```yaml
args:
  - --model=microsoft/Phi-3-mini-4k-instruct
  - --enable-lora
  - --lora-modules
  - phi3-financial-ft=/model-cache/phi3-financial-lora
```

Ollama n'a pas d'équivalent. Si vous voulez servir un modèle affiné avec Ollama, vous devez le convertir au format GGUF et créer un Modelfile. vLLM charge directement l'adaptateur LoRA au format HuggingFace, sans étape de conversion.

---

## Les vrais compromis sur CPU

Être honnête sur ce que vous cédez compte autant que sur ce que vous gagnez.

**Le time-to-first-token est plus lent.** Sur un GPU, un modèle 3B génère les premiers tokens en 200–500 ms. Sur notre i7-8565U avec vLLM, c'est 3–8 secondes selon la longueur du prompt. Pour un chat interactif, c'est perceptible. Pour des pipelines de traitement de documents où le résultat compte plus que l'attente, c'est acceptable.

**Le plafond de débit est plus bas.** Un seul nœud CPU exécutant vLLM avec un modèle 3B gère environ 4–8 tokens par seconde pour une seule requête. Un GPU de milieu de gamme gère 50–200 tokens par seconde. Nous compensons en dimensionnant les modèles prudemment (phi3-mini à 3,8B plutôt que llama3 à 8B) et en routant les requêtes lourdes vers des API cloud via LiteLLM quand le débit local est insuffisant.

**Un modèle à la fois est pragmatique.** Charger deux modèles différents simultanément sur un nœud CPU de 16 Go laisse une marge insuffisante pour le cache KV quand des requêtes concurrentes arrivent. Nous exécutons vLLM avec un seul modèle chargé et gérons la diversité des modèles via le routage LiteLLM vers des fournisseurs cloud.

**Le démarrage est lent.** vLLM sur CPU met 90–120 secondes à s'initialiser — il charge les poids du modèle en mémoire, quantifie le cas échéant, et réchauffe les kernels d'attention. Nous fixons `initialDelaySeconds: 120` sur la sonde de readiness. Pendant les rolling updates, les anciens pods doivent rester en vie jusqu'à ce que le nouveau pod soit prêt, ce qui signifie 2–3 minutes de chevauchement où les deux pods tournent et consomment de la mémoire.

---

## L'architecture après migration

```
Passerelle LiteLLM
      │
      ├── vLLM (fast-heron, CPU, Phi-3-mini) ← modèle affiné local, les données restent sur le cluster
      │
      ├── Groq             ← repli auto pour requêtes générales quand le local est saturé
      ├── DeepSeek         ← tâches de raisonnement
      ├── Mistral / GPT-4o ← palier premium
      └── Gemini / Claude  ← palier premium
```

vLLM gère l'inférence locale qui doit rester sur le cluster — le modèle de domaine affiné et toute requête où la souveraineté des données compte. Les fournisseurs cloud gèrent les requêtes généralistes et les requêtes de palier premium où la latence ou la capacité comptent plus que la localité.

LiteLLM route de façon transparente entre eux. Quand la clé d'un département atteint son budget cloud, les requêtes restent locales. Quand le local est saturé (profondeur de file > seuil via un ScaledObject KEDA), le proxy escalade vers le repli cloud. La couche applicative voit un unique endpoint d'API tout du long.

---

## Devriez-vous faire cela ?

L'inférence CPU avec vLLM est viable pour des modèles jusqu'à 4B paramètres sur du matériel avec 16 Go de RAM, quand vos exigences principales sont la souveraineté des données, la gestion correcte des requêtes concurrentes et l'observabilité de production — et que votre exigence secondaire est le débit.

Ce n'est pas le bon outil si les utilisateurs attendent des réponses sous la seconde, si vous devez servir des modèles 7B+ localement, ou si vous avez le budget pour ne serait-ce qu'un seul GPU grand public. Une RTX 3090 à 800 € vous donnerait 10 à 20× le débit d'un i7 de ThinkPad pour l'inférence LLM.

Mais si vous tournez sur du matériel grand public, avez une réelle exigence de souveraineté des données, et avez besoin d'un système que vous pouvez réellement exploiter — avec des métriques, avec des requêtes concurrentes, avec le support des adaptateurs LoRA — vLLM sur CPU est significativement meilleur qu'Ollama dans la même position.

La migration d'Ollama vers vLLM ne portait pas sur le GPU. Elle portait sur le remplacement d'un outil de développeur par un serveur de production. Le CPU se trouvait être le seul matériel disponible. L'amélioration était réelle quoi qu'il en soit.
