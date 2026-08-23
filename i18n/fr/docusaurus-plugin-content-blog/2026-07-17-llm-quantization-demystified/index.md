---
slug: llm-quantization-demystified
title: "La quantization LLM démystifiée : comment faire tourner un 7B sur un ThinkPad"
authors: [andrelair]
tags: [ai, llm, quantization, ollama, inference, mlops, bare-metal]
date: 2026-07-17
description: "Un 7B en FP32 c'est 28 Go de RAM. Sur mon cluster ThinkPad, impossible. La quantization m'a permis de descendre à 4.7 Go sans perdre la qualité qui compte. Voici comment ça fonctionne."
---

Un modèle 7B en FP32, c'est 28 Go de RAM. Mes ThinkPads en ont 16 à 32. Impossible de charger le modèle — sans parler de faire de l'inférence.

La quantization a résolu ce problème. Pas en sacrifiant la qualité — en changeant la façon dont les poids sont stockés.

{/* truncate */}

## Ce qu'est un paramètre, concrètement

Un LLM "7B" a 7 milliards de paramètres. Chaque paramètre est un nombre en virgule flottante — un poids appris pendant l'entraînement qui encode une fraction des patterns vus dans les données.

En **FP32** (float 32 bits), chaque paramètre occupe 4 octets.

```
7 000 000 000 paramètres × 4 octets = 28 000 000 000 octets = 28 Go
```

28 Go juste pour charger le modèle en RAM. Sans compter le KV cache pendant l'inférence, les activations, l'overhead du runtime.

Sur un ThinkPad avec 16 Go de RAM système et 8 à 12 Go disponibles pour les workloads : **impossible**.

---

## Le principe de la quantization

La quantization réduit la précision de chaque paramètre — moins de bits par nombre, moins de mémoire, au prix d'une légère perte de précision.

L'analogie : imagine que tu mesures une distance. En FP32, tu utilises une règle au millimètre. En Q4, tu utilises une règle au centimètre. Pour construire une maison, la différence est négligeable. Pour de l'horlogerie de précision, ça change tout.

Pour les LLMs, la grande majorité des tâches — conversation, résumé, code, Q&A — tolèrent très bien la réduction de précision des poids. Le réseau neuronal est redondant par nature : des millions de paramètres collaborent pour chaque réponse, et une légère imprécision sur chacun ne change pas le résultat global de façon perceptible.

---

## La hiérarchie des formats

```
FP32    4 bytes/param   7B = 28.0 Go   référence
FP16    2 bytes/param   7B = 14.0 Go   
Q8_0    1 byte/param    7B =  7.0 Go   
Q4_K_M  ~0.5 byte       7B =  4.7 Go   ← le point d'équilibre
Q3_K_M  ~0.4 byte       7B =  3.9 Go   dégradation notable
Q2_K    ~0.25 byte      7B =  2.7 Go   à éviter
```

Chaque niveau vers le bas divise approximativement la mémoire par deux, mais la perte de qualité n'est pas linéaire. De FP32 à Q4_K_M, la dégradation est quasi imperceptible en pratique. De Q4 à Q2, elle devient audible — hallucinations plus fréquentes, raisonnement moins stable.

---

## Ce que signifient les suffixes

Si tu vas sur Ollama ou HuggingFace, tu verras des noms comme `Q4_K_M`, `Q5_K_S`, `IQ3_XS`. Voici comment les lire :

**Le chiffre** — le nombre de bits par paramètre.
- `Q4` = 4 bits
- `Q5` = 5 bits
- `Q8` = 8 bits

**La lettre après le chiffre** — la méthode de quantization.
- `_K` = "K-quant" — une méthode qui quantize différemment selon l'importance relative de chaque couche du réseau. Plus intelligente que la quantization uniforme.
- `_0` = quantization uniforme basique (plus ancienne).

**La dernière lettre** — la taille des "blocs" de calcul.
- `_S` (Small) = plus petit, légèrement plus rapide, légèrement moins précis.
- `_M` (Medium) = équilibre qualité/vitesse.
- `_L` (Large) = plus précis, un peu plus lent.

**Résumé pratique :**
- `Q4_K_M` = 4 bits, K-quant, taille medium → **le choix par défaut**.
- `Q5_K_M` = 5 bits, K-quant, medium → +20% de RAM, presque aucune perte vs Q4.
- `Q8_0` = 8 bits, uniforme → pratiquement identique à FP16.
- `IQ3_XS` = une variante "importance-aware" à 3 bits → pour situations très contraintes.

---

## Les quatre familles de formats

Selon ton hardware, tu croiseras quatre formats principaux :

### GGUF — le format CPU-first

Développé par llama.cpp, utilisé par **Ollama**. Conçu pour tourner sur CPU avec possibilité d'offloader des couches vers un GPU si disponible.

C'est le format qu'on utilise sur minicloud. Tous les suffixes `Q4_K_M`, `Q5_K_M`, etc. font référence à GGUF.

**Avantage :** fonctionne sans GPU, très bien optimisé pour les architectures x86 modernes.
**Inconvénient :** moins efficace qu'un format GPU-natif si tu as un GPU.

### GPTQ — quantization post-training orientée GPU

Quantize les poids après entraînement en minimisant l'erreur de reconstruction. Très bon si tu as assez de VRAM.

**Avantage :** bonne qualité sur GPU.
**Inconvénient :** CPU-unfriendly, nécessite ExLlama ou AutoGPTQ pour l'inférence.

### AWQ — Activation-aware Weight Quantization

Plus récent que GPTQ. L'idée : certains paramètres sont plus importants que d'autres (ceux qui activent souvent). AWQ les protège en les quantizant moins agressivement.

**Avantage :** meilleure qualité que GPTQ à même taille, de plus en plus standard.
**Inconvénient :** nécessite un runtime compatible (vLLM, AutoAWQ).

### EXL2 — ExLlamaV2

Format propriétaire à ExLlamaV2, très efficace pour l'inférence GPU en batch. Permet des taux de bits mixtes par couche.

**Avantage :** débit maximal sur GPU NVIDIA.
**Inconvénient :** écosystème plus fermé, pas pour CPU.

---

## La règle d'or

> Descends d'un niveau de quantization avant de descendre à un modèle plus petit.

Un 7B Q4 surpasse un 3B Q8 sur presque toutes les tâches — raisonnement, suivi d'instructions, cohérence longue. Les 7 milliards de paramètres, même légèrement imprécis, encodent plus de connaissance que 3 milliards de paramètres très précis.

Concrètement sur minicloud :

| Option | RAM | Qualité relative |
|---|---|---|
| qwen2.5 3B Q8 | 3.0 Go | Baseline |
| qwen2.5 7B Q4_K_M | 4.7 Go | +20–30% qualité |
| qwen2.5 7B Q5_K_M | 5.8 Go | +22–32% qualité |

Pour 1.7 Go de RAM supplémentaire, on gagne un saut de qualité massif.

---

## L'impact sur la qualité — les chiffres réels

Le standard de mesure de la dégradation par quantization est la **perplexité** — une mesure de la "surprise" du modèle face à un texte de référence. Plus la perplexité est basse, mieux le modèle prédit le langage.

Sur Llama 3 8B (valeurs représentatives de la famille 7-8B) :

| Format | Perplexité (WikiText-2) | Différence vs FP16 |
|---|---|---|
| FP16 | 6.12 | référence |
| Q8_0 | 6.13 | +0.01 (+0.2%) |
| Q4_K_M | 6.22 | +0.10 (+1.6%) |
| Q3_K_M | 6.47 | +0.35 (+5.7%) |
| Q2_K | 7.15 | +1.03 (+16.8%) |

En pratique : entre FP16 et Q4_K_M, la différence de perplexité est de 1.6%. Dans une conversation réelle, c'est imperceptible. Entre Q4 et Q2, le saut de 16.8% correspond à des réponses notablement moins cohérentes sur les tâches complexes.

---

## Ce que ça donne sur le cluster minicloud

Le cluster tourne sur des ThinkPads CPU-only (pas de GPU). La contrainte est réelle.

Avant : `phi4-mini` (3.8B, format propriétaire Microsoft) — 2.5 Go en RAM, ~15 tokens/sec sur ThinkPad.

Après : `qwen2.5:7b-instruct-q4_k_m` (7B, GGUF Q4_K_M) — 4.7 Go en RAM, ~10 tokens/sec.

On perd 5 tokens/sec (vitesse), on gagne 15–20% de qualité sur les benchmarks. Pour du chat interactif où l'utilisateur lit à 4–5 mots/seconde, 10 tokens/sec est largement suffisant.

```bash
# Vérifier les modèles chargés sur les 3 instances Ollama
kubectl exec -n ai deployment/ollama -- ollama list
kubectl exec -n ai deployment/ollama-secondary -- ollama list
kubectl exec -n ai deployment/ollama-tertiary -- ollama list
```

```
NAME                          ID              SIZE
qwen2.5:7b-instruct-q4_k_m    845dbda0ea48    4.7 GB
phi4-mini:latest               78fad5d182a7    2.5 GB
deepseek-r1:7b                 755ced02ce7b    4.7 GB
...
```

Trois instances Ollama, chacune sur un nœud différent. LiteLLM route les requêtes vers l'instance la moins occupée. La quantization Q4_K_M est ce qui rend ce setup possible sur du hardware grand public.

---

## Comment choisir

```
Tu as un GPU avec assez de VRAM ?
├── Oui → AWQ ou GPTQ (meilleure qualité à même taille que GGUF)
└── Non → GGUF, et le format :

    RAM disponible pour le modèle ?
    ├── < 5 Go    → Q4_K_M  (défaut)
    ├── 5–7 Go    → Q5_K_M  (si tu peux)
    ├── 7–15 Go   → Q8_0    (quasi-FP16)
    └── > 15 Go   → FP16    (référence)

    Q2 ou Q3 ?
    └── Éviter sauf contrainte extrême (edge, IoT, <3 Go impératif)
```

---

## Ce qu'on retient

La quantization n'est pas un compromis entre "bon modèle" et "modèle qui tient en RAM". C'est une technique mature, mesurée, avec des pertes de qualité documentées et prévisibles.

Q4_K_M est devenu le standard de facto de l'écosystème open-source pour une raison : c'est le point où la perte de précision devient théorique plutôt que pratique pour la grande majorité des tâches.

Sur minicloud, c'est ce qui permet de faire tourner un LLM 7B de qualité production sur du matériel qu'on aurait jeté il y a trois ans.
