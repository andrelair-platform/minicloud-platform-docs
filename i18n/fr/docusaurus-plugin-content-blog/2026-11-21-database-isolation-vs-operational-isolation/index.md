---
slug: database-isolation-vs-operational-isolation
title: "L'isolation des bases n'est pas l'isolation opérationnelle — quand des apps Postgres doivent partager un cluster"
authors: [andrelair]
tags: [databases, postgresql, cnpg, backup, disaster-recovery, architecture, dora, carnets]
date: 2026-11-21
description: "En parcourant les bases de la plateforme, j'ai remarqué que deux serveurs Postgres hébergent plusieurs bases — Backstage 13, le serveur IA 6. D'où la vraie question de conception : quand des apps doivent-elles partager un cluster Postgres, et quand chacune mérite-t-elle le sien ? La réponse tient à une distinction facile à manquer — des bases séparées isolent l'accès, pas les opérations, et surtout pas la restauration."
---

En câblant un client SQL de bureau sur la vingtaine d'instances Postgres de la plateforme, petite surprise :
deux serveurs hébergent **plusieurs** bases à la fois. **Backstage** en garde **13** (une par plugin —
`backstage_plugin_catalog`, `_auth`, `_scaffolder`, …) ; le serveur **IA** partagé en garde **6** (une par
outil — `openwebui`, `litellm`, `ragdb`, `vaultwarden`, `flowise`, `mlflow`). Tout le reste utilise une base
par serveur.

C'est une curiosité d'interface. Mais elle a forcé la vraie question de conception derrière : **quand des
apps doivent-elles partager un cluster Postgres, et quand chacune doit-elle avoir le sien ?** La réponse
repose sur une distinction facile à aplatir — et coûteuse quand on le fait.

{/* truncate */}

## Un serveur, plusieurs bases

D'abord le modèle mental, parce qu'il piège. Un **serveur** Postgres (une instance, un host:port, un login)
est un *conteneur* de plusieurs **bases** :

```
Serveur/instance   (un pod, un host:port, un login superutilisateur)
   └── Bases               ← il peut y en avoir plusieurs
         └── Schémas
               └── Tables
```

Le serveur est un immeuble ; chaque base est un appartement. Le superutilisateur `postgres` est le passe —
mais il faut quand même choisir **quel appartement** ouvrir. (Connectez-vous au mauvais — la base `postgres`
vide par défaut — et vous jurerez que les données ont disparu. Non : vous êtes dans la mauvaise pièce.)

Backstage et le serveur IA détiennent beaucoup d'appartements à dessein : Backstage tourne en mode
*base-par-plugin*, et le serveur IA regroupe plusieurs petits outils sur une instance au lieu de faire
tourner six déploiements Postgres séparés sur un cluster à ressources serrées. La consolidation est un *bon*
réflexe ici. La question est jusqu'où la pousser — et c'est là que les deux isolations comptent.

## La distinction : isolation des bases ≠ isolation opérationnelle

Mettre deux apps sur un cluster avec des bases et rôles séparés donne l'**isolation des bases**. Cela ne
donne **pas** l'**isolation opérationnelle**. Ce sont deux choses différentes :

| | **Isolation des bases** (base + rôle séparés) | **Isolation opérationnelle** (cluster séparé) |
|---|---|---|
| Ce que ça contrôle | l'**accès** — ce que chaque app peut lire/écrire | le **rayon d'impact** — CPU, mémoire, I/O disque, une panne ou mise à jour à l'échelle du cluster |
| Les apps d'un même cluster partagent quand même | — | tout ce qui précède, **plus une seule frontière de backup/PITR** |

Un rôle restreint à sa propre base signifie que LiteLLM ne peut pas lire les lignes d'Open WebUI. Bien. Mais
les deux se disputent toujours le même CPU, la même mémoire et les mêmes I/O disque, les deux tombent dans
la même panne de cluster, les deux bougent ensemble lors d'une mise à jour — et, le point le plus dur,
**les deux vivent dans la même frontière de backup physique.**

## La frontière de restauration, celle qu'on oublie

Un backup physique CloudNativePG + restauration à un instant (PITR) restaure le **cluster entier** — pas une
seule base. Donc « restaurer seulement `litellm` à hier 14h00 » n'est pas une commande unique. C'est :

1. restaurer le cluster **entier** sur une instance **temporaire** à cet instant,
2. en extraire la base `litellm` par `pg_dump`,
3. la recharger dans le cluster vivant.

Des bases séparées n'offrent **pas** une restauration séparée. Un **cluster dédié**, si. Ce seul fait
réordonne beaucoup de décisions « mets-le juste sur le partagé ».

## Alors, où va chaque app ?

La règle retenue : **consolider le peu risqué, isoler le critique pour la restauration.**

| Charge | Placement | Pourquoi |
|---|---|---|
| Open WebUI · Flowise · LiteLLM · MLflow | Cluster **partagé**, base + rôle par app | peu risqué ; mutualiser capacité et maintenance ; isoler l'*accès*, pas les opérations |
| Retrieva · `ragdb` | Partagé si l'indexation est légère ; **dédié** si contention | l'ingestion de masse + construction d'index vectoriels se battent avec les requêtes interactives pour CPU/disque |
| Backstage (13 bases plugin) | **Un** cluster pour toutes | les séparer seulement si le portail dev doit survivre à un incident DB IA/workplace |
| **Authentik** | **Dédié** | une panne d'auth bloque de nombreux services et complique toute autre restauration |
| **Vaultwarden** | **Dédié**, hors du cluster IA | les identifiants de secours doivent avoir un chemin de restauration indépendant des charges IA |

Deux de ces choix sont non négociables sur une plateforme qu'il faut *restaurer* : ce qui authentifie tout
(Authentik) et ce qui détient les identifiants de secours (Vaultwarden) ne doivent pas partager une
frontière de panne ou de restauration avec un tas d'outils IA expérimentaux.

## Une correction au raccourci habituel

« Une base par serveur » est une simplification. Une **instance** Postgres accepte **plusieurs logins**, et
un cluster CNPG tourne avec un **primaire plus des réplicas**. Pour l'hébergement partagé, la discipline
est : **un rôle par app, restreint à sa propre base, avec un `connectionLimit` par rôle** pour qu'une app
bavarde n'épuise pas les connexions du cluster. N'utilisez le superutilisateur comme *login admin séparé*
que lorsque vous voulez délibérément parcourir plusieurs bases.

## Ne pas l'argumenter — le mesurer

Le geste honnête n'est pas de décréter une politique ; c'est d'en prouver une. Avant de migrer plus de
charges sur le cluster partagé, je ferais :

1. **Consolider d'abord les bases *dev* légères** (enjeu le plus faible).
2. **Un exercice de restauration :** récupérer `litellm` sur un cluster *temporaire* **pendant que le
   cluster partagé vivant continue de servir** les autres outils. C'est toute la thèse à l'épreuve —
   peut-on restaurer une app sans faire tomber ses voisines ?
3. **Mesurer l'empreinte Longhorn (PVC + réplicas) réellement éliminée.** Sur un cluster dont le vrai
   goulot est la reconstruction des réplicas de stockage, ce chiffre — pas le nombre de bases qu'affiche
   DBeaver — dit s'il faut consolider davantage.

## La phrase à garder

**Des bases séparées isolent l'accès. Seul un cluster séparé isole les opérations — et la restauration.**
Décidez le placement sur la seconde : *si je devais restaurer cette app seule, à 3h du matin, pendant que
tout le reste continue de tourner, l'organisation actuelle me le permettrait-elle ?* Si oui, partagez sans
crainte. Si non, elle a mérité son propre cluster.
