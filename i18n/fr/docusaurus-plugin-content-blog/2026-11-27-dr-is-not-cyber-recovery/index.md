---
slug: dr-is-not-cyber-recovery
title: "DR n'est pas Cyber Recovery — construire un coffre de backup immuable, anti-ransomware"
authors: [andrelair]
tags: [backup, disaster-recovery, cyber-recovery, aws, object-lock, vault, security, dora, sre, carnets]
date: 2026-11-27
description: "En revérifiant la DR de la plateforme, j'ai réalisé que les backups off-site étaient supprimables — ce qui survit à un serveur mort, mais pas à un opérateur compromis ni à un ransomware. J'ai donc ajouté une 3ᵉ couche : un coffre AWS S3 immuable (Object Lock), et j'ai prouvé que je pouvais restaurer Vault en 37 secondes avec une seule clé off-cluster. Voici la distinction que la DR masque, et les arbitrages que j'ai faits."
---

Je suis allé revérifier la reprise après sinistre de la plateforme, et j'ai trouvé quelque chose de
gênant. Les joyaux de la couronne — la base de control-plane k3s **kine** et le snapshot raft de
**Vault** — *étaient* bien mirrorés off-site sur Cloudflare R2. Bien. Sauf que chaque objet dans R2 est
**supprimable par quiconque détient les creds.**

Ça me protège d'une panne (mon contrôleur meurt, le site brûle — je reconstruis depuis R2) et me laisse
grand ouvert à une tout autre : **un opérateur compromis, ou un ransomware, qui supprime les backups
eux-mêmes.** Off-site n'est pas la même chose qu'in-effaçable.

{/* truncate */}

## La distinction que la DR masque

Deux pannes, deux réponses différentes :

| | **Disaster Recovery** | **Cyber Recovery** |
|---|---|---|
| La question | « mon site est détruit — reconstruis-le » | « mon infra est compromise et mes backups peuvent être supprimés — récupère quand même un état sain » |
| Ce qu'il faut | une copie off-site | une copie **immuable** qu'un attaquant **ne peut pas effacer** |
| Ici | Cloudflare R2 | **AWS S3 + Object Lock** |

J'avais la DR. Je n'avais pas la Cyber Recovery. J'ai donc bâti la 3ᵉ couche :

```
MinIO (opérationnel)  →  Cloudflare R2 (Disaster Recovery)  →  AWS S3 + Object Lock (Cyber Recovery)
LAN, restore rapide       off-site, supprimable                 immuable (WORM), provider indépendant
```

## Ce que j'ai construit

Un job quotidien sur le contrôleur copie les joyaux (~650 Mio) dans un **bucket S3 avec Object Lock**.
Trois propriétés comptaient :

- **Immuable (WORM).** Object Lock en mode **COMPLIANCE** : une fois écrit, personne — ni le writer, ni un
  admin, **ni root** — ne peut supprimer ou raccourcir la rétention pendant 35 jours. C'est la garantie
  anti-ransomware.
- **Aucune clé statique nulle part.** Le job de copie mint des **STS courts** via le moteur AWS de Vault
  (un `assumed_role` avec une policy S3 *add-only* — `PutObject`, pas de `Delete`, pas de
  `BypassGovernanceRetention`). Rien de statique ne touche le disque, Git, ou le state Terraform.
- **Provider indépendant.** AWS ≠ Cloudflare, donc le coffre survit aussi à une compromission du compte
  Cloudflare. Répondre à la concentration-cloud de DORA est un effet de bord, pas un pansement.

## Les arbitrages que j'ai vraiment pesés

**R2 Bucket Locks vs AWS S3 Object Lock.** Cloudflare R2 propose désormais aussi une rétention d'objets —
donc l'immuabilité *seule* n'imposait pas AWS. J'ai choisi AWS pour l'**indépendance de provider**, les
garanties matures du **mode COMPLIANCE**, et la vraie pratique d'**isolation IAM**. R2 reste la couche
DR ; il n'est pas *aussi* la couche cyber.

**Glacier ? Non.** Glacier Deep Archive est quasi gratuit, mais sa récupération en 9–48 h échangerait mon
RTO contre des centimes. Un coffre de récupération, c'est **S3 Standard** — récupération immédiate. Du
stockage pas cher ne vaut rien si tu ne peux pas ressortir la donnée vite.

**GOVERNANCE → COMPLIANCE.** J'ai tourné en GOVERNANCE (une identité privilégiée peut encore corriger une
erreur) jusqu'à ce qu'un restore drill prouve la cadence, puis j'ai flippé en COMPLIANCE. Ce flip est une
**porte à sens unique** : le bucket ne peut même plus être `terraform destroy` tant que des objets
verrouillés existent. Pour un coffre cyber, c'est le but — pas un bug.

## Un backup non testé est une hypothèse

Alors je l'ai testé. Deux fois.

1. **Restore normal.** Récupérer un snapshot depuis le coffre, le restaurer dans un Vault jetable tournant
   la même image avec le même auto-unseal AWS KMS, relire un témoin. **RTO ≈ 15 secondes.** Identique, de
   la source à la restauration.

2. **Le vrai scénario cyber — off-cluster.** En cas de compromission, le Vault du cluster peut avoir
   *disparu*, donc la récupération ne doit pas en dépendre (ce serait circulaire). J'ai provisionné une
   identité least-privilege `cyber-recovery-break-glass` (lire le coffre + les ops KMS de seal Vault),
   stocké sa clé **age-chiffrée off-cluster**, et lancé toute la restauration avec **cette clé seule** —
   zéro cluster, zéro Vault on-cluster. **RTO 37 secondes.** Vault est revenu, secrets lisibles.

Voilà la phrase que je peux dire honnêtement maintenant : *si mon cluster et mon coffre de secrets sont
tous deux détruits, je reconstruis Vault depuis une copie immuable qu'un attaquant ne peut pas toucher, en
moins d'une minute, avec une seule clé off-cluster.*

## Deux leçons qui restent

- **Immuable ≠ off-site, et off-site ≠ immuable.** C'est orthogonal. Il faut les deux, et il faut dire
  quelle panne chacun adresse.
- **Un secret se déplace d'un terminal vers son coffre — jamais à travers une conversation.** Je l'ai
  appris brutalement en cours de route (une clé collée là où il ne fallait pas), rotationnée en quelques
  secondes, et on avance. La discipline — rotation-sur-exposition, moindre privilège, zéro clé statique —
  *est* le livrable qu'un auditeur vérifie.

*(ktayl est un assureur fictif utilisé comme laboratoire d'ingénierie — données synthétiques, aucun client
réel. L'ingénierie, les arbitrages et les RTO mesurés sont réels ; l'entreprise est un décor.)*
