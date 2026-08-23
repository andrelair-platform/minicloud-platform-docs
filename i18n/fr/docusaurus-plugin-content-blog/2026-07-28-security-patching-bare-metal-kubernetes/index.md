---
slug: security-patching-bare-metal-kubernetes
title: "Le patch de sécurité d'un cluster Kubernetes auto-géré — cinq couches, zéro magie"
authors: [andre]
description: >
  Sur un fournisseur Kubernetes managé, le patch de sécurité est largement invisible. Sur un cluster
  k3s auto-géré, vous possédez chaque couche : correctifs du noyau OS, CVE du binaire k3s, images de base
  de conteneurs, versions de charts Helm, et dérive de posture CIS. Cet article documente toute la pile
  de patching sur minicloud — ce qui tourne automatiquement, ce qui requiert une PR, et comment chaque
  couche se compare à EKS, GKE et AKS.
tags: [kubernetes, k3s, security, patching, cve, renovate, kured, cis, bare-metal, platform-engineering, eks, gke, aks, devops]
date: 2026-07-28
image: /img/docusaurus-social-card.jpg
---

Les fournisseurs Kubernetes managés font paraître le patch de sécurité simple. Vous activez l'auto-mise à jour sur GKE, vous cliquez « mettre à jour le groupe de nœuds » sur EKS, et la CVE disparaît. Ce qui se passe réellement, c'est que le fournisseur patche l'image OS, remplace le nœud, valide le binaire, et restaure vos workloads — le tout dans le temps qu'il faut pour rafraîchir la console AWS.

Sur un cluster auto-géré, rien de cela n'est automatique. Vous possédez l'OS. Vous possédez le runtime. Vous possédez les images de base. Vous possédez les versions de charts Helm. Et quand une CVE tombe, vous possédez la décision sur la couche où elle vit et le mécanisme qui la fermera.

Cet article documente les cinq couches de patching sur **minicloud** — un cluster k3s de 5 nœuds sur des ThinkPads bare-metal — ce qui est automatisé, ce qui requiert une PR, et où étaient les manques et comment ils ont été comblés.

{/* truncate */}

## La surface de patching

Les correctifs de sécurité sur un cluster Kubernetes ne forment pas une file unique. Ils vivent à travers cinq couches indépendantes, chacune avec une chaîne d'outils, une cadence et un mode de défaillance différents si ignorée.

| Couche | Ce qu'elle couvre | Pire cas si ignorée |
|---|---|---|
| Paquets OS | glibc, OpenSSL, CVE noyau | Compromission au niveau nœud via un noyau non patché |
| Binaire k3s | k3s, containerd, runc, plugins CNI | Évasion de conteneur, escalade de privilèges |
| Images de base de conteneurs | `FROM golang:1.25`, `FROM node:22-alpine`, etc. | Runtime vulnérable dans chaque pod |
| Versions de charts Helm | Mises à jour de charts d'applications avec correctifs CVE | Vulnérabilités au niveau workload (p. ex. bypass d'auth Grafana) |
| Posture CIS | Config kubelet, RBAC, politique d'audit | Une mauvaise configuration du cluster dérive après les mises à jour |

Chaque couche requiert son propre outil et son propre déclencheur. Il n'y a pas de bouton unique « tout patcher » sur bare-metal.

---

## Couche 1 — Paquets OS : `unattended-upgrades` + kured

Les cinq nœuds tournent sous **Ubuntu 22.04**. Les correctifs de sécurité au niveau OS (glibc, OpenSSL, curl, CVE noyau) arrivent via `apt` depuis le pocket de sécurité Ubuntu.

### Téléchargement automatique des correctifs

`unattended-upgrades` est configuré sur chaque nœud pour appliquer automatiquement les mises à jour du pocket de sécurité :

```ini
# /etc/apt/apt.conf.d/50unattended-upgrades
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::Automatic-Reboot "false";   // kured gère les redémarrages
Unattended-Upgrade::Remove-Unused-Dependencies "true";
```

`Automatic-Reboot "false"` est intentionnel — redémarrer un nœud Kubernetes en pleine journée sans le drainer d'abord évincerait les pods de façon non-gracieuse. À la place, `unattended-upgrades` écrit `/var/run/reboot-required` quand un correctif noyau ou libc requiert un redémarrage. Ce fichier est le signal de relais vers kured.

### Séquencement automatisé des redémarrages noyau : kured

**kured** (Kubernetes Reboot Daemon) tourne en DaemonSet — un pod par nœud. Il surveille `/var/run/reboot-required` sur le système de fichiers hôte de chaque nœud et, quand il en trouve un, émet un drain natif Kubernetes suivi d'un redémarrage :

```
Le pod kured voit /var/run/reboot-required sur fast-heron
→ acquiert le verrou de redémarrage (un seul nœud redémarre à la fois)
→ kubectl cordon fast-heron
→ kubectl drain fast-heron (respecte les PDB — attend le rééquilibrage Longhorn)
→ nsenter → systemctl reboot
→ le nœud revient → kubelet se ré-enregistre → kured uncordon
→ libère le verrou → le nœud suivant peut continuer
```

Le cluster fait tourner kured depuis plus de trois semaines. Statut actuel :

```bash
kubectl get ds -n kured
# NAME    DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE
# kured   5         5         5       5            5
```

Un pod par nœud, y compris `set-hog` (plan de contrôle). Le drain respecte tous les PodDisruptionBudgets — le DaemonSet de Longhorn est `ignoreDaemonSets: true`, et les PDB d'applications imposent des nombres minimaux de répliques. Un correctif noyau qui atterrit sur `fast-heron` à 03:00 aura le nœud de retour en service avant le matin.

**La réserve swift-mac :** `swift-mac` est un MacBook Pro 2012. kured peut le drainer et le redémarrer via les mécanismes normaux de Kubernetes. Si le MacBook se fige pendant le processus de boot (comportement du SMC d'Apple), kured ne peut pas le power-cycler — une intervention physique est requise. C'est un manque connu accepté pour ce matériel.

**Ce que font les fournisseurs managés à la place :** les nœuds workers cloud sont des VM. Le patch de l'OS signifie remplacer la VM par une nouvelle construite à partir d'une AMI patchée (EKS) ou d'une nouvelle image de nœud (GKE, AKS). Il n'y a pas de patch noyau sur place ni de redémarrage — le nœud est terminé et un nouveau rejoint. Le problème du « nœud sale » disparaît. kured est inutile.

---

## Couche 2 — Binaire k3s : system-upgrade-controller + GitHub Actions hebdomadaire

k3s regroupe containerd, runc et les plugins CNI dans un binaire unique. Une CVE dans l'un de ces composants (y compris le serveur d'API k3s lui-même) se corrige en mettant à jour k3s. La version du binaire porte aussi la version mineure Kubernetes — `v1.36.2+k3s1` signifie k3s 1 par-dessus Kubernetes 1.36.2.

### Détection : workflow GitHub Actions hebdomadaire

Un workflow tourne chaque lundi à 08:00 UTC, récupère la dernière release k3s depuis l'API GitHub, et la compare à la version des Plans system-upgrade :

```yaml
- name: Get latest k3s release
  run: |
    LATEST=$(curl -sf \
      -H "Authorization: Bearer ${{ secrets.GITHUB_TOKEN }}" \
      "https://api.github.com/repos/k3s-io/k3s/releases/latest" \
      | jq -r '.tag_name')

- name: Get current version
  run: |
    CURRENT=$(grep -m1 '^ *version:' \
      manifests/system-upgrade/01-k3s-plans.yaml | awk '{print $2}')
```

Si les versions diffèrent, le workflow bumpe `version:` dans les deux Plans system-upgrade et ouvre une PR avec une checklist de pré-fusion en six points : notes de release, vérification de version containerd, revue des PDB, santé des répliques Longhorn, sauvegarde kine/SQLite.

### Application : Plans system-upgrade-controller

Fusionner la PR déclenche la synchronisation ArgoCD → system-upgrade-controller lit le nouveau Plan → les mises à jour s'exécutent :

1. Plan `k3s-server` : cordon `set-hog`, drain (avec `ignoreDaemonSets: true`, timeout 120s), échange du binaire, uncordon
2. L'étape `prepare` du Plan `k3s-agent` attend la fin du serveur
3. Les workers se mettent à jour un à la fois (`concurrency: 1`) — drain, échange, uncordon

Toute la séquence tourne sans surveillance. Surveillez avec :

```bash
ssh controller "kubectl get nodes -w && kubectl get jobs -n system-upgrade -w"
```

**Ce que font les fournisseurs managés à la place :** l'équivalent du binaire k3s sur EKS est l'AMI de nœud + la version du plan de contrôle Kubernetes. AWS patche le plan de contrôle silencieusement. Les AMI de nœuds sont mises à jour via le remplacement progressif du groupe de nœuds managé — nouvelle AMI, nouveau nœud, pas de mise à jour de binaire sur place. GKE fait de même via l'auto-mise à jour de pool de nœuds sur les canaux de release. Vous ne touchez jamais un binaire.

---

## Couche 3 — Images de base de conteneurs : Renovate + Harbor/Trivy

C'est la couche de patching la plus fréquemment négligée et celle qui affecte le plus de CVE en pratique. Chaque image personnalisée construite depuis `FROM ubuntu:22.04`, `FROM golang:1.25-alpine` ou `FROM node:22-alpine` hérite de la surface de CVE de cette image de base au moment du build. Quand `ubuntu:22.04` patche une vulnérabilité critique d'OpenSSL, chaque image bâtie dessus a besoin d'un rebuild.

### Ce qui manquait

Les six dépôts d'images (minicloud-backstage, minicloud-open-webui, minicloud-onlyoffice, minicloud-plane, platform-demo, ktayl-solution-web) n'avaient aucun mécanisme automatisé pour détecter quand leurs images de base avaient de nouvelles releases de sécurité. Une CVE dans `golang:1.25-alpine` resterait non patchée jusqu'à ce que quelqu'un le remarque.

### Le correctif : Renovate auto-hébergé sur tous les dépôts

**Renovate** est un outil de mise à jour de dépendances qui surveille les manifestes de paquets — Dockerfiles, `go.mod`, `package.json`, `targetRevision` de charts Helm, `targetRevision` d'Applications ArgoCD — et ouvre des PR quand de nouvelles versions sont disponibles.

Un unique workflow GitHub Actions dans `minicloud-gitops` exécute Renovate chaque lundi 06:00 UTC sur les sept dépôts de la plateforme :

```yaml
# .github/workflows/renovate.yml
name: Renovate
on:
  schedule:
    - cron: '0 6 * * 1'   # Lundi 06:00 UTC
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
        default: false
jobs:
  renovate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: renovatebot/github-action@v46.1.21
        with:
          configurationFile: .github/renovate-global.json
          token: ${{ secrets.GITOPS_TOKEN }}
        env:
          LOG_LEVEL: info
          RENOVATE_DRY_RUN: ${{ inputs.dry_run == true && 'full' || 'null' }}
```

La config globale liste les sept dépôts :

```json
{
  "repositories": [
    "andrelair-platform/minicloud-gitops",
    "andrelair-platform/minicloud-backstage",
    "andrelair-platform/minicloud-open-webui",
    "andrelair-platform/minicloud-onlyoffice",
    "andrelair-platform/minicloud-plane",
    "andrelair-platform/platform-demo",
    "andrelair-platform/ktayl-solution-web"
  ],
  "onboarding": false,
  "requireConfig": "optional"
}
```

Chaque dépôt a son propre `renovate.json` qui active les managers pertinents et groupe les mises à jour :

| Dépôt | Managers | Stratégie de groupement |
|---|---|---|
| `minicloud-gitops` | `argocd`, `helm-values` | Minor/patch groupés hebdomadairement ; major requiert approbation du dashboard |
| `minicloud-backstage` | `dockerfile`, `npm` | Paquets npm groupés ; version majeure Backstage = revue manuelle |
| `minicloud-open-webui` | `dockerfile` | Label `check-default-changes` — Open WebUI change les défauts d'env entre versions |
| `minicloud-onlyoffice` | `dockerfile` | Label `check-ca-cert` — le chemin d'injection CA change avec la version Node.js dans l'image |
| `platform-demo` | `dockerfile`, `gomod` | Modules Go groupés ; major golang = revue manuelle |
| `minicloud-plane` | `dockerfile`, `gomod` | Idem — vérification de compatibilité du client NATS sur major |
| `ktayl-solution-web` | `dockerfile`, `npm` | Astro + Tailwind groupés ; major Astro = revue manuelle |

Les images Harbor privées (`harbor.10.0.0.200.nip.io/library/*`) sont explicitement exclues — Renovate ne peut pas joindre le registre interne depuis les runners GitHub Actions.

### Scan Trivy de Harbor

Harbor exécute Trivy sur chaque image poussée. Le scan tourne au moment du push et les résultats sont visibles dans l'UI Harbor sous chaque tag d'image. Les images avec des CVE CRITICAL peuvent être signalées (et optionnellement bloquées au pull) via la politique de projet de Harbor.

```bash
# Vérifier le statut de scan actuel pour une image
/usr/bin/curl --cacert ~/minicloud-ca.crt \
  "https://harbor.10.0.0.200.nip.io/api/v2.0/projects/library/repositories/platform-demo/artifacts" \
  -u "admin:$(cat ~/.harbor-admin)" | python3 -m json.tool | grep -A3 '"scan"'
```

### La boucle de patching

Quand Renovate détecte que `golang:1.25-alpine` a une nouvelle version patch :
1. Il ouvre une PR dans `platform-demo` bumpant le Containerfile
2. La CI construit et pousse la nouvelle image vers Harbor
3. Trivy la scanne au moment du push
4. Si propre, la PR est revue et fusionnée
5. ArgoCD détecte le nouveau tag d'image dans gitops et déploie

De bout en bout : une CVE d'image de base obtient une PR ouverte dans la semaine suivant la release amont. Sans Renovate, elle attend qu'on vérifie manuellement.

**Ce que font les fournisseurs managés à la place :** les fournisseurs cloud patchent les images de base à la couche hyperviseur (nouvelle AMI = nouvel OS, nouveau containerd, nouveau noyau). Mais le `FROM golang:1.25-alpine` de votre Dockerfile applicatif reste votre responsabilité sur chaque plateforme Kubernetes — le scan d'images ECR, le scan Artifact Registry de GCR et le scan ACR fonctionnent exactement comme Harbor Trivy. Aucun fournisseur managé ne reconstruit automatiquement vos conteneurs applicatifs quand leurs images de base se mettent à jour. Renovate comble le même manque sur toute plateforme Kubernetes.

---

## Couche 4 — Versions de charts Helm : Renovate + ArgoCD

Les charts Helm portent leur propre surface de CVE. `kube-prometheus-stack 65.x` pourrait livrer une version de Grafana avec un bypass d'authentification connu. `cert-manager v1.14` pourrait avoir une vulnérabilité de webhook. Ce sont des CVE au niveau applicatif qui vivent dans le chart, pas dans l'OS ni le runtime.

### Ce que Renovate scanne dans minicloud-gitops

Le manager `argocd` lit chaque fichier `apps/*.yaml` et extrait `targetRevision` :

```yaml
# apps/cert-manager.yaml
spec:
  sources:
    - repoURL: https://charts.jetstack.io
      chart: cert-manager
      targetRevision: "v1.20.2"   # ← Renovate surveille ceci
```

Quand cert-manager sort `v1.20.3` avec un correctif CVE, Renovate ouvre une PR bumpant `targetRevision`. La PR déclenche la synchronisation ArgoCD après fusion. La mise à jour du chart se déploie avec le contrôleur cert-manager redémarrant sur la nouvelle version.

### Cas spéciaux requérant une revue manuelle

Certains charts obtiennent un `dependencyDashboardApproval: true` explicite quel que soit le type de mise à jour :

- **ArgoCD** — ArgoCD se mettant lui-même à jour a un risque inhabituel : une mise à jour ratée peut empêcher toute synchronisation ultérieure
- **Vault** — les changements de backend de secrets requièrent de tester la connectivité ESO + applications avant déploiement
- **Authentik** — les mises à jour SSO affectent tous les chemins d'authentification ; un mauvais déploiement déconnecte tous les utilisateurs

Les correctifs mineurs de ceux-ci sont tout de même remontés par Renovate, mais ils restent sur l'issue du Dependency Dashboard jusqu'à approbation explicite.

**Ce que font les fournisseurs managés à la place :** les add-ons managés (VPC CNI d'EKS, Cloud DNS de GKE, Azure CNI d'AKS) sont patchés par le fournisseur avec leur propre planning de release. Vos charts Helm applicatifs — ceux que vous possédez — requièrent le même motif Renovate + ArgoCD sur EKS/GKE/AKS que sur bare-metal. Cette couche n'est pas simplifiée par le choix d'un fournisseur managé.

---

## Couche 5 — Durcissement CIS : kube-bench + Ansible

Le CIS Kubernetes Benchmark définit les exigences de durcissement pour la configuration kubelet, le RBAC, les politiques d'audit et les réglages au niveau nœud. Le cluster minicloud passe **CIS k3s-1.7 à 16/16** sur tous les nœuds workers, appliqué via des playbooks Ansible.

Le problème du durcissement à un instant donné : il dérive. Une mise à jour k3s change les flags kubelet. Une exécution Ansible qui modifie la config containerd peut réinitialiser les réglages de durcissement. Après tout changement d'infrastructure, la posture CIS a besoin d'une revérification.

### Relancer kube-bench après les mises à jour

```bash
# Exécuter kube-bench comme Job sur chaque nœud
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-node.yaml

# Attendre et collecter les résultats
kubectl wait --for=condition=complete job/kube-bench --timeout=120s
kubectl logs -l app=kube-bench
```

Sortie attendue après une mise à jour k3s propre : les 16 vérifications PASS. Tout FAIL ou WARN est une exécution de remédiation Ansible.

### Ce que le durcissement CIS couvre réellement

- kubelet `--protect-kernel-defaults`, `--read-only-port 0`, `--anonymous-auth false`
- Configuration du runtime containerd (pas de `--allow-privileged` sans annotation explicite)
- RBAC : pas de bindings `cluster-admin` pour les comptes de service
- Politique d'audit : journal d'audit du serveur d'API activé avec verbosité minimale
- NetworkPolicies : default-deny-all dans les namespaces de production

**Ce que font les fournisseurs managés à la place :** EKS, GKE et AKS imposent les défauts CIS Niveau 1 par défaut. Les groupes de nœuds managés démarrent depuis des AMI/images durcies avec la plupart des flags kubelet pré-configurés. Vous pouvez demander le durcissement CIS Niveau 2 sur GKE via la config du pool de nœuds. Le coût opérationnel du durcissement CIS — le vérifier après chaque mise à jour — disparaît sur les clusters managés car l'image de base est toujours l'état de référence connu du fournisseur.

---

## La couche secrets et TLS

Pas strictement une couche de « patch », mais la rotation des secrets et le renouvellement des certs TLS sont des opérations de maintenance de sécurité qui suivent la même discipline.

**cert-manager** gère le renouvellement des certificats TLS automatiquement. Les certificats de Let's Encrypt (via ACME) et de la CA interne minicloud sont renouvelés avant expiration sans interaction humaine. Le cert de la root CA minicloud a 10 ans de validité — le renouvellement manuel est au calendrier pour 2034.

**Vault + ESO** gère les secrets applicatifs. La rotation des secrets est actuellement manuelle : mettre à jour le secret dans Vault, l'ESO récupère la nouvelle valeur via l'intervalle de sync `ExternalSecret`, les pods récupèrent la nouvelle variable d'env au prochain redémarrage (ou via Reloader si annoté). La rotation automatisée est un chantier futur.

**Les tokens OIDC Authentik** sont de courte durée (tokens d'accès : 5 minutes, tokens de rafraîchissement : 30 jours). Aucune rotation manuelle nécessaire — les clients OIDC gèrent le rafraîchissement de token automatiquement.

---

## La carte complète de l'automatisation du patching

```
Chaque nuit (02:30 UTC)
└── kine-backup.sh (timer systemd du contrôleur)
    └── Sauvegarde SQLite sûre avec WAL vers MinIO (filet de sécurité pré-patch)

Chaque nuit (unattended-upgrades)
└── pocket de sécurité apt → télécharge les correctifs sur tous les nœuds
    └── si noyau/libc → écrit /var/run/reboot-required
        └── kured détecte → drain → redémarrage → uncordon (un nœud à la fois)

Chaque lundi 06:00 UTC (workflow Renovate)
└── Scanne 7 dépôts pour :
    ├── versions d'images de base Dockerfile/Containerfile
    ├── versions de modules go.mod
    ├── versions npm package.json
    ├── targetRevision d'app ArgoCD (versions de charts Helm)
    └── tags d'images helm-values
    → Ouvre des PR groupées pour les mises à jour minor/patch
    → Signale les mises à jour major pour revue manuelle

Chaque lundi 08:00 UTC (workflow de mise à jour k3s)
└── Interroge l'API GitHub pour la dernière release k3s
    → Si plus récente que les Plans : ouvre une PR bumpant la version dans les deux Plans
    → Après fusion : ArgoCD synchronise → system-upgrade-controller met à jour les nœuds

Après chaque mise à jour k3s (manuel, ~5 minutes)
└── kubectl apply Job kube-bench
    └── Vérifier les 16/16 vérifications CIS PASS
    └── Exécuter la remédiation Ansible si un FAIL
```

---

## Côte à côte : bare-metal vs fournisseurs managés

| Couche de patching | minicloud (k3s bare-metal) | EKS | GKE | AKS |
|---|---|---|---|---|
| **Correctifs de sécurité OS** | `unattended-upgrades` télécharge ; kured draine + redémarre | Nouvelle AMI par mise à jour de groupe de nœuds ; pas de patch sur place | Nouvelle image de nœud par mise à jour de pool | Mise à jour d'image de nœud (commande séparée) |
| **Séquencement des redémarrages noyau** | DaemonSet kured — drain → redémarrage → uncordon | Remplacement de nœud ; pas de redémarrage | Remplacement de nœud ; pas de redémarrage | Remplacement de nœud ; pas de redémarrage |
| **Binaire k3s / runtime** | system-upgrade-controller + automatisation PR hebdomadaire | Plan de contrôle EKS patché silencieusement ; l'AMI de nœud inclut containerd | Nœuds GKE mis à jour via canal de release | Mise à jour de pool de nœuds AKS |
| **Images de base de conteneurs** | Renovate (hebdomadaire) ouvre une PR par dépôt | Scan ECR + déclenchement manuel de rebuild | Scan Artifact Registry + rebuild manuel | Scan ACR + rebuild manuel |
| **CVE de charts Helm** | Renovate ouvre une PR ; ArgoCD synchronise après fusion | Idem — vous possédez vos charts d'app | Idem | Idem |
| **Posture CIS** | kube-bench après chaque mise à jour ; remédiation Ansible | Le fournisseur impose les défauts CIS L1 ; AMI fraîche = état connu | CIS L1 par défaut ; images de nœuds durcies disponibles | CIS L1 par défaut |
| **Renouvellement de cert TLS** | cert-manager (automatique, zéro ops) | ACM + cert-manager ou terminaison TLS fournisseur | Certs managés ou cert-manager | Certs managés Azure ou cert-manager |
| **Rotation des secrets** | Vault + ESO (déclenchement de rotation manuel) | Auto-rotation AWS Secrets Manager | Rotation Secret Manager | Rotation Azure Key Vault |
| **Ce que vous possédez** | Les cinq couches + leurs chaînes d'outils | Images de conteneurs, charts d'app, secrets | Images de conteneurs, charts d'app, secrets | Images de conteneurs, charts d'app, secrets |

---

## Ce que les fournisseurs managés ne peuvent pas retirer de votre assiette

Il vaut la peine d'être précis sur ce que « managé » signifie réellement ici.

Les fournisseurs cloud retirent le patch de l'OS, le patch du binaire runtime et la maintenance de posture CIS de votre responsabilité. Ce sont de vraies réductions significatives de charge opérationnelle — surtout les couches OS et runtime, qui requièrent kured, system-upgrade-controller, Ansible et kube-bench sur bare-metal.

Ce qu'ils ne retirent pas :
- Les CVE d'images de base de conteneurs. `FROM golang:1.25-alpine` dans votre Dockerfile est votre responsabilité sur chaque plateforme Kubernetes. Renovate n'est ni une fonctionnalité EKS ni une fonctionnalité GKE — c'est un outil universel.
- Les versions de charts Helm applicatifs. Les charts que vous possédez ont besoin de bumps de version quand des CVE sont patchées. ArgoCD + Renovate fonctionne à l'identique sur EKS, GKE et AKS.
- La rotation des secrets. AWS Secrets Manager et GCP Secret Manager ont des API d'auto-rotation, mais configurer les politiques de rotation et mettre à jour les applications reste votre travail.
- La posture CIS de vos workloads. Le fournisseur durcit le nœud. Vos pods peuvent toujours tourner avec `privileged: true`, des permissions RBAC excessives, ou des montages hostPath. Gatekeeper/OPA et Polaris les imposent — et ils tournent pareil sur les clusters managés et auto-gérés.

La distinction compte car les ingénieurs qui passent de bare-metal à EKS présument parfois que tout le problème de patch de sécurité est résolu. Les couches 3 et 4 — images de conteneurs et charts Helm — restent exactement aussi manuelles qu'avant. Les deux outils qui les traitent, Renovate et Harbor/Trivy, sont agnostiques du cluster.

---

## Le coût honnête de chaque couche

| Couche | Temps de mise en place | Coût continu (par mois) | Économisé par le fournisseur managé |
|---|---|---|---|
| Téléchargement de correctifs OS | Nul (`unattended-upgrades` par défaut) | Nul | Oui |
| Redémarrage noyau (kured) | 30 minutes | Nul (DaemonSet, 50m de CPU demandé) | Oui |
| Automatisation de mise à jour k3s | 2 heures (Plans SUC + GH Actions) | Nul | Oui (absorbé dans la version k8s) |
| CVE d'images de conteneurs (Renovate) | 2 heures (config globale + 6 configs par dépôt) | Nul | **Non** |
| CVE de charts Helm (Renovate) | Inclus ci-dessus | Nul | **Non** |
| Durcissement CIS (kube-bench + Ansible) | 4 heures initiales ; 5 minutes post-mise à jour | Nul | Oui |

Les couches qui requièrent un vrai temps de mise en place sur bare-metal sont celles que les fournisseurs managés résolvent. Les couches qui restent votre responsabilité — images de conteneurs et charts Helm — coûtent les mêmes deux heures de configuration Renovate sur n'importe quelle plateforme.

Le savoir rend la proposition de valeur du fournisseur managé précise plutôt que vague. Vous payez 73 $/mois pour un plan de contrôle EKS pour éliminer les couches OS/runtime/CIS. L'histoire du patch des images de conteneurs et des charts est identique des deux côtés de cet achat.

---

## La conclusion qui compte vraiment

Les fournisseurs managés — EKS, GKE, AKS — éliminent les **couches 1, 2 et 5** : patch de l'OS, binaire runtime Kubernetes, et maintenance de posture CIS. Ce sont de vraies économies. kured, system-upgrade-controller et kube-bench existent sur bare-metal précisément parce qu'aucun fournisseur n'absorbe ce travail.

Ils ne touchent pas les **couches 3 et 4** : CVE d'images de base de conteneurs et CVE de charts Helm applicatifs. Une vulnérabilité critique dans `golang:1.25-alpine` est votre problème que vous tourniez sur un ThinkPad ou sur un cluster EKS à 500 $/mois. `FROM ubuntu:22.04` dans votre Dockerfile hérite des CVE sur n'importe quelle plateforme. Renovate traite les deux, et il tourne à l'identique sur bare-metal et sur EKS.

C'est la partie oubliée dans le conseil « utilise juste un fournisseur managé ». Les couches qui semblent les plus pénibles sur bare-metal — celles qui impliquent de redémarrer des nœuds, d'échanger des binaires et de relancer des benchmarks CIS — sont exactement celles que les fournisseurs managés gèrent. La couche qui est discrètement la plus dangereuse — un conteneur applicatif bâti sur une image de base vieille de six mois avec 40 CVE non patchées — est également votre responsabilité partout.
