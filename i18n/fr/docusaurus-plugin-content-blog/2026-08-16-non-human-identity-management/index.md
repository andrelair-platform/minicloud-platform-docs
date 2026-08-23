---
slug: non-human-identity-management-k8s-platform
title: "Chaque identité non-humaine sur une plateforme k8s auto-hébergée : une taxonomie complète"
authors: [andrelair]
tags: [security, iam, kubernetes, vault, service-accounts, devops, k3s, self-hosted]
date: 2026-08-16
description: "Comptes de service, comptes robots, tokens break-glass, identifiants client OAuth2, clés d'API — une plateforme Kubernetes auto-hébergée les utilise tous. Voici comment ils diffèrent, pourquoi chacun existe, et ce qui arrive quand vous en perdez un de vue."
---

Quand vous construisez une plateforme Kubernetes de production de zéro, vous accumulez des identités non-humaines plus vite que prévu. Au moment où la plateforme minicloud a atteint sa maturité opérationnelle — un cluster k3s bare-metal de 5 nœuds exécutant plus de 70 workloads — elle comptait plus de 35 identités non-humaines distinctes réparties en six catégories différentes. La plupart sont invisibles en exploitation normale. Vous ne les remarquez que lorsque l'une casse.

Cet article cartographie chaque type d'identité non-humaine utilisé sur la plateforme, explique comment ils diffèrent, et documente les leçons opérationnelles tirées de ceux qui ont causé des incidents.

{/* truncate */}

## Les six types d'identité

Toutes les identités non-humaines ne se valent pas. Elles diffèrent par qui les crée, comment elles s'authentifient, combien de temps elles vivent, et ce qui arrive quand elles tournent mal.

### 1. Comptes de service Kubernetes

Le type d'identité le plus propre de la pile. Un objet `ServiceAccount` dans un namespace donne à un pod un token JWT, monté automatiquement à `/var/run/secrets/kubernetes.io/serviceaccount/token`. Le kubelet fait tourner ce token régulièrement. Quand le pod est supprimé, le token disparaît.

Les comptes de service sont le bon choix chaque fois qu'un workload doit appeler l'API Kubernetes ou tout système qui supporte l'authentification native Kubernetes (comme Vault avec la méthode d'auth `kubernetes`).

```yaml
# cert-manager s'authentifie auprès de Vault PKI avec le JWT de son ServiceAccount
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  vault:
    auth:
      kubernetes:
        role: cert-manager
        serviceAccountRef:
          name: cert-manager
```

Le token est de courte durée, tourné automatiquement, et lié à l'identité du pod. Aucune gestion d'identifiant requise.

**Comptes de service minicloud utilisés :**

| SA | Namespace | S'authentifie auprès de |
|---|---|---|
| `cert-manager` | cert-manager | Moteur PKI Vault |
| `external-secrets` | external-secrets | Vault (lit tout `secret/platform/*`) |
| `argocd-application-controller` | argocd | API k8s (cluster-admin) |
| `velero` | velero | API k8s + stockage objet |
| `backstage` | backstage | API k8s (découverte du catalogue) |
| `minicloud-agent` | ai | API k8s + LiteLLM |
| `longhorn-pvc-labeler` | longhorn-system | API k8s (patch des volumes Longhorn) |
| `node-problem-detector` | node-problem-detector | API k8s (patch des conditions de nœud) |

---

### 2. Comptes robots / techniques

Un compte robot est une identité en forme humaine qui appartient à une machine. C'est la terminologie de Harbor ; d'autres systèmes parlent d'« utilisateur de service », de « compte système » ou de « compte bot ». Il s'authentifie exactement comme un utilisateur humain — nom d'utilisateur et mot de passe ou token d'API — mais l'identifiant appartient à un système automatisé.

La caractéristique déterminante : **l'identifiant vit quelque part en dehors du système qui l'a émis**. Après avoir créé un compte robot Harbor, vous copiez le token affiché une seule fois vers Vault et vers vos secrets de CI. Le token et le compte mènent ensuite des vies indépendantes. Si la base de données du compte est effacée, le token dans Vault pointe désormais vers rien.

C'est exactement ce qui est arrivé avec `robot$ci` fin juillet 2026. Une panne de PVC Longhorn a forcé un effacement et une reconstruction de la base Harbor. L'ancien compte `robot$ci` a été recréé avec le même nom, mais le token était nouveau — et les secrets d'organisation GitHub détenaient toujours l'ancien. Les pushes d'images CI ont échoué silencieusement pendant des semaines avant que l'incohérence ne soit remarquée.

**Le correctif :** stocker le token dans Vault (`secret/platform/harbor` clé `robot-ci-secret`) immédiatement après création. Lors de la reconstruction de Harbor, vérifier Vault d'abord, puis mettre à jour les secrets GitHub.

**Comptes robots/techniques minicloud :**

| Compte | Système | Emplacement du token |
|---|---|---|
| `robot$ci` | Harbor | Vault `secret/platform/harbor` + secrets d'org GitHub |
| `admin` | MinIO (Docker) | Vault `secret/platform/minio` |
| `ktayl` | MAAS | Local au contrôleur uniquement (faible risque — MAAS est propre au contrôleur) |

---

### 3. Comptes break-glass

Un compte break-glass est une sortie de secours. Il doit être scellé, documenté, et utilisé uniquement lorsque le chemin d'authentification normal (OIDC/SSO) est indisponible.

Sur la plateforme minicloud, Authentik fournit le SSO pour ArgoCD, Grafana, Harbor, Backstage, Plane, ERPNext, et plus. Si Authentik tombe — crash de pod, corruption de base, panne de volume Longhorn — chacune de ces UI devient inaccessible aux opérateurs humains. Les comptes break-glass sont le chemin hors-ligne.

**Comptes break-glass minicloud :**

| Compte | Système | Chemin de login normal | Identifiant d'urgence |
|---|---|---|---|
| `admin` | ArgoCD | Authentik OIDC → `kanmegnea` | Vault `secret/platform/break-glass` clé `argocd` |
| `admin` | Grafana | Authentik OIDC → `kanmegnea` | Vault `secret/platform/break-glass` clé `grafana` |
| `admin` | Harbor | Authentik OIDC → `kanmegnea` | Vault `secret/platform/break-glass` clé `harbor` |
| `minicloud-break-glass` | API k3s | kubeconfig OIDC `minicloud-oidc` | Contexte kubeconfig à certificat statique |

La discipline opérationnelle pour les comptes break-glass :
1. **Les créer une fois** et écrire les identifiants dans Vault immédiatement
2. **Les redésactiver après usage** (l'admin local ArgoCD requiert `accounts.admin: enabled: false` dans `argocd-cm`)
3. **Les tester périodiquement** — un compte break-glass jamais testé peut ne pas fonctionner quand vous en avez le plus besoin

Avant cette session, les mots de passe break-glass n'existaient que comme fichiers sur le système du contrôleur (`~/.argocd-admin`, `~/.grafana-admin`, `~/.harbor-admin`). Si le disque du ThinkPad X390 du contrôleur tombait, ces identifiants seraient irrécupérables. Ils vivent désormais dans Vault à `secret/platform/break-glass`.

---

### 4. Identifiants client OAuth2 (fournisseurs OIDC)

Chaque application qui délègue l'authentification à Authentik détient une paire d'identifiants client OAuth2 : `client_id` + `client_secret`. Authentik les émet quand vous créez un fournisseur OAuth2/OIDC pour une application.

Ce ne sont pas des « comptes » — ce sont des identifiants qui identifient une application auprès du fournisseur d'identité. L'application les utilise pour échanger un code d'autorisation contre un token d'accès.

```
Navigateur → ArgoCD → Authentik (présente client_id, reçoit un code)
                    → échange code + client_secret contre un JWT
                    → l'utilisateur arrive sur ArgoCD avec les claims du JWT
```

**Fournisseurs OIDC minicloud (un par application) :**

| Application | Slug du fournisseur Authentik | Emplacement du client_secret |
|---|---|---|
| ArgoCD | `argocd` | Secret k8s `argocd-secret` |
| Harbor | `harbor` | Secret k8s + Vault `secret/platform/harbor` |
| Grafana | `grafana` | Secret k8s `grafana-oidc` |
| Backstage | `backstage` | Secret k8s |
| Plane CE | `plane` | Secret k8s |
| ERPNext | `frappe` | Secret k8s |
| Open WebUI | `open-webui` | Secret k8s |
| Vaultwarden | `vaultwarden` | Secret k8s (fork Timshel requis pour le SSO) |
| Matrix/Element | `synapse` | Config Synapse |

Le profil de risque des identifiants client OAuth2 est plus faible que celui des comptes robots — ils ne peuvent qu'initier des flux d'authentification, pas accéder directement aux données. Si un `client_secret` fuit, un attaquant peut usurper l'application auprès d'Authentik, mais ne peut toujours pas contourner l'étape d'authentification de l'utilisateur.

---

### 5. Clés d'API de services externes

Des tokens de longue durée émis par des services tiers qui ne supportent pas l'auth native Kubernetes. Ce sont les identifiants de Cloudflare, AWS SES, Tailscale, GitHub et des services de supervision.

Tous vivent dans Vault sous `secret/platform/<service>` et sont tirés dans le cluster via l'External Secrets Operator à l'exécution. Les pods ne voient jamais le token brut — ils voient le Secret k8s que l'ESO a peuplé.

**Clés d'API externes minicloud :**

| Service | Chemin Vault | Utilisé par |
|---|---|---|
| API Cloudflare (token `MINICLOUD`) | `secret/platform/cloudflare` clé `api-token` | tunnel cloudflared + DNS01 cert-manager |
| Clé d'accès + secret R2 Cloudflare | `secret/platform/cloudflare` clés `r2-*` | BSL de sauvegarde hors-site Velero |
| OAuth Tailscale | Secrets d'org GitHub | Pipelines CI (tous les dépôts, action Tailscale) |
| GitHub `GITOPS_TOKEN` | Secrets d'org GitHub | CI → push kustomize, scaffolder Backstage |
| SMTP AWS SES | `secret/platform/mail` | Relais mail Stalwart |
| Clé d'API Healthchecks.io | `secret/platform/healthchecks-io` | heartbeat minicloud-ops + alertes watchdog |

---

### 6. Le token root de Vault

Dans une catégorie différente de tout le reste. Le token root de Vault n'est pas une identité d'application — c'est la clé maîtresse du magasin de secrets lui-même. Tout autre identifiant de la plateforme est accessible à quiconque détient le token root.

Sur minicloud, le token root vit à `~/.vault-root-token` sur le système du contrôleur (mode 600). Il a été généré lors de `vault operator init` et n'a jamais été tourné.

L'amélioration apportée dans cette session : un token `platform-ops` limité a été créé avec une politique en lecture seule sur `secret/platform/*` plus des permissions de signature PKI. Ce token vit à `~/.vault-ops-token` et c'est ce que l'automatisation et les scripts quotidiens devraient utiliser. Le token root est réservé aux opérations d'écriture et à la gestion des politiques.

```
politique platform-ops :
  secret/data/platform/*    → read, list
  secret/metadata/platform/* → read, list
  pki/sign/*                → create, update
  pki/issue/*               → create, update
```

Le token `platform-ops` est un token périodique de 10 ans, renouvelable. La procédure de rotation du token root (révoquer + `vault operator generate-root` avec la clé de descellement) est documentée mais pas encore exécutée — cette étape requiert une coordination hors-ligne avec la clé de descellement.

---

## La règle de décision

Quand vous avez besoin d'une nouvelle identité non-humaine sur la plateforme, le choix suit cette hiérarchie :

| Situation | Type d'identité |
|---|---|
| Un pod doit appeler l'API k8s ou Vault | `ServiceAccount` Kubernetes |
| Un pipeline CI doit pousser vers un registre | Compte robot (stocké dans Vault immédiatement) |
| Service externe sans notion de SA | Compte technique avec identifiants dans Vault |
| Application délègue le login à Authentik | Identifiant client OAuth2 (fournisseur OIDC) |
| API SaaS tierce (Cloudflare, AWS) | Clé d'API dans Vault `secret/platform/<service>` |
| Urgence humaine quand le SSO est HS | Compte break-glass, redésactivé après usage |

La hiérarchie reflète l'auto-rotation : utilisez l'option la plus automatisée disponible. Les SA Kubernetes tournent automatiquement. Les identifiants client OAuth2 tournent à la réémission Authentik. Les clés d'API et les comptes robots sont manuels — Vault est l'atténuation.

---

## Ce qui casse quand vous en perdez la trace

Trois incidents de l'historique opérationnel de minicloud, correspondant chacun à un type d'identité différent :

**Compte robot — Harbor `robot$ci` (2026-08-16) :**
Base Harbor effacée et reconstruite après une panne de PVC Longhorn. `robot$ci` a été recréé avec le même nom mais un nouveau token. Les secrets d'org GitHub détenaient toujours l'ancien token. Les pushes d'images CI ont commencé à échouer en 401. Correctif : recréer le compte robot, mettre à jour les secrets GitHub, stocker le nouveau token dans Vault. Délai de résolution : découvert lors d'un audit de routine des apps ArgoCD Degraded. **Leçon : toujours stocker les tokens robots dans Vault immédiatement après création. Ne jamais se fier au seul secret de CI.**

**Compte break-glass — admin ArgoCD (en cours jusqu'à aujourd'hui) :**
Le mot de passe admin ArgoCD n'existait que sur le système du contrôleur. Si le NVMe du X390 tombait, le seul chemin vers ArgoCD pendant une panne d'Authentik serait de régénérer le hash bcrypt directement dans argocd-cm. C'est une procédure de 20 minutes pendant ce qui est déjà un incident. **Leçon : les identifiants break-glass ont leur place dans Vault, pas dans des fichiers locaux.**

**ESO SecretSyncedError — silencieux pendant 5 jours (2026-08-11 au 2026-08-16) :**
L'ExternalSecret `harbor-stable-secrets` a échoué après la suppression d'une clé Vault pendant l'effacement de la base Harbor. L'ESO a journalisé `SecretSyncedError` mais les pods ont continué de tourner — le Secret k8s avait déjà des données valides en cache de la dernière synchronisation réussie. La panne était invisible jusqu'à un audit. **Leçon : la santé de l'ESO n'est pas visible depuis la santé des pods. Surveillez les `.status.conditions` de l'ExternalSecret séparément, pas seulement le statut des pods.**

---

## Inventaire complet des identités

Pour référence, le décompte complet des identités minicloud au 2026-08-16 :

| Type | Nombre | Auto-tourné | Tous dans Vault |
|---|---|---|---|
| Comptes de service Kubernetes | 9 | Oui (JWT kubelet) | S.O. |
| Comptes robots / techniques | 3 | Non — manuel | Oui (depuis cette session) |
| Comptes break-glass | 4 | Non | Oui (depuis cette session) |
| Identifiants client OAuth2 | 9 | Non | Partiellement |
| Clés d'API externes | 6 | Non | Oui |
| Tokens root / ops Vault | 2 | Non | S.O. (racine de confiance) |
| **Total** | **33** | — | — |

L'objectif pour une plateforme à ce niveau de maturité : chaque identité non-humaine qui ne peut pas s'auto-tourner devrait avoir son identifiant dans Vault, avec l'ESO qui le tire dans le cluster à l'exécution. Les seules exceptions sont le token root de Vault lui-même (il doit être stocké hors de Vault) et le kubeconfig break-glass k8s (il doit être stocké hors du cluster).
