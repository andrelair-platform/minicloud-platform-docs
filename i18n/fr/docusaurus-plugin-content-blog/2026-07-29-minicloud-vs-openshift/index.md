---
slug: minicloud-vs-openshift-self-hosted
title: "Kubernetes auto-hébergé : ce que j'ai construit vs ce que livre OpenShift"
authors: [andre]
description: >
  Une comparaison couche par couche entre minicloud — un cluster k3s de 5 nœuds assemblé à partir de composants CNCF —
  et OpenShift Container Platform (OCP) auto-hébergé. Mêmes problèmes, approches différentes : nœuds immuables,
  gestion du plan de contrôle, posture de sécurité, mises à jour, et ce que chaque modèle vous enseigne.
tags: [kubernetes, k3s, openshift, okd, platform-engineering, devops, cncf, security, gitops, bare-metal]
date: 2026-07-29
image: /img/docusaurus-social-card.jpg
---

OpenShift Container Platform est une distribution Kubernetes d'entreprise avec des choix affirmés. Mon cluster minicloud est une pile k3s de 5 nœuds assemblée composant par composant à partir de projets CNCF. Après avoir traversé la construction complète — GitOps, observabilité, secrets, registre, OIDC, ingress, réplication de stockage, tests de chaos, correctifs de sécurité, mises à jour — je peux dire avec une certaine précision quelle est réellement la différence.

Ce n'est pas qu'OpenShift en fait plus. C'est qu'OpenShift a déjà fait chaque choix que vous auriez à faire vous-même, a empaqueté ces choix en une unité versionnée, testée et supportée, et les a imposés au niveau de l'architecture. Que ce soit un avantage ou une contrainte dépend entièrement de ce que vous cherchez à faire.

{/* truncate */}

## Le décor

**minicloud** est un cluster k3s v1.36.2 de 5 nœuds sur Ubuntu 22.04 bare-metal :

| Nœud | IP | Rôle |
|------|----|------|
| `set-hog` | 10.0.0.2 | plan de contrôle k3s (ThinkPad X390) |
| `fast-skunk` | 10.0.0.4 | worker |
| `fast-heron` | 10.0.0.7 | worker |
| `star-kitten` | 10.0.0.8 | worker |
| `swift-mac` | 10.0.0.10 | worker (MacBook Pro 2012, Ubuntu 22.04, stockage Longhorn) |

Chaque composant a été choisi, configuré et déployé à la main : ArgoCD pour le GitOps, Harbor pour les images, Authentik pour l'OIDC, Longhorn pour le stockage bloc, NGINX + MetalLB pour l'ingress, Vault + ESO pour les secrets, Gatekeeper pour les politiques, Falco pour la sécurité à l'exécution, kube-prometheus-stack pour l'observabilité.

**OpenShift OCP** auto-hébergé tourne sur bare-metal ou VM. Empreinte de production minimale : trois masters (16 Go de RAM, 120 Go de disque chacun) plus deux workers. L'OS du plan de contrôle est RHEL CoreOS (RHCOS), une image immuable gérée par le cluster lui-même. Les workers peuvent être RHCOS ou RHEL 9.

---

## La réalité matérielle

Avant de comparer les fonctionnalités, l'écart d'empreinte minimale est réel :

| | minicloud (k3s) | OpenShift OCP |
|---|---|---|
| Nœuds de plan de contrôle | 1 (ThinkPad X390) | 3 masters minimum |
| RAM par nœud de plan de contrôle | ~8 Go | 16 Go minimum |
| RAM totale minimale du cluster | ~20 Go sur 5 nœuds | ~64 Go sur 5 nœuds |
| Temps d'installation | binaire k3s : 5 minutes | installeur OpenShift IPI : 45–90 minutes |
| Disque minimal par plan de contrôle | ~256 Go NVMe | 120 Go minimum (etcd est sensible aux I/O) |
| Coût de licence | Open source (MIT) | Abonnement Red Hat (~10k$+/an par cluster) |

k3s tourne sur un ThinkPad. OpenShift ne peut pas. Ce n'est pas une critique d'OpenShift — il embarque une plateforme d'entreprise complète, et cette plateforme a de vraies exigences de ressources. Mais cela signifie que les deux outils résolvent des problèmes différents à des échelles différentes.

L'alternative communautaire est **OKD**, l'amont gratuit d'OpenShift utilisant Fedora CoreOS au lieu de RHCOS. Même architecture, mêmes opérateurs, pas d'abonnement Red Hat. OKD est ce qu'il faut utiliser pour évaluer le modèle d'OpenShift sans le coût de licence.

---

## Couche 1 : l'OS des nœuds — Ubuntu vs RHCOS

Vos nœuds tournent sous Ubuntu 22.04. Vous gérez les correctifs OS via `unattended-upgrades`, les redémarrages noyau via kured, et la configuration des nœuds via Ansible. La configuration peut dériver silencieusement. Un fichier édité à la main sur `fast-heron` peut différer de `star-kitten` sans trace nulle part.

Les nœuds de plan de contrôle et de worker OpenShift tournent sous **RHEL CoreOS** — un OS immuable. Il n'y a pas de gestionnaire de paquets à appeler. La configuration est entièrement gérée par le **Machine Config Operator (MCO)** :

```yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  name: 99-worker-sysctl-inotify
spec:
  config:
    storage:
      files:
        - path: /etc/sysctl.d/99-inotify.conf
          contents:
            source: "data:,fs.inotify.max_user_watches%3D524288"
```

Appliquez ce MachineConfig, et MCO draine les nœuds cibles, applique le changement via `rpm-ostree`, redémarre et uncordon. Pas de playbooks Ansible. Pas de SSH. Pas de dérive. Le nœud ne peut pas avoir une configuration qui diffère de son MachineConfig — c'est la contrainte que l'architecture impose.

**Ce que cela signifie concrètement :** ma pile Ansible + kured + kube-bench couvre le même terrain que MCO (configuration des nœuds, posture CIS, séquencement des redémarrages après correctifs). La différence est que MCO impose la convergence architecturalement ; mon Ansible requiert que quelqu'un se souvienne de lancer le playbook.

---

## Couche 2 : le plan de contrôle — Kine/SQLite vs etcd + CVO

minicloud exécute un plan de contrôle mononœud (`set-hog`) avec l'adaptateur Kine de k3s remplaçant etcd par SQLite. C'est un compromis délibéré : point unique de défaillance pour le serveur d'API, fenêtre de reprise de 90 secondes en cas de panne matérielle, contrôle administratif total du datastore. Deux mécanismes de sauvegarde indépendants (CronJob k8s + timer systemd du contrôleur) couvrent le chemin de reprise.

OpenShift requiert trois masters avec un vrai cluster etcd à trois nœuds. Perdez un master, le serveur d'API continue d'ordonnancer. Le cluster etcd est entièrement géré par l'**etcd Operator**, lui-même géré par le **Cluster Version Operator (CVO)**.

CVO est la partie d'OpenShift sans équivalent dans l'écosystème k3s. Il gère chaque composant du plan de contrôle — serveur d'API, controller-manager, scheduler, etcd, routeur ingress, pile de supervision, registre d'images — comme un ensemble d'opérateurs versionnés. Quand vous lancez :

```bash
oc adm upgrade --to-latest=true
```

CVO :
1. Valide que la charge de la nouvelle version est sûre à appliquer depuis la version actuelle
2. Met à jour les opérateurs du plan de contrôle dans un ordre de dépendance défini
3. Déclenche MCO pour mettre à jour RHCOS sur chaque nœud de plan de contrôle (drain → `rpm-ostree` → redémarrage → uncordon)
4. Met à jour tous les opérateurs embarqués (supervision, logs, routeur) dans la bonne séquence
5. Valide chaque étape avant de passer à la suivante
6. Peut se mettre en pause et reprendre en plein milieu d'une mise à jour

Mon équivalent est system-upgrade-controller (SUC) pour le binaire k3s + GitHub Actions pour la détection de release + Renovate pour les bumps de charts Helm déclenchés par le changement de version. CVO gère toute la plateforme comme une unité versionnée. Ma pile gère le binaire k3s puis traite chaque autre composant séparément. CVO sait que cert-manager version N est compatible avec OCP 4.17 parce que Red Hat a testé cette combinaison. Mes vérifications de compatibilité sont manuelles.

---

## Couche 3 : sécurité — Gatekeeper + Falco vs SCC + SELinux + RHACS

C'est là que l'écart est le plus significatif.

### Security Context Constraints vs Pod Security Admission

Kubernetes livre Pod Security Admission (PSA) avec trois niveaux intégrés : `privileged`, `baseline`, `restricted`. Ils s'appliquent au niveau namespace, sont tout-ou-rien dans un niveau, et ne peuvent pas être personnalisés.

OpenShift livre les **Security Context Constraints (SCC)** comme un remplacement plus granulaire qui précède PSA et reste le mécanisme d'application principal. Les SCC sont attachées aux comptes de service :

```yaml
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: restricted-v2
allowPrivilegedContainer: false
allowHostDirVolumePlugin: false
runAsUser:
  type: MustRunAsRange      # impose le non-root avec une plage d'UID dynamique par namespace
seLinuxContext:
  type: MustRunAs           # étiquetage SELinux obligatoire sur chaque conteneur
fsGroup:
  type: MustRunAs
seccompProfiles:
  - runtime/default
```

La différence essentielle avec PSA : `MustRunAsRange` assigne un UID depuis une plage spécifique au namespace. Si deux namespaces utilisent tous deux la SCC `restricted-v2`, leurs pods obtiennent des UID différents. Un processus compromis qui s'échappe de son conteneur ne peut pas écrire de fichiers appartenant aux pods d'un autre namespace. PSA ne peut pas exprimer cela — il autorise soit le non-root (aucun UID spécifique), soit refuse le root (tout UID non-nul).

Mon équivalent est Gatekeeper/OPA avec des politiques rego personnalisées. Je peux m'approcher du comportement des SCC, mais j'ai écrit chaque contrainte manuellement. Les SCC sont intégrées et appliquées par défaut sur chaque pod de chaque namespace sans aucune configuration de webhook d'admission.

### SELinux vs AppArmor

Chaque nœud RHCOS exécute SELinux en mode enforcing. Les processus des pods reçoivent des étiquettes SELinux obligatoires. L'accès au système de fichiers est contrôlé au niveau noyau par ces étiquettes — un processus ne peut pas lire un fichier sauf si son étiquette le permet, quelles que soient les permissions Unix. Vous ne pouvez pas désactiver SELinux sur un nœud RHCOS sans MCO.

Les nœuds Ubuntu (minicloud) utilisent AppArmor par défaut. AppArmor est basé sur des profils : vous définissez ce à quoi un processus peut accéder, et tout ce qui n'est pas dans le profil est refusé. C'est efficace, mais c'est en opt-in par workload et cela ne fournit pas l'isolation inter-processus que donnent les étiquettes obligatoires de SELinux.

### RHACS vs Falco + Harbor Trivy + Gatekeeper

Red Hat Advanced Cluster Security (RHACS, à l'origine StackRox) est une plateforme complète de sécurité de conteneurs disponible via OperatorHub. Elle couvre :

- Scan de vulnérabilités des images de conteneurs (similaire à Harbor Trivy)
- Détection de menaces à l'exécution (similaire à Falco)
- Application de la segmentation réseau avec topologie réseau visuelle
- Reporting de conformité contre CIS, NIST, PCI-DSS, SOC2 d'emblée
- Notation de risque par déploiement basée sur les CVE, le comportement à l'exécution et l'exposition réseau

Ma pile fait le même travail avec quatre outils séparés : Falco (exécution), Harbor Trivy (scan d'images), Gatekeeper (politiques), kube-bench (conformité). Chacun est configuré et maintenu séparément. RHACS intègre tout cela dans un seul opérateur avec une UI unifiée.

---

## Couche 4 : réseau — Flannel + MetalLB vs OVN-Kubernetes

minicloud utilise **Flannel** (défaut k3s, encapsulation VXLAN) pour le réseau des pods et **MetalLB** pour l'assignation d'IP LoadBalancer via annonce ARP L2. Ajouter le **contrôleur NGINX Ingress** en DaemonSet par-dessus donne le routage HTTP/HTTPS. Trois composants, chacun versionné et configuré indépendamment.

OpenShift livre **OVN-Kubernetes** comme CNI par défaut. OVN-Kubernetes est construit sur Open Virtual Network, qui fournit :

- Routage L3 distribué (chaque nœud gère son propre trafic est-ouest, pas de passerelle centralisée)
- Support du déchargement matériel (via SR-IOV ou SmartNIC sur les nœuds qui en ont)
- **AdminNetworkPolicy** — une politique réseau à portée cluster qui prime sur les NetworkPolicy à portée namespace. Les admins de la plateforme peuvent imposer une segmentation de base que les équipes tenantes ne peuvent pas surcharger.
- Assignation d'IP d'egress (IP sortante stable par namespace ou sélecteur de pod pour l'allowlisting pare-feu)

**Routes vs Ingress :** OpenShift a une ressource compatible `Ingress` mais livre aussi `Route` — une CRD de première classe qui précède la spec Ingress et porte plus de surface de configuration :

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: my-service
spec:
  host: my-service.apps.cluster.example.com
  to:
    kind: Service
    name: my-service
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

Le routeur basé sur HAProxy est un composant central géré par CVO, pas un chart Helm. Le DNS wildcard (`*.apps.cluster.example.com`) pointe vers la VIP du routeur. Chaque Route obtient automatiquement un nom d'hôte sous ce wildcard. Mon équivalent est cert-manager (TLS) + DaemonSet NGINX (routage) + MetalLB (VIP) + des enregistrements DNS explicites par service — quatre composants séparés là où OCP en a un.

---

## Couche 5 : l'expérience développeur

### Opérateurs vs charts Helm

minicloud déploie tout via des charts Helm gérés par ArgoCD. Chaque chart est une dépendance versionnée indépendante. Renovate ouvre des PR quand de nouvelles versions de charts sortent.

Le mécanisme de livraison principal d'OpenShift est les **Opérateurs** depuis **OperatorHub** — une place de marché organisée d'opérateurs certifiés et testés. Un Opérateur est un contrôleur qui gère une application spécifique avec des CRD natives Kubernetes. Installer Prometheus sur OpenShift :

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: prometheus
  namespace: openshift-monitoring
spec:
  channel: stable
  installPlanApproval: Automatic
  name: prometheus
  source: redhat-operators
```

L'**Operator Lifecycle Manager (OLM)** gère l'installation, la résolution des dépendances et les mises à jour. Un Opérateur qui déclare une dépendance à cert-manager fera qu'OLM installe cert-manager automatiquement. Helm n'a pas de résolution de dépendances — vous installez la dépendance manuellement et espérez que la version est compatible.

Le compromis : les Opérateurs sont plus puissants mais moins portables. Un chart Helm tourne partout où Helm tourne. Une souscription OLM ne fonctionne que sur un cluster avec OLM installé (OpenShift, ou OLM installé séparément sur du Kubernetes vanille).

### La console

k3s n'a pas de console web intégrée. Ma surface de plateforme est ArgoCD (GitOps), Grafana (métriques/logs/traces), Harbor (images), Backstage (IDP/catalogue), Homer (dashboard). Chacune a son propre flux d'authentification, même avec Authentik OIDC qui les fédère.

OpenShift livre une console web complète avec deux perspectives :

- **Administrateur** : ressources à l'échelle du cluster, statut des nœuds, gestion des opérateurs, flux d'événements, consommation de quotas, topologie réseau
- **Développeur** : vues à portée projet, graphes de topologie montrant les connexions de services, pipelines de build, suivi de logs intégré par pod

Les deux utilisent la même session OAuth OpenShift. Un seul login, visibilité complète sur tous les namespaces auxquels l'utilisateur a accès. La console est un composant géré par CVO — elle se met à jour avec le cluster et est toujours compatible avec la version en route.

Pour les équipes où tout le monde n'est pas platform engineer, cela compte. Sur minicloud, déboguer un pod en panne requiert de savoir aller sur ArgoCD pour le statut de synchronisation, Grafana pour les logs, kubectl pour les événements. Sur OpenShift, la console fait remonter tout cela dans une seule vue.

---

## Correspondance des composants

Assembler minicloud a signifié choisir et câbler indépendamment l'équivalent de chaque composant intégré d'OpenShift :

| Composant | minicloud | OpenShift OCP |
|---|---|---|
| GitOps | ArgoCD (Helm, auto-géré) | OpenShift GitOps = ArgoCD certifié |
| Pipelines CI/CD | GitHub Actions (externe) | OpenShift Pipelines = Tekton |
| Registre d'images | Harbor (Helm) | Registre intégré |
| Authentification | Authentik OIDC (Helm) | Serveur OAuth intégré |
| Ingress | NGINX + MetalLB (Helm) | Routeur HAProxy (géré par CVO) |
| TLS | cert-manager (Helm) | cert-manager (OperatorHub) |
| Stockage | Longhorn (Helm) | OpenShift Data Foundation = Rook/Ceph |
| Supervision | kube-prometheus-stack (Helm) | cluster-monitoring-operator (géré par CVO) |
| Logs | Loki (Helm) | OpenShift Logging = Loki ou Elasticsearch |
| Traçage | Tempo (Helm) | OpenShift Distributed Tracing = Tempo/Jaeger |
| Secrets | Vault + ESO (Helm) | Vault (OperatorHub) ou Secrets Store CSI |
| Application de politiques | Gatekeeper/OPA (Helm) | SCC intégrées + Gatekeeper optionnel |
| Sécurité à l'exécution | Falco (Helm) | RHACS (Red Hat Advanced Cluster Security) |
| Scan d'images | Harbor Trivy | RHACS ou scan de registre intégré |
| Mises à jour de nœuds | system-upgrade-controller + GH Actions | Cluster Version Operator (CVO) |
| Configuration des nœuds | Ansible | Machine Config Operator |
| Durcissement CIS | kube-bench + Ansible (manuel post-maj) | CIS L2 intégré, SELinux imposé |
| Service mesh | non déployé | OpenShift Service Mesh = Istio + Kiali |
| Console développeur | Backstage + Homer + Grafana | Console web OpenShift complète |
| Mises à jour de dépendances | Renovate (auto-hébergé) | Renovate — pas une fonctionnalité OCP, pareil des deux côtés |

Le motif notable : les outils de la colonne de gauche sont les mêmes projets CNCF amont qu'OpenShift empaquette dans la colonne de droite. ArgoCD est ArgoCD. cert-manager est cert-manager. Tempo est Tempo. OpenShift ajoute les tests, les garanties de compatibilité, les contrats de support et la livraison via OLM. Il ne remplace pas la technologie sous-jacente.

---

## Ce qu'OpenShift vous donne et que vous ne pouvez pas facilement répliquer

**Immuabilité des nœuds :** MCO + RHCOS rend la dérive des nœuds impossible par architecture. Mon approche Ansible requiert de la discipline — une session SSH sur `fast-heron` à 2h du matin peut laisser le nœud durablement différent de son état voulu. RHCOS rejette cela.

**Coordination des mises à jour au niveau plateforme :** CVO traite tout le cluster comme un artefact versionné. Lors d'une mise à jour d'OCP 4.16 vers 4.17, CVO connaît le bon ordre de mise à jour de chaque composant parce que Red Hat a testé cette séquence exacte. Mon approche SUC + Renovate met à jour k3s puis chaque chart Helm indépendamment — la compatibilité entre versions est mon problème.

**Conformité CIS Niveau 2 d'emblée :** OCP passe CIS L2 à l'installation. Mon cluster a besoin de kube-bench pour vérifier, et le faire passer requiert du travail Ansible post-installation. Après une mise à jour k3s, je relance kube-bench car la mise à jour du binaire peut réintroduire des findings.

**Chemin de support entreprise :** un cluster OCP en panne a un ticket de support Red Hat avec un niveau de service. Un cluster k3s en panne a Stack Overflow et les issues GitHub de k3s.

**OpenShift Local (CRC) :** Red Hat livre une installation OCP mono-VM pour le développement local. Si vous avez besoin de fonctionnalités spécifiques à OpenShift (SCC, Routes, OperatorHub) en développement, CRC vous y amène sans construire un cluster multi-nœuds.

---

## Ce que minicloud a et qu'OpenShift ne peut pas vous donner

**Flexibilité matérielle :** OCP ne peut pas tourner sur un ThinkPad. k3s si. Toute la plateforme minicloud tourne sur du matériel que vous pourriez acheter dans un atelier de réparation de laptops pour moins de 1 000 € au total.

**Choix des composants :** la pile de supervision intégrée d'OCP (cluster-monitoring-operator) ne peut pas être remplacée. C'est ainsi qu'OCP se supervise lui-même. Mon Prometheus peut être remplacé par VictoriaMetrics, reconfiguré ou étendu sans que CVO ne me combatte.

**Coût à petite échelle :** open source plus coûts d'électricité contre un abonnement Red Hat. Pour un cluster de portfolio ou une petite équipe, le modèle d'abonnement n'a aucune justification.

**Profondeur d'apprentissage :** construire un cluster à partir de primitives CNCF force la compréhension à chaque couche. Un ingénieur OpenShift qui n'a jamais construit un cluster de zéro ne sait souvent pas pourquoi cert-manager existe, quel problème MetalLB résout, ou comment fonctionne l'élection de leader etcd. La plateforme le cache. Construire minicloud signifie savoir exactement ce que fait chaque composant parce qu'il a fallu le faire fonctionner.

**Vélocité amont :** k3s suit typiquement l'amont Kubernetes en quelques jours après une release. OCP livre les nouvelles versions Kubernetes avec un délai de 4 mois pendant que Red Hat termine les tests d'intégration. minicloud tournait sous k3s v1.36.2 alors que de nombreux clusters OCP étaient encore sur 1.31.

---

## La conclusion qui compte vraiment

En construisant minicloud composant par composant, j'ai assemblé l'équivalent fonctionnel d'OpenShift avec les mêmes projets CNCF amont qu'OpenShift empaquette. GitOps, observabilité, gestion des secrets, registre d'images, OIDC, application de politiques, sécurité à l'exécution, déploiements canary, tests de chaos, sauvegarde et PRA — tout présent sur les deux plateformes.

La proposition de valeur d'OpenShift, c'est tout ce qui entoure ces composants :
- Red Hat les a tous testés ensemble à une matrice de versions spécifique
- CVO automatise le séquencement des mises à jour sur toute la plateforme comme une unité
- MCO impose l'immuabilité des nœuds pour que la dérive de configuration soit architecturalement impossible
- Les SCC et SELinux fournissent un modèle de sécurité plus fort que ce que PSA + AppArmor peuvent livrer
- OperatorHub vous donne une place de marché de composants organisée et certifiée avec la résolution de dépendances OLM
- Le contrat de support vous donne un appel à passer quand le cluster est à terre à 3h du matin

Ce qu'aucune plateforme ne gère pour vous : le patch des CVE des images de conteneurs et les mises à jour des charts Helm/OLM applicatifs. Renovate tourne à l'identique sur k3s et OCP. Cette couche est toujours la vôtre.

Le choix ne porte pas sur quelle plateforme est techniquement supérieure. Il porte sur ce pour quoi vous optimisez. Une entreprise réglementée avec une équipe plateforme de 100 personnes et une exigence de conformité optimise pour les garanties qu'OpenShift fournit. Un platform engineer construisant un cluster de portfolio, apprenant toute la pile, ou exploitant un environnement de production contraint en coûts, optimise pour tout ce qui fait de minicloud la bonne réponse.

Les deux sont valides. Savoir quel modèle convient à quel contexte — et pourquoi — est la véritable compétence.
