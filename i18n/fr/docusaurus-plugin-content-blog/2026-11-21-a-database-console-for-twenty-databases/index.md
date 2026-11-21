---
slug: a-database-console-for-twenty-databases
title: "Une console pour vingt bases de données — pourquoi j'ai supprimé Adminer et choisi DBeaver"
authors: [andrelair]
tags: [databases, postgresql, mariadb, clickhouse, kubernetes, cnpg, security, tooling, dbeaver]
date: 2026-11-21
description: "La plateforme compte désormais ~20 instances PostgreSQL, plus MariaDB et ClickHouse, réparties sur de nombreux namespaces. Une seule console web SQL dans le cluster (Adminer) n'était plus la bonne réponse. Voici le comparatif d'outils que j'ai mené, pourquoi un client local bat une console hébergée, et les trois détails Kubernetes qui le rendent sûr."
---

La plateforme a franchi un seuil sans bruit : elle fait tourner **~20 instances PostgreSQL** (des clusters
CloudNativePG avec paires dev/prod, plus quelques StatefulSets simples), **3 bases MariaDB** et un magasin
**ClickHouse** — répartis sur une vingtaine de namespaces. La question n'était plus *« comment j'ouvre une
console SQL ? »* mais *« comment me donner une console sur plus de vingt bases sans transformer cette console
en passif ? »*

J'utilisais **Adminer** — une seule console web SQL dans le cluster, derrière le SSO. Parfait à trois bases.
À vingt-trois, en dev et en prod, c'était la mauvaise forme. Cet article est le comparatif que j'ai
réellement mené et la décision à laquelle j'ai abouti.

{/* truncate */}

## Ce qui n'allait pas avec l'outil que j'avais déjà

Adminer est un charmant fichier PHP de 400 Ko. Mais comme cockpit base-de-données *principal* d'un cluster
multi-namespace, il a trois problèmes structurels :

1. **C'est une surface d'attaque permanente.** Une UI web capable d'atteindre les namespaces de plusieurs
   bases, c'est par définition un pod + un ingress + une série de trous NetworkPolicy ouverts vers ces
   namespaces. Une seule mauvaise configuration, et chaque base qu'elle voit est à un onglet de navigateur.
2. **Tous les onglets se ressemblent.** Rien ne distingue visuellement `claims (dev)` de `claims (PROD)`.
   La seule chose entre un `DELETE` distrait et la production, c'est votre propre vigilance. Ce n'est pas
   un contrôle.
3. **Deux moteurs seulement.** Adminer fait PostgreSQL et MySQL/MariaDB. Il ne parle pas ClickHouse — il
   n'allait donc de toute façon jamais être l'outil *unique*.

Rien de tout cela n'est la faute d'Adminer. C'est ce qui arrive quand on demande à une console web
mono-fichier d'être un cockpit base-de-données à l'échelle de l'entreprise.

## Le terrain que j'ai comparé

Je voulais un seul outil pour tous les moteurs SQL, une sécurité dev/prod que je puisse *voir*, et — ce qui
compte sur un cluster auto-hébergé — **rien de nouveau à exploiter et à sécuriser**. Voici le score des
candidats face à *cette* installation (pas dans l'abstrait) :

| Outil | Forme | Moteurs couverts ici | Garde-fou dev/prod | Empreinte cluster | Coût | Verdict |
|---|---|---|---|---|---|---|
| **Adminer** | UI web dans le cluster | PostgreSQL, MariaDB | aucun (onglets identiques) | **permanente** : pod + ingress + trous netpol | FOSS | **retiré** |
| pgAdmin / phpMyAdmin | web ou bureau, mono-moteur | un moteur chacun | par outil | web = empreinte ; bureau = aucune | FOSS | un outil *par moteur* — inadapté à 4 moteurs |
| **DBeaver CE** | client bureau local | **PostgreSQL, MariaDB, ClickHouse, SQLite** (+ tout JDBC) | **couleur par type de connexion + lecture seule par défaut** | **nulle** (sur mon portable) | gratuit (Apache-2.0) | **choisi** |
| DBeaver PRO | client bureau local | + Redis, MongoDB, Cassandra… | idem | nulle | payant | pas encore nécessaire — des compagnons gratuits couvrent ça |
| TablePlus | client bureau local | nombreux | couleur par connexion | nulle | payant | soigné, mais aucun avantage sur CE *ici* |
| Beekeeper Studio | client bureau local | PostgreSQL, MySQL… | partiel | nulle | FOSS + offre payante | plus léger, mais pas de ClickHouse natif |

Deux colonnes ont tranché : **« moteurs couverts ici »** et **« empreinte cluster »**. DBeaver CE est le
seul outil gratuit qui parle mes trois moteurs SQL dans une même fenêtre *et* n'ajoute rien au cluster —
c'est une appli bureau qui passe par mon propre `kubectl`. TablePlus et Beekeeper sont vraiment bien ; ils
n'ont simplement pas battu *gratuit + tous-mes-moteurs + empreinte-nulle* sur ce tableau précis.

### Les magasins non-SQL vont à des compagnons spécialisés

La limite honnête : DBeaver CE ne couvre pas **Redis/Valkey** (~11), **OpenSearch** (criblage des
sanctions) ni **Qdrant** (vecteurs RAG). Plutôt que d'acheter PRO pour Redis, je laisse chaque outil
spécialisé faire son travail — **RedisInsight**, **OpenSearch Dashboards** (déjà web) et le
`:6333/dashboard` intégré de **Qdrant**. Un « panneau unique » moins bon sur chaque panneau ne vaut pas la
licence.

## La décision : déplacer la console vers le client

Le recadrage qui a tout éclairci : **une console base-de-données est une surface d'attaque, et la surface
d'attaque la moins chère est celle qui n'existe pas.** Un client local via `kubectl port-forward` a une
empreinte permanente *nulle*. L'accès est borné par mon propre RBAC kubeconfig — il n'y a aucun service
partagé, toujours actif, avec un accès large aux bases que quelqu'un pourrait trouver. Supprimer Adminer
n'a pas seulement changé d'outil : cela a retiré un pod permanent, un ingress, une intégration SSO et une
poignée de trous NetworkPolicy inter-namespaces.

## Trois détails Kubernetes qui le rendent réellement sûr

Pointer un client bureau vers des bases dans le cluster ne vaut que par le câblage. Trois choses comptent :

**1. Tunnel vers le Service `-rw`, jamais un pod.** Les clusters CloudNativePG exposent `<cluster>-rw`, qui
suit toujours le primaire courant. Forwardez vers lui et un failover vous est invisible ; forwardez vers un
pod et vous lirez une réplica — ou rien — après le prochain basculement.

```bash
kubectl --context minicloud-oidc -n ktayl-core-prod \
  port-forward svc/ktayl-core-cnpg-rw 55438:5432
```

**2. Les identifiants sont tirés par session — jamais stockés dans le fichier de connexion.** Le jeu de
connexions généré porte les hôtes, les ports et les noms de base, mais **aucun mot de passe**. Chaque mot de
passe est lu depuis le Secret Kubernetes de la base au moment de la connexion, vers le coffre chiffré du
client :

```bash
kubectl --context minicloud-oidc -n ktayl-core-prod get secret ktayl-core-cnpg-app \
  -o jsonpath='{.data.password}' | base64 -d
```

Un fichier de connexion qui fuite est une carte, pas une clé.

**3. La production est rouge et en lecture seule par défaut.** C'est le contrôle qu'Adminer ne pouvait pas
offrir. Chaque connexion `*-prod` est étiquetée `Production` — le client peint ses onglets en **rouge** et
les ouvre en **lecture seule**, avec confirmation à l'exécution. Écrire en production est un geste
délibéré, pas un accident d'onglet actif. Les connexions dev restent neutres.

L'ensemble est généré depuis une table unique de référence (port · namespace · service `-rw` · moteur · env
· secret), si bien que les tunnels, le fichier de connexions et la doc ne divergent jamais.

## Ce que je me dirais, trois bases plus tôt

Pas *« prends DBeaver ».* La leçon transférable, c'est l'ordre des questions : **partez de la surface
d'attaque et du rayon d'impact, pas de la liste de fonctionnalités.** La meilleure console pour vingt bases
s'est avérée être celle qui ne tourne nulle part, ne stocke aucun mot de passe et rend la production
visiblement dangereuse à toucher. Le comparatif de fonctionnalités n'a compté qu'*après* que ces
contraintes aient déjà éliminé l'essentiel du terrain.
