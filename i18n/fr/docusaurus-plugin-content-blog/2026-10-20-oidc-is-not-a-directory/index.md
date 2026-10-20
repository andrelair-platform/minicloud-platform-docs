---
slug: oidc-is-not-a-directory
title: "OIDC n'est pas un annuaire : pourquoi je ressors LDAP à côté d'Authentik"
authors: [andrelair]
tags: [identity, authentik, ldap, oidc, scim, sso, platform-engineering, insurance]
date: 2026-10-20
description: "J'exploite le SI d'un assureur simulé avec Authentik comme fournisseur d'authentification unique — un seul login pour tout. Alors pourquoi viens-je, pour la deuxième fois, de brancher un serveur LDAP à côté ? Parce que le SSO répond à une seule question, et que deux fois j'en avais une autre. Voici la cause racine, et la règle qui dit d'avance quel protocole il vous faut vraiment."
---

J'exploite le système d'information d'un assureur simulé sur un cluster Kubernetes de six nœuds, et l'histoire de l'identité est limpide : **Authentik** est le fournisseur d'authentification unique, chaque application est derrière lui, un seul login ouvre tout. C'est toute la promesse du SSO — arrêter de disséminer des mots de passe dans quarante applications.

C'était donc un peu gênant de me retrouver, pour la **deuxième** fois, à monter un serveur **LDAP** juste à côté d'Authentik. D'abord pour la messagerie. Puis, cette semaine, pour l'ITSM. Deux fois, j'ai dépassé la jolie porte OIDC pour en ouvrir une plus ancienne et moins à la mode. À ce moment-là, la vraie question d'un bon ingénieur n'est pas *« comment câbler LDAP ? »* — c'est **« pourquoi mon beau SSO me laisse-t-il tomber ici ? »**.

La réponse s'est révélée identique les deux fois, et elle mérite d'être écrite pour ne jamais la redécouvrir une troisième fois.

{/* truncate */}

## Ce qu'est réellement OIDC (et ce qu'il n'est pas)

OpenID Connect — le protocole derrière « Se connecter avec Authentik » — est un flux **interactif, par redirection navigateur, à chaque connexion**. Un humain arrive sur une application, est renvoyé vers Authentik, s'authentifie, et revient avec un jeton plein de *claims*. Il est excellent pour une seule question :

> **« La personne dans ce navigateur, maintenant — qui est-elle ? »**

C'est tout. OIDC est un *événement d'authentification*, déclenché par un humain, dans un navigateur, un utilisateur à la fois. Ce n'est **pas** un endroit où aller *interroger* les utilisateurs. Il n'existe pas d'appel « vérifie-moi ce mot de passe », ni d'appel « donne-moi tout le monde ». OIDC est un tourniquet, pas une armoire à dossiers.

Les deux fois où j'ai heurté le mur, c'est parce que l'application avait besoin de l'armoire à dossiers.

## Cas 1 — Messagerie : un mot de passe sans endroit où le vérifier

Le serveur de messagerie (Stalwart) doit laisser un client mail de bureau ou de téléphone se connecter en **IMAP et SMTP**. Ces clients s'authentifient à l'ancienne : ils envoient un **identifiant et un mot de passe sur le réseau** et attendent que le serveur dise oui ou non — un « bind ».

Il n'y a aucun navigateur dans cette conversation. Thunderbird ne peut pas être redirigé vers Authentik pour cliquer sur un écran de consentement ; il a juste un mot de passe en main et un socket ouvert. OIDC n'a littéralement rien à offrir ici — tout le protocole *est* la redirection navigateur que la messagerie ne peut pas faire.

Ce qu'un serveur mail *sait* faire, c'est un **bind sur un annuaire** : « voici un identifiant et un mot de passe, sont-ils valides ? ». C'est le verbe natif de LDAP. Nous avons donc activé l'**outpost LDAP** d'Authentik — qui réexpose les mêmes utilisateurs Authentik en LDAP — et pointé Stalwart dessus. Même personne, même mot de passe, un protocole que le client mail sait réellement parler.

## Cas 2 — ITSM : il me fallait la liste *avant* que quiconque se connecte

Le travail de cette semaine était l'**ingestion** des employés dans GLPI (notre ITSM). Le besoin a l'air trivial : *« quand un ticket arrive, on doit savoir qui l'a demandé »*. Pour cela, chaque employé doit **exister dans GLPI comme demandeur sélectionnable** — idéalement avant même sa première connexion.

Voici le problème discret du SSO : avec OIDC, un utilisateur **apparaît la première fois qu'il se connecte**, pas une seconde avant. Le jeton parle de *la seule personne en train de s'authentifier* — il ne peut rien dire des vingt autres qui ne se sont pas encore présentées. Il n'existe pas d'endpoint OIDC signifiant « énumère tout mon effectif ». Un ITSM uniquement en OIDC a donc une liste de demandeurs à moitié vide jusqu'à ce que, un par un, tout le monde se soit connecté. On ne peut pas assigner un ticket à quelqu'un qui n'est pas là.

Ce qu'il me fallait, c'était **lire la population d'utilisateurs et la tenir synchronisée** — importer les ~20 employés maintenant, rafraîchir chaque jour au gré des arrivées et des départs. C'est une *recherche d'annuaire*, et là encore la réponse fut l'outpost LDAP d'Authentik : GLPI fait un bind avec un compte de service, cherche tous les membres du groupe `Workplace Users`, et les importe comme demandeurs. Une tâche quotidienne relance la synchronisation.

Et comme LDAP expose aussi l'**appartenance aux groupes**, j'ai eu le besoin suivant gratuitement : une règle GLPI disant *« membres de `Direction IT / SI` → profil Technicien »*, pour que l'équipe IT puisse se voir **assigner** des tickets, pas seulement en ouvrir. Les claims OIDC pourraient aussi porter les groupes — mais seulement pour la personne qui se connecte, et seulement à la connexion. Pour une règle qui doit s'appliquer à des gens pas encore connectés, il faut l'annuaire.

## Le motif : SSO et annuaire sont deux organes différents

Une fois vu deux fois, la forme était évidente. Ce sont **trois questions différentes**, qui veulent **trois protocoles différents** :

| Le besoin réel | Protocole | La question à laquelle il répond |
|---|---|---|
| Un humain se connecte à une application web | **OIDC / SAML** (SSO Authentik) | « Qui est la personne dans ce navigateur, maintenant ? » |
| Un client non-navigateur s'authentifie (IMAP, SMTP, applis à bind LDAP, certains VPN/RADIUS) | **LDAP** (bind) | « Cet identifiant + mot de passe sont-ils valides ? » |
| Une appli doit détenir, énumérer ou pré-provisionner la liste des utilisateurs + groupes | **LDAP** (search/sync) ou **SCIM** (push) | « Qui *sont* tous les utilisateurs, et dans quels groupes ? » |

OIDC couvre magnifiquement la première ligne et pas du tout les deux autres. Ce n'est pas un défaut d'OIDC — c'est une erreur de catégorie que de l'attendre de lui. Le SSO est un *tourniquet* ; un annuaire est une *armoire à dossiers* ; le provisioning (SCIM) est un *courrier qui pousse les mises à jour*. Des organes différents.

La règle de décision que j'appliquerai la prochaine fois, avant de câbler quoi que ce soit :

- **Un humain + un navigateur ?** → OIDC. Toujours par défaut.
- **Un client qui n'est pas un navigateur doit se connecter ?** → il lui faut un **bind** → LDAP.
- **Une appli a besoin de tout l'effectif, ou que les utilisateurs existent avant de se connecter ?** → il lui faut **lire/synchroniser l'annuaire** → LDAP, ou **SCIM** si l'appli peut être *poussée* (GLPI parle LDAP, pas SCIM — ce fut donc LDAP).

Si j'avais eu ce tableau il y a un an, aucune de ces deux fois n'aurait semblé une surprise.

## Ce qui empêche que cela tourne au désordre

Monter LDAP deux fois *ressemble* à une dispersion de l'identité — deux magasins d'utilisateurs, deux jeux de mots de passe, une dérive en embuscade. Il n'en est rien, et la raison compte : **Authentik reste la source de vérité unique.** L'outpost LDAP n'est pas un second annuaire avec ses propres utilisateurs ; ce sont les *mêmes* utilisateurs Authentik, vus par un second protocole. Une personne, un identifiant, deux portes.

C'est pourquoi, sur toute la plateforme, je suis `kanmegnea@devandre.sbs` partout, mon mot de passe mail *est* mon mot de passe Authentik, et mon compte GLPI est la même identité que mon login SSO. Nous avons ajouté un **protocole**, pas un **système d'identité**. Le jour où il y aura deux endroits pour modifier un utilisateur sera le jour où cela aura mal tourné — et il n'y en a pas.

## La leçon que je donnerais à moi-même d'avant

Le SSO est tellement bon sur le problème du login qu'on finit par croire qu'il est le problème de *l'identité*, tout entier. Il ne l'est pas. « On a Authentik » répond à *l'authentification des humains dans des navigateurs*. Dès qu'un besoin porte sur **un identifiant non-navigateur** ou sur **l'ensemble des utilisateurs lui-même**, le SSO se tait, et le bon réflexe n'est pas de lutter — c'est de poser un annuaire à côté et de garder une source de vérité unique derrière les deux.

Tout vieux protocole n'est pas un boulet hérité du passé. LDAP a quarante ans et reste la réponse la plus propre à « vérifie ce bind » et « liste tout le monde ». Le ressortir à côté d'un IdP moderne n'est pas un retour en arrière — c'est utiliser le bon organe pour la question.

*ktayl-solution est un assureur fictif utilisé comme laboratoire d'ingénierie — données synthétiques, utilisateurs simulés, aucun client réel. La conception de l'identité, elle, est bien réelle et en production.*
