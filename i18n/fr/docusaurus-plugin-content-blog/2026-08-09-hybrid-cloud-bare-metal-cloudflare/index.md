---
slug: hybrid-cloud-bare-metal-cloudflare
title: "Le bare-metal d'abord, le cloud en périphérie — notre décision d'architecture hybride"
authors: [andrelair]
tags: [kubernetes, bare-metal, hybrid-cloud, cloudflare, aws, architecture, devops, infrastructure, k3s, self-hosted]
date: 2026-08-09
description: "La plupart des tutoriels vous apprennent à déployer sur AWS. Nous avons pris l'autre chemin : cinq nœuds bare-metal au sol, Cloudflare en périphérie, et des services cloud uniquement là où la physique rend l'auto-hébergement impossible. Voici pourquoi."
---

La plupart des tutoriels Kubernetes commencent par `eksctl create cluster` ou `gcloud container clusters create`. Un plan de contrôle managé, des groupes de nœuds à auto-scaling, des load balancers qui apparaissent avec une simple annotation. Le cloud abstrait entièrement le matériel.

Nous avons pris la direction opposée. Cinq machines physiques — quatre ThinkPads et un MacBook Pro de 2012 — exécutant k3s, avec chaque workload ordonnancé et exploité par nous. Pas de plan de contrôle managé. Pas de groupe de nœuds à auto-scaling. Pas de load balancer cloud. Juste Linux, containerd et Flannel sur du fer que l'on peut toucher.

Mais nous utilisons bien des services cloud. AWS achemine nos e-mails. Cloudflare se place devant chaque requête HTTP. Une instance Lightsail relaie le trafic UDP de nos appels vidéo. Tailscale nous connecte au cluster depuis n'importe où.

Cet article explique comment nous avons décidé ce qui va où, et pourquoi l'architecture résultante n'est pas un compromis — c'est une conception délibérée.

{/* truncate */}

## La question de départ

Quand vous exploitez une infrastructure, chaque service que vous ajoutez impose la même question : est-ce que ça tourne sur mon matériel, ou est-ce que ça tourne ailleurs ?

La réponse naïve est « ça dépend ». La réponse utile requiert un cadre. Le nôtre a trois critères :

1. **Est-ce que cela nécessite une IP publique ou une position réseau spécifique que je ne peux pas fournir ?**
2. **Est-ce que l'exploiter moi-même endommagerait quelque chose que je ne peux pas réparer — comme la réputation de délivrabilité e-mail ?**
3. **Le coût opérationnel de l'exploiter moi-même est-il disproportionné par rapport au bénéfice ?**

Si la réponse à l'une de ces questions est oui, le service a sa place dans le cloud. Sinon, il tourne sur nos nœuds.

Appliquons cela à chaque service de la plateforme.

---

## Ce qui tourne on-premise

Tout ce qui répond oui à « peut-on l'exploiter nous-mêmes sans désavantage structurel » tourne sur le cluster.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Cluster k3s — 5 nœuds, bare-metal                                  │
│                                                                     │
│  set-hog (plan de contrôle)  fast-skunk    fast-heron               │
│  star-kitten                 swift-mac (MacBook Pro 2012)           │
│                                                                     │
│  Workloads (sélection) :                                            │
│  ArgoCD · Authentik · Harbor · Grafana · Loki · Tempo               │
│  Backstage · Plane · ERPNext · Matrix · Element · Jitsi             │
│  Stalwart mail · Open WebUI · Vaultwarden · Vault                   │
│  LiteLLM · vLLM · Flowise · MLflow · n8n · Temporal                │
│  Stockage Longhorn · MinIO · PostgreSQL · MariaDB                   │
└─────────────────────────────────────────────────────────────────────┘
```

Ce sont vingt-cinq workloads de production, toutes leurs bases de données, tout leur stockage — tournant sur du matériel dont l'exploitation ne coûte rien par mois au-delà de l'électricité. C'est aussi là que réside chaque donnée sensible : dossiers de contrats d'assurance, données RH des salariés, identifiants d'authentification, embeddings vectoriels, inférence LLM.

La dimension de souveraineté des données compte ici plus que le coût. Exploiter un système d'information d'assurance français signifie opérer sous le RGPD et la surveillance de l'ACPR. Chaque octet de données personnelles restant à l'intérieur d'un matériel physique que nous contrôlons, dans une juridiction choisie, est une décision de conformité autant qu'une décision d'infrastructure.

---

## Ce qui tourne dans le cloud, et pourquoi

### Cloudflare — la couche de périphérie

Le cluster se trouve derrière une connexion internet domestique. Les FAI grand public attribuent des IP dynamiques, partagent souvent les IP entre clients, et ne fournissent ni la mitigation DDoS ni le peering BGP qui rendent un endpoint public fiable. Cloudflare résout tout cela.

**Cloudflare Tunnel** est le mécanisme central. Plutôt que d'exposer l'IP de notre cluster à internet, nous exécutons un léger démon `cloudflared` sur le contrôleur. Il maintient une connexion sortante vers la périphérie de Cloudflare. Quand une requête arrive pour `argocd.devandre.sbs`, Cloudflare la route par ce tunnel jusqu'à notre service interne — sans que notre IP ne soit jamais publiée.

```
Requête externe → argocd.devandre.sbs
                        │
                        ▼
          Périphérie Cloudflare (WAF + mitigation DDoS)
                        │
                   Cloudflare Tunnel
                        │
                        ▼
          Démon cloudflared (contrôleur, 100.88.123.8)
                        │
                        ▼
          Service ArgoCD (namespace argocd, 10.0.0.200)
```

Chacun de nos vingt-trois endpoints publics suit ce chemin. Le WAF inspecte le trafic avant qu'il n'atteigne le cluster. Le trafic DDoS est absorbé à la périphérie de Cloudflare, pas par nos nœuds. L'IP d'origine n'est jamais exposée.

**Cloudflare R2** stocke notre sauvegarde hors-site. Velero sauvegarde l'état du cluster vers une instance MinIO interne au cluster chaque jour. Un planning hebdomadaire séparé écrit vers R2. Si le matériel physique est détruit — incendie, inondation, vol — l'état du cluster survit dans R2 et peut être restauré vers n'importe quel cluster Kubernetes. C'est le seul scénario où le stockage on-premise ne peut structurellement pas aider : la sauvegarde doit survivre à la perte du site.

**Le coût :** Cloudflare Tunnel est gratuit. R2 est gratuit jusqu'à 10 Go de stockage et 1 million d'opérations de classe A par mois. Notre sauvegarde hebdomadaire reste largement dans ces limites. Le WAF Cloudflare en formule gratuite couvre les règles essentielles. Dépense mensuelle totale : zéro.

---

### AWS SES — délivrabilité e-mail

Stalwart Mail tourne sur le cluster et gère tous les e-mails entrants et sortants de `devandre.sbs`. Pour l'entrant, cela fonctionne parfaitement — Stalwart reçoit, analyse et stocke le courrier entièrement on-premise.

Pour le sortant, exploiter son propre relais SMTP est structurellement désavantagé. La réputation d'IP est primordiale en délivrabilité e-mail. Une IP domestique n'a aucune réputation d'expéditeur — elle sera classée comme résidentielle et rejetée ou filtrée par la plupart des grands fournisseurs. Réchauffer une nouvelle IP prend des mois. Si l'IP est un jour partagée avec une source de spam, la réputation suit l'IP, pas l'expéditeur.

AWS SES résout cela. Il fournit une infrastructure d'envoi avec une réputation d'IP établie, la signature DKIM, l'alignement SPF et le support DMARC. Nos e-mails naissent dans Stalwart, transitent par SES comme relais, et arrivent avec le profil de délivrabilité d'une plateforme d'envoi commerciale.

Le coût est de 0,10 $ par millier de messages. Pour le volume d'e-mails transactionnels d'une petite compagnie d'assurance — confirmations de contrat, mises à jour de sinistre, relances, alertes — la dépense mensuelle est de quelques centimes.

Cela satisfait précisément le critère 2 : l'exploiter nous-mêmes endommagerait la délivrabilité e-mail d'une manière que nous ne pouvons pas réparer sans des mois de réchauffement d'IP et sans certitude de résultat.

---

### AWS Lightsail — relais TURN pour la vidéo

Jitsi Meet tourne sur le cluster. La plupart des appels vidéo fonctionnent en pair-à-pair ou via le Jitsi Videobridge (JVB) tournant sur `star-kitten`. Mais le pair-à-pair WebRTC échoue quand les deux participants sont derrière un NAT symétrique — courant sur les réseaux mobiles et les pare-feu d'entreprise.

La solution est un serveur TURN : un relais que les deux participants peuvent joindre directement, qui transfère les paquets UDP entre eux. Un serveur TURN doit être joignable sur des ports UDP publics sans NAT. Il doit avoir une IP publique stable.

Notre cluster se trouve derrière un NAT. Nous ne pouvons pas exposer de manière fiable des ports UDP arbitraires sans IP publique fixe et sans contrôle du routeur. Une instance Lightsail à 3,50 $/mois résout cela proprement : IP statique, ports UDP publics, coturn tournant comme service.

Cela satisfait le critère 1. Le serveur TURN requiert une position réseau — joignabilité UDP publique sans NAT — que nous ne pouvons structurellement pas fournir depuis le cluster.

---

### Tailscale — VPN zéro-confiance

Le cluster n'est pas directement joignable depuis internet (par conception — Cloudflare Tunnel gère le HTTP). Mais le contrôleur doit être joignable pour le SSH, pour kubectl, et pour les opérations d'infrastructure.

Tailscale fournit cela via un réseau maillé basé sur WireGuard. Chaque nœud reçoit une adresse Tailscale dans la plage `100.x.x.x`. Le contrôleur est joignable à `100.88.123.8` depuis n'importe quel appareil du même réseau Tailscale. Le plan de données est pair-à-pair ; aucun trafic ne passe par les serveurs de Tailscale si un chemin direct existe.

Le plan de contrôle est un service SaaS — Tailscale gère la distribution des clés et l'authentification des appareils. C'est un compromis délibéré : nous ne voulons pas exploiter nous-mêmes la PKI et le service de coordination pour un overlay zéro-confiance. La formule gratuite couvre jusqu'à 100 appareils, que nous ne dépasserons pas.

---

### GitHub — gestion de code et CI

Tout le code, les manifestes GitOps et la documentation vivent dans GitHub. La CI tourne sur GitHub Actions avec des runners fournis par GitHub. C'est une dépendance SaaS, mais elle satisfait le critère 3 : le coût opérationnel d'exploiter nous-mêmes un Gitea auto-hébergé, une flotte de runners CI et un pipeline de scan de conteneurs serait disproportionné par rapport au bénéfice, alors que la formule gratuite de GitHub fournit tout cela.

La seule décision délibérée ici est que le registre de conteneurs n'est **pas** le GitHub Container Registry. Toutes les images sont poussées vers Harbor, tournant sur le cluster, pour deux raisons : la localité des données (les images sont tirées depuis l'intérieur du cluster, pas via internet) et le contrôle (nous gérons nous-mêmes la rétention des images, le scan de vulnérabilités et le contrôle d'accès).

---

## Le cadre de décision en pratique

Chaque fois que nous ajoutons un nouveau service, nous appliquons les trois mêmes questions :

```
Nécessite-t-il une IP publique ou une position réseau spécifique ?
    OUI → cloud (Lightsail, offre gratuite EC2)
    NON ↓

L'exploiter moi-même endommagerait-il une réputation irremplaçable ?
    OUI → cloud (SES pour la délivrabilité e-mail)
    NON ↓

La charge opérationnelle est-elle disproportionnée par rapport au bénéfice ?
    OUI → SaaS cloud (Tailscale, GitHub)
    NON → on-premise (tout le reste)
```

C'est pourquoi vingt-cinq workloads tournent sur bare-metal et quatre services cloud gèrent ce que le bare-metal ne peut pas.

---

## La comparaison des coûts

Exécuter l'équivalent de cette plateforme sur AWS nécessiterait :

| Composant | Équivalent AWS | Coût mensuel estimé |
|---|---|---|
| 5 nœuds workers k8s (2 vCPU, 8 Go) | 5× workers EKS t3.large | ~270 $ |
| Plan de contrôle | EKS managé | 72 $ |
| Stockage (2 To au total) | EBS gp3 | ~160 $ |
| Stockage objet (équivalent MinIO) | S3 | ~46 $ |
| Load balancer | ALB | ~20 $ |
| Passerelle NAT | NAT GW | ~32 $ |
| **Total** | | **~600 $/mois** |

Notre dépense cloud réelle :

| Service | Coût mensuel |
|---|---|
| AWS SES | ~0,50 $ |
| AWS Lightsail (TURN) | 3,50 $ |
| Cloudflare | 0 $ |
| Tailscale | 0 $ |
| GitHub | 0 $ |
| **Total** | **~4 $/mois** |

Les nœuds bare-metal ont un coût d'acquisition unique (ThinkPads d'occasion, ~200–400 € chacun) et un coût d'électricité continu (environ 15 €/mois pour 5 machines). Le coût du cluster tourne autour de 25 €/mois tout compris.

L'architecture n'économise pas de l'argent en étant maligne. Elle économise de l'argent en identifiant correctement quels problèmes nécessitent une infrastructure cloud et lesquels non.

---

## Ce que cette architecture ne peut pas faire

L'honnêteté impose de lister les compromis.

**Pas de mise à l'échelle élastique.** Si le trafic dépasse la capacité de nos cinq nœuds, il n'y a pas de groupe d'auto-scaling pour ajouter de la capacité. Nous montons en charge verticalement (plus de RAM dans un ThinkPad) ou acceptons que le cluster ait un plafond.

**Pas de redondance par zone de disponibilité.** Les cinq nœuds sont au même emplacement physique. Une coupure de courant, un incendie ou une panne réseau met tout à terre simultanément. La sauvegarde Cloudflare R2 et Velero nous donnent la récupération des données, mais le RTO (temps de reprise) se mesure en heures, pas en minutes.

**Charge opérationnelle plus élevée.** Quand un nœud tombe, nous le réparons. Quand un disque lâche, nous le remplaçons. Quand k3s publie un correctif de sécurité, nous planifions et exécutons la mise à jour. Un service Kubernetes managé gère la plupart de cela automatiquement.

Ce sont des compromis conscients faits pour un contexte spécifique : une plateforme de portfolio démontrant une capacité d'infrastructure full-stack, où la souveraineté des données et le contrôle opérationnel comptent plus que la mise à l'échelle élastique ou la disponibilité à cinq neuf.

Pour une compagnie d'assurance en production à grande échelle, l'architecture évoluerait : on-premise pour le traitement des données réglementées, Kubernetes cloud (EKS/AKS) pour les workloads sans état ayant besoin de capacité élastique, avec la même couche de périphérie Cloudflare devant les deux.

---

## Le principe

La question n'est jamais « cloud ou on-premise ». C'est toujours « de quoi ce workload spécifique a-t-il besoin, et où cela le place-t-il ? »

Nos workloads de bases de données requièrent la localité des données, des IOPS constantes et le contrôle de conformité. Ils tournent sur bare-metal.

Notre délivrabilité e-mail requiert une réputation d'IP qui prend des mois à bâtir. Elle passe par SES.

Notre relais vidéo requiert une adresse UDP publique sans NAT. Il tourne sur Lightsail.

Nos endpoints publics requièrent une mitigation DDoS et une adresse d'origine stable. Ils passent par Cloudflare.

Tout le reste tourne sur le cluster.

Voilà le cloud hybride : non pas répartir les workloads arbitrairement entre environnements, mais placer chaque workload dans l'environnement qui lui convient structurellement. Les services cloud que nous utilisons coûtent quatre euros par mois. La plateforme qu'ils exposent, c'est vingt-cinq workloads de production tournant sur du matériel au sol.
