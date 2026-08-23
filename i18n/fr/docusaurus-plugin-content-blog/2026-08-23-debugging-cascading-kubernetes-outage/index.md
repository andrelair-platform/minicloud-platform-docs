---
slug: debugging-cascading-kubernetes-outage
title: "Anatomie d'une panne Kubernetes en cascade : quand le premier symptôme est à trois niveaux de la cause"
authors: [andrelair]
tags: [kubernetes, sre, incident-response, post-mortem, k3s, longhorn, gitops, argocd, cilium, reliability, storage, dns]
date: 2026-08-23
description: "Un disque s'est rempli. Puis le DNS du cluster est tombé. Puis les volumes de stockage ont refusé de se reconstruire. La cause évidente n'était qu'un symptôme — le vrai coupable était un journal d'écriture anticipée (WAL) SQLite gonflé qui affamait la couche de stockage. Voici tout le fil du débogage, le correctif, et la prévention livrée ensuite."
---

Une alerte de supervision s'est déclenchée : le watchdog de la plateforme était `DOWN`. En quelques minutes, le tableau devenait moche — le DNS du cluster refusait les connexions, et peu après, les volumes de stockage distribué ont cessé de se reconstruire. Une cascade de manuel.

Voici le post-mortem complet : comment la panne s'est propagée, pourquoi la cause *évidente* s'est révélée être un symptôme situé à trois niveaux de la racine, le correctif, et — surtout — la prévention livrée pour qu'elle ne puisse pas se reproduire de la même manière. Chaque changement évoqué ici est une pull request publique et vérifiable.

La plateforme en question — **minicloud** — est un environnement Kubernetes de qualité production tournant sur des ThinkPads reconditionnés, construite et opérée en solo comme simulation du système d'information d'une entreprise. Du bare-metal, aucun plan de contrôle managé, aucun filet de sécurité. C'est précisément pour cela qu'elle enseigne bien.

{/* truncate */}

## La cascade, de haut en bas

L'alerte disait « DNS down ». Poursuivre cette piste en premier aurait gaspillé une heure. Voici ce qui se passait réellement, du symptôme jusqu'à la racine :

```
watchdog DOWN (l'alerte)
  └─ le DNS du cluster refuse les connexions
       └─ le service DNS du contrôleur (bind9) avait planté
            └─ sa base de données (PostgreSQL embarqué de MAAS) avait planté
                 └─ le disque racine du contrôleur était plein à 100 %
```

Le disque s'était rempli parce qu'un groupe de sauvegarde reconstruisait sans cesse deux gros volumes recréables (un cache de registre de conteneurs et un magasin analytique) qui auraient dû être exclus — l'exclusion existait dans le code, mais une étiquette obsolète sur les objets en production les maintenait dans l'ensemble de sauvegarde. Un classique décalage (« drift ») entre « ce que dit git » et « ce qui tourne réellement ».

Le *premier* correctif était donc banal : récupérer l'espace disque (supprimer les données de sauvegarde orphelines via l'API du magasin objet lui-même, car un disque plein à 100 % bloque la plupart des autres approches), puis redémarrer le service DNS. Le DNS est revenu. L'alerte s'est effacée.

Si c'était toute l'histoire, ça ne vaudrait pas la peine d'être écrit.

## La deuxième panne, plus profonde : un stockage qui refuse de guérir

Le cluster à nouveau joignable, la couche de stockage (Longhorn) était un désastre — une vingtaine de volumes en état `degraded`, chacun tournant sur une seule réplique au lieu de trois. Normalement, Longhorn se contente de reconstruire les répliques manquantes. Il ne le faisait pas.

Je lançais une réconciliation, je voyais une rafale d'activité de reconstruction démarrer… puis se bloquer. Les reconstructions commençaient et abandonnaient, encore et encore. Aucune erreur évidente. Beaucoup d'espace disque libre et de nœuds schedulables. Le paramètre régissant la concurrence des reconstructions était correct.

C'est la partie qui compte, car la réponse n'était pas du tout dans la couche de stockage.

## Cause racine : un journal d'écriture affamait la boucle de reconstruction

k3s stocke l'état du cluster dans SQLite (via kine) plutôt que dans etcd — courant sur bare-metal. Quand un cluster est *arrêté brutalement* (coupure de courant, redémarrage forcé) au lieu d'un arrêt propre, kine n'a jamais l'occasion de faire un checkpoint de son **journal d'écriture anticipée (WAL)**. Le WAL gonfle. Au redémarrage, chaque lecture d'API doit rejouer un WAL énorme, et toute l'API Kubernetes ralentit jusqu'à ramper.

Une API lente a une victime collatérale non évidente : **le contrôleur de reconstruction de Longhorn dépend d'appels API rapides pour coordonner les reconstructions de répliques.** Quand l'API est visqueuse, la boucle de reconstruction lance le travail, ne parvient pas à le mener à terme à temps, et abandonne. Ça *ressemble* à un problème de stockage. C'est en réalité un problème de datastore du plan de contrôle déguisé en stockage.

Le correctif a été un redémarrage propre de k3s sur le nœud du plan de contrôle, ce qui force kine à faire un checkpoint du WAL :

```text
# Taille du WAL, avant → après un checkpoint propre :
state.db-wal   914 Mo  →  111 Mo

# Réactivité de l'API, pendant l'incident → après :
kubectl get nodes   >15s (timeout)  →  0,7s
```

Dès que l'API était de nouveau rapide, les reconstructions ont repris et se sont terminées. Vérifié après remise en état :

```console
$ kubectl get nodes
NODE            STATUS   VERSION
fast-heron      Ready    v1.36.3+k3s1
fast-skunk      Ready    v1.36.3+k3s1
loving-gannet   Ready    v1.36.3+k3s1
set-hog         Ready    v1.36.3+k3s1
star-kitten     Ready    v1.36.3+k3s1
swift-mac       Ready    v1.36.3+k3s1

$ # latence de kubectl get nodes :
717ms          # pendant l'incident : timeout (>15s)

$ # santé des volumes Longhorn :
robustness: {'healthy': 42, 'unknown': 1}   # 1 = un volume détaché/inactif, non dégradé
```

## Corriger le correctif : prévention, pas seulement remise en état

Récupérer d'une panne, c'est le minimum. Le vrai travail consiste à s'assurer que la même classe de défaillance ne puisse pas se reproduire silencieusement. Trois choses ont été livrées :

**1. Ne plus jamais arrêter le cluster brutalement.** Tout le problème de gonflement du WAL n'existe que parce que le cluster a été arrêté à chaud. J'ai donc écrit un script d'arrêt propre qui *cordon* les workers, arrête les agents, et stoppe proprement k3s sur le nœud du plan de contrôle — ce qui *fait le checkpoint du WAL dans le cadre d'un arrêt propre*. Un script de démarrage assorti attend l'API et *uncordon* les workers. Les démarrages à froid reviennent maintenant en quelques minutes avec un petit WAL, au lieu d'heures de tempêtes de reconstruction.

**2. Un DNS auto-réparateur.** Le service DNS peut se retrouver désactivé après un crash ou un redémarrage automatique de la pile de provisioning. Une petite garde systemd le réaffirme désormais au démarrage et à intervalle court, de sorte que le DNS ne peut pas rester indisponible plus de quelques minutes, quel que soit ce qui l'a fait tomber. Elle a fait ses preuves la même semaine — un redémarrage de nœud a ramené le DNS sans aucune intervention.

**3. Une sauvegarde qui ne peut pas se bloquer.** La sauvegarde du plan de contrôle utilisait `sqlite3 .backup`, qui s'appuie sur l'API de sauvegarde en ligne — et cette API *redémarre la copie chaque fois que la source est modifiée*. Sur une base désormais plus grande et sollicitée, elle se bloquait indéfiniment sans jamais finir. Passage à `VACUUM INTO`, un instantané cohérent en une seule transaction qui compacte aussi la base : il se termine en quelques secondes au lieu de traîner plus de dix minutes. L'image a aussi été rendue autonome pour qu'une sauvegarde ne dépende jamais d'un accès internet en plein incident.

## Les changements (publics, révisables)

Tout ce qui précède a été livré sous forme de pull requests sur le dépôt GitOps — horodatées, validées par la CI, révisables :

| PR | Quoi |
|----|------|
| **#765** | L'étiqueteur de stockage retire activement l'étiquette de sauvegarde obsolète (le drift qui a rempli le disque) |
| **#766** | Sauvegarde du plan de contrôle : image autonome + `VACUUM INTO` (plus de blocage, plus de dépendance internet) |
| **#767** | Hygiène des exemptions de politiques d'admission (un signalement de sécurité obsolète, correctement re-ciblé sur le vrai sujet) |
| **#768** | Micro-segmentation réseau pour les namespaces des agents IA et des workflows (default-deny egress, internet bloqué, interne au cluster autorisé) |
| **#770** | Correctif de drift GitOps : ignorer un champ status géré par l'opérateur sur une CRD (pour que le *vrai* drift ressorte) |
| **#771** | Suppression d'un manifeste obsolète pour un namespace supprimé qui faisait échouer silencieusement chaque synchronisation de cette app |

Une vérification représentative, après changement — le namespace de l'agent IA peut joindre sa passerelle LLM interne mais est bloqué depuis l'internet public, et les politiques d'admission durcies signalent zéro violation :

```console
$ # application de l'egress depuis un pod agent IA :
LiteLLM interne    : joignable
internet public    : BLOQUÉ

$ # violations de politique Gatekeeper après remédiation :
no-privileged-containers: totalViolations=0
block-net-raw:            totalViolations=0
```

## Ce que je soulignerais à quiconque opère du Kubernetes bare-metal

- **Le premier symptôme n'est presque jamais la cause racine.** « Le DNS est tombé » était à quatre niveaux au-dessus de « le disque s'est rempli à cause d'un drift de configuration ». Suivez la chaîne, pas son sommet.
- **Une API de plan de contrôle lente a un rayon d'impact imprévisible.** Elle n'a pas seulement rendu `kubectl` poussif — elle a silencieusement cassé l'auto-réparation du stockage. Quand quelque chose *devrait* se rétablir et ne le fait pas, vérifiez si le plan de contrôle suit.
- **L'arrêt propre est une fonctionnalité, pas un luxe.** Sur k3s adossé à SQLite, un arrêt gracieux qui fait le checkpoint du WAL fait la différence entre un redémarrage de deux minutes et une tempête de reconstruction de deux heures. C'est gratuit. Écrivez le script.
- **Corrigez la récurrence, pas seulement l'incident.** La panne a été à peu près réglée dans la première heure. Les quatre heures suivantes — les scripts de prévention, la réécriture de la sauvegarde, les correctifs de drift — sont ce qui a réellement rendu la plateforme plus fiable qu'avant sa panne.

La même semaine, sur le cluster désormais sain, j'ai aussi ajouté un sixième nœud de bout en bout via provisioning PXE bare-metal (amorçage réseau → inventaire matériel → installation de l'OS → jonction au cluster), c'est pourquoi la sortie `kubectl get nodes` ci-dessus montre six nœuds. Croissance et durcissement dans le même élan — ce qui est en gros l'intérêt d'exploiter sa propre plateforme : chaque défaillance est un programme d'apprentissage.

---

*minicloud est une plateforme Kubernetes de qualité production, construite en solo sur du matériel reconditionné, livrée entièrement via GitOps. Si vous opérez du Kubernetes bare-metal ou edge et rencontrez quelque chose de similaire, j'aimerais sincèrement comparer nos notes.*
