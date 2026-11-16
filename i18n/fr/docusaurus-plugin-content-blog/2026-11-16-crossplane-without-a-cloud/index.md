---
slug: crossplane-without-a-cloud
title: "Crossplane sans cloud — pourquoi je l'ai reporté un an, et ce qui lui a enfin donné sa place"
authors: [andrelair]
tags: [crossplane, platform-engineering, idp, self-service, backstage, architecture]
date: 2026-11-16
description: "Le réflexe, c'est que Crossplane sert à provisionner des ressources cloud — RDS, GKE, S3 — donc sur un cluster bare-metal sans compte cloud, il n'a rien à faire. J'y ai cru et je l'ai reporté un an. Je me trompais sur ce à quoi sert Crossplane. Sa valeur, ce n'est pas un compte cloud ; c'est une API d'infrastructure en self-service, et ce qui rend ça utile à construire, c'est un portail développeur. Voici la décision, ce que j'ai construit (dont le composite-de-composites qui m'a vraiment bluffé), la frontière qui l'empêche de dupliquer Helm, et la leçon sur le timing."
---

Pendant près d'un an, le doc d'architecture de ma plateforme avait une page intitulée **« Phase 11 — Crossplane (Reporté) »**. Le raisonnement me semblait solide : Crossplane provisionne de l'infrastructure externe sous forme de ressources Kubernetes — instances RDS AWS, clusters GKE, abonnements Azure — et mon cluster, c'est six laptops dans un placard. Pas de compte cloud, pas de ressources cloud, rien à provisionner. Donc Crossplane n'avait aucun travail. Reporté.

Cette page prédisait même sa propre fin : *« le foyer le plus probable de Crossplane est le portail développeur Backstage, où les Compositions sont les templates sur lesquels un développeur clique "créer". »*

La semaine dernière j'ai supprimé le mot « Reporté » du titre. Voici ce que j'avais mal compris, et ce qui a finalement fait que Crossplane a mérité sa place.

{/* truncate */}

## Ce sur quoi je me trompais

Je définissais Crossplane par ses **providers** — provider-aws, provider-gcp — pour conclure que sans cloud, il n'y a rien à orchestrer. C'est regarder la tuyauterie et rater l'essentiel.

Le vrai rôle de Crossplane, c'est d'être une **API d'infrastructure en self-service**. L'équipe plateforme définit un nouveau type de ressource Kubernetes — disons `PostgresInstance` — et une *Composition* qui transforme une petite requête en tous les objets réels qu'une base de données nécessite. Un développeur écrit alors six lignes de YAML (ou clique sur un bouton) et obtient une base. Pas de Helm, pas de `kubectl`, pas de PR dans les entrailles de la plateforme.

Vu comme ça, le déclencheur pour adopter Crossplane n'a jamais été *« ai-je un compte cloud »*. C'était ***« ai-je quelqu'un qui veut se servir en self-service d'infrastructure »***. Et le moment où c'est devenu vrai, c'est le moment où un portail développeur (Backstage) est monté avec des golden-paths. La note de report avait la bonne réponse écrite dessus depuis le début.

Voici la leçon généralisable, sortie du contexte Crossplane :

> **Le bon moment pour adopter un outil n'est pas quand l'outil est intéressant. C'est quand un vrai consommateur existe.** Crossplane sans consommateur self-service, c'est un control plane qui ne gère rien — impressionnant et inutile. Avec un portail devant, c'est le moteur de tout l'IDP. Le même logiciel, un an d'écart, une valeur complètement différente.

## Ce que j'ai construit

Deux API self-service, chacune une *Composite Resource Definition* Crossplane (le nouveau type) plus une *Composition* (ce qu'elle rend), toutes deux consommées depuis Backstage.

**`PostgresInstance`** — un développeur demande une base par taille, et obtient un cluster CloudNativePG (une instance pour `small`, une paire HA à deux instances pour `medium`), une NetworkPolicy qui la verrouille à son namespace, et un secret de connexion. Une requête, trois objets réels.

**`AppBundle`** — c'est celui qui m'a fait sourire. C'est *toute la base d'infrastructure* d'une app en une seule requête, et sa construction utilise le mouvement avancé de Crossplane : un composite qui **compose un autre composite**.

```
AppBundle/orders            (une requête)
├─ PostgresInstance/orders   ← un composite IMBRIQUÉ, réconcilié par SA PROPRE Composition
│   ├─ Cluster/orders-cnpg        (la base de données)
│   └─ NetworkPolicy/orders-db-netpol
└─ NetworkPolicy/orders-baseline  (la baseline réseau default-deny de l'app)
```

`AppBundle` ne réimplémente pas la base — il *demande un `PostgresInstance`*, que Crossplane développe ensuite via sa propre Composition. Supprime le seul `AppBundle` et tout l'arbre est garbage-collecté. Une requête de haut niveau qui en assemble de plus bas niveau : c'est le pattern qui transforme un tas de primitives en vraie plateforme.

## La frontière qui l'empêche de dupliquer Helm

Le piège évident avec `AppBundle`, c'est qu'il se met à ressembler à « déployer mon app », ce que la plateforme fait déjà avec un golden-path Helm. J'ai donc tracé une ligne nette :

- **Crossplane (`AppBundle`) possède l'*infrastructure* de l'app** — sa base, sa baseline réseau.
- **Helm (`wrapper-service`) possède le *déploiement* de l'app** — le Deployment/Rollout, Service, Ingress, certificat TLS.

Ils **composent** au lieu de se chevaucher : le Deployment monte le secret créé par le bundle, et ses pods sont sélectionnés par la NetworkPolicy baseline. Infra vs runtime. Si tu ne traces pas cette ligne explicitement, une abstraction « bundle » va lentement grignoter le chemin de déploiement et tu auras deux outils qui se battent sur les mêmes objets.

## Les parties honnêtes

Quelques points qui n'étaient pas gratuits :

- **Installer sur un cluster durci, c'est une cascade, pas un `helm install`.** Gatekeeper, un AppProject ArgoCD verrouillé et un modèle RBAC scopé ont chacun dû apprendre l'existence des pods provider de Crossplane avant que quoi que ce soit tourne. À écrire une fois ; pénible à redécouvrir.
- **Composer un composite imbriqué m'a mordu.** Mon premier `AppBundle` essayait d'écrire un champ de status *sur le `PostgresInstance` composé* — un champ absent du schéma de cette ressource — et toute l'imbrication échouait silencieusement à se matérialiser. Pour exposer une valeur, on la lit *depuis* l'enfant, on ne la patche pas *dedans*. Le test live l'a attrapé ; un test unitaire non.
- **C'est toujours du bare metal.** Le provider que j'utilise est `provider-kubernetes`, qui compose des ressources in-cluster. Le jour où je veux des buckets *cloud* en self-service, j'ajoute `provider-aws` pointé sur un tier always-free — mais j'applique la même règle : seulement quand un vrai consommateur le demande.

## Alors : le reporter était-il une erreur ?

Non — et c'est le point. Construire Crossplane il y a un an, sans portail et sans personne pour se self-servir, aurait été un control plane n'orchestrant rien : un coût de maintenance, zéro valeur. Le construire la semaine où le portail avait besoin de « clic → base de données » était exactement juste. L'outil n'a pas changé. Le *consommateur* est arrivé. C'est le signal à surveiller — pas la réputation de l'outil, ni un plan en 22 phases qui l'avait par hasard inscrit pour le printemps dernier.

*L'as-built complet — les XRD, les Compositions, la cascade d'installation — vit sur la [page Crossplane](/platform/iac/crossplane) dans la doc plateforme.*
