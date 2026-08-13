---
id: retrospective-risk-register
title: Rétrospectives & Registre des risques — CERT-1
sidebar_label: Rétrospectives & Risques
---

# Rétrospectives & Registre des risques

**Projet :** ktayl-solution Claims & Policy Platform (CERT-1 / RNCP39583 BC01)

---

## 1. Rétrospectives de sprint

Chaque rétrospective suit le format **Keep / Improve / Action** (KIA) — simple, actionnable, et adapté au contexte solo/micro-équipe.

---

### Sprint 0 — Architecture et Cadrage

**Dates :** 2026-08-13 · **Durée :** 1 session · **Items livrés :** 8/8

#### Ce qui a bien fonctionné

| Observation | Impact |
|-------------|--------|
| CdCF rédigé en une session avec structure complète (14 sections + RACI) | Artefact BC01 principal livré à temps |
| Choix de Docusaurus comme dépôt des artefacts de certification | Un seul endroit pour tous les documents, déployé en continu sur GitHub Pages |
| Standard de gouvernance défini avant tout développement | Évite de devoir retrofit le RACI sur les sprints futurs |
| Critères d'acceptation (REC-*) définis dès M0 | Les tests E2E du sprint M8 peuvent être écrits maintenant |

#### Ce qui peut s'améliorer

| Observation | Cause identifiée | Priorité |
|-------------|-----------------|----------|
| Les items du sprint n'étaient pas tracés dans GitHub avant de commencer | Travail démarré directement sans créer les issues GitHub d'abord | Haute |
| Le registre des risques n'existait pas en début de sprint | Aucun template établi | Haute |
| La dénomination des blocs BC dans le CdCF ne correspondait pas exactement à RNCP39583 | Copie approximative du référentiel | Moyenne |

#### Actions

| # | Action | Responsable | Deadline |
|---|--------|-------------|----------|
| A0-1 | Créer les GitHub Issues **avant** de démarrer le sprint M1 (ktayl-policy-service) | TL | Avant Sprint 1 |
| A0-2 | Adopter BMAD pour la génération structurée des stories M1–M8 | SA + PM | Sprint 1 |
| A0-3 | Corriger les noms de blocs BC dans le CdCF (BC03/BC04 libellés RNCP exacts) | BA | Sprint 1 |

---

### Platform Sprint — Infra Automation (2026-08-13)

**Dates :** 2026-08-07 → 2026-08-13 · **Items livrés :** 5/6 · **Item différé :** MAAS → dnsmasq

#### Ce qui a bien fonctionné

| Observation |
|-------------|
| Identification rapide du problème drain/finalizer Longhorn (diagnostic < 30 min) |
| cloudflared → k8s HA livré sans interruption de service (transition transparente) |
| GRUB_TIMEOUT=3 appliqué sur les 4 ThinkPads via SSH séquentiel — aucun reboot manual |
| k3s upgrade 5 nœuds sans drain : ~30s par nœud, aucune indisponibilité |

#### Ce qui peut s'améliorer

| Observation | Cause |
|-------------|-------|
| PR #689 fusionnée vide (branch créée avant git add) | `git push` lancé sans vérifier `git diff --stat` |
| L'item MAAS → dnsmasq a consommé du temps d'analyse avant d'être différé | Manque de critère de décision Go/No-Go explicite en début de sprint |

#### Actions

| # | Action |
|---|--------|
| A-INF-1 | Toujours exécuter `git diff --stat` avant `git push origin <branch>` |
| A-INF-2 | Définir un critère Go/No-Go explicite pour chaque item en début de sprint |

---

### Platform Sprint — ERP-1 (2026-08-10)

**Dates :** 2026-08-10 · **Items livrés :** 6/6

#### Ce qui a bien fonctionné

| Observation |
|-------------|
| PCG 2025 (845 comptes) chargé en une migration sans perte de données |
| TSCA correctement identifié comme taxe assurance (≠ TVA) dès la conception |
| Test invoice ACC-SINV-2026-00001 (MRH, TSCA 13%, 1695€) valide le parcours complet |

#### Ce qui peut s'améliorer

| Observation | Cause |
|-------------|-------|
| Redis stale cache après remplacement COA — erreur non anticipée | Comportement interne Frappe non documenté |
| Suffix ` - KS` sur les noms de templates — découvert en production | Convention ERPNext non lue au préalable |

#### Actions

| # | Action |
|---|--------|
| A-ERP-1 | Documenter les gotchas Frappe dans la section Migration du guide ERPNext |
| A-ERP-2 | Ajouter `frappe.cache.flushall()` au script de migration standard |

---

## 2. Registre des risques

**Légende probabilité/impact :** H = Haute · M = Moyenne · L = Faible
**Score = P × I** (HH=9, HM=6, MH=6, MM=4, etc.)

### 2.1 Risques techniques

| ID | Risque | Catégorie | P | I | Score | Mitigation | Statut | Date |
|----|--------|-----------|---|---|-------|------------|--------|------|
| RT-01 | k3s upgrade drain bloqué par finalizers Longhorn instance-manager (iSCSI) | Technique | H | H | 9 | `cordon: true` uniquement dans les Plans system-upgrade — pas de `drain:` | ✅ Fermé | 2026-08-13 |
| RT-02 | Prometheus WAL replay > probe failureThreshold → restart loop infini | Technique | H | H | 9 | `failureThreshold=240`, `walCompression: true`, `memory-snapshot-on-shutdown` | ✅ Fermé | 2026-08-07 |
| RT-03 | Longhorn volume RWO deadlock lors du rolling update d'un Deployment | Technique | M | H | 6 | `strategy: Recreate` + `dataLocality: best-effort` + `nodeSelector` pour StatefulSets | ✅ Fermé | 2026-08-01 |
| RT-04 | MinIO conserve l'état disk-full en mémoire après libération d'espace | Technique | M | H | 6 | `remediate_minio_disk_recovery()` dans minicloud-ops (flag file + restart automatique) | ✅ Fermé | 2026-08-13 |
| RT-05 | Redis cache Frappe obsolète après remplacement du plan comptable | Technique | M | M | 4 | `frappe.cache.flushall()` ajouté au script de migration ERPNext | ✅ Fermé | 2026-08-10 |
| RT-06 | ArgoCD SSA + Helm CSA conflict : nouvelles clés ConfigMap silencieusement ignorées | Technique | L | M | 2 | `kubectl patch --type merge` (kubectl-patch manager prioritaire) | ✅ Fermé | 2026-08-07 |
| RT-07 | Longhorn replica rebuild lente sur swift-mac (port switch limité à 100 Mbps) | Technique | M | M | 4 | Correction physique câble/port switch requise — surveillance active | ⚠️ Ouvert | 2026-08-08 |
| RT-08 | ThinkPads bootent sur PXE au lieu du NVMe après coupure secteur | Technique | H | M | 6 | `GRUB_TIMEOUT=3` + `efibootmgr --create` sur les 4 nœuds | ✅ Fermé | 2026-08-13 |
| RT-09 | KEDA ScaledObject Lua health check — `nil == 0` false → Rollout bloqué en Progressing | Technique | L | M | 2 | Vérification `status.phase=="Healthy"` avant coercion numérique | ✅ Fermé | 2026-08-07 |
| RT-10 | Incompatibilité RNCP39583 BC03/BC04 libellés dans le CdCF vs référentiel officiel | Documentation | M | H | 6 | Correction des libellés dans le CdCF avant dépôt dossier jury | ⚠️ Ouvert | 2026-08-13 |

### 2.2 Risques opérationnels

| ID | Risque | Catégorie | P | I | Score | Mitigation | Statut | Date |
|----|--------|-----------|---|---|-------|------------|--------|------|
| RO-01 | Perte d'accès SSH si Tailscale tombe (accès controller) | Disponibilité | M | H | 6 | Cloudflare Tunnel SSH backup path (`controller.devandre.sbs → ssh://10.0.0.1:22`) PR #680 | ✅ Fermé | 2026-08-13 |
| RO-02 | Interruption de 90s sur `devandre.sbs` à chaque redémarrage du controller | Disponibilité | H | H | 9 | cloudflared → k8s 2 réplicas HA (PRs #678+#679) | ✅ Fermé | 2026-08-13 |
| RO-03 | Disque controller plein → Velero backup failure → MinIO stale error | Données/DR | M | H | 6 | Monitoring disk usage + `minicloud-recovery-check` check 14/15 + auto-restart MinIO | ✅ Fermé | 2026-08-08 |
| RO-04 | Absence de redondance géographique — panne secteur = cluster entier hors service | Disponibilité | L | H | 3 | Velero off-site Cloudflare R2 (backup hebdomadaire) + RTO < 4h documenté | ⚠️ Résiduel | 2026-08-07 |
| RO-05 | MAAS DHCP race condition avec box SFR — attribution IP incorrecte aux nœuds | Réseau | M | H | 6 | Plage dynamique supprimée, entrées DHCP statiques par MAC | ✅ Fermé | 2026-08-07 |
| RO-06 | swift-mac ne démarre pas après coupure secteur (WoL non configuré) | Disponibilité | M | M | 4 | `minicloud-wake-swift-mac.service` — envoi magic packet 60s après k3s | ✅ Fermé | 2026-08-07 |

### 2.3 Risques projet / certification

| ID | Risque | Catégorie | P | I | Score | Mitigation | Statut | Date |
|----|--------|-----------|---|---|-------|------------|--------|------|
| RP-01 | BC02 non validé si les 4 microservices ne sont pas construits avant la soutenance | Planning | M | H | 6 | Plan de livraison M1–M7 (Sep 2026 → Apr 2027), démarrage Sprint 1 immédiat | ⚠️ Ouvert | 2026-08-13 |
| RP-02 | Critères d'acceptation (REC-*) non validés faute de services déployés | Qualité | M | H | 6 | Validation incrémentale sprint par sprint — REC-POL-01 visé Sprint 1 | ⚠️ Ouvert | 2026-08-13 |
| RP-03 | Audit RGAA non réalisé sur ktayl-portal avant la soutenance | Conformité | M | H | 6 | Sprint M7 dédié RGAA AA — axe-core CI gate (issue #204) | ⚠️ Ouvert | 2026-08-13 |
| RP-04 | Dérive scope — ajout de fonctionnalités non dans le CdCF | Planning | M | M | 4 | CdCF §3.3 hors périmètre v1.0 explicite — toute évolution = avenant de CdCF | ✅ Mitigé | 2026-08-13 |
| RP-05 | Manque d'artefacts BC03 (coordination équipe, grille compétences) | Documentation | H | M | 6 | Issue #195 checklist : grille d'évaluation + plan développement compétences à livrer avant sept. 2026 | ⚠️ Ouvert | 2026-08-13 |

---

## 3. Tableau de bord des risques ouverts

```
Score ≥ 6 (Haute priorité) :
  RP-01  BC02 — microservices non construits                    [P: M, I: H]
  RP-02  REC-* non validés                                      [P: M, I: H]
  RP-03  RGAA audit non réalisé                                 [P: M, I: H]
  RP-05  Artefacts BC03 manquants                               [P: H, I: M]
  RT-10  Libellés BC erronés dans le CdCF                       [P: M, I: H]

Score 3–5 (Surveillance) :
  RT-07  swift-mac rebuild lente (port 100 Mbps)                [P: M, I: M]
  RO-04  Absence redondance géographique (résiduel acceptable)   [P: L, I: H]

Score ≤ 2 (Accepté) :
  aucun risque résiduel en dessous du seuil
```

---

## 4. Processus de gestion des risques

### Identification
Chaque début de sprint : revue de ce registre + identification de nouveaux risques via la checklist :
1. Un seul nœud est-il critique pour ce livrable ?
2. Une migration de données est-elle impliquée ?
3. Une dépendance externe non testée est-elle dans le périmètre ?
4. Le délai est-il tendu (< 1 semaine de marge) ?

### Escalade
| Score | Traitement |
|-------|-----------|
| ≥ 9 | Blocant — sprint ne démarre pas sans mitigation |
| 6–8 | Haute priorité — plan de mitigation défini avant J+2 |
| 3–5 | Surveillance — revue hebdomadaire |
| ≤ 2 | Accepté — documenté, pas d'action immédiate |

### Clôture
Un risque est fermé quand :
- La mitigation est déployée en production (PR mergée + ArgoCD Synced), **et**
- Le risque a été observé absent lors d'au moins un test ou incident réel

---

## 5. Prochaine revue

| Date cible | Déclencheur |
|------------|-------------|
| Début Sprint 1 (Sep 2026) | Revue risques RP-01, RP-02, RP-05 — plan de mitigation concret |
| Fin Sprint M3 (Jan 2027) | Revue risques certification : REC-CLM-*, COREP |
| Sprint M7 (Mar 2027) | Revue RP-03 — RGAA audit réalisé |
| 4 semaines avant soutenance | Revue globale — tous les risques ouverts doivent être fermés ou acceptés |
