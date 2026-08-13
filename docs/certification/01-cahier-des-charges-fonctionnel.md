---
id: cahier-des-charges-fonctionnel
title: Cahier des charges fonctionnel — Plateforme ktayl-solution
sidebar_label: Cahier des charges fonctionnel
---

# Cahier des charges fonctionnel  
## Plateforme de gestion de contrats et sinistres — ktayl-solution IS

| | |
|---|---|
| **Référence** | CERT-1 / CdCF-v1.0 |
| **Date** | 13 août 2026 |
| **Auteur** | Andrey-Vanlaurel Kanmegne Tabouguie |
| **Statut** | Draft — soumis pour validation RNCP39583 |
| **Certification visée** | RNCP39583 — Expert en Informatique et Système d'Information |
| **Blocs couverts** | BC01 · BC02 · BC03 · BC04 |

---

## 1. Objet du document

Ce cahier des charges fonctionnel (CdCF) définit les exigences fonctionnelles et non-fonctionnelles du système d'information ktayl-solution, une plateforme de gestion de contrats d'assurance et de sinistres déployée sur infrastructure bare-metal Kubernetes.

Le document constitue l'artefact de référence pour :
- la conception et le développement des quatre microservices constituant le cœur métier ;
- la validation des choix d'architecture vis-à-vis des contraintes réglementaires ACPR, GDPR et DORA ;
- le cahier de recette liant les exigences aux cas de tests (L1–L4) ;
- la démonstration des compétences BC01 à BC04 du référentiel RNCP39583.

---

## 2. Contexte et commanditaire

### 2.1 Contexte organisationnel

**ktayl-solution** est une organisation simulée d'assurance IARD et Vie opérant sous le régime prudentiel ACPR (Autorité de Contrôle Prudentiel et de Résolution). Elle couvre sept lignes de métier (LOB) : Auto, MRH, Santé, Prévoyance, Responsabilité Civile, Cyber-risque et Retraite collective.

Le système d'information existant repose sur un monolithe legacy Java EE, analogue aux systèmes de cœur assurance (type GERAS, Guidewire PolicyCenter, Alis) encore en production dans la majorité des assureurs français. Ce monolithe présente les caractéristiques typiques de la dette technique sectorielle :

- cycle de déploiement mensuel (release figée) ;
- absence d'API externe exploitable par des canaux digitaux ;
- absence de traçabilité DORA Art. 9 sur les décisions métier ;
- impossibilité d'intégrer des traitements IA sans extraction batch.

### 2.2 Enjeux stratégiques

| Enjeu | Traduction fonctionnelle |
|---|---|
| **Modernisation SI** | Migration strangler-fig : les nouveaux parcours passent par les microservices ; le legacy reste en lecture seule |
| **Conformité réglementaire** | ACPR (SCR/MCR), DORA (Art. 9 traçabilité, Art. 11 RTO < 4h), GDPR, RGAA AA |
| **Efficience opérationnelle** | Automatisation du triage sinistre J+0 (actuellement 2–3h/dossier) |
| **Time-to-market** | Pipeline GitOps dev → staging → prod en < 20 min |

### 2.3 Portée de la certification

Ce projet constitue le support technique de la certification **RNCP39583 — Expert en Informatique et Système d'Information** (niveau 7, équivalent Master 2) de l'auteur. Il démontre les compétences requises par les quatre blocs de compétences :

| Bloc | Intitulé | Démonstration principale |
|---|---|---|
| BC01 | Piloter un projet de développement logiciel | Architecture, CdCF, plan de charge, gouvernance Scrumban/PRINCE2 |
| BC02 | Concevoir et développer une solution logicielle | 4 microservices polyglots, tests L1–L4, OpenAPI, event sourcing |
| BC03 | Déployer et sécuriser une solution logicielle | GitOps k8s, RBAC, Gatekeeper OPA, cosign SBOM, Vault secrets |
| BC04 | Optimiser et faire évoluer une solution logicielle | Observabilité (Grafana/Loki/Tempo), VPA, canary Argo Rollouts, DORA metrics |

---

## 3. Objectifs du projet

### 3.1 Objectif principal

Concevoir et déployer un système de gestion de contrats et sinistres d'assurance cloud-native, composé de quatre microservices indépendants, communiquant par événements NATS JetStream, et exposés via un portail unifié.

### 3.2 Objectifs secondaires

1. **Automatisation du triage sinistre** : réduire le délai de première analyse de 2–3h à < 15 min via un assistant IA basé sur LangGraph.
2. **Traçabilité réglementaire complète** : chaque décision métier (souscription, avenant, liquidation) est horodatée, signée et archivée.
3. **Accessibilité RGAA AA** : le portail client doit passer un audit axe-core CI sans blocant.
4. **Résilience DORA** : RTO < 4h démontré par test de basculement Velero en Game Day documenté.
5. **Interopérabilité ERPNext** : synchronisation bidirectionnelle des données financières (primes, indemnités) via API REST.

### 3.3 Hors périmètre (v1.0)

- Gestion actuarielle et calcul des réserves SCR/MCR (relevé du système actuariel externe)
- Interfaçage avec le registre FICOBA (agrégation bancaire)
- Module de réassurance (cession proportionnelle)
- Application mobile native (iOS/Android)

---

## 4. Périmètre fonctionnel

Le projet couvre quatre domaines fonctionnels correspondant aux quatre microservices :

```
┌─────────────────────────────────────────────────────────────┐
│                    ktayl-portal (BC)                        │
│              Next.js 14 — Authentik OIDC                    │
│    ┌──────────────┐          ┌──────────────────────────┐   │
│    │  Portail     │          │    Portail courtier       │   │
│    │  assuré      │          │    (rôle: brokers)       │   │
│    └──────────────┘          └──────────────────────────┘   │
└───────────────┬──────────────────────┬──────────────────────┘
                │ REST                 │ REST
      ┌─────────▼──────┐    ┌──────────▼──────────┐
      │ ktayl-policy-  │    │  ktayl-claims-       │
      │ service (Go)   │    │  service (Java 21)   │
      └─────────┬──────┘    └──────────┬───────────┘
                │ NATS                 │ NATS
                └──────────┬───────────┘
                           │ claim.created / policy.amended
                  ┌────────▼───────────────┐
                  │ ktayl-ai-claims-       │
                  │ assistant (Python)     │
                  └────────────────────────┘
```

---

## 5. Acteurs et rôles

### 5.1 Utilisateurs finaux

| Acteur | Rôle Authentik | Fonctions accessibles |
|---|---|---|
| **Assuré** | `policyholders` | Consulter contrats et sinistres, soumettre une déclaration (FNOL), télécharger attestations, contacter l'assistant IA |
| **Courtier** | `brokers` | Gérer portefeuille clients, soumettre demandes de souscription, suivre commissions, accéder aux rapports LOB |
| **Gestionnaire sinistres** | `adjusters` | Instruire dossiers, valider/rejeter l'analyse IA, saisir décisions de liquidation |
| **Souscripteur** | `underwriters` | Valider propositions de contrats, paramétrer règles de souscription |
| **Administrateur IS** | `platform-admins` | Gérer utilisateurs, accéder aux logs d'audit, superviser pipelines batch |

### 5.2 Systèmes externes

| Système | Type | Interaction |
|---|---|---|
| **ERPNext** | ERP financier (on-cluster) | Synchronisation primes, quittances, sinistres liquidés |
| **Docuseal** | Signature électronique | Signature de contrats et règlements sinistres |
| **Paperless-ngx** | DMS | Archivage long terme des pièces justificatives |
| **Authentik** | IAM/OIDC | SSO, gestion des rôles, M2M client credentials |
| **NATS JetStream** | Message broker | Transport des événements inter-microservices |
| **LiteLLM / vLLM** | Inférence IA | Modèles LLM pour le triage et la génération de rapports |
| **Qdrant** | Base vectorielle | Recherche sémantique sur documents de contrats |

---

## 6. Besoins fonctionnels

### 6.1 Gestion des contrats (ktayl-policy-service)

#### BF-POL-01 — Souscription d'un nouveau contrat

**Description** : Un courtier ou un souscripteur peut créer un nouveau contrat à partir d'une proposition commerciale validée.

**Entrées** :
- Identité de l'assuré (nom, SIREN/SIRET ou NIR selon LOB)
- LOB et produit (ex. IARD-AUTO-RC)
- Dates d'effet et d'échéance
- Sommes assurées et franchises
- Mode de paiement (SEPA, virement)

**Traitement** :
1. Validation des règles de souscription (âge, zone géographique, antécédents)
2. Calcul de la prime nette + taxes applicables (TSCA ou TVA selon produit)
3. Génération d'un numéro de police unique (format : `POL-AAAA-NNNNNN`)
4. Publication de l'événement `policy.created` sur NATS JetStream
5. Déclenchement de la génération de l'attestation PDF (via Docuseal)

**Sorties** :
- Contrat créé en base PostgreSQL (état `DRAFT`)
- Événement NATS publié
- Demande de signature électronique créée dans Docuseal

**Règles métier** :
- Un contrat ne passe à l'état `ACTIVE` qu'après réception du webhook Docuseal confirmant la signature
- La prime doit être supérieure à la prime minimale paramétrable par LOB
- Le délai de rétractation de 14 jours est tracé (DORA Art. 9)

#### BF-POL-02 — Avenant (modification de contrat)

**Description** : Modification d'un contrat actif (changement de véhicule, modification des garanties, ajout de clause).

**Types d'avenants supportés** :
- Changement d'objet assuré
- Modification des garanties (extension, réduction)
- Changement des coordonnées bancaires (SEPA)
- Suspension temporaire (résidence secondaire)

**Contraintes** : Tout avenant déclenche un recalcul de prime (pro-rata temporis) et publie `policy.amended`.

#### BF-POL-03 — Renouvellement

**Description** : Renouvellement automatique à l'échéance anniversaire (J-60 : avis d'échéance, J-30 : relance, J-0 : renouvellement ou résiliation).

**Batch** : Spring Batch job `PolicyRenewalJob` exécuté quotidiennement à 06:00 UTC.

#### BF-POL-04 — Résiliation

**Description** : Résiliation à l'initiative de l'assuré (loi Hamon, loi Chatel) ou de l'assureur (non-paiement, aggravation du risque).

**Motifs implémentés** :

| Code | Motif | Préavis réglementaire |
|---|---|---|
| `RES-HAM` | Résiliation loi Hamon (après 1 an) | 1 mois |
| `RES-CHA` | Résiliation loi Chatel | À la date d'échéance |
| `RES-IMP` | Non-paiement | 40 jours après mise en demeure |
| `RES-RIS` | Aggravation du risque | 10 jours après notification |

#### BF-POL-05 — Consultation du portefeuille (API)

**Description** : API REST permettant la consultation paginée des contrats d'un assuré ou d'un courtier.

**Endpoints** :
- `GET /policies` — liste paginée, filtrable par LOB/statut/date
- `GET /policies/{id}` — détail complet avec historique des avenants
- `GET /policies/{id}/documents` — liste des pièces (attestation, conditions générales)

---

### 6.2 Gestion des sinistres (ktayl-claims-service)

#### BF-CLM-01 — Déclaration de sinistre (FNOL)

**Description** : Première déclaration de sinistre (First Notice of Loss) par un assuré ou un courtier.

**Entrées** :
- Référence de la police (validation via appel à ktayl-policy-service)
- Type d'événement (accident, incendie, vol, dégât des eaux, etc.)
- Date et heure du sinistre
- Description textuelle et pièces jointes (photos, PV de police, certificat médical)
- Coordonnées du déclarant

**Traitement** :
1. Validation de l'existence et de l'activité de la police référencée
2. Vérification de la couverture du type de sinistre
3. Attribution d'un numéro de sinistre unique (`SIN-AAAA-NNNNNN`)
4. Stockage des pièces jointes dans MinIO → déclenchement archivage Paperless-ngx
5. Publication de `claim.created` sur NATS → déclenchement de l'assistant IA
6. Notification au gestionnaire assigné (via Matrix/Element)

**État initial** : `SUBMITTED`

#### BF-CLM-02 — Machine à états du sinistre

```
DRAFT ──► SUBMITTED ──► UNDER_INVESTIGATION ──► PENDING_DOCUMENTS
                                │
                                ├──► APPROVED ──► SETTLEMENT_PENDING ──► SETTLED ──► CLOSED
                                │
                                └──► REJECTED
```

**Transitions autorisées** :

| De | Vers | Acteur | Condition |
|---|---|---|---|
| `SUBMITTED` | `UNDER_INVESTIGATION` | Gestionnaire | Automatique après analyse IA |
| `UNDER_INVESTIGATION` | `PENDING_DOCUMENTS` | Gestionnaire | Pièces manquantes identifiées |
| `PENDING_DOCUMENTS` | `UNDER_INVESTIGATION` | Système | Réception des pièces requises |
| `UNDER_INVESTIGATION` | `APPROVED` | Gestionnaire | Analyse complète, couverture confirmée |
| `UNDER_INVESTIGATION` | `REJECTED` | Gestionnaire | Exclusion de garantie ou fraude avérée |
| `APPROVED` | `SETTLEMENT_PENDING` | Système | Accord de l'assuré sur l'indemnité |
| `SETTLEMENT_PENDING` | `SETTLED` | Système | Virement effectué (ERPNext payment.created) |
| `SETTLED` | `CLOSED` | Système | Délai de recours expiré (90 jours) |

**Contraintes** :
- Toute transition est auditée : acteur, timestamp, motif (DORA Art. 9)
- Délai de traitement maximal : 30 jours (Art. L113-5 Code des assurances)
- Une alerte Alertmanager se déclenche si un sinistre reste `UNDER_INVESTIGATION` > 15 jours

#### BF-CLM-03 — Instruction du dossier

**Description** : Interface de travail du gestionnaire sinistres permettant de consulter l'analyse IA, saisir les décisions, demander des expertises.

**Fonctions** :
- Consultation de l'analyse IA (résumé, score de fraude, clauses applicables)
- Validation ou rejet de la recommandation IA
- Saisie du montant d'indemnité proposé
- Ajout de notes d'instruction (tracées)
- Déclenchement d'une expertise (créé comme tâche Plane CE)

#### BF-CLM-04 — Rapport COREP batch (Spring Batch)

**Description** : Génération mensuelle du bordereau de règlements sinistres au format ACPR (COREP — Common Reporting).

**Spécifications** :
- Fréquence : 1er jour ouvré du mois suivant, 02:00 UTC
- Format de sortie : XML XBRL (schéma EIOPA S.19.01) + CSV de contrôle
- Périmètre : tous sinistres `SETTLED` du mois précédent
- Dépôt : MinIO bucket `acpr-reports/` + notification Email via Stalwart

---

### 6.3 Assistant IA de triage (ktayl-ai-claims-assistant)

#### BF-AI-01 — Triage automatique à la réception FNOL

**Description** : Dès réception de `claim.created` sur NATS, l'assistant analyse le dossier et produit une recommandation structurée.

**Workflow LangGraph** :

```
claim.created (NATS)
    │
    ▼
[extract_fields]
    Extraction structurée depuis PDF/photos
    (via markitdown-proxy + Docling)
    │
    ▼
[validate_coverage]
    Appel ktayl-policy-service : la police couvre-t-elle ce type de sinistre ?
    │
    ▼
[search_policy_clauses]
    RAG Qdrant (collection: policy-docs)
    Récupère top-5 clauses pertinentes
    │
    ▼
[score_fraud_risk]
    Modèle scikit-learn : probabilité de fraude 0→1
    Features : montant déclaré, délai déclaration, historique assuré, zone géo
    │
    ├── [score > 0.7] ──► [human_interrupt]
    │                         Alerte gestionnaire + suspension
    │
    └── [score ≤ 0.7] ──► [generate_summary]
                              Résumé LLM (< 200 mots, français)
                              + montant d'indemnité suggéré
                              │
                              ▼
                          [create_plane_task]
                              Tâche Plane CE pour le gestionnaire
                              │
                              ▼
                          [notify_adjuster]
                              Message Matrix avec résumé + lien dossier
```

**Sortie** :
- Résumé structuré JSON (persisté en base, lisible depuis le portail gestionnaire)
- Score de fraude (0–100)
- Clauses contractuelles applicables (références + extraits)
- Montant d'indemnité suggéré (basé sur barèmes configurés)
- Tâche Plane CE créée

**Performances cibles** :
- Temps de traitement total : < 15 min (contre 2–3h manuel)
- Disponibilité : 99,5% (1 replica minimum, scalé par KEDA sur queue NATS)

#### BF-AI-02 — Interface de chat assistée (portail assuré)

**Description** : Widget de chat dans le portail assuré permettant de poser des questions sur son contrat et son sinistre.

**Capacités** :
- Questions sur les garanties du contrat (RAG sur policy-docs)
- Statut du sinistre en cours
- Documents téléchargeables disponibles
- Questions génériques sur les procédures (FAQ RAG)

**Contraintes** :
- Le chat ne peut pas prendre de décisions engageantes (ex. ouvrir un sinistre) — redirige vers le formulaire FNOL
- Toutes les conversations sont tracées dans Langfuse (rétention 90 jours)
- Le modèle doit refuser les questions hors périmètre assurance

---

### 6.4 Portail client et courtier (ktayl-portal)

#### BF-POR-01 — Authentification et gestion de session

**Description** : Authentification centralisée via Authentik OIDC. Aucune gestion de mot de passe dans le portail.

**Flux** :
1. L'utilisateur clique « Se connecter »
2. Redirection vers Authentik (`auth.devandre.sbs`)
3. Authentification (identifiant + TOTP ou WebAuthn)
4. Retour avec `id_token` + `access_token` (PKCE)
5. next-auth persiste la session (cookie httpOnly)
6. Les routes sont protégées par middleware Next.js selon le groupe Authentik

**Groupes et accès** :
- `/my/*` — groupe `policyholders`
- `/broker/*` — groupe `brokers`
- `/admin/*` — groupe `platform-admins`

#### BF-POR-02 — Tableau de bord assuré

Accès : `/my/dashboard`

| Widget | Source de données | Fréquence de rafraîchissement |
|---|---|---|
| Contrats actifs | ktayl-policy-service | Temps réel (React Query) |
| Sinistres en cours | ktayl-claims-service | Temps réel |
| Prochain prélèvement | ERPNext payment schedule | Quotidien |
| Documents récents | Paperless-ngx API | Quotidien |

#### BF-POR-03 — Formulaire FNOL en ligne

**Description** : Formulaire guidé en 5 étapes permettant à un assuré de déclarer un sinistre.

**Étapes** :
1. Sélection du contrat concerné
2. Sélection du type d'événement et de la date
3. Description textuelle (champ libre + validation longueur > 50 caractères)
4. Téléversement des pièces jointes (PDF, images, max 10 Mo/fichier, 5 fichiers max)
5. Récapitulatif + confirmation

**Accessibilité** : Chaque étape respecte RGAA AA — labels explicites, gestion du focus, messages d'erreur associés aux champs, pas de validation uniquement par couleur.

#### BF-POR-04 — Espace courtier

Accès : `/broker/*`

| Fonctionnalité | Endpoint consommé |
|---|---|
| Portefeuille clients | `GET /policies?broker_id={id}` |
| Soumission de proposition | `POST /policies` |
| Suivi commissions | ERPNext CRM API |
| Rapports de production | ktayl-policy-service analytics |

#### BF-POR-05 — Téléchargement de documents

**Description** : Les assurés peuvent télécharger leurs documents (attestations, conditions générales, avis d'échéance).

**Sources** :
- Attestations PDF : générées à la volée par ktayl-policy-service (Go + `wkhtmltopdf`)
- Conditions générales : Paperless-ngx DMS (documents statiques indexés)
- Correspondance : Paperless-ngx (documents entrants archivés)

---

## 7. Exigences non-fonctionnelles

### 7.1 Performance

| Métrique | Cible | Mesure |
|---|---|---|
| Latence API p95 (hors IA) | < 200 ms | Grafana / Tempo |
| Latence triage IA p95 | < 15 min | Langfuse trace duration |
| Latence chargement portail (FCP) | < 1,5 s | Lighthouse CI |
| Débit FNOL simultanés | 50 req/s | k6 load test |
| Disponibilité (SLO) | 99,5% sur 30 jours | Grafana SLO dashboard |

### 7.2 Sécurité

| Exigence | Implémentation |
|---|---|
| Authentification forte | Authentik OIDC + TOTP obligatoire pour `adjusters` et `underwriters` |
| Autorisation fine | RBAC Kubernetes + groupe Authentik sur chaque route |
| Secrets | Vault (ESO) — aucun secret en clair dans Git |
| Chiffrement transit | TLS 1.3 sur tous les endpoints internes et externes |
| Chiffrement repos | Longhorn volume encryption (LUKS) pour les PVC PostgreSQL |
| Admission | OPA Gatekeeper — 18 constraints actives (non-root, no-hostPath, etc.) |
| Supply chain | cosign + SBOM sur chaque image (staging et prod) |
| DAST | OWASP ZAP en CI sur PR → main |
| Audit log | Chaque action métier : acteur, timestamp, IP source, hash contenu |

### 7.3 Résilience

| Exigence | Cible | Mécanisme |
|---|---|---|
| RTO (DORA Art. 11) | < 4 h | Velero restore + Longhorn snapshots |
| RPO | < 1 h | Backup horaire Longhorn + kine SQLite |
| Disponibilité nœud | 1 nœud down tolerable | PodDisruptionBudget + affinity rules |
| Dégradation gracieuse | Portail lisible sans IA | Circuit breaker Resilience4j (claims-service) |

### 7.4 Observabilité

| Signal | Outil | Rétention |
|---|---|---|
| Métriques | Prometheus + Grafana | 15 jours |
| Logs | Loki (OTel pipeline) | 30 jours |
| Traces | Tempo (OTLP) | 7 jours |
| Traces IA | Langfuse | 90 jours |
| Alertes | Alertmanager → Stalwart mail + Matrix | — |

Dashboards Grafana requis :
- `ktayl-claims-slo` : taux d'erreur, latence, saturation par service
- `ktayl-ai-triage` : durée moyenne de triage, score de fraude moyen, taux human_interrupt
- `ktayl-batch-corep` : statut du batch mensuel, nombre de dossiers traités

### 7.5 Accessibilité (RGAA)

Le portail (`ktayl-portal`) doit satisfaire :

- **RGAA 4.1 Level AA** : 50 critères applicables
- **WCAG 2.1 AA** : conformité vérifiée par axe-core en CI (0 violations de niveau critique ou sérieux)
- **Lighthouse Accessibility** : score ≥ 90 en CI sur chaque PR
- Audit manuel NVDA/ChromeVox sur les parcours FNOL et consultation de contrat

---

## 8. Architecture générale

### 8.1 Vue d'ensemble

```
Internet ──► Cloudflare Tunnel ──► nginx-ingress (10.0.0.200)
                                        │
              ┌─────────────────────────┼────────────────────────┐
              │                         │                         │
         ktayl-portal             ktayl-policy-service     ktayl-claims-service
         (Next.js 14)             (Go 1.23)                (Java 21 / Spring Boot 3)
         ns: portal               ns: insurance            ns: insurance
              │                         │                         │
              └─────────────────────────┴─────────────────────────┘
                                        │ NATS JetStream
                                  ktayl-ai-claims-assistant
                                  (Python 3.12 / LangGraph)
                                  ns: ai
```

### 8.2 Stack par microservice

| Service | Langage | Framework | DB | Messaging |
|---|---|---|---|---|
| ktayl-policy-service | Go 1.23 | net/http + pgx | PostgreSQL 16 | NATS pub |
| ktayl-claims-service | Java 21 | Spring Boot 3.3 + Spring Batch | PostgreSQL 16 | NATS pub/sub |
| ktayl-ai-claims-assistant | Python 3.12 | FastAPI + LangGraph | — (stateless) | NATS sub |
| ktayl-portal | TypeScript | Next.js 14 App Router | — (BFF only) | — |

### 8.3 Justification des choix technologiques

**Go pour le service de polices** : langage natif de la plateforme (platform-demo, minicloud-plane) ; idéal pour un service REST haute fréquence (notation, avenant batch). Goroutines < JVM overhead pour ce profil de charge.

**Java 21 pour le service sinistres** : standard de l'industrie française (AXA, GMF, CNP). Spring Batch est la solution de référence pour les exports COREP. Les virtual threads (Project Loom) éliminent le besoin de WebFlux pour la concurrence. Démontre l'expertise sur le stack legacy modernisé.

**Python pour l'assistant IA** : seul écosystème natif pour LangGraph, LiteLLM, scikit-learn et bge-m3. Cohérence avec minicloud-agent et minicloud-crew-agent déjà en production.

**Next.js 14 pour le portail** : SSR nécessaire pour RGAA (accessibilité) et Core Web Vitals mobiles. App Router (React Server Components) réduit la surface JS côté client. Un seul codebase pour les vues assuré et courtier (route-level auth par groupe Authentik).

---

## 9. Modèle de données (vue logique)

### 9.1 Service de polices

```
Policy
├── id: UUID (PK)
├── policy_number: VARCHAR(20) UNIQUE -- POL-2027-000001
├── status: ENUM(DRAFT, ACTIVE, SUSPENDED, CANCELLED, EXPIRED)
├── lob: VARCHAR(20) -- IARD-AUTO, IARD-MRH, PREV-IND, ...
├── product_code: VARCHAR(30)
├── policyholder_id: UUID (FK → external: Authentik user ID)
├── broker_id: UUID (FK → ERPNext CRM contact)
├── effective_date: DATE
├── expiry_date: DATE
├── net_premium: DECIMAL(12,2)
├── tax_rate: DECIMAL(5,4)
├── total_premium: DECIMAL(12,2)
├── payment_schedule: JSONB
├── created_at: TIMESTAMPTZ
└── updated_at: TIMESTAMPTZ

PolicyEndorsement
├── id: UUID (PK)
├── policy_id: UUID (FK → Policy)
├── endorsement_type: ENUM
├── effective_date: DATE
├── changes: JSONB
├── premium_delta: DECIMAL(12,2)
└── created_at: TIMESTAMPTZ

AuditLog (append-only)
├── id: UUID (PK)
├── entity_type: VARCHAR(20)
├── entity_id: UUID
├── action: VARCHAR(50)
├── actor_id: VARCHAR(255)
├── ip_address: INET
├── payload_hash: VARCHAR(64) -- SHA-256
└── created_at: TIMESTAMPTZ
```

### 9.2 Service sinistres

```
Claim
├── id: UUID (PK)
├── claim_number: VARCHAR(20) UNIQUE -- SIN-2027-000001
├── policy_id: UUID (FK → policy-service, cross-service reference)
├── status: ENUM(DRAFT, SUBMITTED, UNDER_INVESTIGATION, ...)
├── event_type: VARCHAR(50)
├── event_date: TIMESTAMPTZ
├── declared_amount: DECIMAL(12,2)
├── settled_amount: DECIMAL(12,2)
├── fraud_score: DECIMAL(5,4)
├── ai_summary: TEXT
├── adjuster_id: VARCHAR(255)
├── created_at: TIMESTAMPTZ
└── updated_at: TIMESTAMPTZ

ClaimDocument
├── id: UUID (PK)
├── claim_id: UUID (FK → Claim)
├── document_type: VARCHAR(30)
├── minio_key: VARCHAR(500)
├── paperless_id: INTEGER
├── uploaded_at: TIMESTAMPTZ
└── uploaded_by: VARCHAR(255)

ClaimStatusHistory (append-only)
├── id: UUID (PK)
├── claim_id: UUID (FK → Claim)
├── from_status: ENUM
├── to_status: ENUM
├── actor_id: VARCHAR(255)
├── reason: TEXT
└── created_at: TIMESTAMPTZ
```

---

## 10. Intégrations

### 10.1 NATS JetStream

| Subject | Producteur | Consommateurs | Payload |
|---|---|---|---|
| `policy.created` | ktayl-policy-service | ktayl-portal, ERPNext webhook | PolicyCreatedEvent |
| `policy.amended` | ktayl-policy-service | ERPNext webhook | PolicyAmendedEvent |
| `policy.cancelled` | ktayl-policy-service | ERPNext webhook | PolicyCancelledEvent |
| `claim.created` | ktayl-claims-service | ktayl-ai-claims-assistant | ClaimCreatedEvent |
| `claim.status_changed` | ktayl-claims-service | ktayl-portal | ClaimStatusChangedEvent |
| `claim.settled` | ktayl-claims-service | ERPNext webhook | ClaimSettledEvent |

Configuration JetStream :
- **Stream** : `INSURANCE`, retention `limits`, max age 30 jours
- **Consumer** : durable, deliver policy `all`, ack policy `explicit`
- **Replay** : enabled (pour rejeu en cas de panne du consommateur IA)

### 10.2 ERPNext

| Flux | Direction | Mécanisme |
|---|---|---|
| Création de quittance prime | claims-service → ERPNext | REST API POST /api/resource/Sales Invoice |
| Enregistrement de règlement | ERPNext → claims-service | Webhook ERPNext `payment_entry.after_insert` |
| Fiche contact assuré | ktayl-portal → ERPNext | REST API GET /api/resource/Customer |

### 10.3 Docuseal

**Flux signature de contrat** :
1. ktayl-policy-service POST `/api/v1/submissions` avec template `Contrat de police`
2. Docuseal envoie email au souscripteur et au courtier
3. Après signature, Docuseal appelle webhook `POST /webhooks/docuseal/signed` sur ktayl-policy-service
4. ktayl-policy-service passe la police de `DRAFT` à `ACTIVE`

**Authentification** : API token Vault `secret/platform/docuseal:api-token`

### 10.4 Paperless-ngx

Archivage automatique de tout document signé ou généré :
- ktayl-policy-service : attestations PDF → POST `/api/documents/` avec tag `policy`
- ktayl-claims-service : pièces jointes FNOL → POST `/api/documents/` avec tag `claim`
- Paperless assigne les correspondants automatiquement via son moteur de règles (correspondant = numéro de police)

---

## 11. Contraintes réglementaires

### 11.1 ACPR (Autorité de Contrôle Prudentiel et de Résolution)

| Exigence | Implémentation |
|---|---|
| Conservation des données de gestion 10 ans | Longhorn PVC + Velero off-site (Cloudflare R2), politique de rétention 10 ans |
| Traçabilité complète des décisions de souscription | AuditLog append-only, signé par hash SHA-256 |
| Reporting prudentiel (COREP S.19.01) | Spring Batch `ClaimsReportJob` — XML XBRL mensuel |
| Délai de traitement sinistres (Art. L113-5) | Alertmanager : alerte J+15 si `UNDER_INVESTIGATION` |

### 11.2 RGPD (Règlement Général sur la Protection des Données)

| Exigence | Implémentation |
|---|---|
| Minimisation des données | Seules les données nécessaires au contrat sont collectées (PIA documenté) |
| Droit à l'effacement | Procédure de pseudonymisation (pas d'effacement physique — obligation ACPR prime) |
| Durée de conservation | Données de contrat : 10 ans après expiration ; logs d'accès : 1 an |
| Transferts hors UE | Aucun (infrastructure on-premises FR, LLM local vLLM ou Azure OpenAI EU) |
| DPO | Rôle de DPO fictif : administrateur IS |

### 11.3 DORA (Digital Operational Resilience Act — EU 2022/2554)

| Article | Exigence | Implémentation |
|---|---|---|
| Art. 9 | Traçabilité et classification des incidents TIC | AuditLog, Falco alerting, severity classification dans Alertmanager |
| Art. 11 | Tests de résilience opérationnelle numérique | Game Day documenté (PR chaos-mesh #phase81), RTO mesuré < 4h |
| Art. 17 | Gestion des prestataires TIC tiers | OpenTofu registre (AWS SES, Azure OpenAI, Cloudflare) — budget €10/mois |
| Art. 25 | Tests de pénétration basés sur la menace (TLPT) | OWASP ZAP CI + Kube-bench rapports dans le backlog |

### 11.4 Factur-X / E-invoicing

Toutes les factures générées par ERPNext doivent être conformes à la **Factur-X Minimum** (profil CII/D16B) — obligation légale française à compter du 1er septembre 2026 pour les assujettis à la TVA.

Implémentation : générateur Python pure (`apps/erpnext/erpnext/public/py/facturx_generator.py`) — 5 assertions vérifiées en CI.

---

## 12. Plan de livraison prévisionnel

### 12.1 Jalons

| Jalon | Date cible | Livrable |
|---|---|---|
| **M0** | Août 2026 | CdCF finalisé + architecture validée (ce document) |
| **M1** | Octobre 2026 | ktayl-policy-service v1.0 — CRUD polices + tests L1/L2 |
| **M2** | Novembre 2026 | ktayl-claims-service v1.0 — FNOL + machine à états + tests |
| **M3** | Décembre 2026 | ktayl-ai-claims-assistant v1.0 — workflow LangGraph complet |
| **M4** | Janvier 2027 | ktayl-portal v1.0 — portail assuré + audit RGAA |
| **M5** | Février 2027 | Intégration complète + tests E2E + batch COREP |
| **M6** | Mars 2027 | Performance tuning + chaos game day + documentation finale |
| **Soutenance** | Avril 2027 | Présentation RNCP39583 |

### 12.2 Plan de charge estimé

| Service | Complexité | Effort estimé |
|---|---|---|
| ktayl-policy-service (Go) | Moyenne | 3 semaines |
| ktayl-claims-service (Java) | Élevée (Spring Batch + COREP) | 5 semaines |
| ktayl-ai-claims-assistant (Python) | Élevée (LangGraph + ML) | 4 semaines |
| ktayl-portal (Next.js) | Moyenne (RGAA + SSR) | 3 semaines |
| Intégration & tests E2E | — | 2 semaines |
| Documentation & soutenance | — | 1 semaine |
| **Total** | | **18 semaines** |

---

## 13. Critères d'acceptation

### 13.1 Critères fonctionnels (cahier de recette)

| Réf. | Scénario | Résultat attendu | Statut |
|---|---|---|---|
| REC-POL-01 | Souscription contrat IARD-AUTO avec signature Docuseal | Police `ACTIVE`, événement `policy.created` publié, attestation PDF générée | À valider |
| REC-POL-02 | Résiliation loi Hamon avant échéance | Police `CANCELLED`, remboursement pro-rata calculé, email de confirmation | À valider |
| REC-CLM-01 | FNOL assuré — sinistre MRH dégât des eaux | Sinistre `SUBMITTED`, analyse IA déclenchée < 1 min, tâche Plane créée | À valider |
| REC-CLM-02 | Sinistre avec score de fraude > 0,7 | Workflow suspendu, alerte gestionnaire dans Matrix, statut `UNDER_INVESTIGATION` | À valider |
| REC-CLM-03 | Liquidation et virement ERPNext | Sinistre `SETTLED`, entrée de paiement ERPNext créée, document archivé Paperless | À valider |
| REC-AI-01 | Triage complet sur dossier test (PDF + 3 clauses) | Résumé < 200 mots, montant suggéré dans ±10% du barème, < 15 min | À valider |
| REC-POR-01 | FNOL via portail — parcours complet | Sinistre créé, pièces uploadées, confirmation affichée, RGAA 0 violation | À valider |
| REC-BATCH-01 | Batch COREP mensuel | XML XBRL valide, 0 erreur de validation de schéma, déposé dans MinIO | À valider |

### 13.2 Critères de qualité logicielle

| Critère | Seuil | Outil |
|---|---|---|
| Couverture de tests (L1) | ≥ 80% sur code métier | JaCoCo (Java) / go test -cover / pytest-cov |
| Tests d'intégration (L2) | 100% des endpoints REST | Testcontainers + Playwright |
| Lint / formatage | 0 erreur | golangci-lint, checkstyle, ruff, eslint + tsc |
| Vulnérabilités connues | 0 critique | Trivy + Dependabot |
| Accessibilité | 0 violation axe-core niveau A/AA | axe-core CI + Lighthouse ≥ 90 |
| Documentation API | 100% endpoints documentés | OpenAPI (Swagger UI + Backstage) |

### 13.3 Définition of Done (GOV-3, issue #149)

Chaque service est considéré « Done » lorsque :

- [ ] OpenAPI spec publiée dans le portail API Backstage
- [ ] Tests unitaires L1 ≥ seuil de couverture
- [ ] Tests d'intégration L2 avec conteneurs réels
- [ ] Pipeline GitOps complet : dev → staging → prod
- [ ] Entrée Catalog Backstage (`catalog-info.yaml`)
- [ ] Événements NATS documentés (JetStream subject + schéma JSON)
- [ ] Secrets gérés via ESO/Vault (0 secret dans Git)
- [ ] PVC Longhorn épinglé au nœud approprié (pour StatefulSets)
- [ ] Dashboard Grafana `ktayl-*` déployé en ConfigMap

---

## 14. Annexes

### 14.1 Glossaire

| Terme | Définition |
|---|---|
| **FNOL** | First Notice of Loss — première déclaration d'un sinistre par l'assuré |
| **COREP** | Common Reporting — cadre de reporting réglementaire prudentiel ACPR/EBA |
| **LOB** | Line of Business — ligne de métier assurance (Auto, MRH, etc.) |
| **TSCA** | Taxe Spéciale sur les Conventions d'Assurance (remplace TVA pour l'assurance) |
| **PCG** | Plan Comptable Général — référentiel comptable français |
| **GERAS** | Système de gestion de sinistres legacy (référentiel de comparaison HDI) |
| **Strangler Fig** | Pattern de modernisation progressive : les nouveaux appels passent par le nouveau système, le legacy reste en arrière-plan |
| **M2M** | Machine-to-Machine — authentification inter-services sans utilisateur humain |
| **BFF** | Backend For Frontend — couche d'agrégation côté serveur Next.js |
| **RGAA** | Référentiel Général d'Amélioration de l'Accessibilité (standard français, base WCAG) |
| **DORA** | Digital Operational Resilience Act — règlement européen sur la résilience numérique |
| **RTO** | Recovery Time Objective — temps maximal de remise en service après incident |
| **RPO** | Recovery Point Objective — perte de données maximale acceptable |

### 14.2 Références

| Document | Lien |
|---|---|
| Platform Backlog | https://github.com/andrelair-platform/platform-backlog |
| Issue #198 — ktayl-claims-service | https://github.com/andrelair-platform/platform-backlog/issues/198 |
| Issue #203 — ktayl-policy-service | https://github.com/andrelair-platform/platform-backlog/issues/203 |
| Issue #200 — ktayl-ai-claims-assistant | https://github.com/andrelair-platform/platform-backlog/issues/200 |
| Issue #202 — ktayl-portal | https://github.com/andrelair-platform/platform-backlog/issues/202 |
| Architecture de production | [Production Stack Architecture](../developer-platform/production-stack-architecture) |
| Catalogue des applications métier | [Business Applications Catalog](../insurance-platform/business-applications-catalog) |
| Stratégie de tests | [Testing Strategy](../engineering-standards/testing-strategy) |
| RNCP39583 | https://www.francecompetences.fr/recherche/rncp/39583/ |
| ACPR COREP | https://www.acpr.banque-france.fr/reglementation/reporting-prudentiel |
| DORA (EU 2022/2554) | https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32022R2554 |
| RGAA 4.1 | https://www.numerique.gouv.fr/publications/rgaa-accessibilite/ |
