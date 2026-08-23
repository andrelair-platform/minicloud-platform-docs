---
slug: llm-slm-quantization-inference-serving
title: "Les LLM sur bare-metal : quantification, SLM, et remplacement de phi4-mini par Qwen 2.5 7B"
authors: [andrelair]
tags: [ai, llm, ollama, litellm, kubernetes, inference, quantization, mlops]
date: 2026-07-16
description: "Comment nous raisonnons sur la taille des modèles, les formats de quantification et le réglage d'inférence pour un cluster k3s CPU-only de 5 nœuds — et pourquoi nous avons remplacé phi4-mini par Qwen 2.5 7B Q4_K_M."
---

Faire tourner des LLM sur du matériel CPU bare-metal vous force à comprendre les chiffres derrière les fichiers de modèles. Cet article documente comment nous raisonnons sur la taille des modèles, la quantification et le service d'inférence sur minicloud — et le changement concret que nous avons fait : remplacer phi4-mini par Qwen 2.5 7B sur les trois instances Ollama.

{/* truncate */}

## Ce que « 7B » signifie réellement

Le « 7B » dans un nom de modèle est le nombre de paramètres — des poids en virgule flottante stockés dans le réseau de neurones. Chaque paramètre détient des connaissances apprises à l'entraînement. Plus de paramètres signifie généralement un meilleur raisonnement, des connaissances plus larges et moins d'hallucinations sur les tâches complexes.

Le hic : plus de paramètres signifie plus de RAM.

| Taille | RAM en FP32 (brut) | Usage typique |
|---|---|---|
| 1–3B | 4–12 Go | Edge, mobile, matériel très contraint |
| 7B | 28 Go | Le point d'équilibre qualité/ressources |
| 13B | 52 Go | Bon raisonnement, faisable sur GPU 48 Go |
| 30–34B | ~120 Go | Multi-GPU ou quantifié sur 24 Go |
| 70B | 280 Go | Multi-GPU haut de gamme ou cloud |

Notre cluster n'a pas de GPU dédié — swift-mac a 8 Go de RAM, les workers ThinkPad ont 16–32 Go. En FP32, même un modèle 7B est hors de portée. C'est là que la quantification devient essentielle.

## Quantification — pourquoi elle change tout

Un paramètre FP32 = 4 octets. La quantification représente le même poids avec moins de bits, acceptant une petite perte de précision en échange d'un usage mémoire drastiquement plus faible.

```
FP32   → 4 octets/param  → modèle 7B = 28 Go   (référence)
FP16   → 2 octets/param  → modèle 7B = 14 Go
Q8_0   → 1 octet/param   → modèle 7B =  7 Go
Q4_K_M → ~0,5 octet/param → modèle 7B = 4,1 Go  ← le plus populaire
Q2_K   → ~0,25 octet/param → modèle 7B = 2,7 Go  (perte de qualité notable)
```

La perte de qualité de Q4_K_M vs FP16 est mesurable sur les benchmarks mais imperceptible à l'usage pratique pour le chat et le RAG. Q2 et Q3 sont une autre histoire — évitez-les pour tout ce qui requiert un raisonnement précis.

**Règle empirique :** descendez d'un niveau de quantification avant de descendre vers un modèle plus petit. Un 7B Q4 bat un 3B Q8 sur presque chaque tâche.

### Le zoo des formats

Vous rencontrerez quatre formats principaux selon votre runtime :

- **GGUF** (llama.cpp / Ollama) — format CPU-first avec déchargement GPU optionnel. Les suffixes comme `Q4_K_M`, `Q5_K_M`, `Q8_0` indiquent le niveau de quantification. C'est ce qu'Ollama utilise.
- **GPTQ** — quantification post-entraînement orientée GPU. Meilleur que GGUF si vous avez assez de VRAM.
- **AWQ** — Activation-aware Weight Quantization. Meilleure qualité que GPTQ à taille égale, de plus en plus standard.
- **EXL2** — format ExLlamaV2, très efficace pour l'inférence par lots sur GPU.

Pour un cluster CPU-only ou CPU-primaire : GGUF Q4_K_M est votre format.

## Candidats SLM — les vraies options sous 8B

Les petits modèles de langage (SLM, ≤7B) ont énormément rattrapé leur retard depuis 2024. Voici les pertinents pour un cluster d'inférence contraint :

| Modèle | Taille | Forces | Idéal pour |
|---|---|---|---|
| phi4-mini (Microsoft) | 3,8B | Raisonnement fort pour sa taille | RAG, Q&R factuel — nous l'avions en route |
| Llama 3.2 3B | 3B | Bon instruct, multilingue | Chat, résumé |
| Llama 3.1 8B | 8B | Référence de qualité pour 7-8B | Usage général |
| Gemma 3 4B | 4B | Excellent code + suivi d'instructions | Assistant de code |
| Mistral 7B v0.3 | 7B | Fort en français nativement, contexte long | Utilisateurs francophones |
| Qwen 2.5 7B | 7B | Meilleur 7B sur les benchmarks récents | Usage général — notre choix |
| deepseek-r1 7B (distillé) | 7B | Raisonnement en chaîne de pensée | Tâches analytiques |

## Pourquoi nous avons remplacé phi4-mini

phi4-mini n'est pas un mauvais modèle — Microsoft a fait du bon travail sur le raisonnement à 3,8B. Mais il a deux limites structurelles :

**3,8B est le plafond de qualité.** À 3,8B paramètres, le modèle a moins de « mémoire » des schémas d'entraînement. Il hallucine plus sur les faits précis, le raisonnement multi-étapes se dégrade plus vite, et le suivi d'instructions complexes est moins fiable qu'un 7B.

**Le marché a évolué.** En 2024–2025, les modèles 7B sont devenus ce que les modèles 13B étaient en 2023. Qwen 2.5 7B en particulier surpasse phi4-mini sur presque chaque benchmark tout en tenant dans la même contrainte de RAM une fois quantifié.

La comparaison qui a rendu la décision claire :

| Modèle | MMLU | HumanEval | Français | RAM en Q4_K_M |
|---|---|---|---|---|
| phi4-mini 3,8B | 69 % | 62 % | Passable | 2,5 Go |
| Mistral 7B v0.3 | 64 % | 45 % | Natif | 4,1 Go |
| Llama 3.1 8B | 73 % | 72 % | Bon | 4,7 Go |
| **Qwen 2.5 7B** | **75 %** | **83 %** | **Excellent** | **4,5 Go** |

Qwen 2.5 est nativement entraîné sur 29 langues dont le français. Pour des utilisateurs finaux francophones interagissant avec Open WebUI, c'est un avantage direct sur Llama.

## Quelles métriques comptent vraiment pour le service d'inférence

Trois métriques à optimiser, selon le cas d'usage :

**Time To First Token (TTFT)** — latence avant que l'utilisateur ne voie le premier mot. Critique pour le chat interactif. Les modèles plus petits gagnent ici. Le matériel LPU de Groq atteint un TTFT < 200 ms même sur des modèles 8B.

**Tokens par seconde (débit)** — vitesse de génération. GPU >> CPU. Sur CPU, phi4-mini Q4 génère ~15 tok/s sur un ThinkPad, Llama 3.1 8B ~6 tok/s.

**Concurrence** — combien d'utilisateurs simultanés. Ollama gère une requête à la fois par instance par défaut. Pour du multi-utilisateur, il vous faut plusieurs instances (nous en avons trois) ou un serveur de batching comme vLLM.

### Matrice de décision

```
L'utilisateur attend une réponse en < 2s ?
├── Oui → Groq (LPU cloud) ou phi4-mini local Q4
└── Non → Llama 3.1 8B Q4 ou Qwen 2.5 7B Q4

La tâche requiert du raisonnement (maths, analyse) ?
├── Oui → distill deepseek-r1 ou phi4-mini (fort en raisonnement)
└── Non → Mistral 7B ou Llama 3.2 3B (plus rapide, moins cher)

Utilisateurs francophones ?
├── Oui → Mistral 7B (FR natif) ou Llama 3.1 8B (multilingue solide)
└── Non → Qwen 2.5 7B ou Gemma 3 4B
```

## Régler Ollama pour l'inférence CPU

Au-delà du choix du modèle, plusieurs variables d'environnement ont un impact immédiat.

### Garder le modèle chargé

Le changement isolé le plus impactant : régler `OLLAMA_KEEP_ALIVE=-1` pour que le modèle ne soit jamais déchargé de la RAM. Sans cela, Ollama évince le modèle après 5 minutes d'inactivité — la requête suivante paie une pénalité de démarrage à froid de 3–5 secondes pendant que le modèle se recharge.

```yaml
env:
  - name: OLLAMA_KEEP_ALIVE
    value: "-1"
```

### Flash Attention

Réduit l'usage mémoire du cache KV et accélère le calcul d'attention :

```yaml
  - name: OLLAMA_FLASH_ATTENTION
    value: "1"
```

Gain : ~15–20 % de RAM en moins, ~10 % plus rapide sur les contextes plus longs.

### Fenêtre de contexte — le levier le plus sous-estimé

Ollama charge par défaut la fenêtre de contexte maximale du modèle (128k pour Qwen 2.5). Le cache KV croît linéairement avec la longueur du contexte. Pour le chat standard, vous n'avez pas besoin de 128k tokens.

Forcer `num_ctx=4096` dans les params LiteLLM :

```yaml
litellm_params:
  model: ollama/qwen2.5:7b-instruct-q4_k_m
  api_base: http://ollama.ai.svc.cluster.local:11434
  num_ctx: 4096
```

Impact : passer de `num_ctx=32768` à `num_ctx=4096` peut **doubler le débit** sur CPU en réduisant la quantité de mémoire que le modèle lit par étape de génération de token.

### Threads CPU — aligner sur les cœurs physiques

Ollama utilise tous les cœurs disponibles par défaut, mais l'hyperthreading peut nuire à l'inférence (deux threads logiques sur le même cœur physique se disputent la même ALU). Réglez les threads sur le nombre de cœurs physiques :

```yaml
  - name: OLLAMA_NUM_THREADS
    value: "6"   # cœurs physiques, pas logiques — évite la surcharge d'hyperthreading
```

### Parallélisme et modèles chargés

```yaml
  - name: OLLAMA_NUM_PARALLEL
    value: "4"   # max de requêtes concurrentes par instance
  - name: OLLAMA_MAX_LOADED_MODELS
    value: "2"   # garder au plus 2 modèles en RAM simultanément
  - name: OLLAMA_KV_CACHE_TYPE
    value: "q8_0"  # quantifier le cache KV lui-même — économise de la RAM pendant les longues conversations
```

### Résumé : ce que chaque réglage gagne

| Optimisation | Gain estimé sur CPU de ThinkPad |
|---|---|
| `OLLAMA_KEEP_ALIVE=-1` | −3–5s de démarrage à froid par requête |
| `num_ctx: 4096` au lieu de 32k | ×1,8–2× tokens/s |
| `OLLAMA_FLASH_ATTENTION=1` | −15–20 % RAM, +10 % vitesse |
| `OLLAMA_NUM_THREADS=6` (cœurs physiques) | +5–10 % de stabilité sous charge |
| 3 instances LiteLLM équilibrées | ×3 utilisateurs simultanés |
| phi4-mini → Qwen 2.5 7B Q4 | +15–20 % de qualité sur les benchmarks |

## Ce que nous avons réellement fait sur minicloud

Les trois instances Ollama (`ollama`, `ollama-secondary`, `ollama-tertiary` dans le namespace `ai`) avaient déjà toutes les variables d'environnement réglées lors d'une session de tuning précédente. La seule pièce manquante était le modèle lui-même.

Le pull du modèle depuis l'intérieur d'un pod était bloqué : la NetworkPolicy default-deny-egress et une différence de routage entre le trafic IPv4 au niveau pod et au niveau nœud vers Cloudflare R2 causaient un `connection refused` sur `172.64.66.x:443`. Le nœud lui-même pouvait joindre le registre sans problème, mais le chemin de trafic CNI (flannel) depuis les IP de pod ne fonctionnait pas de la même façon.

**Contournement utilisé :** patch temporaire de `hostNetwork: true` sur les trois déploiements. Cela fait utiliser au pod l'espace de noms réseau du nœud directement, contournant le CNI. Le nœud peut joindre registry.ollama.ai — donc le pull fonctionne.

```bash
# Ajouter hostNetwork temporairement
kubectl patch deployment/ollama deployment/ollama-secondary deployment/ollama-tertiary \
  -n ai --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/hostNetwork","value":true}]'

# Tirer le modèle (4,7 Go par instance)
kubectl exec -n ai deployment/ollama -- ollama pull qwen2.5:7b-instruct-q4_k_m
kubectl exec -n ai deployment/ollama-secondary -- ollama pull qwen2.5:7b-instruct-q4_k_m
kubectl exec -n ai deployment/ollama-tertiary -- ollama pull qwen2.5:7b-instruct-q4_k_m

# Retirer hostNetwork — les pods redémarrent avec le réseau CNI normal
kubectl patch deployment/ollama deployment/ollama-secondary deployment/ollama-tertiary \
  -n ai --type=json \
  -p '[{"op":"remove","path":"/spec/template/spec/hostNetwork"}]'
```

Les fichiers de modèles sont stockés sur un PVC, donc ils persistent à travers les redémarrages de pods. Après avoir retiré `hostNetwork`, les trois instances sont remontées avec `qwen2.5:7b-instruct-q4_k_m` en cache local — et LiteLLM a commencé à y router immédiatement.

Le problème réseau sous-jacent (chemin IPv4 pod-vers-Cloudflare via flannel) est une limitation connue. **La Phase 76 remplacera flannel par Cilium**, qui ajoute des politiques d'egress basées sur FQDN et l'observabilité Hubble — rendant ce genre de débogage trivial la prochaine fois.

## La suite

Avec Qwen 2.5 7B tournant sur les trois instances et LiteLLM routant le trafic en least-busy, la pile IA est :

- **pipeline phi3-financial** : Groq `llama-3.1-8b-instant` en primaire (rapide grâce au LPU), Qwen 2.5 7B ×3 en repli local
- **chat Open WebUI** : Qwen 2.5 7B pour l'usage général, deepseek-r1 7B pour les tâches de raisonnement
- **ingestion RAG** : `nomic-embed-text` pour les embeddings (inchangé)

L'optimisation par décodage spéculatif (un petit modèle brouillon pré-génère des tokens que le modèle principal vérifie) est disponible dans Ollama v0.5+ et pourrait pousser le débit 2–3× plus loin sur les sorties prévisibles. C'est la prochaine frontière de tuning une fois cette configuration stable.
