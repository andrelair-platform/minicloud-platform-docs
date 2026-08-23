---
slug: enterprise-ai-gateway-litellm
title: "Construire une passerelle IA d'entreprise sur Kubernetes : LiteLLM, modèles locaux et garde-fous zéro-confiance"
authors: [andrelair]
tags: [ai, llm, litellm, kubernetes, enterprise, mlops, self-hosted, data-sovereignty, presidio, langfuse, ollama, vllm, rgpd, gdpr]
date: 2026-08-08
description: "Comment construire une passerelle IA de production qui route entre modèles locaux et API cloud, applique des contrôles d'accès par département, retire les données personnelles avant qu'elles ne quittent votre réseau, et trace chaque appel — le tout derrière un unique endpoint compatible OpenAI."
---

La plupart des déploiements IA d'entreprise font tôt la même erreur d'architecture : donner à chaque équipe une clé d'API directe vers OpenAI ou Anthropic et considérer le travail fait. Le résultat est prévisible — aucune visibilité sur les coûts, aucun contrôle d'accès, aucune piste d'audit, et des données sensibles envoyées aux API cloud sans le moindre garde-fou.

Une vraie passerelle IA d'entreprise change la forme du problème. Au lieu de nombreuses équipes parlant à de nombreuses API, vous avez un seul endpoint qui gère le routage, la limitation de débit, l'expurgation des données personnelles, le cache et l'observabilité. Les équipes la consomment de la même manière, que le modèle tourne sur votre propre matériel ou sur le parc GPU d'un fournisseur cloud.

Cet article couvre la conception complète d'une telle passerelle, construite sur Kubernetes avec LiteLLM comme couche de proxy, Ollama et vLLM pour l'inférence locale, et Presidio pour la protection des données personnelles — avec une configuration réelle qui tourne en production.

{/* truncate */}

## Le problème de l'accès direct aux API

Quand les équipes se connectent directement aux API LLM cloud, quatre problèmes s'aggravent rapidement.

**Opacité des coûts.** Vous découvrez votre facture mensuelle à la fin du mois. À ce moment-là, le modèle coûteux que quelqu'un a utilisé pour un pipeline de test tourne depuis trois semaines.

**Aucune frontière de données.** Chaque prompt part vers une API externe, sauf si quelqu'un intervient activement. Pour les organisations traitant des données personnelles sous le RGPD, ou des données financières sous la surveillance de l'ACPR, ce n'est pas un choix de configuration — c'est un problème de conformité.

**Aucun contrôle d'accès.** La même clé d'API qui permet à un développeur de prototyper lui permet aussi de lancer des jobs batch automatisés consommant un million de tokens par heure. Aucune limite de dépense par département, aucun palier de modèle, aucune limite de débit.

**Aucune piste d'audit.** Quand quelque chose tourne mal — un prompt inapproprié, une sortie inattendue, un pic de coût — vous n'avez aucune trace de ce qui a été demandé, de ce qui a été répondu, ni de l'équipe responsable.

Une passerelle résout les quatre, et le coût d'en exploiter une est assez bas pour qu'il n'y ait aucune bonne raison de s'en passer.

---

## Vue d'ensemble de l'architecture

La passerelle s'interpose entre chaque consommateur d'IA (interfaces de chat, pipelines RAG, agents, scripts) et chaque fournisseur d'IA (modèles locaux, API cloud). Rien n'appelle un modèle directement.

```
Open WebUI ──► Passerelle LiteLLM (:4000)
Agents      ──►      │
Scripts     ──►      │
                     ├── Ollama primaire   (fast-heron,  :11434)  ← local d'abord
                     ├── Ollama secondaire (star-kitten, :11434)  ← local d'abord
                     ├── vLLM              (star-kitten, :8000)   ← haut débit
                     │
                     ├── Groq             (llama-3.1-8b-instant) ← repli auto #1
                     ├── DeepSeek         (deepseek-chat)        ← repli auto #2
                     ├── Mistral          (large, small)
                     ├── Anthropic        (claude-sonnet, haiku)
                     ├── OpenAI           (gpt-4o, gpt-4o-mini)
                     ├── Gemini           (gemini-2.5-flash)
                     └── NVIDIA NIM       (nemotron-70b, deepseek-r1)

LiteLLM ──► Cache Valkey    (:6379)    ← dédup de prompt exact, TTL 10 min
LiteLLM ──► Langfuse                ← trace chaque appel
LiteLLM ──► Postgres               ← clés virtuelles, suivi des dépenses
```

LiteLLM expose un unique endpoint compatible OpenAI. Chaque consommateur utilise la même API `/v1/chat/completions`, que la requête finisse sur une instance Ollama locale ou chez un fournisseur cloud. Faire passer une équipe de GPT-4o à Mistral Large ne nécessite aucun changement de code de leur côté — seulement un changement de configuration dans la passerelle.

---

## Routage local d'abord avec repli cloud automatique

Le principe central de routage est « local d'abord » : les requêtes vont vers les modèles on-premise par défaut et n'escaladent vers le cloud que lorsque l'inférence locale échoue.

```yaml
router_settings:
  routing_strategy: least-busy
  num_retries: 2
  timeout: 120
  cooldown_time: 60
  allowed_fails: 3
  fallbacks:
    - qwen3.5:4b:
        - groq-fallback
        - deepseek-chat
    - phi4-mini:
        - groq-fallback
        - deepseek-chat
```

`least-busy` répartit les requêtes entre backends selon le nombre d'appels en cours plutôt qu'en round-robin. Avec deux nœuds Ollama, les requêtes s'équilibrent naturellement vers le nœud le moins chargé.

Le disjoncteur (circuit breaker) est la pièce critique : après 3 échecs consécutifs, un backend est marqué dégradé pendant 60 secondes. Sans cela, un processus Ollama bloqué absorberait tout le budget de réessais de chaque requête entrante avant d'expirer. Avec cela, un nœud dégradé est contourné presque immédiatement et la requête réussit sur l'autre backend — ou sur Groq si les deux nœuds locaux sont tombés.

Certains modèles n'ont **aucun repli cloud, par conception** :

```yaml
# phi3-financial : modèle spécifique au domaine, aucun repli cloud
# Les prompts financiers ne doivent pas quitter le cluster
- model_name: phi3-financial
  litellm_params:
    model: ollama/phi3-financial
    api_base: http://ollama-primary.ai.svc.cluster.local:11434
```

Le modèle affiné spécifique au domaine, les modèles de vision et le modèle d'embedding sont uniquement locaux. La passerelle l'impose — il n'existe aucun chemin de code où un prompt financier atteint une API externe.

---

## Contrôle d'accès par département

Les clés virtuelles associent chaque département à un ensemble de contraintes : modèles autorisés, limites de débit en tokens, limites de débit en requêtes, et un plafond de budget mensuel.

Trois paliers couvrent différents profils de risque :

| Palier | Limite tokens | Limite requêtes | Budget mensuel | Accès aux modèles |
|---|---|---|---|---|
| **premium** | 200k TPM | 500 RPM | 100 $ | Tous les modèles, dont GPT-4o, Claude, Nemotron |
| **standard** | 100k TPM | 200 RPM | 30 $ | Modèles locaux + Groq, DeepSeek, Mistral Small, GPT-4o-mini |
| **basic** | 50k TPM | 100 RPM | 5 $ | Modèles locaux uniquement |

Chaque département reçoit sa propre clé, stockée dans Vault. Quand la clé d'un département atteint sa limite de budget, LiteLLM renvoie un HTTP 429 (`BudgetExceededError`) et la réinitialisation se produit automatiquement au début de la période de facturation suivante.

Les métadonnées de la clé — nom du département, palier, budget — transitent jusqu'à Langfuse et au dashboard de coûts Grafana. Vous pouvez voir, par département, combien il a dépensé, quel pourcentage de son budget est consommé, et quels modèles il utilise réellement.

C'est le genre de visibilité impossible avec des clés d'API directes. Quand votre équipe actuariat dépense 87 $ de son budget mensuel de 100 $ dès la première semaine en routant tout via GPT-4o, vous le savez immédiatement — et vous pouvez avoir la conversation sur le choix des modèles avant que le dépassement ne survienne.

---

## Protection des données personnelles avant qu'elles ne quittent votre réseau

Le garde-fou le plus important est celui qui s'exécute avant chaque requête à destination du cloud : un expurgateur de données personnelles propulsé par Microsoft Presidio.

Presidio tourne comme deux services internes au cluster — un analyseur qui détecte les types d'entités personnelles et un anonymiseur qui les remplace par des espaces réservés typés. LiteLLM les appelle comme garde-fou `pre_call` avant de transférer tout prompt à une API externe.

```
"Client jean.dupont@acme.fr, tél +33612345678, veut un devis pour le contrat 78441"
        ↓  garde-fou pre_call Presidio
"Client <EMAIL_ADDRESS>, tél <PHONE_NUMBER>, veut un devis pour le contrat <IN_PAN>"
        ↓  envoyé au modèle cloud (GPT-4o, Claude, Mistral, etc.)
```

Les modèles locaux ne sont pas affectés — ils reçoivent le prompt original car la donnée ne quitte jamais le cluster. Les modèles cloud ne reçoivent que la version anonymisée.

Le garde-fou fonctionne en `default_on: true`, c'est-à-dire actif sur chaque requête sans aucune adhésion requise. Les développeurs n'ont pas besoin de savoir qu'il existe. Il s'exécute, simplement.

Une décision de périmètre importante : le garde-fou s'applique uniquement à l'**entrée**. Il n'anonymise pas les réponses des modèles. C'est intentionnel. La détection d'entités de Presidio est agressive — elle classera les noms de pays, les personnages historiques et les dates respectivement en `<LOCATION>`, `<PERSON>` et `<DATE_TIME>`. Une réponse à une question de culture générale deviendrait illisible. L'objectif de conformité est de protéger les données utilisateur envoyées *vers* les fournisseurs cloud, pas de transformer ce qui revient.

Un second garde-fou tourne en parallèle avec la bibliothèque `detect-secrets`, qui scanne chaque prompt à la recherche de motifs d'identifiants — clés d'API, tokens, chaînes de connexion. Les prompts contenant de vrais identifiants à haute confiance sont rejetés avec un HTTP 400 avant d'atteindre le moindre modèle.

---

## Cache de prompts pour la vitesse et le coût

Des prompts identiques — même modèle, même contenu de message — renvoient une réponse en cache depuis Valkey (compatible Redis) sans passer par l'inférence.

La différence de performance est significative : un hit de cache à 80 ms contre un appel à froid à 2 500 ms sur un modèle local, ou 600 ms sur une API cloud. Pour les pipelines RAG qui appellent le même modèle à répétition avec un contexte de récupération similaire, le taux de hit peut atteindre 40 à 60 %.

```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: litellm-cache.ai.svc.cluster.local
    port: 6379
    ttl: 600
    namespace: litellm
```

Le TTL de 10 minutes est un compromis délibéré. Il est assez long pour capturer les requêtes répétées d'une session interactive mais assez court pour qu'un contexte évolutif — un document en cours d'édition, un jeu de données mis à jour — ne renvoie pas de réponses périmées plus de quelques minutes.

---

## Observabilité complète : Langfuse + Grafana

Chaque requête produit une trace Langfuse contenant le modèle utilisé, le décompte de tokens, la latence, l'estimation de coût, la clé du département, et si des garde-fous ont été déclenchés. La trace est disponible au niveau du span — vous pouvez inspecter le prompt brut, la version masquée transférée, et la réponse.

Pour le reporting des coûts, un dashboard Grafana interroge directement les tables de dépenses PostgreSQL de LiteLLM. Huit panneaux couvrent les métriques qui comptent vraiment en production :

- Dépenses totales et usage de tokens sur les dernières 24 heures
- Utilisation du budget par département avec seuils de couleur (vert / orange / rouge)
- Répartition des tokens et des requêtes par modèle sur les 30 derniers jours
- Une piste d'audit des 50 dernières requêtes avec attribution par département

Le tableau d'utilisation du budget est celui que l'on partage avec la direction. Il montre en un coup d'œil si un département approche de sa limite — et permet des conversations éclairées sur les ajustements de quota avant que les limites ne soient atteintes.

---

## Ce qui fait passer la démarche passerelle à l'échelle

La propriété la plus précieuse de cette architecture est qu'**ajouter un nouveau modèle ne nécessite aucun changement chez les consommateurs**.

Quand un nouveau modèle Ollama est téléchargé, il apparaît dans la liste des modèles de LiteLLM et devient immédiatement disponible pour toute équipe au bon palier. Quand un fournisseur cloud sort un meilleur modèle, le remplacement se fait en un seul changement de configuration — les limites de débit par département, les garde-fous de données personnelles et le suivi des coûts continuent de fonctionner exactement comme avant.

L'inverse est aussi vrai : retirer un modèle, changer de fournisseur ou ajuster le budget d'un département se font tous de manière centralisée, avec effet immédiat, sans toucher au code d'aucun consommateur.

C'est ce qui distingue une passerelle IA d'une collection de clés d'API. Les clés vous donnent l'accès. La passerelle vous donne le contrôle.

---

## L'exécuter sur Kubernetes

Tous les composants tournent dans le namespace `ai`, gérés par une unique application ArgoCD. La passerelle elle-même est sans état — elle peut être mise à l'échelle horizontalement derrière un service ClusterIP. Les seuls composants avec état sont PostgreSQL (pour le suivi des dépenses et les clés virtuelles) et Valkey (pour le cache de prompts), tous deux sur des volumes persistants Longhorn.

La configuration des NetworkPolicies mérite d'être notée : seuls les pods LiteLLM ont un egress vers le port 443. Ollama et Open WebUI sont bloqués d'internet par politique. Cela signifie que même si un bug applicatif contournait la passerelle, il n'existe aucun chemin pour qu'Ollama contacte directement une API externe.

```yaml
# Seuls les pods litellm peuvent joindre les API cloud externes
networkPolicy:
  name: allow-litellm-cloud-egress
  podSelector:
    matchLabels:
      app: litellm
  egress:
    - ports:
        - port: 443
```

Pour les organisations qui doivent démontrer des contrôles de données — que ce soit à des auditeurs, au juridique ou à un DPO — ce type d'application au niveau réseau est bien plus solide qu'une promesse au niveau applicatif.

---

La configuration complète — config du proxy LiteLLM, définitions des garde-fous, NetworkPolicies, intégration Langfuse, dashboard Grafana — est documentée dans la section AI Gateway de la documentation de la plateforme.
