---
slug: why-insurers-need-guidelines
title: "Pourquoi un assureur a besoin de directives — et comment j'ai construit tout le cadre comme du code"
authors: [andrelair]
tags: [governance, compliance, insurance, solvency-ii, dora, policy-as-code, platform-engineering]
date: 2026-10-20
description: "Une compagnie d'assurance ne fonctionne pas en embauchant des gens et en laissant chaque département improviser. Elle fonctionne sur un cadre de politiques, standards, directives, procédures et contrôles. J'ai construit ce cadre pour mon assureur simulé — 15 livres de gouvernance, 80 pages, câblés aux applications métier — et j'ai appris que le difficile n'est pas d'écrire les règles. C'est de garder la règle humaine, la règle exécutable et la décision d'ingénierie comme une seule et même chose."
---

Un véritable assureur industriel ne fonctionne pas en embauchant des salariés et en laissant chaque département improviser. Il fonctionne sur un cadre structuré — **politiques, standards, directives, procédures et contrôles** — qui définit comment les décisions sont prises, qui est autorisé à les prendre, quels contrôles s'appliquent, et quelles preuves sont conservées. Pour un assureur, ce n'est pas de la bureaucratie : l'entreprise porte la responsabilité financière de risques valant des millions, voire des milliards d'euros.

Imaginez cinq situations :

- Un souscripteur accepte un risque industriel de 200 M€ sans évaluation correcte.
- Un gestionnaire de sinistres approuve un sinistre de 2 M€ sans vérifier la garantie ni obtenir l'approbation requise.
- Un commercial promet une couverture que l'entreprise ne peut légalement fournir.
- Un administrateur IT accorde l'accès à des données sinistres confidentielles sans autorisation.
- Un manager signe un contrat avec un fournisseur sous sanctions financières.

Chacune est une perte financière potentielle, un problème juridique, une violation réglementaire ou une atteinte à la réputation. Les directives existent précisément pour les empêcher — en définissant *comment* les décisions doivent être prises, *qui* peut les prendre, *quels* contrôles sont requis, et *quelle* preuve doit subsister.

J'ai reconstruit ce cadre de bout en bout pour **ktayl-solution**, un assureur simulé que j'exploite comme laboratoire d'ingénierie. Voici ce que j'en ai retiré.

{/* truncate */}

## La hiérarchie de gouvernance (cinq niveaux, pas un tas de PDF)

L'idée la plus utile : une réglementation, une politique, une directive et une procédure **ne sont pas la même chose** — elles répondent à des questions différentes :

| Niveau | Exemple | Répond à |
|---|---|---|
| **1 — Exigence externe** | Solvabilité II · DORA · RGPD · IDD | À quoi devons-nous nous conformer ? |
| **2 — Politique d'entreprise** | Politique de sécurité · Politique de gestion des risques | Quels principes sont non négociables ? |
| **3 — Directive métier** | Gestion des accès · Appétit de souscription | Comment opère-t-on au quotidien ? |
| **4 — Procédure (SOP)** | SOP d'onboarding · runbook de déploiement | Quelles étapes exactes ? |
| **5 — Assurance** | Approbations · pistes d'audit · KPI · exceptions | Comment le *prouve*-t-on ? |

Elles se recouvrent dans le langage courant, mais servent des objectifs de gestion différents — et un assureur mature gère non seulement ses processus métier, mais les **règles qui gouvernent ces processus.**

Ce n'est pas théorique. Sous Solvabilité II, un assureur européen régulé publie un **Rapport sur la solvabilité et la situation financière (SFCR)** qui décrit typiquement un Code de conduite à l'échelle du Groupe, appuyé par des directives de conformité plus détaillées, sur des sujets comme l'anti-corruption, le droit de la concurrence, la conformité commerciale, les **sanctions financières et embargos**, la lutte anti-blanchiment et le droit prudentiel — revues régulièrement, les managers devant adapter les instructions de travail concernées. De tels assureurs opèrent un modèle des **Trois lignes de maîtrise** : les opérations possèdent le risque, Risques/Conformité surveillent et challengent, l'Audit interne assure de façon indépendante.

## Les 12 domaines que j'ai réellement construits

J'ai organisé la gouvernance de ktayl-solution en **12 domaines**, chacun un livre « Cadre de gouvernance » avec la même hiérarchie `01 Politique → 02 Standard → 03 Directive → 04 Procédure → 05 Runbook` :

> Gouvernance d'entreprise & stratégie · Juridique/Conformité/Éthique · Gestion des risques d'entreprise · Souscription & administration des polices · Sinistres & fraude · Réassurance & programmes internationaux · Finance/Investissements/Actuariat · RH & conduite · IT/Cyber/Résilience numérique · Données/Vie privée/IA · Achats/Tiers/Externalisation · Durabilité/Communication/Continuité.

Concrètement, cela a donné **15 livres de gouvernance / 80 pages** dans un wiki (BookStack), derrière le SSO, ancrés dans Solvabilité II Pilier 2, IDD POG, DORA, RGPD, IFRS 17 et le dispositif LCB-FT/sanctions. Chaque page porte son titulaire, sa cadence de revue et ses références réglementaires — car une directive sans propriétaire ni date de revue est déjà en train de pourrir.

*(Pour être clair : ce catalogue combine des sujets de gouvernance sectoriels publiquement documentés avec un cadre complet recommandé — ce n'est pas une affirmation qu'un assureur particulier utilise chaque titre ou workflow exact.)*

## Le difficile n'était pas d'écrire des règles. C'était les trois foyers d'une même règle.

La leçon qui compte vraiment : une même directive vit dans **trois endroits à la fois**, et ils doivent rester une seule chose.

1. **La directive humaine** — la politique/standard/directive qu'une personne lit (le wiki).
2. **La règle exécutable** — la même règle appliquée par l'application métier (appétit, limites d'autorité, plancher tarifaire).
3. **La décision d'ingénierie** — l'architecture/l'ADR qui dit *comment* c'est construit.

Si ces trois dérivent, la gouvernance devient du théâtre. J'ai donc rendu le lien explicite. La **matrice de délégation d'autorité** et le **plancher de tarification technique** de la directive de souscription ne sont pas que de la prose — ils sont *exécutés* par le workbench de souscription : une cotation sous le plancher technique est bloquée et référée ; une liaison au-delà d'un palier d'autorité exige un double regard. La politique d'accès est *exécutée* par le système IAM (moindre privilège, double approbation, joiner-mover-leaver). Chacune de ces pages wiki porte un **complément « policy-as-code »** qui nomme exactement quelles règles l'application applique — et affirme clairement que le wiki reste la source de vérité.

C'est la différence entre *« nous avons une politique »* et *« la politique ne peut pas être violée »*. Le modèle de données que je vise relie toute la chaîne :

```
Réglementation → Obligation → Politique → Directive → Processus → Contrôle → Application → Preuve → Audit
```
Par exemple : `DORA → contrôle des changements ICT → politique de changement IT → directive de déploiement → gestion des releases → approbation de déploiement → le pipeline CI/CD → le journal d'audit.`

## Des directives qui lient tout le monde, assignées par rôle

Certaines règles sont universelles — Code de conduite, confidentialité, usage acceptable de l'IT, protection des données, anti-corruption, alerte éthique. Mais **tout salarié ne devrait pas recevoir toute directive avec le même poids.** Un gestionnaire de sinistres a besoin des règles d'autorité de règlement ; un administrateur IT a besoin des règles de gestion des changements et d'accès privilégié ; les deux ont besoin de confidentialité et de sensibilisation à la sécurité. Les directives sont donc **assignées par rôle** — dans ma construction, les groupes de votre identité décident des espaces de gouvernance que vous voyez et pouvez éditer, la même identité qui garde chaque application. Gouvernance et accès sont la même surface de contrôle.

Un petit exemple révélateur de la construction : la gouvernance RH *exigeait* déjà des salariés qu'ils signent une « charte informatique » à l'embauche — mais la charte elle-même n'avait jamais été écrite. C'était un **artefact mandaté-mais-manquant** : une règle qui pointe vers un document inexistant. Une directive n'est pas « en place » tant que ce qu'elle exige n'existe pas réellement. J'ai balayé toute la bibliothèque à la recherche de ce défaut et comblé les trous.

## Trois lignes de maîtrise, et qui possède quoi

Publier des PDF n'est pas de la gouvernance. C'est le modèle opérationnel qui la rend réelle :

- **1re ligne — opérations** (Souscription, Sinistres, Finance, IT) : possèdent le risque, exécutent les contrôles, tiennent la preuve.
- **2e ligne — surveillance** (Risques, Conformité, Actuariat) : définissent les cadres, surveillent, challengent.
- **3e ligne — Audit interne** : assurance indépendante.

Chaque directive reçoit un **titulaire, un approbateur, des rôles applicables, des références réglementaires, une version, une date de revue, des procédures liées, des contrôles associés, des preuves et un chemin d'exception** — un registre de gouvernance, pas un dossier de fichiers. La cadence de revue respecte la loi : Solvabilité II article 41, par exemple, exige que certaines politiques écrites de gouvernance soient revues au moins annuellement.

## Où l'IA s'insère — et où elle ne doit pas

La tentation est de mettre un modèle d'IA derrière un endpoint `calculatePremium()` ou de laisser un chatbot répondre de façon autoritaire à « ai-je le droit de faire ça ? ». Je ne l'ai délibérément pas fait. Le rôle honnête de l'IA ici est d'**aider un humain à trouver et appliquer la bonne règle**, jamais d'*être* la règle :

- Un souscripteur pourrait demander *« Puis-je assurer une usine chimique au Brésil, et quelles approbations me faut-il ? »* et obtenir l'appétit, les règles territoriales et de sanctions applicables plus la matrice d'autorité — **extraits des directives approuvées en vigueur, avec liens vers la source** — mais l'IA n'autorise pas le contrat et n'invente pas de limite d'autorité.
- Le modèle de tarification est entraîné hors-ligne et **compilé en un tarif approuvé et versionné** ; le prix est toujours reconstructible sans le modèle. (J'ai écrit cela séparément — *[« OIDC n'est pas un annuaire »](./oidc-is-not-a-directory)* et l'ADR d'évolution tarifaire.)

Cette frontière — automatiser le contrôle répétable, préserver la responsabilité humaine sur le jugement — est en soi la décision de conception senior.

## L'essentiel

Les directives d'entreprise servent deux besoins qu'un assureur ne peut pas totalement séparer : la **gouvernance des personnes** (comment on se comporte, ce qu'on peut approuver, quand on escalade) et la **gouvernance métier** (comment l'entreprise accepte les risques, tarife, règle les sinistres, utilise des tiers, reste conforme). Une règle d'autorité de souscription est *les deux* — un contrôle de risque métier *et* une limite au pouvoir de décision d'un individu.

L'objectif est une organisation où les décisions sont **cohérentes, autorisées, traçables, conformes et proportionnées au risque** — sans demander à chaque salarié d'interpréter seul des centaines de documents. Le construire pour un assureur simulé m'a appris que le cadre est les 20 % faciles ; garder la règle humaine, la règle exécutable et la décision d'ingénierie comme une seule chose vivante, c'est les 80 % qui protègent réellement l'entreprise.

*ktayl-solution est un assureur fictif utilisé comme laboratoire d'ingénierie — données synthétiques, utilisateurs simulés, aucun client réel. Le cadre de gouvernance, et son câblage dans les systèmes en fonctionnement, sont bien réels.*
