---
slug: kubernetes-datastore-kine-sqlite-vs-etcd
title: "Votre cluster Kubernetes ne fait pas tourner etcd — le mien non plus"
authors: [andre]
description: >
  k3s remplace etcd par Kine/SQLite — un seul fichier sur une seule machine. Cet article explique
  précisément ce que cela implique pour les sauvegardes, la haute disponibilité et la reprise sur un
  cluster bare-metal, et le compare à la façon dont EKS, GKE et AKS gèrent le même problème de manière invisible.
tags: [kubernetes, k3s, etcd, kine, sqlite, backup, platform-engineering, bare-metal, eks, gke, aks]
date: 2026-07-28
image: /img/docusaurus-social-card.jpg
---

Chaque tutoriel Kubernetes mentionne etcd. Les schémas d'architecture montrent un cluster etcd à trois nœuds avec consensus Raft, élection de leader et réplication entre pairs. Si vous utilisez EKS, GKE ou AKS, ce cluster existe quelque part — vous ne pourrez simplement jamais le voir.

Si vous utilisez k3s, vous n'avez pas d'etcd du tout.

Cet article explique ce que k3s utilise réellement, ce que cela signifie de gérer soi-même les sauvegardes et la reprise, et où cela vous situe par rapport à un fournisseur managé.

{/* truncate */}

## Ce que fait réellement etcd (en un paragraphe)

etcd est un magasin clé-valeur distribué que Kubernetes utilise comme source de vérité unique. Chaque objet que vous créez — pods, secrets, ConfigMaps, rôles RBAC, tout — est écrit dans etcd. Quand le serveur d'API redémarre, il lit etcd pour reconstruire son état en mémoire. Quand un contrôleur réconcilie, il surveille etcd pour détecter les changements.

Perdez etcd, et le cluster devient un instantané en lecture seule : les pods en cours continuent de tourner (kubelet est indépendant), mais plus aucun ordonnancement, plus aucun changement de configuration, plus aucune rotation de secret. Corrompez etcd sans sauvegarde, et l'état du cluster est perdu.

C'est pourquoi chaque schéma d'architecture montre trois nœuds etcd. Le consensus Raft exige un quorum impair : trois nœuds tolèrent une panne, cinq nœuds en tolèrent deux. Un nœud etcd unique n'a aucune tolérance.

## Ce que k3s utilise réellement

k3s remplace etcd par **Kine** — un adaptateur qui traduit l'API gRPC etcd v3 en requêtes SQL. k3s passe tous ses appels etcd habituels à Kine, et Kine les écrit dans un **fichier SQLite** :

```
/var/lib/rancher/k3s/server/db/state.db
```

Un seul fichier. Sur une seule machine. Pas de réplication, pas de consensus, pas de nœuds pairs.

Sur mon cluster, cette machine est `set-hog` — un ThinkPad X390 qui exécute le plan de contrôle k3s. Le fichier fait environ 55 Mo après des mois d'exécution de plus de 20 workloads sur 5 nœuds.

Ce n'est ni un compromis ni une limitation — c'est un choix de conception délibéré pour les petits clusters. SQLite est [le moteur de base de données le plus déployé au monde](https://www.sqlite.org/mostdeployed.html), son mode WAL gère les lectures concurrentes sans verrouiller les écritures, et pour un cluster de moins d'environ 1 000 nœuds, il fonctionne très bien. k3s permet aussi de remplacer le backend de Kine par PostgreSQL ou MySQL si vous avez besoin de plus de débit ou d'un accès multi-écrivain.

La conséquence est une simplicité architecturale : il n'y a pas de cluster etcd à gérer, pas de certificats TLS entre pairs, pas de quorum à maintenir. Il y a un fichier à sauvegarder et un fichier à restaurer.

## Les deux mécanismes de sauvegarde

Comme l'état réside dans un seul fichier, la sauvegarde est simple — mais j'exécute deux mécanismes indépendants, car ils ont des modes de défaillance différents.

### Mécanisme 1 — Timer systemd du contrôleur (02:30 UTC)

Il s'exécute sur le contrôleur MAAS (`ktayl-ThinkPad-X390`), en se connectant en SSH à `set-hog` pour copier le fichier. Point crucial, il s'exécute **en dehors de Kubernetes** — il ne dépend ni du serveur d'API ni de la santé d'un quelconque pod.

```bash
#!/bin/bash
set -euo pipefail

TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)
BACKUP_KEY="kine/kine-${TIMESTAMP}.db.gz"
TMP_DB="/tmp/kine-backup-${TIMESTAMP}.db"

# .backup maintient une transaction de lecture pendant toute la durée de la copie — sûr avec WAL.
# Il produit un instantané binaire cohérent à un instant précis.
ssh ubuntu@10.0.0.2 \
  "sudo sqlite3 /var/lib/rancher/k3s/server/db/state.db \".backup ${TMP_DB}\" \
   && sudo cat ${TMP_DB} \
   ; sudo rm -f ${TMP_DB}" \
  | gzip -9 \
  | mc pipe "minilocal/db-backups/${BACKUP_KEY}"
```

Rétention de 30 jours. Fichiers nommés `kine-YYYYMMDD-HHMMSS.db.gz`. C'est la sauvegarde depuis laquelle vous pouvez restaurer même si k3s lui-même est le problème.

### Mécanisme 2 — CronJob Kubernetes (03:30 UTC)

Il s'exécute à l'intérieur du cluster, une heure après le timer systemd. Un pod monte le fichier SQLite via hostPath sur `set-hog` et écrit une sauvegarde binaire directement dans MinIO :

```bash
sqlite3 /db/state.db ".backup /backup/state-$(date +%Y%m%d%H%M%S).db"
```

Rétention de 7 fichiers dans le bucket `k3s-backup/`. **Si le plan de contrôle est mort, ce job ne peut pas s'exécuter** — ce qui est précisément la raison d'être du timer systemd.

### Pourquoi `.backup` et pas `.dump`

SQLite dispose de deux méthodes d'export : `.dump` produit du texte SQL (instructions INSERT, CREATE TABLE, etc.), et `.backup` produit une copie binaire.

La différence essentielle est la cohérence. `.dump` lit les pages séquentiellement sans maintenir de transaction d'instantané — si k3s écrit un nouvel objet pod en plein dump, le SQL résultant peut décrire un état incohérent. `.backup` maintient une seule transaction de lecture pour toute l'opération, donc la sortie est toujours cohérente à un instant précis. C'est surtout important sous charge, mais le bon choix est `.backup` dans tous les cas.

Les deux mécanismes utilisent désormais `.backup`. La sortie binaire compressée fait environ 55 Mo pour ce cluster.

### Contrôle de santé

```bash
ssh controller "systemctl status kine-backup.timer --no-pager && \
  ~/.local/bin/mc ls minilocal/db-backups/kine/ | tail -3 && \
  ~/.local/bin/mc ls minilocal/k3s-backup/ | tail -3"
```

La sortie attendue montre les deux buckets avec un fichier daté des dernières 24 heures.

## Haute disponibilité : intentionnellement absente

Une vraie configuration k3s HA nécessite trois nœuds serveur avec `--cluster-init` sur le premier et `--server` sur les autres. Cela bascule le datastore embarqué vers un véritable etcd (k3s embarque etcd pour ce mode) avec consensus Raft entre les trois nœuds. Perdez-en un, le cluster continue d'ordonnancer.

Le cluster minicloud ne fait pas cela. `set-hog` est l'unique plan de contrôle. S'il plante :

- **Les pods en cours continuent de tourner.** Le kubelet de chaque worker est un processus distinct ; il continue de gérer ses pods locaux quelle que soit la santé du serveur d'API.
- **Aucun nouvel ordonnancement.** Pas de serveur d'API signifie pas de création de pod, pas de mise à jour de ConfigMap, pas de déploiement de rollout.
- **Temps de reprise = temps de redémarrage.** `set-hog` redémarre en environ 90 secondes. k3s démarre automatiquement. Le cluster se rétablit tout seul.

Ajouter deux nœuds de plan de contrôle supplémentaires coûterait deux machines de plus, deux installations d'OS de plus, et la gestion continue d'un cluster Raft — pour un cluster de portfolio qui tourne sur des ThinkPads. Le compromis est clair : plan de contrôle mononœud, reprise rapide, zéro complexité de quorum.

## Reprise : disque remplacé ou corruption

Voici la procédure quand `set-hog` a besoin d'un nouveau disque ou que `state.db` est corrompu :

```bash
# 1. Installer un k3s neuf sur set-hog (même version)
ssh set-hog "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.36.2+k3s1 sh -"

# 2. Arrêter k3s avant de toucher à la base
ssh set-hog "sudo systemctl stop k3s"

# 3. Trouver la dernière sauvegarde binaire dans MinIO
ssh controller "~/.local/bin/mc ls minilocal/db-backups/kine/ | tail -3"
# p. ex. kine-20260728-030001.db.gz

# 4. Décompresser et transférer vers set-hog
ssh controller "~/.local/bin/mc cat minilocal/db-backups/kine/kine-20260728-030001.db.gz \
  | gunzip | ssh ubuntu@10.0.0.2 'sudo tee /var/lib/rancher/k3s/server/db/state.db > /dev/null'"

# 5. Corriger les droits et redémarrer
ssh set-hog "sudo chown root:root /var/lib/rancher/k3s/server/db/state.db \
  && sudo systemctl start k3s"

# 6. Vérifier
ssh controller "kubectl get nodes && kubectl get pods -A | grep -v Running | grep -v Completed"
```

**Fenêtre de perte de données :** jusqu'à 23 heures pour les objets créés entre la dernière sauvegarde et le crash. Les données applicatives résident dans les PVC Longhorn (stockage physique séparé sur les nœuds workers) — les données des PVC ne sont pas dans cette sauvegarde.

**Ré-enregistrement des workers :** les workers se ré-enregistrent automatiquement auprès du serveur d'API après son retour. Aucune action nécessaire.

## Comment se comparent les fournisseurs managés

| | minicloud (k3s/Kine) | EKS | GKE | AKS |
|---|---|---|---|---|
| **Datastore** | SQLite (1 fichier, 1 machine) | etcd, géré par le fournisseur, multi-AZ | etcd, géré par Google | etcd, géré par Azure |
| **HA** | Non — plan de contrôle mononœud | Oui — etcd sur 3 AZ, SLA fournisseur | Oui — totalement opaque, garanti par SLA | Oui — entièrement managé |
| **RPO** | ~23h (sauvegarde nocturne à 02:30 UTC) | Sous la minute (réplication continue) | Sous la minute | Sous la minute |
| **RTO** | 90s (redémarrage de set-hog) + temps de restauration | Le fournisseur restaure automatiquement, généralement invisible | Le fournisseur restaure automatiquement | Le fournisseur restaure automatiquement |
| **Format de sauvegarde** | SQLite binaire (`.db.gz`) dans votre MinIO | Snapshot etcd — inaccessible pour vous | Snapshot etcd — inaccessible pour vous | Snapshot etcd — inaccessible pour vous |
| **Restauration** | Vous la faites, procédure complète ci-dessus | Non accessible à l'utilisateur | Non accessible à l'utilisateur | Non accessible à l'utilisateur |
| **Ce que vous possédez** | Planning, format, rétention, procédure de restauration | Conception des PDB, tolérance au drain | Conception des PDB, tolérance au drain | Conception des PDB, tolérance au drain |
| **Coût** | Électricité + stockage MinIO sur matériel existant | 0,10 $/h de plan de contrôle (73 $/mois) + frais de stockage etcd | Plan de contrôle gratuit en Standard ; Autopilot facture par workload | Plan de contrôle gratuit ; on paie les VM des nœuds |
| **Observabilité** | `sqlite3 state.db ".dbinfo"`, logs du timer systemd, bucket MinIO | CloudWatch, EKS upgrade insights | Cloud Logging, notifications de mise à jour GKE | Azure Monitor |

L'histoire de la HA managée est simple : les fournisseurs exécutent etcd sur une infrastructure que vous ne voyez jamais, le répliquent entre zones de disponibilité, et prennent des snapshots automatiques avant chaque mise à jour. RPO sous la minute, reprise automatique, zéro surcharge opérationnelle.

Ce qu'ils retirent en échange : vous ne pouvez pas accéder à la sauvegarde, ne pouvez pas effectuer une restauration à un instant précis arbitraire, et ne pouvez pas déplacer l'état vers un autre cloud. Si le fournisseur perd vos données etcd (ce qui n'est pas arrivé à grande échelle), votre seul recours est son processus de support.

Sur bare-metal, les fichiers de sauvegarde sont à vous. Ils vivent dans MinIO sur votre contrôleur. Vous pouvez les restaurer sur n'importe quelle installation k3s compatible sans demander la permission à quiconque. Le coût opérationnel est réel — vous avez conçu la sauvegarde, vous avez vérifié qu'elle s'exécute, vous avez écrit la procédure de restauration — mais le contrôle est le vôtre.

## L'asymétrie facile à oublier

Les fournisseurs managés sauvegardent etcd automatiquement. Mais ils le font *pour leurs propres besoins de reprise*, pas les vôtres. Le snapshot qu'ils prennent avant une mise à jour n'est pas quelque chose que vous pouvez déclencher, télécharger ou restaurer. Si vous supprimez accidentellement 200 namespaces avec `kubectl delete ns --all`, aucun fournisseur managé ne restaurera l'état de votre cluster tel qu'il était il y a cinq minutes.

Sur minicloud, vous le pouvez. La sauvegarde binaire est une copie complète et ponctuelle de l'état du cluster. Restaurez-la, redémarrez k3s, et les namespaces supprimés reviennent — moins tout ce qui a été créé dans les heures intermédiaires.

Ce n'est pas une raison de préférer le bare-metal au Kubernetes managé en général. C'est une raison de comprendre ce que « sauvegarde » signifie dans chaque modèle avant de supposer qu'elle couvre vos scénarios.

## Les coûts réels

**Kubernetes managé (exemple EKS) :**
- Plan de contrôle : 0,10 $/h = 73 $/mois
- Stockage etcd : inclus
- Sauvegarde : incluse (mais non accessible pour une restauration à un instant précis)
- Total pour plan de contrôle + datastore : 73 $/mois avant tout nœud worker

**minicloud :**
- Matériel : ThinkPads déjà possédés
- MinIO : tourne sur le contrôleur, stockage sur le NVMe de 98 Go existant
- Stockage de sauvegarde par fichier : ~55 Mo compressé, rétention 30 jours = ~1,6 Go pour 30 fichiers
- Coût incrémental total pour le datastore du plan de contrôle : quasi nul

La comparaison n'est pas « SQLite est meilleur qu'etcd ». SQLite n'a pas de HA, pas de RPO sous la minute, et serait le mauvais choix pour un cluster de production avec des centaines de nœuds et une équipe qui en dépend 24h/24. La comparaison porte sur la compréhension de ce que chaque modèle coûte et de ce qu'il vous apporte — pour que, lorsque vous utilisez EKS ou GKE, vous sachiez exactement quelle partie du problème ils résolvent et quelles parties restent les vôtres.
