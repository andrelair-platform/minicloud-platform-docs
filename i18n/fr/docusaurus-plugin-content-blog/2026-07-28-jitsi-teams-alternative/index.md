---
slug: jitsi-self-hosted-teams-alternative
title: "Adieu Microsoft Teams : exploiter sa propre visioconférence avec Jitsi Meet sur Kubernetes"
authors: [andre]
description: >
  Un plongeon en profondeur dans l'auto-hébergement de Jitsi Meet comme remplacement complet de Microsoft
  Teams — architecture, internes WebRTC, déploiement Kubernetes, SSO Authentik, et résolution du problème
  CGNAT DS-Lite de la 5G SFR avec un chemin média IPv6 direct. Tout ce qu'il faut pour le comprendre et le construire vous-même.
tags: [jitsi, webrtc, kubernetes, self-hosted, video-conferencing, teams-alternative, ipv6, turn, coturn, authentik, sso, platform-engineering]
date: 2026-07-28
image: /img/blog/jitsi/jitsi-architecture.svg
---

import useBaseUrl from '@docusaurus/useBaseUrl';

Microsoft Teams coûte de l'argent. Il envoie vos données de réunion vers des serveurs que vous ne contrôlez pas. Il requiert des comptes dans un tenant Microsoft. Et si les licences changent, votre visioconférence disparaît du jour au lendemain.

Jitsi Meet ne coûte rien, tourne sur du matériel que vous possédez, garde vos données à l'intérieur de votre réseau, et fonctionne avec n'importe quel navigateur — aucune installation d'application requise.

Voici l'histoire de comment je l'ai déployé sur un cluster Kubernetes bare-metal, résolu un problème réseau épineux avec des utilisateurs mobiles SFR 5G, et l'ai câblé à un système SSO à l'échelle de l'entreprise. À la fin de cet article, vous comprendrez comment les appels vidéo WebRTC fonctionnent réellement, et aurez une carte claire pour déployer Jitsi vous-même.

{/* truncate */}

## Qu'est-ce que Jitsi Meet ?

Jitsi Meet est une plateforme de visioconférence entièrement open-source. Vous ouvrez un navigateur, tapez un nom de salle, et démarrez un appel. Aucun compte requis pour les participants, aucune application à installer, aucune licence par siège.

Sous le capot, il utilise **WebRTC** — le même standard que Google Meet, le client navigateur de Zoom et la vidéo de Discord utilisent tous. La différence est qu'avec Jitsi, vous exploitez les serveurs vous-même.

La plateforme est maintenue par 8x8 (l'entreprise qui a racheté le projet Jitsi à Atlassian), mais le code est 100 % open source sous licence Apache 2.0.

### Pourquoi ne pas simplement utiliser Teams ou Zoom ?

| | Microsoft Teams | Zoom | Jitsi (auto-hébergé) |
|--|--|--|--|
| **Coût** | 4–12,50 €/utilisateur/mois | 139 €/an/hôte | Gratuit |
| **Emplacement des données** | Centres de données Microsoft | Centres de données Zoom | Vos serveurs |
| **Support navigateur** | Chrome, Edge (Firefox limité) | Tous les navigateurs | Tous les navigateurs |
| **Compte requis** | Oui (compte Microsoft) | Oui pour les hôtes | Non |
| **Rejoindre sans app** | Limité | Oui | Oui |
| **Personnalisation** | Palier entreprise | Palier entreprise | Gratuit |
| **Accès API** | Oui (Graph API) | Oui | Oui |
| **Intégration SSO** | Azure AD | SAML/OIDC (payant) | Tout fournisseur OIDC |
| **On-premise** | Teams Rooms uniquement | Non | Pile complète |

Le compromis est clair : vous échangez de l'argent et le verrouillage fournisseur contre la responsabilité opérationnelle d'exploiter l'infrastructure.

---

## Comment fonctionne Jitsi : les quatre composants principaux

Jitsi n'est pas une application unique — ce sont quatre services qui travaillent ensemble. Comprendre ce que fait chacun est la clé pour le déployer et le dépanner avec confiance.

<div style={{textAlign: 'center', margin: '2rem 0'}}>
  <img
    src={useBaseUrl('/img/blog/jitsi/jitsi-architecture.svg')}
    alt="Schéma d'architecture complète du système Jitsi Meet"
    style={{maxWidth: '100%', borderRadius: '8px'}}
  />
  <div style={{color: '#8b949e', fontSize: '0.9rem', marginTop: '0.5rem'}}>
    Architecture complète : pile Jitsi, relais TURN, SSO et les trois chemins média
  </div>
</div>

### 1. Jitsi Web — le frontend

C'est l'application web que vous voyez en ouvrant `meet.devandre.sbs`. C'est une application React/JavaScript qui :
- Sert l'UI de réunion
- Charge la configuration (à quel serveur XMPP se connecter, quels serveurs TURN utiliser)
- Utilise les API WebRTC du navigateur pour capturer votre caméra et votre micro

Ce sont entièrement des fichiers statiques. Aucune logique backend — il cède simplement le contrôle au moteur WebRTC du navigateur une fois chargé.

### 2. Prosody — le serveur de signalisation

Prosody est un serveur XMPP. XMPP est un protocole de chat (le même sur lequel WhatsApp a été construit à l'origine), et Jitsi le réutilise pour la **signalisation** — les messages qui coordonnent l'établissement de l'appel avant qu'aucune vidéo ne circule.

Quand vous rejoignez une salle, votre navigateur se connecte à Prosody via un WebSocket et envoie des messages comme :
- « Je veux rejoindre la salle `myroom` »
- « Voici mes candidats ICE (mes adresses réseau) »
- « Voici mon offre SDP (les codecs audio/vidéo que je supporte) »

Prosody transfère ces messages aux autres participants et à Jicofo.

### 3. Jicofo — l'orchestrateur de conférence

Jicofo signifie **Jitsi Conference Focus**. C'est le cerveau de l'opération :
- Crée la conférence quand la première personne rejoint
- Dit à JVB d'allouer un nouvel endpoint pour chaque participant
- Envoie à chaque participant l'offre/réponse SDP avec les adresses réseau de JVB
- Gère le cycle de vie des participants (rejoindre, quitter, couper le micro)

Voyez Jicofo comme le gestionnaire de salle de réunion : il réserve la salle, distribue les badges (candidats ICE), et s'assure que tout le monde sait où s'asseoir.

### 4. JVB — le pont vidéo (le composant critique)

JVB signifie **Jitsi Video Bridge**. C'est par là que tout le trafic vidéo réel circule.

JVB est une **SFU — Selective Forwarding Unit**. Voici ce que cela signifie en clair :

> Dans un appel vidéo normal entre 3 personnes, chaque personne devrait téléverser sa vidéo aux 2 autres. Avec 10 personnes, cela fait 9 flux de téléversement chacun. Cela passe très mal à l'échelle.
>
> Une SFU se place au milieu. Chaque personne téléverse **un seul flux** vers la SFU. La SFU **transfère** ensuite les bons flux aux bonnes personnes. 3 personnes → 3 flux de téléversement au total, pas 6.

Point crucial, JVB **ne décode pas votre vidéo**. Il transfère des paquets chiffrés. Le contenu de votre vidéo ne quitte jamais le flux chiffré, même s'il passe par le serveur JVB.

---

## Comment un appel est réellement établi

Le processus de connexion semble compliqué, mais il suit une séquence claire. Voici ce qui se passe entre « cliquer Rejoindre » et « voir le visage de votre collègue » :

<div style={{textAlign: 'center', margin: '2rem 0'}}>
  <img
    src={useBaseUrl('/img/blog/jitsi/jitsi-call-flow.svg')}
    alt="Diagramme de séquence d'établissement d'appel Jitsi"
    style={{maxWidth: '100%', borderRadius: '8px'}}
  />
  <div style={{color: '#8b949e', fontSize: '0.9rem', marginTop: '0.5rem'}}>
    Étape par étape : du clic navigateur à la vidéo SRTP en direct
  </div>
</div>

### Étape 1 : authentification

Avant de voir quoi que ce soit, votre navigateur atteint l'ingress NGINX qui transfère la requête à Authentik. Si vous avez une session SSO valide, vous passez immédiatement. Sinon, vous êtes redirigé vers la page de login Authentik (nom d'utilisateur + code TOTP). Une fois authentifié, l'UI Jitsi Web se charge.

Cela signifie que **personne ne peut rejoindre une réunion sans un compte d'entreprise**. Le nom de la salle n'est pas un secret — la couche SSO est la barrière.

### Étape 2 : signalisation (XMPP)

Votre navigateur se connecte à Prosody via un WebSocket et envoie une requête « rejoindre la salle ». Prosody la passe à Jicofo, qui dit à JVB de créer un nouvel endpoint pour vous. JVB répond avec ses adresses réseau — ses **candidats ICE**.

### Étape 3 : ICE — trouver le meilleur chemin réseau

C'est l'étape que la plupart des gens ignorent. **ICE (Interactive Connectivity Establishment)** est le processus où votre navigateur et JVB négocient la meilleure façon de se joindre.

ICE fonctionne en faisant lister par les deux côtés toutes leurs adresses réseau (appelées **candidats**), puis en essayant chacune par ordre de priorité jusqu'à en trouver une qui fonctionne :

- **Candidats host** : adresses IP directes (IP LAN, IP Tailscale, adresses IPv6)
- **Candidats server-reflexive** : votre IP publique vue depuis un serveur STUN
- **Candidats relayed** : adresses sur un serveur relais TURN

Le navigateur les essaie toutes en parallèle. La première qui obtient une réponse de ping STUN réussie est sélectionnée.

### Étape 4 : DTLS + SRTP

Une fois qu'ICE sélectionne un chemin, le navigateur et JVB effectuent une **poignée de main DTLS** — essentiellement du TLS sur UDP. De cette poignée de main, les deux côtés dérivent des clés de chiffrement. À partir de là, tout l'audio et la vidéo sont chiffrés en **SRTP** (Secure Real-time Transport Protocol).

Le flux vidéo est chiffré de bout en bout au sens où il est toujours dans un paquet SRTP chiffré. JVB transfère ces paquets sans jamais avoir la clé de déchiffrement.

---

## Le déploiement : Jitsi sur Kubernetes

### Pourquoi Kubernetes ?

Exécuter Jitsi comme quatre services Docker Compose sur une seule VM fonctionne bien pour une petite équipe. Les raisons de passer à Kubernetes sont :

- **Redémarrages automatiques** si un composant plante
- **Limites de ressources** pour empêcher un service d'affamer les autres
- **GitOps** — chaque changement de configuration est un commit git, pas une édition manuelle sur un serveur
- **Gestion des secrets** via Vault + External Secrets Operator (pas de mots de passe dans git)
- **Observabilité** — scraping Prometheus, dashboards Grafana, logs Loki

La pile Jitsi dans cette configuration tourne dans un namespace `collab` dédié sur k3s.

### Le chart Helm et les valeurs

Le chart Helm `jitsi-contrib` maintenu par la communauté déploie les quatre composants avec un seul `helm install`. Les décisions de configuration clés :

```yaml
# helm-values/jitsi-values.yaml (simplifié)

publicURL: "https://meet.devandre.sbs"
tz: "Europe/Paris"

# Pas d'auth JWT par réunion — Authentik gère le contrôle d'accès
# au niveau HTTP avant que quiconque n'atteigne Jitsi
enableAuth: false
enableGuests: true

jvb:
  # JVB doit utiliser directement les interfaces réseau de l'hôte
  # pour pouvoir se lier aux vraies adresses IP et IPv6
  useHostNetwork: true

  # Épingler JVB au nœud avec la bonne config réseau
  nodeSelector:
    kubernetes.io/hostname: star-kitten

  # Annoncer l'IP LAN pour que les clients Tailscale/LAN puissent le joindre directement
  publicIPs:
    - "10.0.0.8"

  # Le port média — doit correspondre à la règle UFW et au pare-feu de la box SFR
  UDPPort: 10000

prosody:
  # Injecter la config TURN via ConfigMap + secret ESO
  extraEnvFrom:
    - configMapRef:
        name: jitsi-coturn-config    # TURN_HOST, TURN_PORT
    - secretRef:
        name: jitsi-coturn-secret    # TURN_CREDENTIALS (HMAC)
```

### La décision `hostNetwork: true` de JVB

C'est le choix de configuration le plus important. Par défaut, un pod Kubernetes obtient sa propre interface réseau virtuelle avec une IP de pod privée (`10.42.x.x`). C'est bien pour les services web, mais fatal pour un pont vidéo.

JVB doit envoyer des paquets UDP directement à l'IP de votre navigateur. Avec un réseau de pod, les paquets seraient source-NAT'és vers l'IP du nœud par `kube-proxy` — et JVB penserait que tous les clients viennent du nœud lui-même, détruisant ICE.

Avec `hostNetwork: true`, le pod JVB partage l'espace de noms réseau de l'hôte. Il se lie aux interfaces réelles de `star-kitten` : `10.0.0.8` (LAN), `100.x.x.x` (Tailscale), et toutes les adresses IPv6 assignées par le routeur SFR. Chaque interface devient un candidat ICE.

### Gestion des secrets

Aucun mot de passe n'est codé en dur. Tous les secrets circulent depuis Vault via l'External Secrets Operator :

```
Vault secret/platform/jitsi
  ├── jvb-auth-user          → Secret Kubernetes jitsi-jvb-secret
  ├── jvb-auth-password      →   (utilisé par prosody + jvb)
  ├── jicofo-auth-password   → Secret Kubernetes jitsi-jicofo-secret
  └── coturn-secret          → Secret Kubernetes jitsi-coturn-secret
                                 (clé HMAC pour les tokens d'auth TURN)
```

---

## L'intégration SSO : Authentik

Chaque app de cette plateforme est protégée par Authentik, un fournisseur d'identité open-source. Pour Jitsi, la configuration utilise le **forward-auth** à la couche ingress NGINX.

Voici comment ça marche :

1. Une requête arrive à `meet.devandre.sbs`
2. NGINX envoie une sous-requête à l'endpoint `/outpost.goauthentik.io/auth/nginx` d'Authentik
3. Authentik vérifie si la requête a un cookie de session valide
4. Si oui : NGINX transfère la requête à Jitsi Web, en injectant aussi le nom d'utilisateur comme `X-authentik-username`
5. Si non : NGINX renvoie une redirection 302 vers la page de login Authentik

Tout le flux d'authentification est géré avant qu'un seul composant Jitsi ne voie la requête. Jitsi lui-même ne connaît ni ne se soucie de l'authentification — l'ingress NGINX a déjà filtré les utilisateurs non authentifiés.

```
nginx.ingress.kubernetes.io/configuration-snippet: |
  auth_request     /outpost.goauthentik.io/auth/nginx;
  error_page       401 = @goauthentik_proxy_signin;
```

L'avantage : tout changement sur qui peut accéder à Jitsi (nouveaux utilisateurs, politiques MFA, restrictions de groupe) se fait dans Authentik, pas dans la configuration de Jitsi. Jitsi n'a pas besoin de connaître votre annuaire d'utilisateurs.

---

## Le serveur TURN : joindre les clients derrière un NAT

La plupart des réseaux domestiques et de bureau utilisent le NAT (Network Address Translation). Votre laptop a une IP privée comme `192.168.1.50`, mais internet le voit comme l'IP publique de votre routeur `37.65.x.x`. Cela crée un problème pour WebRTC : comment JVB envoie-t-il des paquets vidéo à `192.168.1.50` quand il ne connaît que l'IP publique ?

STUN aide dans la plupart des cas en découvrant l'IP et le port publics. Mais certains pare-feu et NAT d'opérateurs sont assez stricts pour que STUN ne fonctionne pas. C'est là que **TURN** intervient.

Un serveur TURN est un relais. Au lieu de se connecter directement à JVB, le client se connecte au serveur TURN et dit « relaie mes paquets vers JVB ». Le serveur TURN transfère tout dans les deux directions.

Dans cette configuration, Coturn tourne sur le contrôleur (le ThinkPad X390 qui exécute aussi MAAS et le NAT du cluster), exposé via port-forward sur le routeur domestique.

```
turn.devandre.sbs → 37.65.57.112 (IP publique) → NAT routeur → 192.168.1.130 (contrôleur)
```

Coturn utilise des **tokens HMAC limités dans le temps** pour l'authentification. Prosody génère un token frais quand vous rejoignez une réunion. Le token encode votre nom d'utilisateur et un horodatage d'expiration, signés avec un secret partagé. Même si quelqu'un intercepte le token, il cesse de fonctionner après 24 heures.

---

## Le problème SFR 5G — et la solution IPv6

C'est la partie la plus intéressante du déploiement, et le problème qui a pris le plus de temps à diagnostiquer.

### Le problème : DS-Lite bloque l'IPv4 entrant

SFR (un opérateur mobile français) utilise une technologie appelée **DS-Lite** sur son réseau 5G. Dans DS-Lite, votre téléphone obtient une vraie adresse IPv6 publique, mais son trafic IPv4 est tunnelisé à travers un NAT partagé de niveau opérateur (CGNAT) appelé AFTR.

La conséquence : **les connexions IPv4 entrantes vers votre téléphone sont bloquées au niveau de l'opérateur**. L'AFTR se place entre votre téléphone et internet, et il ne transfère pas les paquets entrants non sollicités.

Cela casse TURN. Les navigateurs WebRTC demandent toujours `REQUESTED-ADDRESS-FAMILY=IPv4` en allouant une adresse relais TURN. Le serveur TURN vous donne une adresse relais IPv4, mais quand JVB tente d'y envoyer le média, le paquet n'atteint jamais le téléphone — il est bloqué à l'AFTR.

<div style={{textAlign: 'center', margin: '2rem 0'}}>
  <img
    src={useBaseUrl('/img/blog/jitsi/jitsi-network-paths.svg')}
    alt="Diagramme des chemins média réseau de Jitsi"
    style={{maxWidth: '100%', borderRadius: '8px'}}
  />
  <div style={{color: '#8b949e', fontSize: '0.9rem', marginTop: '0.5rem'}}>
    Les trois chemins média : LAN/Tailscale, IPv6 direct (SFR 5G) et repli relais TURN
  </div>
</div>

### Le diagnostic

La négociation ICE du téléphone semblait fonctionner — les paquets STUN du téléphone arrivaient à l'interface réseau de `star-kitten`. `tcpdump` les capturait clairement. Mais JVB ne répondait jamais.

```bash
# tcpdump sur star-kitten — paquets visibles au niveau NIC :
# 21:17:32 2a0d:e487:22af:6804::1 > 2a02:8424:6ee0:be01:fa75:a4ff:fef9:2fe9: UDP 108
# 21:17:32 2a0d:e487:22af:6804::1 > 2a02:8424:6ee0:be01:fa75:a4ff:fef9:2fe9: UDP 108
# (zéro paquet sortant de JVB)
```

Le pare-feu était le coupable. L'UFW d'Ubuntu était configuré avec des règles IPv4 uniquement — `ufw allow 10000/udp` ajoute une règle iptables pour IPv4, mais l'équivalent IPv6 (ip6tables) était une chaîne vide avec politique DROP.

Les paquets arrivaient à la NIC. Le pare-feu les jetait avant qu'ils n'atteignent le socket de JVB.

### Le correctif

```bash
# Sur star-kitten — ceci ajoute les règles IPv4 ET IPv6 :
sudo ufw allow 10000/udp
# Crée :
#   iptables  -A ufw-user-input -p udp --dport 10000 -j ACCEPT
#   ip6tables -A ufw6-user-input -p udp --dport 10000 -j ACCEPT
```

Et sur le routeur domestique SFR (GR140IG), trois règles de pare-feu IPv6 pour autoriser le trafic entrant vers le cluster (Sécurité → Accès → Réseau v6) :

| Nom de la règle | Destination | Port | Protocole |
|--|--|--|--|
| `jvb-v6` | `2a02:8424:6ee0:be01:fa75:a4ff:fef9:2fe9` | 10000 | UDP |
| `coturn-turn-v6` | `2a02:8424:6ee0:be01:df85:1432:24b6:4494` | 3478 | TCP + UDP |
| `coturn-relay-v6` | idem | 49152–49199 | UDP |

Après le correctif, le résultat a été immédiat :

```
ICE state: Completed
Selected pair: [fa75:a4ff:fef9:2fe9]:10000/udp/host → [2a0d:e487:…]:57806/udp/prflx
DTLS 1.2 complete
```

Le téléphone s'est connecté en moins d'une seconde sans aucun relais TURN, utilisant un chemin IPv6 direct entre le réseau 5G et l'adresse IPv6 de `star-kitten` — contournant entièrement le CGNAT.

---

## Le faire vous-même : un guide pratique

Voici une procédure condensée pas à pas pour déployer Jitsi sur votre propre cluster Kubernetes.

### Prérequis

- Un cluster Kubernetes (k3s, EKS, GKE — peu importe)
- Un contrôleur NGINX Ingress
- cert-manager pour les certificats TLS
- Un nom de domaine avec contrôle DNS
- Un nœud où JVB tournera (a besoin d'une IP publique ou routable)

### Étape 1 — Ajouter le dépôt Helm

```bash
helm repo add jitsi-contrib https://jitsi-contrib.github.io/jitsi-helm/
helm repo update
```

### Étape 2 — Générer des mots de passe aléatoires

```bash
# Ceux-ci vont dans des Secrets Kubernetes ou Vault
JICOFO_PASSWORD=$(openssl rand -hex 32)
JVB_PASSWORD=$(openssl rand -hex 32)
TURN_SECRET=$(openssl rand -hex 32)
```

### Étape 3 — Créer le namespace et les secrets

```bash
kubectl create namespace jitsi

kubectl create secret generic jitsi-jicofo-secret -n jitsi \
  --from-literal=JICOFO_AUTH_PASSWORD=$JICOFO_PASSWORD

kubectl create secret generic jitsi-jvb-secret -n jitsi \
  --from-literal=JVB_AUTH_PASSWORD=$JVB_PASSWORD

kubectl create secret generic jitsi-turn-secret -n jitsi \
  --from-literal=TURN_CREDENTIALS=$TURN_SECRET
```

### Étape 4 — Écrire votre fichier de valeurs

```yaml
# values.yaml
publicURL: "https://meet.yourdomain.com"
tz: "Europe/Paris"

enableAuth: false
enableGuests: true

web:
  ingress:
    enabled: true
    ingressClassName: nginx
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
    hosts:
      - host: meet.yourdomain.com
        paths: [/]
    tls:
      - secretName: jitsi-tls
        hosts: [meet.yourdomain.com]

jvb:
  useHostNetwork: true          # Critique — ne sautez pas ceci
  nodeSelector:
    kubernetes.io/hostname: YOUR_NODE_NAME
  publicIPs:
    - "YOUR_NODE_PUBLIC_IP"
  UDPPort: 10000
  xmpp:
    existingSecretName: jitsi-jvb-secret

jicofo:
  xmpp:
    existingSecretName: jitsi-jicofo-secret

coturn:
  enabled: false    # Exécuter Coturn séparément pour plus de contrôle
```

### Étape 5 — Ouvrir le pare-feu

Sur le nœud où JVB tournera :

```bash
# Autoriser le trafic média WebRTC
sudo ufw allow 10000/udp

# Vérifier que les règles IPv4 et IPv6 ont été ajoutées :
sudo ufw status numbered
# Devrait montrer les règles 3 et 4 pour le port 10000/udp
```

Ouvrez aussi le UDP 10000 sur votre routeur/security group cloud pointant vers ce nœud.

### Étape 6 — Installer

```bash
helm install jitsi jitsi-contrib/jitsi-meet \
  -n jitsi \
  -f values.yaml
```

Vérifiez que tous les pods tournent :

```bash
kubectl get pods -n jitsi
# NAME                          READY   STATUS    RESTARTS
# jitsi-web-xxx                 1/1     Running   0
# jitsi-prosody-xxx             1/1     Running   0
# jitsi-jicofo-xxx              1/1     Running   0
# jitsi-jvb-xxx                 1/1     Running   0
```

### Étape 7 — Tester

Ouvrez `https://meet.yourdomain.com/test` dans deux navigateurs différents (ou navigateur + téléphone). Si la vidéo circule dans les deux directions, ICE a réussi.

Pour vérifier quel candidat ICE a été sélectionné, ouvrez la console développeur du navigateur et lancez :

```javascript
// Dans Chrome/Edge — montre la paire ICE sélectionnée
const pc = APP.conference._room.rtc._peerConnections.values().next().value.peerconnection;
const stats = await pc.getStats();
stats.forEach(s => { if(s.type === 'candidate-pair' && s.nominated) console.log(s); });
```

---

## Coturn : exploiter votre propre serveur TURN

Pour les utilisateurs qui ne peuvent pas se connecter directement (pare-feu d'entreprise stricts, certains réseaux mobiles), un serveur TURN est le repli.

Coturn est le serveur TURN open-source le plus déployé. Voici la configuration minimale :

```bash
# /etc/coturn/turnserver.conf

# L'IP sur laquelle Coturn écoute (l'IP LAN de votre serveur)
listening-ip=192.168.1.130
# Optionnel : ajouter IPv6 si votre serveur a une IPv6 publique
listening-ip=2001:db8::1

# Mapper l'IP d'écoute privée vers l'IP publique pour les clients externes
external-ip=203.0.113.1/192.168.1.130
external-ip=2001:db8::1

listening-port=3478
min-port=49152
max-port=49199

realm=yourdomain.com

# Authentification HMAC (tokens limités dans le temps — plus sûr que user/password)
use-auth-secret
static-auth-secret=YOUR_RANDOM_SECRET_HERE

# N'autoriser le relais que vers votre nœud JVB (sécurité !)
allowed-peer-ip=10.0.0.0-10.255.255.255

no-loopback-peers
no-multicast-peers
log-file=stdout
```

Exécutez-le comme conteneur Docker :

```bash
docker run -d --name coturn \
  --net=host \
  --restart=always \
  -v /etc/coturn:/etc/coturn:ro \
  coturn/coturn:4.6 \
  -c /etc/coturn/turnserver.conf
```

Puis ajoutez la config TURN à l'environnement de Prosody :

```bash
TURN_HOST=turn.yourdomain.com
TURN_PORT=3478
TURN_TRANSPORT=udp
TURN_CREDENTIALS=YOUR_RANDOM_SECRET_HERE
```

---

## Observabilité : savoir quand quelque chose ne va pas

Une plateforme vidéo auto-hébergée a besoin de supervision. Trois signaux comptent le plus :

**1. Nombre de conférences JVB** — des appels actifs ont-ils lieu ?
```promql
jitsi_jvb_conferences
```

**2. Échecs ICE** — des clients échouent-ils à se connecter ?
```promql
rate(jitsi_jvb_ice_failed_total[5m])
```

**3. Échecs d'allocation TURN** — Coturn accepte-t-il les connexions ?
```bash
# Depuis les logs Coturn
docker logs coturn 2>&1 | grep -i "error\|failed" | tail -20
```

---

## Comparaison des coûts : auto-hébergé vs SaaS

Pour une équipe de 20 personnes :

| Solution | Coût mensuel | Emplacement des données | Contrôle |
|--|--|--|--|
| Microsoft Teams Essentials | 38 € (1,90 €/utilisateur) | Microsoft UE | Faible |
| Microsoft 365 Business Basic | 120 € (6 €/utilisateur) | Microsoft UE | Faible |
| Zoom Pro | 115 €/mois (10 hôtes) | Centres de données Zoom | Faible |
| **Jitsi (auto-hébergé)** | **~5 € d'électricité** | **Votre rack** | **Total** |

Les 5 €/mois sont une estimation pour la consommation électrique supplémentaire de dédier une machine à la tâche. S'il tourne sur du matériel que vous possédez déjà pour d'autres usages (comme dans cette configuration), le coût marginal est essentiellement nul.

Le vrai coût est le temps d'ingénierie pour le mettre en place et le maintenir — environ 8–10 heures de configuration initiale, puis 1–2 heures par mois pour les mises à jour et la revue de supervision.

---

## Leçons apprises

**Les règles IPv6 d'UFW sont séparées des règles IPv4.** `sudo ufw allow 10000/udp` ajoute les deux, mais si vous ajoutez la règle via iptables directement, vous pourriez n'obtenir qu'IPv4. Vérifiez toujours avec `sudo ufw status numbered` et cherchez les entrées IPv4 et « Anywhere (v6) ».

**TURN ne peut pas ponter IPv4 et IPv6.** C'est une contrainte fondamentale de WebRTC. Si l'IPv4 publique d'un client est derrière un NAT d'opérateur (DS-Lite, CGNAT), le relais TURN IPv4 est inutile. La seule solution est un chemin IPv6 direct — ce qui requiert que le serveur ait une IPv6 publique et que le pare-feu autorise l'UDP IPv6 entrant.

**`hostNetwork: true` sur JVB est non négociable.** Sans cela, ICE ne fonctionnera jamais correctement. Vous verrez des candidats, mais le ping-pong STUN échouera car l'IP source des paquets de JVB ne correspondra à aucun candidat.

**Le forward-auth Authentik est plus simple que l'auth JWT intégrée de Jitsi.** Jitsi a son propre système de tokens basé sur JWT pour le contrôle d'accès au niveau salle. Il fonctionne, mais requiert de générer des tokens pour chaque réunion et de les distribuer. Le forward-auth Authentik au niveau ingress est plus simple et vous donne tout le contrôle d'accès nécessaire pour une configuration d'équipe interne.

**Le chemin `coturn.enabled=false` du chart Helm est mal desservi.** Quand vous exécutez Coturn en externe, le chart n'injecte pas la config TURN dans Prosody. Vous devez le faire manuellement via `extraEnvFrom` avec un ConfigMap et un Secret. C'est documenté dans le chart mais facile à manquer.

**Désactivez le transport WebSocket derrière Cloudflare.** Le chart `jitsi-contrib` a deux options WebSocket : `websockets.colibri.enabled` (signalisation JVB) et `websockets.xmpp.enabled` (Prosody). Les deux doivent être `false` quand vous proxifiez le domaine via Cloudflare. La couche proxy de Cloudflare interfère avec l'upgrade WebSocket sur ces chemins, causant des échecs de connexion silencieux difficiles à distinguer des problèmes ICE. Avec elles désactivées, JVB utilise SCTP sur DTLS pour la signalisation, qui circule proprement dans le canal média.

```yaml
websockets:
  colibri:
    enabled: false
  xmpp:
    enabled: false
```

**Authentik `forward_single` vs `forward_domain` — un fournisseur par application.** Le fournisseur `forward_domain` (qui couvre `*.devandre.sbs`) ne peut être assigné qu'à une seule application Authentik à la fois. Si vous tentez de le réutiliser pour Jitsi alors qu'il est déjà assigné à une autre app, vous obtiendrez « Application with this provider already exists ». La solution : créer un fournisseur `forward_single` dédié pour Jitsi (`external_host: https://meet.devandre.sbs`), créer une nouvelle application pointant vers lui, puis PATCHer l'Embedded Outpost pour ajouter le nouveau fournisseur à sa liste `providers`. Un fournisseur, une application — toujours.

---

## La suite

Ce déploiement couvre une équipe toute connectée au même réseau Tailscale ou derrière le même opérateur. Pour un déploiement qui doit supporter de **grandes réunions publiques** (100+ participants), l'étape suivante serait :

- Plusieurs instances JVB avec **Octo Cascade** (fédération JVB-à-JVB)
- **Jibri** pour l'enregistrement de réunions et le streaming en direct
- **Jigasi** pour l'accès téléphonique PSTN via SIP

Pour le cas d'usage actuel — un cluster bare-metal de 5 nœuds servant une équipe de moins de 50 — une seule instance JVB gère tout confortablement. Le transfert de JVB est efficace : dans un appel de 10 personnes, chaque participant téléverse un flux, et JVB le diffuse aux 9 autres. L'usage CPU d'un seul JVB reste sous 30 % pour des appels de cette taille.

---

La configuration complète se trouve dans le dépôt [minicloud-gitops](https://github.com/andrelair-platform/minicloud-gitops) sous `helm-values/jitsi-values.yaml` et `manifests/jitsi/`.
