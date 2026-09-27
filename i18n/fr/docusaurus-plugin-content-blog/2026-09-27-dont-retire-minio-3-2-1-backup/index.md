---
slug: dont-retire-minio-3-2-1-backup
title: "3-2-1, pas 1 : pourquoi j'ai gardé MinIO plutôt que de tout basculer dans le cloud"
authors: [andrelair]
tags: [backup, disaster-recovery, minio, cloudflare-r2, velero, dora, 3-2-1, object-storage, platform-engineering, reliability]
date: 2026-09-27
description: "Il est tentant de supprimer le serveur de sauvegarde et de tout pousser vers du stockage objet cloud bon marché. Sur la plateforme ktayl-solution, j'ai décidé de ne pas le faire — et une heure plus tard, une suppression de bucket à côté de la plaque m'a prouvé exactement pourquoi. Voici le raisonnement derrière la conservation d'un MinIO local aux côtés de Cloudflare R2, et là où l'instinct cloud est réellement pertinent."
---

En durcissant la reprise après sinistre du système d'information ktayl-solution, une question légitime s'est posée : *on réplique déjà les sauvegardes vers Cloudflare R2 — alors pourquoi garder un serveur MinIO qui tourne sur le contrôleur ? Ne pourrait-on pas le retirer et passer full cloud ?*

L'offre gratuite de R2 est généreuse, le stockage objet cloud est durable, et avoir un service de moins à exploiter est toujours séduisant. C'est donc un instinct raisonnable. C'est aussi **faux** — et environ une heure après m'être expliqué pourquoi, je l'ai prouvé à la dure en supprimant le mauvais préfixe de bucket. Cet article, c'est ce raisonnement, et l'incident bien réel qui l'a validé.

{/* truncate */}

## La règle que l'instinct oublie : 3-2-1

La discipline de sauvegarde qui a survécu à toutes les modes s'appelle **3-2-1** : au moins **3** copies des données, sur **2** supports/emplacements différents, dont **1** hors site. Tout l'intérêt est que les copies échouent *indépendamment* — un incendie, un rançongiciel, un blocage de facturation ou une erreur humaine ne devraient jamais pouvoir en détruire plus d'une à la fois.

L'erreur du « passons full cloud », c'est de traiter MinIO et R2 comme **redondants**. Ils ne le sont pas — ce sont les deux *moitiés* d'un 3-2-1 :

|                          | MinIO (sur le contrôleur)                                   | Cloud (R2 / Blob / S3)                                    |
| ------------------------ | ----------------------------------------------------------- | -------------------------------------------------------- |
| **Rôle**                 | **primaire local** — restauration rapide ; les tests le lisent | **DR hors site** — séparation géographique + fournisseur |
| **Vitesse de restauration** | LAN, instantané, gratuit                                 | WAN + egress (R2 sans frais de sortie ✓ ; S3/Azure facturent) |
| **Indépendant d'Internet** | ✅ la restauration fonctionne pendant une panne FAI       | ❌ nécessite qu'Internet soit disponible                 |
| **Coût**                 | gratuit (juste du disque)                                   | gratuit dans les limites ; risque d'egress sur S3/Azure  |

Retirer MinIO pour passer full cloud, ce n'est pas « simplifier à deux copies ». C'est réduire **de 3-2-1 à un seul emplacement**. C'est strictement *moins* résilient, pas plus.

## Pourquoi MinIO-sur-le-contrôleur est un bon design, pas de la dette technique

Trois propriétés font que la copie locale pèse réellement :

**1. Elle vit en dehors de ce qu'elle sauvegarde.** MinIO tourne sur le *contrôleur* — une machine distincte des six nœuds k3s qu'il protège. Les sauvegardes ne devraient jamais vivre à l'intérieur du cluster qu'elles sauvegardent ; si le cluster meurt, les sauvegardes internes meurent avec lui. Un domaine de panne séparé, c'est de l'hygiène correcte, pas un SPOF en germe.

**2. Les restaurations sont rapides (LAN) et gratuites.** Le test de restauration quotidien — qui charge réellement un dump dans un Postgres jetable et vérifie le nombre de lignes, car *une sauvegarde qu'on n'a pas restaurée n'est qu'une hypothèse* — lit depuis MinIO sur le réseau local. Instantané, sans egress. En full cloud, chaque test et chaque vraie reprise paient désormais la latence WAN et (sur S3/Azure) des frais de sortie. On sera tenté de tester moins. Ne construisez pas une architecture qui vous punit de tester la reprise.

**3. Elle est isolée (air-gap) de votre compte cloud.** C'est celle qu'on sous-estime. Un compte cloud peut être bloqué pour facturation, compromis au niveau des identifiants, ou — mon préféré — **victime d'une faute de frappe**.

## L'incident qui a prouvé le propos (une heure plus tard)

En migrant la cible de sauvegarde d'un cluster CloudNativePG vers un bucket dédié, j'ai supprimé l'*ancien* préfixe d'archive WAL pour faire le ménage. C'était la bonne opération sur une mauvaise hypothèse : un standby Postgres était en plein `pg_rewind`, et `pg_rewind --restore-target-wal` récupère les WAL manquants **depuis cette archive**. Je venais de retirer les segments dont il avait besoin. Le replica est parti en boucle de crash.

C'était totalement récupérable — le primaire était sain, alors j'ai reconstruit le standby de zéro et j'ai consigné la leçon (*garder les anciens WAL jusqu'à ce que tous les replicas soient sains sur le nouveau store*). Aucune donnée perdue. Mais posez-vous une seconde sur le contrefactuel : **si cette archive avait été mon unique copie des sauvegardes d'un primaire, un seul `rm` négligent l'aurait rendue irrécupérable.** C'est précisément le mode de défaillance que le 3-2-1 existe pour prévenir, et exactement celui dans lequel le « full cloud » fonce tête baissée. L'erreur humaine ne respecte pas les onze 9 de durabilité d'un fournisseur — la durabilité vous protège de *leur* disque qui meurt, pas de *vous* qui supprimez l'objet.

## Là où l'instinct cloud est réellement pertinent

Rien de tout cela ne signifie « évitez le cloud ». La moitié hors site du 3-2-1 **est** cloud, et elle doit l'être. Sur cette plateforme, MinIO se réplique vers **Cloudflare R2** — 10 Go toujours gratuits avec **zéro frais d'egress**, ce qui en fait la meilleure cible hors site des trois grandes options (S3 et Azure Blob facturent tous deux la récupération de vos données *au pire moment* — pendant une restauration).

Le bon endroit pour dépenser l'instinct « plus de cloud », c'est **diversifier la couche hors site**, pas remplacer la locale. Ajouter un *second* cloud (Azure Blob ou S3) comme copie hors site supplémentaire achète du **DR multi-cloud** — une protection contre une panne fournisseur unique ou un blocage de compte, ce qui, pour un assureur régulé, correspond directement à **DORA Art. 28–29 (risque de concentration ICT)**. Mais c'est un *ajout*, dimensionné pour une offre gratuite, pas un substitut. Et honnêtement, le zéro-egress + 10 Go de R2 couvrent déjà assez bien le besoin pour qu'un second cloud reste un confort, pas une urgence.

## Le bilan, et comment il se traduit dans le design

> Garder **MinIO** (local, primaire, rapide en LAN, air-gap) **+ R2** (hors site, zéro egress). Ajouter éventuellement plus tard un second cloud hors site pour couvrir le risque de concentration. Ne jamais troquer la copie locale contre la copie hors site.

Ce n'est pas abstrait — cela décide *où vont* les nouvelles sauvegardes. Quand j'ai construit des dumps logiques applicativement cohérents pour les deux bases les plus critiques (la base des polices d'assurance et l'ERP), elles écrivent dans **MinIO** `db-logical/`, qui se réplique ensuite vers R2. Chacune obtient ainsi le 3-2-1 complet : l'instantané de volume (Velero), le dump logique local (MinIO) et la copie hors site (R2) — trois copies, deux supports, une hors site.

La leçon n'est pas « cloud mauvais, local bon ». C'est que **la résilience vient de copies *indépendantes*, et que la façon la moins chère de perdre cette indépendance est de se convaincre d'en supprimer une.** J'ai failli le faire — puis un `rm` égaré m'a rappelé pourquoi je ne l'avais pas fait.
