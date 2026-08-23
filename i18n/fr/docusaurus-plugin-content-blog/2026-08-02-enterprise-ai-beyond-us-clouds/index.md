---
slug: enterprise-ai-beyond-us-clouds
title: "L'IA d'entreprise sans Amazon, Microsoft ni Google : une perspective européenne"
authors: [andrelair]
tags: [ai, enterprise, data-sovereignty, mistral, vllm, litellm, rgpd, gdpr, secnumcloud, mlops, kubernetes]
date: 2026-08-02
description: "Le conseil standard est Bedrock, Azure OpenAI ou Vertex AI. Mais qu'en est-il des organisations qui ne peuvent pas ou ne veulent pas envoyer leurs données vers des serveurs américains ? Voici le tableau complet."
---

Chaque article sur l'IA d'entreprise se termine de la même façon. Utilisez Amazon Bedrock. Utilisez Azure OpenAI Service. Utilisez Google Vertex AI. Ces plateformes offrent conformité de niveau entreprise, confidentialité des données et garanties de non-entraînement.

Le conseil est correct — pour les organisations qui peuvent utiliser une infrastructure cloud américaine.

Un nombre important et croissant d'organisations ne le peut pas. Certaines à cause du coût. Beaucoup à cause de la réglementation. Quelques-unes parce que leurs données ne peuvent littéralement pas franchir une frontière selon la loi qui régit leur secteur.

Cet article s'adresse à ces organisations. Il couvre deux problèmes distincts — la souveraineté des données et le coût — et les options concrètes disponibles pour chacun.

{/* truncate */}

## Pourquoi le conseil standard échoue en Europe

La recommandation « utilisez Bedrock / Azure OpenAI / Vertex AI » résout un vrai problème : elle vous donne des SLA d'entreprise, des DPA et des garanties de non-entraînement d'une contrepartie connue. Pour une entreprise américaine, ou une multinationale à l'aise avec les clauses contractuelles types, c'est un choix raisonnable.

Mais elle présume discrètement trois choses que beaucoup d'organisations européennes ne peuvent pas accepter :

**1. Vos données seront traitées aux États-Unis.**

Même avec des options de résidence de données dans l'UE, vos données sont traitées par une entreprise américaine soumise au droit américain. Sous le Cloud Act (2018), les autorités américaines peuvent contraindre les fournisseurs cloud américains à remettre des données stockées n'importe où dans le monde — y compris des centres de données situés en France ou en Allemagne. Un DPA et des CCT fournissent une protection contractuelle. Ils ne fournissent pas de garanties techniques.

**2. Les analyses d'impact de transfert sont une charge gérable.**

Sous l'arrêt Schrems II de la CJUE, tout transfert de données personnelles vers un pays tiers requiert une analyse d'impact de transfert démontrant que les lois de surveillance du pays de destination ne compromettent pas les protections RGPD. Pour les équipes achats des organisations de taille moyenne, ce n'est pas une case à cocher — c'est un exercice juridique de plusieurs semaines que beaucoup renoncent simplement à entreprendre.

**3. Le prix par token est acceptable à l'échelle.**

À faible volume, les API cloud sont bon marché. À l'échelle entreprise — des dizaines de milliers de requêtes d'employés par jour, des pipelines RAG traitant des milliers de documents, des workflows automatisés appelant des modèles en boucle — le coût s'accumule vite.

GPT-4o à 2,50 $ par million de tokens d'entrée ne semble pas cher jusqu'à ce que 500 employés l'utilisent quotidiennement pour résumer des documents. À 2 000 tokens par requête, cela fait un million de tokens par jour, 2,50 $ par jour — gérable. Ajoutez la récupération RAG (encore 2 000 tokens par requête pour le contexte récupéré) et vous êtes à 5 $/jour, 1 825 $/an, rien que pour l'entrée de GPT-4o. Multipliez par les schémas d'usage réels d'entreprise et multipliez encore pour tout workload qui bénéficie d'un modèle plus capable.

---

## Problème 1 : la souveraineté des données

### Le paysage réglementaire en France

Les organisations françaises et européennes font face à un ensemble de exigences en couches selon leur secteur :

**RGPD**
La base pour toute organisation traitant des données personnelles de résidents de l'UE. Exige que les données transférées hors de l'UE aillent vers un pays offrant des protections adéquates, ou soient couvertes par des CCT plus une analyse d'impact de transfert. Les données personnelles des salariés, clients ou citoyens ne peuvent pas être envoyées vers un pays tiers sans cette base légale.

**ACPR (banque et assurance)**
L'Autorité de contrôle prudentiel et de résolution supervise les banques et assureurs français. Ses lignes directrices traitent l'externalisation cloud comme un risque opérationnel significatif. Bien que l'ACPR n'interdise pas d'emblée les fournisseurs cloud américains, les institutions doivent démontrer qu'elles peuvent quitter un fournisseur cloud sans perturbation et que les données sensibles sont protégées contre l'accès de pays tiers. Mistral AI, en tant qu'entreprise française, contourne la plupart de ces préoccupations sans requérir d'analyse d'impact de transfert.

**HDS (hébergement de données de santé)**
Les données de santé en France doivent être hébergées par un prestataire certifié HDS. Les fournisseurs cloud américains peuvent obtenir la certification HDS pour leurs centres de données français, mais l'exposition au Cloud Act demeure. Pour les workloads de santé les plus sensibles, l'auto-hébergement sur une infrastructure française certifiée élimine le risque résiduel.

**SecNumCloud**
Le cadre de qualification de l'ANSSI pour les fournisseurs cloud traitant des données gouvernementales sensibles et des infrastructures critiques. Actuellement, seuls **OVHcloud** et **Outscale** (une filiale de Dassault Systèmes) détiennent cette qualification. AWS, Azure et Google Cloud ne se qualifient pas et ne le peuvent légalement pas sous le cadre actuel, car la qualification requiert que le fournisseur ne soit pas soumis à un droit non-européen susceptible de primer sur ses obligations de protection des données.

### Les alternatives européennes qui existent réellement

| Fournisseur | Pays | Historique réglementaire | Modèles disponibles |
|----------|---------|-----------------|-----------------|
| **Mistral AI** | 🇫🇷 France | Entreprise française, conforme RGPD, aucune exposition au droit américain, API avec DPA disponible | Mistral 7B, Mistral NeMo, Mistral Large, Codestral |
| **OVHcloud AI Endpoints** | 🇫🇷 France | Qualifié SecNumCloud, centres de données certifiés HDS, les données ne quittent jamais la France | Modèles ouverts (Llama, Mistral, etc.) via endpoints hébergés |
| **Aleph Alpha** | 🇩🇪 Allemagne | Entreprise allemande, conception DSGVO-first, déployable on-premise | Famille Luminous (multilingue, forte en allemand/français) |
| **Scaleway** | 🇫🇷 France | Infrastructure française, tarif de location GPU compétitif | Apportez votre propre modèle via instances GPU ou endpoints managés |

### Mistral AI : la réponse par défaut pour les entreprises françaises

Mistral AI, fondée à Paris en 2023, est la réponse la plus claire à la question de souveraineté des données pour la plupart des organisations françaises.

**Le chemin API :** `la-plateforme.mistral.ai` fournit une API standard compatible OpenAI adossée à une infrastructure française, sous un DPA français, sans analyse d'impact de transfert requise. Mistral Small (classe 7B) est à 0,10 € par million de tokens — comparable au tarif de GPT-3.5-Turbo — avec Mistral Large disponible à 2 € par million pour les tâches de raisonnement complexes.

**Le chemin auto-hébergé :** Mistral publie ouvertement les poids de ses modèles plus petits (Mistral 7B, Mistral NeMo 12B, Codestral 22B). Vous pouvez télécharger les poids, les exécuter sur votre propre infrastructure GPU, et vos prompts ne touchent jamais aucun serveur externe. Pas d'API. Pas de DPA nécessaire. Pas d'analyse d'impact de transfert. Aucune donnée ne quitte votre réseau.

Le pitch à un responsable conformité d'entreprise française est simple : *« Le modèle tourne sur nos serveurs en France. Voici le journal d'egress réseau montrant zéro connexion sortante vers un quelconque fournisseur d'IA pendant ces requêtes. »* C'est un niveau d'assurance fondamentalement différent de « nous avons un DPA avec Microsoft ».

---

## Problème 2 : le coût

### Le vrai coût des API cloud à l'échelle

Le tarif par token des API d'IA cloud a chuté de façon spectaculaire ces deux dernières années, ce qui rend l'argument du coût plus difficile à faire à petite échelle. Mais les déploiements d'entreprise n'opèrent pas à petite échelle.

Considérez une équipe finance de 200 personnes utilisant l'IA pour :
- Briefings de portefeuille quotidiens : 5 000 tokens par utilisateur × 200 utilisateurs = 1 M tokens/jour
- Analyse de documents : 20 000 tokens par document × 50 documents/jour = 1 M tokens/jour
- Requêtes de chatbot interne : 2 000 tokens × 500 requêtes/jour = 1 M tokens/jour

À 3 M tokens/jour, avec GPT-4o-mini (0,15 $/1 M entrée + 0,60 $/1 M sortie, environ 0,40 $/1 M mélangé) :

**Coût mensuel : 3 M × 30 × 0,40 $ / 1 M = 36 $/mois**

C'est remarquablement bon marché. Passez à une organisation de 2 000 personnes avec un usage similaire :

**Coût mensuel : 360 $/mois**

Toujours bon marché. Utilisez maintenant GPT-4o au lieu de mini (2,50 $ mélangé par million) :

**Coût mensuel à 2 000 utilisateurs : 2 250 $/mois = 27 000 $/an**

Ajoutez un pipeline RAG qui double la consommation de tokens par requête. Ajoutez un agent de revue de code tournant sur chaque pull request. Ajoutez la classification automatique de documents sur un système de gestion documentaire avec 10 000 nouveaux documents par mois. Les chiffres croissent avec votre ambition, et à un certain point l'auto-hébergement devient l'option la moins chère.

### Le calcul de l'auto-hébergement

Un seul GPU NVIDIA A100 80 Go coûte environ 3 €/heure sur OVHcloud bare-metal. En exécutant Mistral 7B Q4_K_M (quantifié en 4-bit) :

- **Débit :** environ 400 tokens/seconde à pleine capacité
- **Coût quotidien :** 72 € (24 heures à 3 €/h)
- **Capacité quotidienne :** 400 tok/s × 86 400 s = 34,5 millions de tokens

Au même usage de 3 M tokens/jour que l'exemple ci-dessus : **votre GPU est inactif 91 % du temps.** Vous payez 72 €/jour pour générer des tokens qui coûtent 1,20 €/jour sur GPT-4o-mini.

Le point de croisement avec GPT-4o-mini est d'environ 18 M tokens/jour — ce qui requiert une grande organisation avec une forte intégration d'IA. En dessous, les API cloud sont moins chères sur le pur coût du token.

**Mais le coût du token n'est pas la seule variable.** Une fois que vous ajoutez :
- Les exigences de souveraineté des données (non négociables pour les secteurs réglementés)
- La capacité d'affiner sur des données propriétaires sans envoyer ces données à un fournisseur
- Un coût prévisible quels que soient les pics d'usage
- Aucune limite de débit ni épuisement de quota pendant les pics de demande

…le calcul de l'auto-hébergement bascule significativement en faveur de la possession du GPU.

---

## L'architecture qui fait fonctionner les deux

La bonne nouvelle est que vous n'avez pas à choisir définitivement entre API cloud et modèles auto-hébergés. La bonne architecture vous permet d'utiliser les deux simultanément, de basculer de l'un à l'autre sans changement d'application, et d'ajouter de nouveaux backends au fur et à mesure qu'ils deviennent pertinents.

Cette architecture est un **proxy agnostique du modèle** — un endpoint unique que vos applications appellent, qui route les requêtes vers le backend le plus approprié.

[LiteLLM](https://github.com/BerriAI/litellm) est l'implémentation open-source de ce motif. Il accepte les requêtes au format OpenAI et les transfère vers n'importe quel backend : OpenAI, Anthropic, Mistral, Groq, une instance vLLM auto-hébergée, ou tout autre endpoint compatible OpenAI.

```yaml
# La model_list complète dans un config.yaml de LiteLLM
model_list:

  # API cloud européenne — Mistral, entreprise française, résidence des données UE
  - model_name: mistral-small
    litellm_params:
      model: mistral/mistral-small-latest
      api_key: os.environ/MISTRAL_API_KEY

  # vLLM auto-hébergé sur votre propre GPU — aucune donnée ne quitte le cluster
  - model_name: mistral-7b-local
    litellm_params:
      model: openai/mistralai/Mistral-7B-Instruct-v0.3
      api_base: http://vllm.ai.svc.cluster.local:8000/v1
      api_key: token-internal

  # Repli cloud pour la capacité de pointe
  - model_name: groq-fast
    litellm_params:
      model: groq/llama-3.1-8b-instant
      api_key: os.environ/GROQ_API_KEY
```

Votre application appelle un endpoint — `https://litellm.yourdomain.com/v1/chat/completions` — et spécifie un nom de modèle. Le proxy gère le routage, les réessais, les replis et la limitation de débit. Vous pouvez déplacer le trafic de Groq vers Mistral vers votre propre GPU sans toucher une seule ligne de code d'application.

### Ce qui reste identique quel que soit le backend

Quand vous routez via une couche de proxy, toute la pile d'observabilité et de gouvernance s'applique uniformément à chaque backend :

- **Traçage Langfuse** — chaque requête journalisée avec utilisateur, modèle, latence, décompte de tokens et coût
- **Masquage PII Presidio** — prompts expurgés avant d'atteindre le moindre fournisseur
- **Limitation de débit** — budgets de tokens par équipe ou par rôle imposés au proxy
- **RBAC** — clés virtuelles par département, avec allowlists de modèles par clé
- **Métriques Prometheus** — taux de requêtes, taux d'erreurs, coût par modèle par équipe

Basculez de Groq vers votre propre GPU : la trace Langfuse apparaît toujours. Le masquage PII tourne toujours. La limite de débit s'applique toujours. Le dashboard de coûts se met toujours à jour (avec zéro pour les requêtes auto-hébergées, puisqu'il n'y a pas de facturation de tokens).

---

## Le pitch pour l'entreprise française

Si vous êtes consultant ou platform engineer travaillant avec des organisations françaises, la conversation se déroule souvent ainsi :

**Client :** « Nous voulons utiliser l'IA mais notre équipe juridique dit que nous ne pouvons pas envoyer les données clients à ChatGPT. »

**Conseil standard :** « Utilisez Azure OpenAI avec résidence des données UE et un DPA. »

**Meilleure réponse :** « Nous faisons tourner Mistral 7B sur une infrastructure OVHcloud SecNumCloud à Gravelines, en France. Vos données ne quittent jamais le sol français, ne touchent jamais un serveur américain, et nous pouvons le prouver avec des journaux d'egress. Quand vous avez besoin d'un modèle plus puissant pour un raisonnement complexe, nous routons vers Mistral Large — toujours une infrastructure française, toujours le même DPA. »

La différence clé : la meilleure réponse donne au client une *garantie technique* plutôt qu'une *garantie contractuelle*. Un DPA vous dit ce que le fournisseur promet de faire avec vos données. Les journaux réseau vous disent ce qui s'est réellement passé.

Pour l'ACPR, pour la CNIL, et pour toute équipe de conformité ayant traversé une analyse d'impact de transfert Schrems II, la différence entre « nous avons des protections contractuelles » et « nous avons zéro connexion sortante vers des serveurs étrangers » est très significative.

---

## Par où commencer

| Votre situation | Chemin recommandé |
|----------------|-----------------|
| Secteur réglementé (banque, assurance, santé), les données ne peuvent pas quitter la France | API Mistral via `la-plateforme.mistral.ai` pour un démarrage rapide ; vLLM auto-hébergé sur GPU OVHcloud pour la souveraineté complète |
| Gouvernement ou OIV, SecNumCloud requis | OVHcloud AI Endpoints (qualifié) ; ou auto-hébergé sur OVHcloud ou Outscale bare-metal |
| Le coût est la contrainte principale, pas d'exigence dure de souveraineté | Groq (offre gratuite, rapide) + Mistral Small (bon marché, UE) + auto-hébergé quand le volume justifie le matériel |
| Vouloir le contrôle total, aucune dépendance externe | vLLM sur votre propre infrastructure GPU avec des poids Mistral ou Llama ouverts |
| Débuter, incertain | API Mistral + proxy LiteLLM ; ajouter des backends auto-hébergés quand les exigences se clarifient |

Le motif qui fonctionne à toutes les échelles : bâtir sur un proxy agnostique du modèle dès le premier jour. Votre application ne sait pas si le modèle tourne à Paris, à Francfort ou dans la salle serveur du couloir — et elle ne devrait pas avoir besoin de le savoir.
