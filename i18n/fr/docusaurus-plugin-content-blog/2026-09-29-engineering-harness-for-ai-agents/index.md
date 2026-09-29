---
slug: engineering-harness-for-ai-agents
title: "Le harnais d'ingénierie : transformer un agent IA en collègue fiable sur un vrai système d'information"
authors: [andrelair]
tags: [ai-agents, agentic-ai, engineering-harness, context-engineering, guardrails, gitops, testing, reliability, platform-engineering, llmops, dora]
date: 2026-09-29
description: "Tout le monde parle de modèles plus intelligents. Presque personne ne parle du harnais — les règles, la mémoire, les garde-fous et les boucles de vérification qui entourent le modèle et décident s'il livre un travail fiable ou de la camelote plausible. Voici le harnais que j'ai construit pour qu'un agent IA puisse opérer sur le système d'information ktayl-solution sans casser la prod."
---

La conversation de pointe en IA a discrètement changé de sujet. Pendant deux ans, c'était *« quel est le modèle le plus intelligent ? »*. Aujourd'hui, ceux qui livrent réellement des systèmes agentiques posent une autre question : **« que met-on autour du modèle ? »**

Cette machinerie environnante porte un nom — le **harnais**. Le modèle est le moteur. Le harnais, c'est le châssis, la direction, la ceinture et les freins. Un moteur génial boulonné à rien vous tue au premier virage ; un moteur modeste dans une voiture bien conçue vous ramène à la maison à chaque fois. Sur le système d'information ktayl-solution — une plateforme Kubernetes à six nœuds qui fait tourner tout le SI d'un assureur simulé — j'ai passé des mois à construire le harnais qui permet à un agent IA de faire un vrai travail d'ingénierie sur une **infrastructure en production** sans que je retienne mon souffle.

Cet article, c'est ce harnais, concept par concept. Pas la théorie — les règles réelles que j'ai mises en place, pourquoi chacune existe, et l'incident qui l'a le plus souvent imposée.

{/* truncate */}

## Ce qu'est réellement un harnais

Une fois le battage retiré, un harnais d'ingénierie, ce sont cinq choses enroulées autour d'un modèle de langage :

1. **Le contexte** — ce que le modèle a le droit de voir, et *quand*.
2. **La mémoire** — ce qui persiste après la fin de la session.
3. **Les garde-fous** — ce que le modèle est structurellement empêché de faire de travers.
4. **La vérification** — comment le travail est *prouvé*, et non affirmé.
5. **L'orchestration** — le plan de contrôle déterministe qui encadre la sortie non déterministe du modèle.

Un modèle brut n'a rien de tout cela. Il voit ce que vous collez, oublie tout à la fermeture de l'onglet, exécutera un `rm -rf` en toute confiance si on le demande gentiment, rapporte un succès qu'il n'a jamais vérifié, et applique des changements sans aucune barrière entre lui et la production. Chacun de ces points est un échec que j'ai *conçu pour disparaître* de mon installation. Voici comment.

## 1. L'ingénierie du contexte — la discipline de ce qui est dans la fenêtre

L'industrie est passée du « prompt engineering » (la formulation astucieuse) à l'**ingénierie du contexte** (la curation délibérée de ce qui occupe la fenêtre de contexte finie). La fenêtre de contexte est un *budget*, pas un seau. Remplissez-la d'informations périmées, hors-sujet ou contradictoires et même le meilleur modèle se dégrade — un phénomène désormais appelé **context rot** (pourrissement du contexte).

Mon fichier de contexte principal est une fenêtre glissante, par règle :

> **CLAUDE.md** = état courant + les **2 derniers blocs de session** seulement (fenêtre glissante). Les sessions plus anciennes → un `CLAUDE-history.md` archivé sur le contrôleur. Les faits réutilisables → le système de mémoire. Les règles stables → `.claude/rules/*.md`.

Cette seule discipline abat un travail considérable. Le fichier point d'entrée reste petit et *vrai* ; l'historique est préservé mais hors du chemin critique ; et la connaissance durable est partitionnée en fichiers de règles modulaires, chargés automatiquement — `connectivity.md`, `gitops.md`, `testing.md`, `github-projects.md` — qui portent les standards sans gonfler chaque conversation.

L'anti-pattern ici est universel : on laisse un gros fichier d'instructions grossir indéfiniment jusqu'à ce qu'il soit à moitié obsolète et empoisonne discrètement chaque session. Un harnais a besoin d'une **discipline de compaction** autant qu'une application a besoin d'une rotation de ses logs.

## 2. Une mémoire persistante avec rappel sélectif

Un agent qui oublie tout entre deux sessions ne peut pas accumuler de jugement. Mais un agent qui se souvient de *tout* se noie. La réponse est une **mémoire augmentée par la recherche** (retrieval-augmented) : beaucoup de petits faits, chacun étiqueté d'une description qui sert de clé de rappel, et seuls les faits pertinents sont tirés dans le contexte pour une tâche donnée.

Mon système de mémoire, c'est un fait par fichier, avec un frontmatter :

```markdown
---
name: feedback-harbor-gc-deployed-tags
description: le GC keep-N peut supprimer un tag encore utilisé par un Deployment actif → ImagePullBackOff au reschedule
metadata:
  type: feedback
---
```

Quatre choix de conception en font un composant de harnais, et pas juste un dossier de notes :

- **Des mémoires typées** — `user` (qui je suis), `feedback` (comment l'agent doit travailler), `project` (contexte en cours), `reference` (pointeurs externes). Des faits différents ont des durées de vie et des niveaux de confiance différents.
- **La `description:` est la clé de rappel** — le rappel se fait par pertinence, donc l'index (`MEMORY.md`) peut être parcouru à faible coût et seuls les faits pertinents sont chargés.
- **Les `[[liens-wiki]]`** entre faits transforment le magasin en graphe de connaissances — un piège sur Kargo pointe vers le piège sur les SHA d'image tout-en-chiffres.
- **La conscience de l'obsolescence** — le harnais traite explicitement une mémoire rappelée comme *« ce qui était vrai au moment de l'écriture »* et vérifie qu'un fichier ou un flag nommé existe encore avant d'agir dessus.

Ce dernier point compte plus qu'il n'y paraît. La plupart des démos de mémoire d'agent recommandent joyeusement une fonction supprimée il y a trois mois. Un vrai harnais traite la mémoire comme une *hypothèse à vérifier*, pas comme une parole d'évangile.

## 3. Les garde-fous — préférer l'impossible à l'interdit

C'est ici qu'un harnais sérieux se distingue d'un tas de bonnes intentions. Il existe deux sortes de garde-fous, et la plupart des gens ne construisent que le plus faible.

**Les garde-fous souples** sont des instructions : *« pense à utiliser des certificats ECDSA ».* Utile, mais une règle souple ne vaut que l'attention du lecteur un mardi de fatigue.

**Les garde-fous durs** rendent l'erreur *structurellement impossible*. Sur cette plateforme, je tombais sans cesse sur un bug de certificat récurrent — le rôle Vault PKI est EC-only, donc tout `Certificate` omettant l'algorithme échouait silencieusement à la signature. Le correctif souple, c'est « pense à l'algorithme ». Le correctif de harnais fut une **politique d'admission Gatekeeper** (`K8sRequireEcdsaCert`) qui *refuse* un certificat non-ECDSA au niveau de l'API server. La mauvaise chose ne peut plus être créée. C'est la différence entre un panneau « ne pas tomber » et une rambarde.

La même philosophie revient partout sur la plateforme :

| Risque | Garde-fou souple (faible) | Garde-fou dur (ce que j'ai construit) |
| --- | --- | --- |
| Un test frappe une vraie base | « prudence dans les tests destructifs » | un **garde-fou de BD jetable** qui rend un test destructif *incapable* d'atteindre une vraie BD |
| Un mauvais changement atteint la prod | « relire avant de promouvoir » | **merge Git protégé par CODEOWNERS** — la barrière vit en amont dans Git ; aucune synchro live ne peut la contourner |
| Mauvais émetteur de certificat | « utiliser l'émetteur minicloud-ca » | **refus** Gatekeeper limité à l'émetteur |
| L'agent lance un `kubectl sync` prod brut | « ne pas forcer la synchro » | **auto-sync depuis Git uniquement** — le travail de l'agent est de proposer un changement Git, jamais de toucher au cluster |

Le principe, emprunté directement à la pratique de la sûreté de l'IA : **quand on peut rendre un mode de défaillance inatteignable, on fait cela plutôt que de l'interdire par instruction.** Les instructions sont pour les cas de jugement ; la structure est pour ce qui ne doit jamais arriver.

## 4. La boucle de vérification — la preuve plutôt que l'affirmation

Voici la propriété la plus importante — et la plus négligée — d'un bon harnais. Un modèle de langage *rapporte joyeusement un succès qu'il n'a jamais vérifié.* C'est un narrateur fluide et confiant. Laissé sans contrôle, il vous dira que les tests passent parce que « les tests passent » est la forme attendue de l'histoire, pas parce qu'il les a lancés.

Le harnais doit donc imposer **la preuve plutôt que l'affirmation** à chaque couche. Mon standard de test encode cela en une pyramide à cinq couches — statique, unitaire, intégration, contrat, E2E — plus une cinquième barrière qui a les vraies dents :

> **La barrière QA (recette en dev live) est OBLIGATOIRE avant la promotion en prod.** L0–L4 prouvent le code en isolation et avec des mocks ; elles ne détectent **pas** les bugs d'intégration, de déploiement, d'exécution ou de configuration. Une fois un service live en dev, un agent QA fait une *passe de test adversariale contre le service en fonctionnement*. **Un CI vert ne suffit pas à promouvoir.**

Cette règle est écrite dans le sang. Un service récent a été construit en unitaires-seulement, tout vert, et a livré trois bugs que seule une passe adversariale live a attrapés : une API silencieusement non authentifiée, une migration au démarrage qui désactivait tous les logs, et — mon préféré — un datetime RFC3339 que l'app envoyait et que le service en aval rejetait avec un `400`. Chacun était invisible pour un test unitaire mocké.

D'où la leçon centrale que le harnais impose désormais — la **discipline des mocks** :

> Un mock encode une *hypothèse* sur un collaborateur. Si l'hypothèse est fausse, le test mocké reste **vert pendant que la prod échoue**. Donc chaque frontière mockée DOIT être adossée à un test de contrat ou à une intégration réelle qui valide l'hypothèse contre le vrai collaborateur. **Une frontière qui n'est jamais que mockée n'est pas testée, elle est non testée.**

C'est le même principe que « le vérificateur doit être indépendant du générateur ». Un agent qui à la fois écrit le code *et* juge s'il marche corrige sa propre copie avec indulgence. Le harnais insère un contrôle indépendant — une vraie base, un vrai contrat, une passe adversariale live — précisément là où l'auto-évaluation de l'agent est la moins fiable.

## 5. Une orchestration déterministe autour d'un cœur stochastique

La dernière pièce, c'est le plan de contrôle. Le modèle est non déterministe par nature ; la production ne doit pas l'être. Le harnais enveloppe donc l'acteur stochastique dans un **pipeline déterministe** où l'agent n'exprime jamais qu'une *intention*, et où une machinerie déterministe impose le *résultat*.

Sur cette plateforme, ce pipeline, c'est : **la CI build et prouve l'artefact → Kargo le promeut → ArgoCD le réconcilie depuis Git.** L'agent propose un changement Git. Il ne peut pas — et ne doit pas — cliquer sur « sync » en production. La règle est brutale : *le merge de la PR est la seule barrière ; ne jamais forcer une synchro ArgoCD manuelle.* Et la promotion elle-même appartient à une machine, car j'ai appris à la dure qu'éditer un tag d'image à la main invite un bug où un SHA hexadécimal à sept chiffres qui se trouve être tout-décimal (comme `9248482`) est interprété comme le *nombre* `9.2e+06` et casse le déploiement. La règle du harnais est devenue : **ne jamais éditer un tag d'image à la main ; laisser Kargo le posséder** — et Kargo entoure chaque tag de guillemets, tuant structurellement le bug.

C'est le pattern de sûreté agentique en miniature : donner à l'agent l'autonomie de *proposer*, garder la *réconciliation et la barrière* dans des mains déterministes.

## Le méta-pattern : incident → mémoire → règle → filet de sécurité

Si vous ne retenez qu'une chose, retenez celle-ci. Ce qui fait qu'un harnais s'améliore réellement avec le temps, ce n'est aucune règle en particulier — c'est la **boucle qui les produit** :

1. Quelque chose casse en production. (Le GC Harbor supprime une image encore déployée. Le snapshot Vault cible silencieusement un nœud en standby. Un appel inter-services échoue sur un format de date.)
2. La leçon est capturée en **mémoire typée**, datée, avec le *pourquoi*.
3. La mémoire est promue en **règle** dans `.claude/rules/`, pour être chargée automatiquement à jamais.
4. Là où c'est possible, la règle devient un **filet de sécurité structurel** — une politique d'admission, un garde-fou CI, une étape possédée par une machine — pour que la défaillance ne puisse plus se reproduire même si quelqu'un oublie la règle.

Chaque garde-fou de cet article remonte à un incident réel et daté. Cette boucle de rétroaction, c'est la différence entre un harnais qui est de la *documentation* et un harnais qui est une *discipline d'ingénierie*. C'est aussi, non par hasard, exactement ce qu'un cadre de conformité comme DORA veut voir : non pas « on a écrit une politique », mais « un incident a produit un contrôle, et voici la preuve ».

## Pourquoi cela compte au-delà de mon labo

La vérité inconfortable de l'IA agentique en 2026, c'est que **le modèle est rarement le goulot d'étranglement** — c'est le harnais. Un modèle de pointe avec un harnais faible produit un travail confiant, plausible et non vérifié qui échoue exactement là où les mocks se cachent. Un modèle modeste avec un harnais solide — mémoire persistante, garde-fous structurels, une barrière de vérification indépendante et un plan de contrôle déterministe — produit un travail que vous pouvez réellement mettre devant la production.

C'est le basculement à intégrer. Cessez de demander seulement *« le modèle est-il assez bon ? »*. Commencez à demander *« le harnais est-il assez bon pour rendre ce modèle digne de confiance sur mon système ? »*. Sur le SI ktayl-solution, construire ce harnais s'est avéré être l'essentiel de l'ingénierie — et la totalité de la fiabilité.

---

*Les règles évoquées ici vivent dans le répertoire `.claude/rules/` de la plateforme et dans le système de mémoire ; les incidents qui les sous-tendent sont documentés dans des articles précédents de ce blog — le [debug de la panne en cascade](/blog/debugging-cascading-kubernetes-outage) et le [raisonnement sur la sauvegarde 3-2-1](/blog/dont-retire-minio-3-2-1-backup) sont deux bons exemples de la boucle en action.*
