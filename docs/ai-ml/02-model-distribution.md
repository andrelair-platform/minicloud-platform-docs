---
id: model-distribution
title: Ollama — Model Inventory & Distribution Strategy
sidebar_position: 2
---

# Ollama — Model Inventory & Distribution Strategy

The AI stack runs three Ollama instances across the cluster (`ollama`, `ollama-secondary`, `ollama-tertiary`), each pinned to a different node via `nodeSelector`. LiteLLM routes requests across them using the `least-busy` strategy.

This page documents which models are deployed on which instance, why, and the reasoning behind not homogenizing all models across all instances.

**Last updated:** 2026-07-17 (post qwen2.5:7b migration)

---

## Instance → Node Mapping

| Instance | Node | Role |
|---|---|---|
| `ollama` | `fast-heron` (10.0.0.7) | Primary — broadest model set |
| `ollama-secondary` | `star-kitten` (10.0.0.8) | Secondary — mirrors primary minus bge-m3 |
| `ollama-tertiary` | `fast-skunk` (10.0.0.4) | Tertiary — core models only |

---

## Current Model Inventory

| Model | Size | ollama | ollama-secondary | ollama-tertiary | Purpose |
|---|---|---|---|---|---|
| `qwen2.5:7b-instruct-q4_k_m` | 4.7 GB | ✓ | ✓ | ✓ | Chat principal, fallback phi3-financial |
| `phi4-mini:latest` | 2.5 GB | ✓ | ✓ | ✓ | Raisonnement compact |
| `phi3-financial:latest` | 2.5 GB | ✓ | ✓ | ✓ | Pipeline PromptOps financier |
| `nomic-embed-text:latest` | 274 MB | ✓ | ✓ | ✓ | Embeddings RAG pipeline |
| `llama3.2:1b` | 1.3 GB | ✓ | ✓ | ✓ | Tâches légères, TTFT bas |
| `deepseek-r1:7b` | 4.7 GB | ✓ | ✓ | — | Raisonnement chain-of-thought |
| `qwen3.5:4b` | 3.4 GB | ✓ | ✓ | — | Usage général léger |
| `llava-phi3:latest` | 2.9 GB | ✓ | ✓ | — | Vision — analyse image/OCR |
| `moondream:latest` | 1.7 GB | ✓ | ✓ | — | Vision compact |
| `bge-m3:latest` | 1.2 GB | ✓ | — | — | Embeddings multilingues alternatifs |

**Total unique models : 10**

---

## Pourquoi Ne Pas Tout Homogénéiser

La question naturelle : pourquoi ne pas avoir les 10 modèles sur les 3 instances ?

**Réponse : disk budget vs usage réel.**

Les modèles manquants sur `ollama-tertiary` représentent **+12.7 GB** supplémentaires sur ce nœud (deepseek-r1 4.7 GB + qwen3.5 3.4 GB + llava-phi3 2.9 GB + moondream 1.7 GB). Ajouter ces modèles pour du trafic occasionnel n'apporte aucun gain de performance — LiteLLM peut router vers `ollama` ou `ollama-secondary` pour ces modèles sans impact notable.

La redondance n'a de valeur que sur les modèles à forte demande concurrente.

---

## Stratégie de Distribution

| Critère | Action |
|---|---|
| Modèle utilisé en chat interactif principal | Sur les 3 instances (redondance complète) |
| Modèle utilisé dans un pipeline CI automatisé | Sur les 3 instances (résilience) |
| Modèle d'embedding (RAG pipeline — continu) | Sur les 3 instances (charge répartie) |
| Modèle utilisé occasionnellement | 1–2 instances suffisent |
| Modèle vision (rare) | 1–2 instances suffisent |
| Modèle d'embedding alternatif | 1 instance suffit |

---

## Quantization — Choix Retenu

Tous les modèles 7B tournent en **GGUF Q4_K_M** : ~0.5 byte/paramètre, soit 4.5–4.7 GB pour un 7B. C'est le meilleur rapport qualité/taille pour de l'inférence CPU.

```
FP32   → 4 bytes/param → 7B = 28 GB  (impossible sur ThinkPad)
FP16   → 2 bytes/param → 7B = 14 GB  (trop lourd)
Q4_K_M → ~0.5 byte     → 7B =  4.7 GB ← retenu
Q2_K   → ~0.25 byte    → 7B =  2.7 GB  (dégradation trop forte)
```

Descendre d'un niveau de quantization vaut mieux que de prendre un modèle plus petit. Un 7B Q4 surpasse un 3B Q8 sur presque toutes les tâches.

### Lire la notation Q4_K_M

La notation peut sembler opaque au premier abord. Voici comment la décoder.

**Le chiffre — nombre de bits par paramètre**

Un bit est la plus petite unité d'information : soit 0, soit 1.

Avec N bits on peut représenter 2ᴺ valeurs distinctes :

| Format | Bits | Valeurs possibles | Exemple |
|---|---|---|---|
| FP32 | 32 | ~4 milliards | `0.347821493...` très précis |
| Q8 | 8 | 256 | `0.348` précis |
| Q4 | 4 | 16 | `0.35` approché |
| Q2 | 2 | 4 | `0.3` ou `0.4` — très grossier |

La quantization c'est simplement **arrondir chaque paramètre** pour qu'il occupe moins de place. Comme passer d'une règle au millimètre à une règle au centimètre — suffisant pour construire une maison, insuffisant pour de l'horlogerie.

**Le `K` — méthode intelligente**

Sans `K` (ex: `Q8_0`) : tous les paramètres reçoivent exactement le même traitement, qu'ils soient importants ou non.

Avec `K` (ex: `Q4_K_M`) : la méthode détecte quels paramètres ont le plus d'impact sur les sorties du modèle et leur préserve plus de précision. Les paramètres moins critiques sont arrondis plus agressivement. Résultat : même niveau de compression, meilleure qualité finale.

**Le `M` — taille des blocs de calcul**

- `_S` (Small) — groupes petits, légèrement plus rapide
- `_M` (Medium) — équilibre vitesse/précision ← le défaut
- `_L` (Large) — légèrement plus précis, légèrement plus lent

**Résumé en une ligne**

| Notation | Traduction |
|---|---|
| `Q4_K_M` | 4 bits/param, méthode intelligente, bloc medium — **défaut recommandé** |
| `Q5_K_M` | 5 bits/param, méthode intelligente, bloc medium — si +1 GB de RAM disponible |
| `Q8_0` | 8 bits/param, méthode basique — quasi-identique à FP16 |
| `Q2_K` | 2 bits/param — seulement 4 valeurs possibles, dégradation perceptible |

**Règle d'or :** ne descends jamais en dessous de Q4. Et préfère toujours `_K_M` à `_0` à bits équivalents.

---

## Migration phi4-mini → qwen2.5:7b (2026-07-16)

**Raison :** phi4-mini (3.8B) est limité par sa taille. Qwen 2.5 7B surpasse phi4-mini sur MMLU (75% vs 69%), HumanEval (83% vs 62%) et le français natif — tout en tenant dans le même budget RAM une fois quantisé.

| Modèle | MMLU | HumanEval | Français | RAM Q4_K_M |
|---|---|---|---|---|
| phi4-mini 3.8B | 69% | 62% | Passable | 2.5 GB |
| **Qwen 2.5 7B** | **75%** | **83%** | **Excellent** | **4.7 GB** |

---

## Procédure de Pull — Gotcha NetworkPolicy

Le pull de modèles depuis l'intérieur des pods (`kubectl exec -- ollama pull`) est bloqué sur cette infrastructure. Le pod ne peut pas atteindre `registry.ollama.ai` ni les blobs Cloudflare R2 (`172.64.66.x:443`) malgré la NetworkPolicy `allow-ollama-registry-egress`. Le nœud lui-même atteint le registry sans problème — la différence vient du chemin CNI (flannel) pour le trafic IPv4 pod-to-external vs. le trafic node-level.

**Workaround utilisé (temporaire) :** `hostNetwork: true` sur le deployment. Le pod utilise alors directement le network namespace du nœud, contournant le CNI.

```bash
# 1. Activer hostNetwork
kubectl patch deployment/ollama deployment/ollama-secondary deployment/ollama-tertiary \
  -n ai --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/hostNetwork","value":true}]'

# 2. Attendre le redémarrage des pods
kubectl rollout status deployment/ollama deployment/ollama-secondary deployment/ollama-tertiary \
  -n ai --timeout=120s

# 3. Pull le modèle (exemple)
kubectl exec -n ai deployment/ollama -- ollama pull qwen2.5:7b-instruct-q4_k_m
kubectl exec -n ai deployment/ollama-secondary -- ollama pull qwen2.5:7b-instruct-q4_k_m
kubectl exec -n ai deployment/ollama-tertiary -- ollama pull qwen2.5:7b-instruct-q4_k_m

# 4. Retirer hostNetwork
kubectl patch deployment/ollama deployment/ollama-secondary deployment/ollama-tertiary \
  -n ai --type=json \
  -p '[{"op":"remove","path":"/spec/template/spec/hostNetwork"}]'
```

Les fichiers modèles sont stockés sur un PVC (`local-path`). Ils persistent après le redémarrage des pods — le pull est permanent.

**Fix définitif prévu : Phase 76 (Cilium).** Cilium remplace flannel et permet des FQDN egress policies (`matchPattern: "*.ollama.ai"`) + Hubble pour observer exactement quel trafic est bloqué.

---

## Vérification de l'inventaire

```bash
# Lister les modèles sur chaque instance
kubectl exec -n ai deployment/ollama -- ollama list
kubectl exec -n ai deployment/ollama-secondary -- ollama list
kubectl exec -n ai deployment/ollama-tertiary -- ollama list
```

---

## Tuning Ollama (variables d'environnement)

Appliqué sur les 3 instances via `ollama-values.yaml` :

| Variable | Valeur | Impact |
|---|---|---|
| `OLLAMA_KEEP_ALIVE` | `-1` | Modèle jamais déchargé — supprime 3–5s de cold start |
| `OLLAMA_FLASH_ATTENTION` | `1` | −15–20% RAM, +10% vitesse |
| `OLLAMA_NUM_PARALLEL` | `4` | 4 requêtes concurrentes max par instance |
| `OLLAMA_NUM_THREADS` | `6` | Cœurs physiques uniquement (pas hyperthreading) |
| `OLLAMA_MAX_LOADED_MODELS` | `2` | 2 modèles max en RAM simultanément |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | KV cache quantisé — économise RAM sur longs contextes |
| `OLLAMA_NUM_CTX` | `4096` | Context window réduit — ×1.8–2 tokens/s vs 32k |
