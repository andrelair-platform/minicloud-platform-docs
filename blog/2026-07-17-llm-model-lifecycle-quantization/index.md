---
slug: llm-model-lifecycle-quantization
title: "Un modèle sort de l'entraînement à 28 Go. Tu le télécharges à 4.7 Go. Qui a fait la compression ?"
authors: [andrelair]
tags: [ai, llm, quantization, ollama, fine-tuning, mlops, open-source]
date: 2026-07-17
description: "La quantization ne sert pas qu'à réduire la RAM. Derrière cette technique, il y a trois objectifs concrets : démocratiser l'accès, accélérer l'inférence, et permettre le déploiement privé. Et entre le modèle sorti du labo et celui qui tourne sur ton cluster, il s'est passé beaucoup de choses."
---

Un modèle sort de l'entraînement à 28 Go. Tu le télécharges à 4.7 Go. Qui a fait la compression entre les deux — et pourquoi ?

Ce post répond à cette question, et explique comment les modèles open-source circulent depuis les labos de recherche jusqu'à ton cluster.

<!-- truncate -->

## Pourquoi la quantization existe : trois objectifs

La quantization n'est pas une astuce technique pour "faire tenir un modèle". C'est une réponse à trois problèmes concrets.

### 1. Démocratiser l'accès

Sans quantization, un modèle 7B en FP16 occupe 14 Go de VRAM. Il te faut une RTX 3080 (700€ minimum) ou une A100 (10 000€ en datacenter). Seuls les labos de recherche bien financés et les grandes entreprises peuvent faire de l'inférence locale.

Avec Q4_K_M, ce même modèle tient en 4.7 Go de RAM. Un ThinkPad d'occasion à 300€ peut le faire tourner. C'est ce changement qui a déclenché l'explosion de l'open-source LLM en 2023 : le jour où des modèles de qualité sont devenus accessibles sur du hardware grand public.

### 2. Accélérer l'inférence

Moins de bits ne signifie pas seulement moins de mémoire — cela signifie aussi moins de données à lire depuis la RAM à chaque calcul.

Sur CPU, la vitesse de génération de tokens est souvent limitée par la **bande passante mémoire** : le processeur doit lire les poids du modèle à chaque étape de génération. Un modèle Q4 lit 8× moins de données qu'un modèle FP32. En pratique, un 7B Q4_K_M génère souvent 1.5 à 2× plus de tokens par seconde qu'un 7B Q8 — pas seulement parce qu'il est plus petit, mais parce que les lectures mémoire sont plus rapides.

### 3. Permettre le déploiement privé

C'est l'objectif le plus stratégique pour les entreprises.

Si tu utilises l'API OpenAI ou Groq, chaque message de tes utilisateurs traverse les serveurs d'une entreprise tierce. Pour un usage personnel ou grand public, c'est acceptable. Pour des données médicales, financières, ou industrielles, c'est souvent impossible légalement et inacceptable en termes de confidentialité.

Un LLM quantisé qui tourne en local résout ce problème par l'architecture : les données ne quittent jamais l'infrastructure. Sur minicloud, les interactions avec Open WebUI ne quittent pas le cluster. C'est une propriété garantie par le design, pas par une promesse contractuelle.

---

## Le cycle de vie d'un modèle open-source

Il y a une question que peu de gens se posent quand ils font `ollama pull` : d'où vient ce fichier, et qui l'a préparé ?

Voici ce qui se passe entre la sortie d'un modèle et son exécution sur ton cluster.

### Étape 1 — Entraînement par le labo

Un laboratoire (Meta, Alibaba, Mistral, Microsoft...) entraîne le modèle sur des milliers de GPUs pendant des semaines ou des mois. Le résultat : des poids en **FP32 ou BF16** — la représentation la plus précise possible des connaissances acquises.

Ces poids sont publiés sur **HuggingFace**. Le modèle original de Qwen 2.5 7B par Alibaba, par exemple, est disponible là-bas en BF16 (~14 Go).

### Étape 2 — Quantization par la communauté

Des membres de la communauté open-source prennent ces poids FP16/BF16 et créent des versions quantisées. Les noms les plus connus dans cet écosystème : **bartowski**, **TheBloke**, **unsloth**.

Leur travail :
1. Télécharger les poids originaux depuis HuggingFace
2. Appliquer llama.cpp ou d'autres outils pour créer les fichiers GGUF
3. Générer toutes les variantes : Q2_K, Q3_K_M, Q4_K_M, Q5_K_M, Q8_0
4. Publier ces fichiers dérivés sur HuggingFace

C'est un travail bénévole, non rémunéré, qui rend l'écosystème possible.

### Étape 3 — Packaging par Ollama

Ollama récupère les fichiers GGUF créés par la communauté et les rend disponibles via son registry (`registry.ollama.ai`). Il ajoute un `Modelfile` qui précise le template de prompt, le system message par défaut, et les paramètres d'inférence recommandés.

```bash
# Ce que tu fais :
ollama pull qwen2.5:7b-instruct-q4_k_m

# Ce qui se passe :
# → Ollama contacte registry.ollama.ai
# → Télécharge les blobs GGUF Q4_K_M (~4.7 Go)
# → Les stocke dans /root/.ollama/models/
# → Le modèle est prêt à l'inférence
```

### Étape 4 — Inférence sur ton cluster

Le modèle tourne dans un pod Ollama, pinné sur un nœud spécifique. LiteLLM route les requêtes vers l'instance la moins occupée. L'utilisateur voit une réponse en quelques secondes.

```
Utilisateur → Open WebUI → LiteLLM → Ollama (pod fast-heron)
                                           ↓
                                   qwen2.5:7b-instruct-q4_k_m
                                   (GGUF Q4_K_M, 4.7 Go en RAM)
```

---

## Modèles non-quantisés vs quantisés — ce sont des artefacts différents

Une confusion fréquente : on parle de "le modèle" comme s'il n'en existait qu'une version. En réalité :

| Type | Format | Poids | Usage typique |
|---|---|---|---|
| Original (sorti du labo) | FP32 / BF16 | 14–28 Go (7B) | Fine-tuning, recherche |
| Quantisé par la communauté | GGUF Q4_K_M | 4.7 Go (7B) | Inférence sur hardware grand public |
| Spécialisé par Modelfile | GGUF (poids inchangés) | identique au base | Pipeline avec persona + comportement custom |
| Fine-tuné + quantisé | GGUF custom | variable | Spécialisation profonde, nouvelle connaissance |

Le modèle original et ses versions quantisées **coexistent** sur HuggingFace. Elles ne se remplacent pas — elles servent des usages différents.

---

## Les 3 vraies façons de spécialiser un LLM

Avant d'aller plus loin, une distinction essentielle que beaucoup de ressources mélangent.

| Technique | Poids modifiés ? | GPU requis ? | Ce que ça change |
|---|---|---|---|
| **System prompt / Modelfile** | Non | Non | Comportement et persona |
| **RAG** | Non | Non | Accès à des données fraîches et privées |
| **Fine-tuning** | Oui | Oui | La connaissance encodée dans les paramètres |

Ces trois techniques sont complémentaires, pas substituables. On peut les combiner — et c'est exactement ce que fait le pipeline `phi3-financial` sur minicloud.

---

## Le cas de `phi3-financial` — Modelfile, pas fine-tuning

Il est tentant d'appeler `phi3-financial` un modèle fine-tuné parce qu'il a un nom distinct dans `ollama list`. Mais la preuve par les chiffres contredit cette interprétation :

```bash
kubectl exec -n ai deployment/ollama -- ollama list

phi4-mini:latest       78fad5d182a7    2.5 GB
phi3-financial:latest  66e3380808ef    2.5 GB
```

**Exactement la même taille.** Un vrai fine-tuning modifie les valeurs des poids — la taille du fichier GGUF résultant varie légèrement. Ici les deux fichiers font 2.5 GB, ce qui indique que les poids sont identiques.

`phi3-financial` est un **Ollama Modelfile** : une configuration qui enveloppe `phi4-mini` avec un system prompt et des paramètres d'inférence, sans toucher aux poids.

```dockerfile
FROM phi4-mini

SYSTEM """
Tu es un expert en analyse financière spécialisé dans le secteur des assurances.
Tu analyses uniquement des données financières et réponds de façon précise et factuelle.
"""

PARAMETER temperature 0.3
```

Quand tu fais `ollama create phi3-financial -f Modelfile`, Ollama crée une nouvelle entrée dans son registry avec ce nom et cette configuration. Les poids sont **identiques** à ceux de `phi4-mini` — aucun entraînement n'a eu lieu.

La spécialisation de `phi3-financial` vient en réalité de trois couches empilées :

```
Requête utilisateur
    │
    ▼
LangfusePromptHandler (LiteLLM CustomLogger)
    │ Injecte le system prompt financier depuis Langfuse
    │ (versioning des prompts, A/B testing possible)
    ▼
phi3-financial Modelfile
    │ Applique temperature=0.3, contraintes de persona
    ▼
phi4-mini GGUF Q4_K_M
    │ Poids identiques au modèle original Microsoft
    ▼
Réponse générée
```

C'est une **spécialisation par prompt engineering en profondeur**, pas du fine-tuning. C'est parfaitement valide et largement utilisé en production — plus rapide à itérer, plus facile à maintenir, aucun GPU requis.

---

## Quand le fine-tuning devient nécessaire

Le fine-tuning n'est justifié que dans des cas précis :

**Nouvelles connaissances factuelles** — si le modèle doit connaître des faits qui n'étaient pas dans ses données d'entraînement (documentation interne, terminologie propriétaire, données post-cutoff).

**Comportement très contraignant** — si le system prompt seul ne suffit pas à maintenir le persona sous des prompts adversariaux.

**Efficacité à l'inférence** — un modèle fine-tuné sur une tâche précise peut atteindre de meilleures performances avec un context plus court, ce qui réduit les coûts.

Pour `phi3-financial`, le RAG + LangfusePromptHandler couvre les deux premiers besoins sans les coûts d'un fine-tuning réel. Si le pipeline nécessitait un jour de connaître des règlements ACPR très spécifiques absents du pre-training, le fine-tuning deviendrait pertinent.

---

## Ce que ça implique concrètement pour l'inférence

Ces types de modèles ne s'utilisent pas de la même façon dans un stack de production.

**Le modèle original (FP16)** — uniquement pour le fine-tuning. Il faut au minimum un GPU avec 14 Go de VRAM et du temps de calcul. C'est l'entrée d'un pipeline ML, pas sa sortie.

**Le modèle quantisé (GGUF Q4_K_M)** — ce que tu déploies en production pour l'inférence. Tourne sur CPU, sur des GPUs grand public, sur du hardware embarqué. C'est la sortie du pipeline, celle qui crée de la valeur.

**Le Modelfile** — une couche de configuration au-dessus d'un modèle quantisé existant. Zéro coût de calcul supplémentaire, itération rapide sur le comportement. C'est l'état réel de `phi3-financial` sur minicloud.

---

## Pourquoi c'est important pour le déploiement en entreprise

Dans un contexte professionnel, ces quatre niveaux correspondent à des rôles distincts :

| Artefact | Équipe responsable |
|---|---|
| Modèle FP16 original | Data scientists / ML researchers |
| Modèle GGUF quantisé | MLOps / Platform engineers |
| Modelfile + system prompt | AI engineers / Prompt engineers |
| RAG pipeline | AI engineers + Data engineers |
| Fine-tuning | ML engineers (besoin GPU, dataset, évaluation) |

Sur minicloud, ces rôles sont joués par une seule personne. En entreprise, ce sont des équipes distinctes avec des compétences différentes. Comprendre quelle technique appartient à quel niveau — et pourquoi — est ce qui distingue un ingénieur qui "utilise des LLMs" d'un ingénieur qui "conçoit des systèmes AI".
