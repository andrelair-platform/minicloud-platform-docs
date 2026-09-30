---
slug: modular-monolith-first
title: "Le monolithe modulaire d'abord : dimensionner l'architecture selon le problème, pas selon la mode"
authors: [andrelair]
tags: [architecture, modular-monolith, microservices, domain-driven-design, platform-engineering, insurance, decision-records]
date: 2026-09-30
description: "J'exploite le SI d'un assureur simulé sur Kubernetes, construit en services séparés par domaine. Puis je me suis arrêté et j'ai posé la question inconfortable : est-ce la bonne architecture, ou seulement la plus à la mode ? Voici la décision que j'ai prise — le monolithe modulaire d'abord — et, plus utile encore, la décision que j'ai délibérément PAS prise : construire la chose, tout court, maintenant."
---

Il y a un réflexe dans notre métier, et je l'avais aussi : un nouveau domaine métier apparaît, et la main se tend vers *« …donc c'est un nouveau microservice »*. Ça fait moderne. Ça fait scalable. Ça fait ce que font les ingénieurs sérieux.

Sur le système d'information ktayl-solution — une plateforme Kubernetes à six nœuds faisant tourner tout le SI d'un assureur simulé — j'avais construit quatre domaines exactement ainsi : polices, sinistres, souscription, identité, chacun avec son dépôt, sa CI, sa base de données, son couloir de promotion. Puis je me suis arrêté et j'ai posé la question qui compte plus que n'importe quel choix de framework : **est-ce la bonne architecture, ou seulement celle qui est à la mode ?**

Cet article est la réponse à laquelle je suis arrivé — **le monolithe modulaire d'abord** — et, honnêtement, sa moitié la plus précieuse : la décision que je n'ai délibérément *pas* prise.

{/* truncate */}

## L'architecture suit le problème, pas la mode

La vérité inconfortable, c'est que **les microservices sont une solution à un problème organisationnel, pas technique.** Ils se rentabilisent quand des *équipes* doivent déployer indépendamment, quand les profils de *charge* divergent réellement, quand un domaine réclame une *stack différente*. Ils coûtent une fortune — service discovery, retries, disjoncteurs, tracing distribué, cohérence éventuelle, transactions distribuées, N pipelines, N bases, N surfaces d'astreinte — quand on les adopte pour un domaine qui n'a *aucune* de ces pressions.

Pour une plateforme métier interne — le SI d'un assureur, quelques dizaines à quelques milliers d'utilisateurs — le premier goulot d'étranglement n'est presque jamais le débit. C'est la **complexité des processus métier et la maintenabilité.** Et un monolithe modulaire adresse exactement cela tout en évitant entièrement la taxe des systèmes distribués.

Le défaut s'est donc inversé. Non pas « un service par domaine », mais :

> **Commencer par un monolithe modulaire bien structuré. Ne sortir une partie en service que lorsqu'une raison opérationnelle ou organisationnelle concrète le justifie.**

J'ai rendu ce test de décision explicite — extraire quand *plusieurs* de ces réponses passent à oui : déploiement indépendant · une autre équipe le possède · charge très différente · stack technique différente · forte isolation des données · SLA différent · consommé par plusieurs applications · une frontière métier claire et stable. **Un ou deux oui ne font pas un service.** Ils font un module.

## Ce qu'est réellement un monolithe modulaire (et la discipline qui le sauve)

Un monolithe modulaire, c'est un seul livrable dont le code est organisé en **modules faiblement couplés** autour des capacités métier — on obtient les bénéfices de conception des services (frontières claires, séparation des responsabilités, évolution indépendante) sans le réseau au milieu. Mais cela ne fonctionne que si l'on impose la discipline qui le distingue d'un plat de spaghettis :

- **Les modules se parlent via une interface publique, en in-process** — un appel de fonction ou un événement de domaine in-process, jamais les internes d'un autre module. Mettre du HTTP ou une file *entre les modules d'une même application* reconstruit le monolithe distribué *à l'intérieur* du monolithe. À proscrire.
- **Une base de données, mais des données isolées** — un seul Postgres pour la simplicité, **un schéma par module, et une règle stricte : un module ne lit jamais les tables d'un autre module.** Cette unique contrainte est ce qui garde le couplage faible *et* laisse la porte de sortie ouverte : extraire un module plus tard, c'est soulever son schéma et son interface, pas démêler des tables partagées.
- **Forte cohésion, faible couplage, responsabilité unique** — un changement dans `claims` ne doit pas se propager dans `billing`.

Faites cela correctement et vous avez conçu les frontières de service *sans les déployer comme services* — et c'est tout l'enjeu, car cela rend l'extraction ultérieure bon marché plutôt que catastrophique.

## L'audit honnête de ma propre plateforme

Appliquer cela à mon propre SI a été inconfortable — c'est ainsi que j'ai su que ça valait le coup. La réalité du terrain :

- **Quatre domaines sont de vrais services** — et, confrontés à mon propre test de décision, trois sont *justifiés* : `iam` (identité à l'échelle de l'entreprise, consommée par tout), `claims` (une couche anti-corruption au-dessus d'un legacy figé d'une autre stack — la frontière est le sujet), `underwriting` (Python, car les maths de tarification y sont natives). Le quatrième, `policy-service`, est le domaine transactionnel cœur que `underwriting` appelle **trois fois de façon synchrone au bind** — le signe précoce classique d'un monolithe distribué. Justifié aujourd'hui, mais la couture à surveiller.
- **Douze autres domaines étaient *conçus mais pas construits*** — un README et un backlog complet chacun, et **zéro ligne de code.** Les frontières existent ; les services non. C'était en fait la meilleure position possible : la conception est faite, et je n'avais pas encore commis l'erreur de déployer douze services de plus.

La correction fut donc étroite et nette : les quatre restent (ils l'ont mérité) ; les douze deviennent des **modules d'une seule application** à mesure qu'ils sont construits, pas douze services de plus.

## Adopter avant de construire

Voici la partie que le réflexe microservices masque totalement : **la plupart des « domaines » ne sont pas à construire.** Mon domaine finance n'est pas un service à écrire — ERPNext gère déjà le grand livre et la clôture financière. L'ITSM, c'est GLPI. Le reporting, c'est une plateforme de données et Metabase. Les documents, c'est Paperless. L'identité est déjà son propre service.

La surface réellement sur-mesure — le code qu'aucun outil du marché n'écrira jamais pour vous — est petite et spécifique : la logique métier de l'assurance. Portail courtier et CRM. Règles de facturation des primes et IFRS 17. Commissions, coassurance, workflow de conformité. *Voilà* ce qu'un monolithe modulaire doit héberger ; tout le reste, il doit **s'y intégrer, pas le réinventer.** La plateforme qui en résulte est un **hybride** délibéré — des outils adoptés, quelques services justifiés, et un monolithe modulaire pour la logique sur-mesure. Ni tout-dans-un ; ni tout-en-service.

## Les deux gestes séniors que personne ne met sur une slide

**1. La stack est une décision *tardive*.** J'ai failli tomber dans une seconde version du même piège — pré-engager le monolithe sur un framework (« ce sera Spring Boot ») avant même qu'un seul domaine n'existe à construire. C'est l'erreur de la mode-de-stack, déguisée en monolithe modulaire. La position honnête est : le *pattern* monolithe modulaire est agnostique du framework ; la *stack* se choisit **quand le premier vrai domaine est défini, selon ce dont cette solution a réellement besoin** — ça peut être NestJS, Spring Boot avec Spring Modulith, .NET, ce qui convient. Le bon outil pour la tâche, décidé au moment où l'on connaît la tâche. Pas avant.

**2. Le geste le plus sénior a été de ne pas le construire.** Il n'y a aucun monolithe modulaire sur ma plateforme. J'ai vérifié — zéro sur quarante-cinq dépôts. Et je ne vais pas le créer maintenant, car **une architecture de référence vide est un passif, pas une référence.** Un monolithe modulaire ne vaut quelque chose que lorsqu'il porte un vrai domaine faisant un vrai travail. Il naîtra donc le jour où je priorise réellement la construction du premier domaine greenfield sur-mesure — de façon réaliste la couche distribution courtier/CRM — *avec* ce premier module, et pas un commit plus tôt. Choisir de *ne pas* construire, quand tout en vous veut échafauder la belle chose, est une discipline. C'est aussi, presque toujours, le bon choix.

## Le signal, c'est le jugement, pas le nombre de services

S'il ne fallait retenir qu'une chose, c'est que l'artefact impressionnant n'a jamais été « j'ai fait tourner vingt microservices ». N'importe qui peut multiplier les services. Le signal sénior — ce qu'un architecte, un recruteur, un jury de certification lit réellement — c'est le *jugement* : **un défaut monolithe modulaire, des services uniquement là où une vraie frontière en justifie un, l'adoption là où un outil existe déjà, et la retenue de ne pas construire en avance sur le besoin.**

Toute cette décision n'a rien coûté à *ne pas* exécuter. Elle est écrite comme un enregistrement de décision d'architecture ; les frontières sont conçues ; le jour où un vrai domaine réclame un foyer, c'est l'affaire d'un après-midi. D'ici là, la ligne de code la plus précieuse de ce système est celle que j'ai choisi de ne pas écrire.
