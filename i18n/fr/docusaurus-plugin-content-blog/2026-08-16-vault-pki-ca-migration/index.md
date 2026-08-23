---
slug: vault-pki-ca-migration
title: "Déplacer la clé privée de votre CA Kubernetes dans Vault PKI — sans changer un seul certificat"
authors: [andrelair]
tags: [kubernetes, security, vault, cert-manager, pki, tls, gitops, k3s, argocd, secrets-management]
date: 2026-08-16
description: "Comment nous avons migré la clé privée de la root CA minicloud d'un secret Kubernetes en clair vers le moteur PKI de HashiCorp Vault — en important la même CA pour qu'aucun certificat n'ait à être réémis, qu'aucun magasin de confiance n'ait à être mis à jour, et qu'aucun service ne subisse la moindre interruption."
---

Chaque cluster Kubernetes qui utilise cert-manager pour le TLS porte en lui le même risque silencieux : la clé privée de la CA qui signe tous vos certificats internes se trouve dans un secret Kubernetes, stocké en clair dans le datastore de votre cluster.

Sur les clusters managés avec chiffrement etcd au repos, ce risque est correctement atténué. Sur k3s avec kine et SQLite — comme tournent beaucoup de clusters bare-metal — la table des secrets est en clair. Quiconque peut lire `state.db` depuis le nœud du plan de contrôle peut extraire la clé privée de votre CA et forger des certificats que tout votre cluster fait confiance.

Cet article couvre comment nous avons migré la clé privée de la root CA minicloud dans le moteur de secrets PKI de HashiCorp Vault, avec le même certificat de CA pour que rien d'autre n'ait à changer — aucune reconfiance, aucune interruption, aucun changement sur nos 43 ressources Certificate.

{/* truncate */}

## Le problème

Quand cert-manager amorce un ClusterIssuer basé sur une CA, il attend le certificat de la CA et la clé privée sous forme de secret Kubernetes :

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  ca:
    secretName: minicloud-root-ca   # ← la clé privée de la CA vit ici
```

Le secret dans `cert-manager/minicloud-root-ca` contenait trois champs : `ca.crt`, `tls.crt` (identique au cert de la CA) et `tls.key` — la clé privée EC P-256 de 227 octets qui signe chaque certificat TLS du cluster.

Sur k3s, ce secret vit dans une base SQLite sur le nœud du plan de contrôle :

```
/var/lib/rancher/k3s/server/db/state.db
```

Les bases SQLite ne sont pas chiffrées. La couche kine que k3s utilise pour émuler etcd stocke les objets Kubernetes sous forme de lignes dans une table `kine`. La valeur du secret est encodée en base64, pas chiffrée. Quiconque a un accès en lecture à ce fichier — ne serait-ce qu'un `cat` depuis un processus privilégié — peut extraire la clé de la CA :

```bash
# Ce qu'un attaquant avec accès au disque peut faire :
sqlite3 state.db "SELECT value FROM kine WHERE name LIKE '%minicloud-root-ca%'"
# → JSON de Secret Kubernetes encodé en base64, dont tls.key
```

Avec la clé privée de la CA, il peut émettre un certificat pour n'importe quel nom d'hôte que votre cluster fait confiance, le signer avec la root CA minicloud, et votre navigateur, curl et chaque connexion service-à-service l'accepteront sans broncher.

Le certificat de la CA lui-même est public — il est distribué partout, reconnu dans le trousseau macOS, intégré aux images de conteneurs. C'est très bien. La clé privée, non.

---

## Pourquoi ne pas simplement activer le chiffrement au repos de k3s ?

k3s supporte l'`EncryptionConfiguration` de Kubernetes pour chiffrer les secrets dans le datastore SQLite. C'est une atténuation valable. Mais elle déplace le problème plutôt que de le résoudre : la clé de chiffrement (une clé KMS ou un fichier de clé local) devient le matériel sensible, et elle doit toujours vivre quelque part.

Vault PKI résout un problème différent et plus difficile. La clé privée de la CA **ne quitte jamais Vault**. cert-manager ne reçoit pas la clé. Il soumet une demande de signature de certificat (CSR), Vault la signe et ne renvoie que le certificat. Le matériel de clé est accédé par l'opération de signature, pas transféré.

La surface d'exposition devient : quiconque peut s'authentifier auprès de Vault avec un token valide et la politique `cert-manager`. C'est un ensemble bien plus petit et plus auditable que « quiconque peut lire le fichier SQLite ».

---

## Architecture après migration

```
contrôleur cert-manager
        │
        │ 1. crée une CSR
        ▼
Auth Kubernetes de Vault
        │
        │ 2. token SA → token Vault 1h
        ▼
Moteur PKI Vault (pki/)
        │
        │ 3. signe la CSR avec la clé de la CA (la clé ne quitte jamais Vault)
        │ 4. renvoie le certificat signé
        ▼
contrôleur cert-manager
        │
        │ 5. stocke le cert dans un Secret k8s
        ▼
Ingress (Traefik) → TLS terminé avec ce cert
```

Le pod cert-manager s'authentifie auprès de Vault avec son propre token de compte de service Kubernetes. Le backend d'auth Kubernetes de Vault valide le token contre le serveur d'API du cluster, puis émet un token Vault de courte durée (1h) limité à la politique `cert-manager`. Cette politique n'autorise que `pki/sign/cert-manager` et `pki/issue/cert-manager` — rien d'autre.

---

## La stratégie de migration : importer, pas remplacer

Le choix de conception essentiel : **importer la CA existante dans Vault PKI plutôt qu'en générer une nouvelle**.

Générer une nouvelle CA signifierait :
- Distribuer le nouveau certificat de CA à chaque appareil et système qui fait confiance à l'ancien (trousseau macOS, images de conteneurs, rôles Ansible, config de registre k3s, des dizaines de services qui embarquent le bundle de CA)
- Réémettre les 43 certificats existants pour qu'ils chaînent à la nouvelle CA
- Une fenêtre où les anciens certs (toujours de confiance pour l'ancienne CA) et les nouveaux certs (de confiance uniquement pour la nouvelle CA) coexistent

Importer la CA existante signifie :
- Même certificat de CA, même empreinte
- Tous les certs existants restent valides — ils ont été signés par cette CA et continuent de l'être
- Aucun changement de magasin de confiance nulle part
- La transition est invisible pour chaque client TLS

Vault supporte l'import de CA via `POST /v1/pki/config/ca` avec un bundle PEM contenant à la fois le certificat et la clé privée. La clé est stockée en interne ; le cert devient le certificat émetteur pour toutes les opérations de signature ultérieures.

---

## Les étapes de la migration

### 1. Activer et configurer le moteur PKI

```bash
# Activer PKI au chemin par défaut
curl -X POST https://vault.internal/v1/sys/mounts/pki \
  -H "X-Vault-Token: $TOKEN" \
  -d '{"type": "pki"}'

# Ajuster le TTL max de lease pour correspondre à la validité de la CA (10 ans)
curl -X POST https://vault.internal/v1/sys/mounts/pki/tune \
  -H "X-Vault-Token: $TOKEN" \
  -d '{"max_lease_ttl": "87600h"}'

# Configurer les URL de CRL et de certificat émetteur
curl -X POST https://vault.internal/v1/pki/config/urls \
  -H "X-Vault-Token: $TOKEN" \
  -d '{
    "issuing_certificates": "https://vault.internal/v1/pki/ca",
    "crl_distribution_points": "https://vault.internal/v1/pki/crl"
  }'
```

### 2. Extraire la CA existante et l'importer

Le cert et la clé de la CA vivent dans le secret `cert-manager/minicloud-root-ca` :

```bash
# Extraire du secret k8s
CRT=$(kubectl get secret minicloud-root-ca -n cert-manager \
  -o jsonpath='{.data.tls\.crt}' | base64 -d)
KEY=$(kubectl get secret minicloud-root-ca -n cert-manager \
  -o jsonpath='{.data.tls\.key}' | base64 -d)

# Importer le bundle — cert d'abord, puis clé
BUNDLE="${CRT}${KEY}"
curl -X POST https://vault.internal/v1/pki/config/ca \
  -H "X-Vault-Token: $TOKEN" \
  -d "{\"pem_bundle\": \"$BUNDLE\"}"
```

Avant de continuer, vérifiez que l'empreinte de la CA importée correspond à ce qui se trouve dans l'endpoint PKI de Vault :

```bash
# Empreinte du cert de la CA dans Vault
curl -sk https://vault.internal/v1/pki/ca/pem \
  | openssl x509 -noout -fingerprint -sha256

# Doit correspondre à l'empreinte du cert de la CA de confiance partout
openssl x509 -in minicloud-ca.crt -noout -fingerprint -sha256
```

Si celles-ci ne correspondent pas exactement, arrêtez. Quelque chose a mal tourné dans l'import.

### 3. Créer le rôle PKI

Le rôle contrôle ce que cert-manager est autorisé à demander. Nous le restreignons uniquement aux domaines que nous utilisons réellement :

```bash
curl -X POST https://vault.internal/v1/pki/roles/cert-manager \
  -H "X-Vault-Token: $TOKEN" \
  -d '{
    "allowed_domains": ["10.0.0.200.nip.io", "devandre.sbs"],
    "allow_subdomains": true,
    "allow_bare_domains": false,
    "allow_wildcard_certificates": false,
    "max_ttl": "8760h",
    "ttl": "2160h",
    "key_type": "ec",
    "key_bits": 256,
    "generate_lease": false
  }'
```

`allow_wildcard_certificates: false` est délibéré. cert-manager demande toujours des SAN spécifiques, pas des wildcards. Désactiver les wildcards réduit le rayon d'impact si le token Vault était un jour compromis.

### 4. Créer la politique Vault et le rôle d'auth Kubernetes

```bash
# Politique : cert-manager peut seulement signer/émettre des certs via le rôle cert-manager
vault policy write cert-manager - <<EOF
path "pki/sign/cert-manager"  { capabilities = ["create", "update"] }
path "pki/issue/cert-manager" { capabilities = ["create", "update"] }
EOF

# Rôle d'auth Kubernetes : SA cert-manager → politique cert-manager
curl -X POST https://vault.internal/v1/auth/kubernetes/role/cert-manager \
  -H "X-Vault-Token: $TOKEN" \
  -d '{
    "bound_service_account_names": ["cert-manager"],
    "bound_service_account_namespaces": ["cert-manager"],
    "policies": ["cert-manager"],
    "ttl": "1h"
  }'
```

### 5. Mettre à jour le ClusterIssuer sur place

C'est la clé d'une migration sans interruption : nous remplaçons la spec du ClusterIssuer `minicloud-ca` **sur place**, en gardant le même nom. Les 43 ressources Certificate référencent `issuerRef.name: minicloud-ca` — aucune d'elles n'a besoin de changer.

```yaml
# Avant
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  ca:
    secretName: minicloud-root-ca

---
# Après
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: minicloud-ca
spec:
  vault:
    server: https://vault.10.0.0.200.nip.io   # URL interne — contourne Cloudflare Access
    path: pki/sign/cert-manager
    caBundle: <minicloud-ca.crt encodé en base64>
    auth:
      kubernetes:
        mountPath: /v1/auth/kubernetes
        role: cert-manager
        serviceAccountRef:
          name: cert-manager
```

Le champ `caBundle` indique à cert-manager comment vérifier le propre certificat TLS de Vault. Comme le cert de Vault a lui-même été émis par `minicloud-ca`, nous fournissons le même cert de CA. Cela évite une situation d'œuf et de poule : cert-manager peut vérifier le cert de Vault avec le bundle de CA embarqué dans le ClusterIssuer, sans avoir besoin d'appeler d'abord un autre émetteur.

### 6. GitOps : une app ArgoCD dédiée aux ClusterIssuers

Avant cette migration, les ClusterIssuers étaient appliqués via `kubectl` et non suivis dans GitOps. Nous les avons déplacés dans une application ArgoCD dédiée :

```
minicloud-gitops/
  manifests/cert-manager-config/
    00-clusterissuer-selfsigned.yaml   # selfsigned-bootstrap
    01-clusterissuer-vault.yaml        # minicloud-ca (adossé à Vault)
  apps/platform/
    cert-manager-config.yaml           # Application ArgoCD, sync wave -1
```

Le sync wave `-1` importe. cert-manager lui-même tourne au wave `-2`. Les ClusterIssuers au wave `-1` sont créés après que cert-manager est prêt mais avant qu'une autre application ne tente de demander un certificat (wave `0` et au-delà). Sans cet ordre, la première synchronisation d'un nouveau cluster échouerait car les ressources Certificate seraient soumises avant l'existence de leur émetteur.

Un changement de plus requis : `ClusterIssuer` est une ressource à portée cluster et doit être explicitement listée dans le `clusterResourceWhitelist` de l'AppProject :

```yaml
clusterResourceWhitelist:
  - group: "cert-manager.io"
    kind: ClusterIssuer
```

Facile à oublier. Sans cela, ArgoCD signale « resource cert-manager.io:ClusterIssuer is not permitted in project » et la synchronisation échoue.

---

## Pièges rencontrés

### Cloudflare bloque les appels d'API vers l'URL publique de Vault

Notre instance Vault est accessible publiquement à `vault.devandre.sbs` via Cloudflare Tunnel. Cloudflare Access le protège par une authentification basée sur le navigateur. Quand notre script Python de configuration a tenté d'appeler l'API Vault à cette URL, il a reçu un HTTP 403 avec `error code: 1010` — Cloudflare bloquant un client non-navigateur.

Le correctif est de toujours utiliser l'URL interne (`vault.10.0.0.200.nip.io`) pour les appels d'API provenant du contrôleur ou de l'intérieur du cluster. Les pods cert-manager tournent dans le cluster et joignent Vault via le réseau interne, c'est pourquoi le ClusterIssuer utilise `server: https://vault.10.0.0.200.nip.io`.

**Règle :** si vous scriptez des appels d'API Vault depuis autre chose qu'un navigateur, utilisez l'URL interne.

### Supprimer le secret déclenche une régénération immédiate

Une fois la migration terminée, nous avons supprimé `cert-manager/minicloud-root-ca` pour retirer la clé en clair du cluster. cert-manager l'a immédiatement régénérée.

La raison : il restait un objet `Certificate` dans le namespace `cert-manager` nommé `minicloud-root-ca`, référençant le ClusterIssuer `selfsigned-bootstrap`. C'était le certificat d'amorçage qui avait initialement créé le secret de la CA. Avec l'objet Certificate présent, cert-manager considère le secret comme géré — quand il est supprimé, cert-manager le réémet (avec une clé fraîchement générée, pas l'originale).

La séquence correcte est :
1. Supprimer d'abord l'objet `Certificate`
2. Puis supprimer le secret

```bash
kubectl delete certificate minicloud-root-ca -n cert-manager
kubectl delete secret minicloud-root-ca -n cert-manager
```

Après l'étape 1, cert-manager ne gère plus le secret. Après l'étape 2, il a disparu et rien ne le recrée.

### Le whitelist de l'AppProject doit être dans git avant la synchronisation de l'app

Nous avons patché l'AppProject directement avec `kubectl patch` pour ajouter `ClusterIssuer` au whitelist, puis créé l'app ArgoCD `cert-manager-config`. L'app a commencé à se synchroniser — et a rencontré des erreurs « resource not permitted ».

La raison : l'app ArgoCD `argocd-project` gère l'AppProject depuis git (branche `main`). À son cycle de réconciliation suivant (toutes les quelques minutes), elle a écrasé notre `kubectl patch` avec la version git, qui n'incluait pas encore `ClusterIssuer` dans le whitelist. Notre app cert-manager-config était bloquée dans une boucle de réessais.

Le correctif : fusionner d'abord le changement d'AppProject dans `main`, laisser `argocd-project` se synchroniser, puis créer ou recréer l'app `cert-manager-config`. Dans un système GitOps, l'état git gagne toujours — les changements directs via l'API sont réconciliés et effacés.

---

## Vérification

Une fois le ClusterIssuer basculé vers Vault, nous avons forcé le renouvellement d'un certificat pour confirmer le flux de bout en bout :

```bash
# Forcer le renouvellement en supprimant le secret TLS
kubectl delete secret homer-tls -n homer

# cert-manager demande immédiatement un nouveau cert à Vault
kubectl wait --for=condition=Ready certificate/homer-tls -n homer --timeout=30s

# Vérifier que le nouveau cert chaîne à la même root CA
kubectl get secret homer-tls -n homer \
  -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | openssl verify -CAfile minicloud-ca.crt /dev/stdin
# → /dev/stdin: OK

# Vérifier l'émetteur et l'expiration
kubectl get secret homer-tls -n homer \
  -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | openssl x509 -noout -issuer -enddate
# issuer=CN=minicloud Internal Root CA
# notAfter=Nov 13 21:54:14 2026 GMT
```

Le nouveau certificat a été émis en moins de 2 secondes. L'émetteur est inchangé. La chaîne vérifie contre la même root CA minicloud déjà de confiance dans le trousseau macOS.

Nous avons ensuite exécuté le même contrôle `openssl verify` sur les 43 secrets TLS du cluster. Chacun a renvoyé `OK`.

---

## La posture de sécurité avant et après

| | Avant | Après |
|---|---|---|
| Emplacement de la clé privée de la CA | Secret k8s `cert-manager/minicloud-root-ca` | Stockage interne du moteur PKI Vault |
| Chiffrement du datastore | Aucun (kine/SQLite en clair) | Backend de stockage propre de Vault |
| Méthode d'exposition de la clé | Tout processus avec accès lecture SQLite | Journal d'audit Vault uniquement — clé jamais exportée |
| Authentification cert-manager | Aucune (lecture directe du secret via RBAC) | JWT de SA Kubernetes → token Vault 1h limité |
| Qui peut forger un cert | Quiconque lit `state.db` | Quiconque a un token de politique `cert-manager` valide |
| Rayon d'impact d'une escalade RBAC | Compromission complète de la clé de la CA | Émission de token seulement (aucune exposition de clé) |

La différence entre « quiconque lit le fichier SQLite » et « quiconque a un token Vault limité à signer uniquement » est toute la distance entre la prolifération non maîtrisée de secrets et la gestion des secrets.

---

## Ce qui reste identique

Le certificat public de la CA (`minicloud-ca.crt`) est inchangé. Il est toujours de confiance dans le trousseau macOS. Il est toujours distribué aux images de conteneurs via le rôle Ansible. Il est toujours embarqué dans la configuration de registre k3s. Rien de tout cela n'a à bouger.

Chaque certificat TLS existant — les 43 secrets actuellement dans le cluster — reste valide. Ils ont été émis par la clé de la CA que Vault détient désormais. À leur prochain cycle de renouvellement (cert-manager renouvelle 30 jours avant expiration par défaut), ils seront réémis par Vault sans accroc. Les services ne voient jamais d'interruption de validité de certificat.

La seule chose qui a changé, c'est l'endroit où vit la clé privée et qui peut y toucher.

---

## Une chose de plus : Vault est aussi protégé par son propre cert

Il y a ici une dépendance circulaire subtile qui mérite d'être nommée. Le propre certificat TLS de Vault (`vault/vault-tls`) a été émis par cert-manager via le ClusterIssuer `minicloud-ca`. Après la migration, cert-manager émet le cert de Vault en appelant Vault. Vault signe un cert pour lui-même via cert-manager.

Ce n'est pas un problème en pratique. Le cert existant est valide 90 jours avec une fenêtre de renouvellement de 30 jours. Le renouvellement se produit bien avant l'expiration. cert-manager se connecte à Vault avec le cert actuel (toujours valide) pour demander le cert suivant. La transition est fluide.

Mais cela implique : si le cert de Vault expire avant que cert-manager puisse le renouveler, cert-manager ne peut plus joindre Vault, et tout l'émetteur est cassé. La solution est de garder une durée généreuse pour le cert de Vault (90 jours) et de surveiller l'expiration des certs avec de l'alerting — ce que la PrometheusRule existante pour cert-manager gère déjà.

---

## Résumé

Déplacer une clé privée de CA d'un secret Kubernetes vers Vault PKI est une opération sans interruption si vous importez la CA existante plutôt que d'en générer une nouvelle. L'empreinte reste la même. Les certificats restent valides. Les magasins de confiance restent intacts. Le seul changement visible pour quoi que ce soit hors de Vault est que cert-manager demande désormais les certificats différemment — et que la clé privée n'est plus lisible par quiconque peut accéder au datastore du cluster.

La migration a pris une session. Le cluster a tourné en continu tout du long. Quarante-trois certificats vérifiés propres après le basculement. La clé privée de la CA n'existe plus nulle part où une lecture de fichier pourrait la trouver.
