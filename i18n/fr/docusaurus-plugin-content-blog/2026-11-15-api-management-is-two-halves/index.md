---
slug: api-management-is-two-halves
title: "L'API Management, c'est deux moitiés — et vous possédez déjà la plus importante"
authors: [andrelair]
tags: [api-management, backstage, platform-engineering, architecture, api-gateway, governance]
date: 2026-11-15
description: "On vous demande de « mettre en place de l'API management » et le réflexe est d'aller faire les courses — Kong, Gravitee, WSO2, Apigee. Je n'ai rien acheté. Parce que « l'API management » recouvre en réalité deux moitiés distinctes, et sur une plateforme qui a déjà un fournisseur d'identité, une couche de politique réseau et un catalogue de services, vous possédez déjà la moitié qui compte pour les API internes. Voici la décision, ce que j'ai construit, la seule question qui me dit quand acheter une gateway, et les deux choses que j'ai ratées en chemin."
---

On vous demande de *« mettre en place de l'API management »*, et le réflexe est d'ouvrir un navigateur pour comparer des produits : Kong, Gravitee, WSO2, Apigee, Tyk. En choisir un, le déployer, considérer le travail fait.

Je n'ai rien acheté. Pas par économie — par une prise de conscience qui évite beaucoup d'empreinte et de regrets : **« l'API management » n'est pas une seule chose. C'est deux moitiés, et la plupart des équipes possèdent déjà la moitié qui compte réellement pour leurs API internes.**

Voici la décision que j'ai prise pour la plateforme de mon assureur simulé, ce que j'ai réellement construit, la seule question qui me dit quand l'*autre* moitié devient nécessaire — et, honnêtement, les deux choses que j'ai ratées en chemin.

{/* truncate */}

## Les deux moitiés

Quand on dit « API management », on désigne un mélange de ces éléments, et les deux groupes se comportent de façon complètement différente :

| Moitié | Ce qu'elle fait | Nature |
|---|---|---|
| **Catalogue + gouvernance** (un *portail*) | découverte, propriété, contrats d'API, qui-consomme-quoi, identité, politique réseau | plan de contrôle |
| **Gateway + runtime** (un *dataplane*) | clés d'API par consommateur, limitation de débit, quotas, transformation de requêtes, analytique par API | plan de données |

Un produit d'API management monolithique vous vend les deux dans une seule boîte. C'est le piège. Car dès que vous regardez ce que vous *faites déjà tourner*, vous remarquez quelque chose :

- **Identité / authentification-autorisation ?** Déjà là — un fournisseur de SSO qui émet des jetons OIDC pour les utilisateurs et des *client-credentials* pour le service-à-service.
- **Réseau / politique L7 ?** Déjà là — un CNI en *default-deny* avec une politique par service.
- **Catalogue d'API / portail développeur ?** Déjà là — un catalogue de services qui rend l'OpenAPI, suit la propriété et dessine le graphe fournisseur↔consommateur.
- **Contrats d'API ?** Déjà là — un `openapi.yaml` versionné par service et des tests de contrat en CI.

Cette liste *est* la première moitié de l'API management. Pour les API **internes** (service-à-service), c'est tout le travail. Acheter un produit monolithique pour l'obtenir reviendrait à déployer un **deuxième** fournisseur d'identité et un **deuxième** portail juste pour obtenir une gateway dont je n'avais pas encore besoin — et à payer cela en empreinte cluster, sur du matériel qui n'en a pas de reste.

## La décision : composer maintenant, conditionner la gateway

La stratégie s'est donc résumée à une ligne :

> **API management = fournir un catalogue + identité + politique maintenant (à partir de ce que la plateforme fait déjà tourner) ; ajouter une gateway dédiée *uniquement* au bord, conditionnée par le premier vrai consommateur externe.**

Pas de produit monolithique. L'alternative rejetée ne l'a pas été par goût — elle l'a été parce qu'elle dupliquait deux systèmes que j'exploite déjà et résolvait un problème (des API externes, à clé, à débit limité) que je n'ai pas *aujourd'hui*.

## Ce que j'ai réellement construit (le modèle intérimaire)

La pièce manquante n'était pas une gateway. C'était que le catalogue était **vide** — la plateforme *pouvait* rendre des API mais personne ne les avait enregistrées. J'ai donc fait la chose peu coûteuse et à forte valeur : enregistrer les vraies API comme entités de catalogue à part entière — chacune avec son composant propriétaire, sa relation fournisseur↔consommateur, son OpenAPI rendu et un lien vers la documentation de référence.

Cela transforme le catalogue d'une bonne idée en une vraie carte : un ingénieur peut désormais trouver une API, voir qui la possède, lire son contrat et savoir qui la consomme — sans demander à personne. Combiné au fournisseur d'identité, à la couche de politique réseau et aux contrats versionnés, **c'est de l'API management fonctionnel pour le trafic interne.** Cela n'a coûté aucune nouvelle infrastructure.

Le périmètre honnête compte toutefois : c'est la moitié **catalogue + identité + politique**. Elle ne limite **pas** le débit, n'émet pas de clés d'API, n'applique pas de quotas, ne transforme pas les requêtes et ne produit pas d'analytique par consommateur. Un catalogue est un portail, pas un dataplane. Prétendre le contraire serait le genre d'exagération qui se fait démasquer en revue d'architecture.

## La seule question qui me dit quand acheter une gateway

Tout l'intérêt de *conditionner* la gateway est d'avoir un déclencheur net, pour que la décision ne tienne pas au ressenti. Le voici :

> **Une API fait-elle désormais face à une partie que je ne contrôle pas, ou de l'argent / une facturation reposent-ils dessus ?**
> **Oui → construire la gateway. Non → rester en intérimaire.**

Concrètement, je monte une vraie gateway de bord dès que l'un de ces cas est vrai :

1. **Un vrai consommateur externe / tiers** appelle une API — un courtier, un réassureur, un partenaire EDI. *(C'est le déclencheur principal.)*
2. **Des clés d'API par consommateur** sont nécessaires — un partenaire attend une clé à faire tourner et révoquer, pas un flux OIDC.
3. **Limitation de débit ou quotas** doivent protéger un backend exposé à un partenaire ou au public.
4. **Analytique d'usage par consommateur** — facturation, reporting SLA, « qui a appelé quoi, combien de fois ».
5. **Monétisation** — une API facturée à des clients payants.
6. **Médiation / transformation au bord** — traduction de protocole ou de format pour un consommateur externe.
7. **Une exigence d'audit réglementaire** sur la surface d'API externe.

Et l'image miroir — les *non*-déclencheurs, là où réside la discipline : davantage de services internes qui s'appellent, une UI interne qui tape une API interne, ou simplement *vouloir un plus joli catalogue* ne sont **pas** des raisons de monter une gateway. Le fil rouge de chaque vrai déclencheur est un consommateur hors de la frontière de confiance, ou de l'argent.

Aujourd'hui, la plateforme est en dessous des sept. Le modèle intérimaire n'est donc pas un pis-aller dont j'aurais honte — c'est l'état *correct* pour là où le système se trouve réellement.

## Deux choses que j'ai ratées (parce que prétendre le contraire n'aide personne)

**1. J'ai commencé à inventorier au lieu de cartographier.** Mon premier instinct a été d'enregistrer *toute* chose ayant une forme d'API. Erreur : un catalogue est une **carte d'intégration, pas un inventaire de surfaces HTTP**. Une entité d'API que personne ne consomme n'apprend rien au lecteur. J'ai aussi réussi à enregistrer quelques **doublons** — parce que j'ai ajouté des entités sans d'abord vérifier que certains services livraient déjà leurs propres entrées de catalogue. Le correctif : n'enregistrer que les API ayant un vrai rôle, et toujours vérifier l'existant d'abord. (Un doublon est même entré en collision sur un nom ; la copie obsolète s'est discrètement auto-élaguée une fois la source retirée — mais c'était évitable.)

**2. J'ai classé la stratégie sous le mauvais pilier d'architecture.** Je l'ai d'abord documentée comme une préoccupation *Système d'Information*, parce que le domaine d'intégration auquel elle appartient se range sous un regroupement « IS Foundations ». Mais l'API management est une **capacité de plateforme** — elle *fournit* catalogue/identité/politique/gateway à chaque application et survivrait inchangée si l'activité d'assurance disparaissait demain. Le libellé de regroupement et le pilier plateforme-vs-métier sont des **axes orthogonaux**, et je les avais confondus. Déplacée vers le pilier plateforme, là où une capacité partagée appartient. L'*usage* de ces API reste au métier ; la *capacité* est de la plateforme.

## À retenir

« Mettez en place de l'API management » ne signifie presque jamais « achetez un produit d'API management ». Cela signifie : **rendez vos API découvrables, possédées, contractualisées, authentifiées et gouvernées par politique maintenant** — ce que, sur une plateforme mature, vous pouvez le plus souvent *composer* — et gardez la gateway comme une décision délibérée et déclenchée plutôt qu'un achat par défaut. Puis écrivez le déclencheur, pour que le jour où il se produit vous agissiez sur des preuves et non sur une intuition.

---

*Cette plateforme fait tourner un assureur simulé utilisé comme laboratoire d'ingénierie — aucun client réel ni trafic de production. La revendication ici est un jugement d'ingénierie et une capacité intérimaire fonctionnelle, pas une échelle commerciale.*
