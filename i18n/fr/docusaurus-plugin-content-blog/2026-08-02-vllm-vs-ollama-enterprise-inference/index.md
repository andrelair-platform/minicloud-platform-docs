---
slug: vllm-vs-ollama-enterprise-inference
title: "Pourquoi les entreprises devraient exécuter vLLM plutôt qu'Ollama pour l'inférence IA"
authors: [andrelair]
tags: [ai, llm, vllm, ollama, inference, kubernetes, enterprise, mlops, self-hosted]
date: 2026-08-02
description: "Ollama est un excellent outil de développeur. vLLM est ce que vous exécutez quand de vrais utilisateurs attendent. Voici exactement pourquoi la différence compte — et ce qui change quand vous passez de l'un à l'autre."
---

Ollama est la façon dont la plupart des équipes exécutent un grand modèle de langage localement pour la première fois. Vous l'installez en cinq minutes, lancez `ollama pull mistral`, et vous avez une API fonctionnelle. Cela ressemble à de la magie.

Puis vous essayez de servir dix utilisateurs à la fois. Ou cent. Ou vous devez auditer chaque requête pour la conformité. Ou votre équipe juridique demande où vont les données. C'est là que vous réalisez qu'Ollama a été conçu pour tout autre chose.

{/* truncate */}

## Ollama est un outil de développeur

Ce n'est pas une critique. Ollama est réellement excellent pour ce pour quoi il est conçu : rendre trivial pour un développeur seul l'exécution locale d'un modèle à des fins d'expérimentation, de prototypage et d'exploration. La gestion des modèles, la CLI simple, le serveur d'API en une commande — tout est optimisé pour l'expérience d'une personne sur une machine.

Le problème commence quand vous essayez de porter cet outil en production.

### Une requête à la fois

Ollama traite les requêtes séquentiellement. Si deux utilisateurs envoient un prompt au même moment, le second attend que le premier ait entièrement terminé avant qu'un seul token ne soit généré pour lui.

Sur un GPU rapide, cela peut ajouter une ou deux secondes de latence. Sur un cluster CPU — là où la plupart des déploiements auto-hébergés tournent réellement — un modèle 7B peut mettre 30 à 60 secondes à générer une réponse. Avec un traitement séquentiel, dix utilisateurs concurrents signifient que l'utilisateur dix attend jusqu'à dix minutes.

Ce n'est pas un problème de configuration. C'est un choix de conception approprié à son cas d'usage cible : un développeur qui envoie une requête à la fois.

### Une mémoire qui ne peut pas être partagée

Chaque requête Ollama active réserve sa propre tranche de mémoire GPU ou système pour le cache clé-valeur — la structure de données qui stocke la « mémoire » du modèle de la conversation en cours. Quand la requête se termine, cette mémoire est libérée.

Il n'existe aucun mécanisme pour qu'Ollama laisse les requêtes partager intelligemment la mémoire GPU, pagine les contextes inactifs, ou réutilise les états d'attention en cache entre requêtes partageant le même préfixe. Chaque requête repart de zéro.

### Aucune observabilité de production

Ollama n'expose aucune métrique Prometheus, aucun log de requête structuré, aucun histogramme de latence, aucun compteur de débit de tokens. Vous ne pouvez pas construire un dashboard SLO autour. Vous ne pouvez pas alerter sur la latence p99 ni configurer un autoscaling basé sur la profondeur de file. Vous ne pouvez pas auditer quel utilisateur a envoyé quel prompt.

Pour un laptop personnel, rien de tout cela ne compte. Pour un système traitant les requêtes des employés d'une entreprise, tout cela compte.

---

## vLLM est un moteur d'inférence

vLLM a été construit à UC Berkeley et est maintenu par une équipe dont le seul objectif est de servir efficacement des modèles de langage en production. Chaque décision de conception est orientée autour du débit, de la latence et de l'utilisation des ressources sous charge concurrente réelle.

### Batching continu

C'est la différence la plus importante.

Les serveurs d'inférence traditionnels (dont Ollama) traitent un lot de requêtes, attendent qu'elles se terminent toutes, puis démarrent le lot suivant. Cela signifie que les requêtes rapides perdent du temps à attendre les lentes du même lot.

vLLM utilise le **batching continu** (aussi appelé ordonnancement au niveau itération). Dès qu'une requête du lot courant termine de générer un token, une nouvelle requête de la file prend immédiatement sa place. Le GPU n'attend jamais. Chaque cycle de calcul est consacré à générer des tokens pour quelqu'un.

Le résultat pratique : sous charge concurrente, vLLM sert entre 10 et 50 fois plus de tokens par seconde qu'un serveur séquentiel sur le même matériel. Ce n'est pas du marketing — c'est le résultat mesuré du remplacement des frontières de lot par un ordonnancement continu.

```
Ollama (séquentiel) :
  Utilisateur 1: [========== 8s ==========]
  Utilisateur 2:                            [========== 8s ==========]
  Utilisateur 3:                                                       [== 8s ==]
  Temps total pour 3 utilisateurs : 24s

vLLM (batching continu) :
  Utilisateur 1: [========== 8s ==========]
  Utilisateur 2:     [========== 8s ==========]
  Utilisateur 3:         [========== 8s ==========]
  Temps total pour 3 utilisateurs : ~10s
```

### PagedAttention

Le cache clé-valeur d'une longue conversation peut faire plusieurs gigaoctets. Le gérer naïvement — allouer un grand bloc contigu par requête, le conserver pour toute la durée — gaspille l'essentiel de la mémoire allouée la plupart du temps.

vLLM implémente **PagedAttention** : il traite le cache KV comme la mémoire virtuelle d'un système d'exploitation, le divisant en pages de taille fixe et n'allouant que les pages réellement nécessaires à chaque étape de décodage. Les pages des requêtes terminées sont immédiatement récupérées et réutilisées.

Le résultat est que vLLM peut servir trois à quatre fois plus de conversations concurrentes dans la même mémoire GPU qu'une implémentation naïve. Sur un GPU de 24 Go exécutant un modèle 7B, la différence entre gaspiller et paginer efficacement cette mémoire, c'est la différence entre quatre utilisateurs concurrents et seize.

### API compatible OpenAI — identique à ce que vous utilisez déjà

vLLM expose exactement la même API HTTP qu'OpenAI : `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`. Si votre application appelle déjà l'API OpenAI, elle appelle vLLM sans aucun changement de code.

Dans une configuration de proxy LiteLLM, passer d'un modèle cloud à une instance vLLM auto-hébergée est un seul changement de config :

```yaml
# Avant : API cloud
- model_name: qwen2.5:7b
  litellm_params:
    model: groq/llama-3.1-8b-instant
    api_key: os.environ/GROQ_API_KEY

# Après : vLLM auto-hébergé — même proxy, même surface d'API, aucun changement d'application
- model_name: qwen2.5:7b
  litellm_params:
    model: openai/Qwen/Qwen2.5-7B-Instruct
    api_base: http://vllm.ai.svc.cluster.local:8000/v1
    api_key: token-local
```

Tous les garde-fous, le traçage Langfuse, le masquage PII et la limitation de débit continuent de fonctionner à l'identique.

### Observabilité de niveau production d'emblée

vLLM expose un endpoint Prometheus `/metrics` qui inclut :

| Métrique | Ce qu'elle vous indique |
|--------|-------------------|
| `vllm:num_requests_running` | Requêtes concurrentes actives |
| `vllm:num_requests_waiting` | Profondeur de file — indicateur avancé de saturation |
| `vllm:gpu_cache_usage_perc` | Utilisation du cache KV — à 90 %, il vous faut plus de mémoire |
| `vllm:time_to_first_token_seconds` | Time-to-first-token p50/p99 — la métrique de latence côté utilisateur |
| `vllm:request_success_total` | Taux de succès des requêtes par modèle |
| `vllm:num_tokens_generated` | Débit de tokens |

Vous pouvez construire un dashboard Grafana complet, configurer des alertes SLO, et câbler l'autoscaling depuis ces métriques. Avec Ollama, vous ne pouvez pas.

### Parallélisme de tenseurs multi-GPU

Si vous exécutez un modèle qui ne tient pas dans la mémoire d'un seul GPU, vLLM distribue automatiquement les poids du modèle sur plusieurs GPU via le parallélisme de tenseurs. Vous fixez `tensor_parallel_size: 2` et le modèle 70B qui a besoin de 40 Go tient sur deux cartes de 24 Go.

Ollama ne supporte pas cela.

---

## Les exigences d'entreprise que vLLM satisfait

Au-delà de la performance brute, vLLM satisfait des exigences qui apparaissent dans les checklists d'achat d'entreprise et les audits de sécurité.

### Souveraineté des données

Quand vLLM tourne à l'intérieur de votre cluster Kubernetes, aucune donnée ne quitte votre réseau. Prompts, complétions, identifiants d'utilisateur — rien de tout cela ne touche une API externe. Vous pouvez le démontrer avec des NetworkPolicies et des journaux d'egress, ce qui est exactement ce qu'un RSSI ou un responsable conformité ACPR français demandera.

Les API cloud — même celles de palier entreprise avec des DPA — vous obligent à faire confiance à l'infrastructure du fournisseur. vLLM auto-hébergé supprime entièrement cette dépendance.

### Piste d'audit

vLLM journalise chaque requête avec le décompte de tokens, la latence et l'ID du modèle. Alimenter votre pile d'observabilité avec ces logs (Loki, Elasticsearch) vous donne un journal d'audit complet : quel utilisateur a envoyé quoi, quand, combien de temps cela a pris, combien de tokens ont été consommés.

Pour les industries réglementées (finance, assurance, santé), la capacité à produire ce journal à la demande est souvent une exigence légale.

### Aucun verrouillage fournisseur

vLLM exécute n'importe quel modèle Hugging Face — Mistral, Llama, Qwen, Phi, Gemma, Falcon, DeepSeek. Vous changez de modèle en changeant l'argument `model`. Vous n'êtes lié ni à la sélection de modèles d'un fournisseur commercial, ni à ses changements de prix, ni à son calendrier de dépréciation d'API.

### Intégration RBAC

Le mécanisme de clé d'API de vLLM s'intègre à votre IAM existant. Dans un déploiement Kubernetes derrière LiteLLM, vous ajoutez une clé virtuelle par équipe ou rôle, fixez des limites de débit et des allowlists de modèles par clé, et les imposez à la couche proxy — le tout sans toucher à la configuration de vLLM.

---

## Quand Ollama a encore du sens

Ollama n'est pas obsolète. Il reste le bon outil pour :

- **Un développeur exécutant des modèles localement** sur un laptop pendant le développement
- **Explorer un nouveau modèle** avant de décider de le déployer en production
- **Une petite équipe** (< 5 personnes) sans exigence de requêtes concurrentes
- **Du matériel CPU-only** où vous privilégiez la facilité d'installation au débit

Dès que vous avez plus d'un utilisateur, une exigence de conformité ou un objectif de débit, vous l'avez dépassé.

---

## Déploiement sur Kubernetes

Un déploiement vLLM minimal sur Kubernetes avec un seul GPU ressemble à ceci :

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm
  namespace: ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm
  template:
    metadata:
      labels:
        app: vllm
    spec:
      containers:
        - name: vllm
          image: vllm/vllm-openai:latest
          args:
            - --model
            - Qwen/Qwen2.5-7B-Instruct
            - --tensor-parallel-size
            - "1"
            - --max-model-len
            - "4096"
            - --served-model-name
            - qwen2.5:7b
          resources:
            limits:
              nvidia.com/gpu: "1"
              memory: 20Gi
            requests:
              nvidia.com/gpu: "1"
              memory: 16Gi
          ports:
            - containerPort: 8000
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 60
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: vllm
  namespace: ai
spec:
  selector:
    app: vllm
  ports:
    - port: 8000
      targetPort: 8000
```

Ajoutez un ServiceMonitor et Prometheus scrape `/metrics`. Ajoutez une entrée LiteLLM et vos applications existantes y routent de façon transparente. La migration de l'API cloud vers l'inférence on-premise est un changement de config d'une ligne.

---

## Résumé

| | Ollama | vLLM |
|---|---|---|
| Cas d'usage cible | Laptop de développeur | Service de production |
| Requêtes concurrentes | Séquentiel (1 à la fois) | Batching continu (N à la fois) |
| Gestion du cache KV | Allocation par requête | PagedAttention (pages partagées) |
| Débit vs Ollama | 1× | 10–50× sous charge |
| Métriques Prometheus | Aucune | Suite d'histogrammes complète |
| Multi-GPU | Non | Parallélisme de tenseurs |
| API compatible OpenAI | Oui | Oui |
| Souveraineté des données | Oui (local) | Oui (local) |
| Journalisation d'audit | Aucune | Journal de requêtes complet |
| Prêt pour la production | Non | Oui |

Ollama est la façon dont vous démarrez. vLLM est la façon dont vous passez à l'échelle. La bonne nouvelle : si vous avez bâti votre application sur une API compatible OpenAI (directement ou via un proxy comme LiteLLM), basculer entre eux est un changement de configuration, pas une réécriture.
