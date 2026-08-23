---
slug: modern-iam-oidc-vs-ldap-ad
title: "Pourquoi nous avons évité LDAP, Active Directory et Entra ID — et ce que nous avons construit à la place"
authors: [andrelair]
tags: [iam, sso, oidc, oauth2, authentik, kubernetes, enterprise, security, identity, ldap, active-directory, self-hosted]
date: 2026-08-09
description: "La plupart des entreprises traînent 25 ans de dette d'identité — AD on-prem, connecteurs LDAP, agents de sync Entra. Nous avons construit une plateforme Kubernetes de zéro et avons atterri directement à l'extrémité moderne de cet arc. Cet article explique la différence et pourquoi elle compte."
---

La plupart des architectures d'identité d'entreprise n'ont pas commencé comme ce qu'elles sont aujourd'hui. Elles ont démarré en 1999 avec Active Directory, ont accumulé des intégrations LDAP au cours de la décennie suivante, et sont désormais à mi-chemin d'une migration vers l'identité cloud via Microsoft Entra ID — portant le poids de chaque couche qui l'a précédée.

Nous avons construit notre plateforme de zéro. Nous n'avons jamais eu de domaine on-premises. Nous n'avons jamais configuré LDAP. Nous avons sauté directement à la pile de protocoles que les entreprises passent des années et des sommes importantes à essayer d'atteindre. Cet article explique ce que nous avons choisi, pourquoi, et comment l'architecture d'identité résultante se compare au standard d'entreprise.

{/* truncate */}

## Ce que la plupart des entreprises exécutent réellement

Avant de comparer, il vaut la peine de comprendre à quoi ressemble la pile d'identité d'entreprise en pratique, car l'écart entre ce que les organisations ont et ce qu'elles visent est significatif.

Une grande organisation typique a trois couches coexistant simultanément :

```
┌───────────────────────────────────────────────────────────────┐
│  Microsoft Entra ID                                           │
│  (identité cloud, apps modernes, Microsoft 365)               │
└────────────────────────┬──────────────────────────────────────┘
                         │ sync Entra Connect (bidirectionnel)
┌────────────────────────▼──────────────────────────────────────┐
│  Active Directory Domain Services (on-premises)               │
│  (machines Windows, Kerberos, Group Policy, apps héritées)    │
└────────────────────────┬──────────────────────────────────────┘
                         │ requêtes LDAP / LDAPS
┌────────────────────────▼──────────────────────────────────────┐
│  Couche applicative héritée                                   │
│  (VPN, serveurs de fichiers, imprimantes, vieilles apps web)  │
└───────────────────────────────────────────────────────────────┘
```

Chaque couche a été ajoutée parce que la précédente ne pouvait pas gérer la nouvelle exigence. Chaque couche tourne toujours parce que les applications qui en dépendent ne peuvent pas être migrées assez vite. L'organisation paie le coût opérationnel des trois simultanément.

Ce n'est pas une critique — c'est la réalité de tout système ayant évolué sur 25 ans sous de vraies contraintes métier. Mais cela signifie que ce que les entreprises appellent « identité moderne » est souvent Entra ID posé sur Active Directory posé sur LDAP, avec des agents de sync gérant la cohérence entre les trois.

---

## La pile de protocoles sous chaque couche

Les trois technologies ne sont pas équivalentes en nature, ce qui rend la comparaison directe trompeuse.

**LDAP** est un protocole — précisément, un format de transport et un langage de requête pour interroger un service d'annuaire. Il ne stocke pas les utilisateurs lui-même. Il définit comment une application demande *« cet utilisateur existe-t-il ? »* ou *« à quels groupes cet utilisateur appartient-il ? »*

```
Application
     │
     │  requête LDAP  (port 389 / 636)
     ▼
Service d'annuaire
     ├── uid=andre,ou=users,dc=company,dc=com
     ├── memberOf: cn=developers,ou=groups,...
     └── userPassword: {SSHA}...
```

**Active Directory** est un produit qui implémente LDAP aux côtés de Kerberos pour l'authentification, du DNS pour la découverte de services, et de Group Policy pour la configuration des machines Windows. C'est le service d'annuaire on-premises dominant parce qu'il était livré avec Windows Server et est devenu le défaut pour les entreprises centrées sur Windows.

**Microsoft Entra ID** est une plateforme d'identité cloud. Malgré la conservation d'« Active Directory » dans son ancien nom, il ne parle ni LDAP ni Kerberos nativement vers les applications cloud. Il parle OAuth 2.0, OpenID Connect et SAML — les mêmes protocoles utilisés par chaque service web moderne. Le changement de modèle mental est significatif :

```
Modèle LDAP                   Modèle OIDC
──────────────────────        ──────────────────────
L'app interroge l'annuaire     L'app délègue l'auth
L'app vérifie le mot de passe  L'utilisateur s'authentifie à l'IDP
L'app gère la session          L'IDP émet un token JWT
L'app décide l'accès           L'app fait confiance aux claims du token
```

Sous LDAP, l'application contrôle l'authentification. Sous OIDC, c'est le fournisseur d'identité. C'est une frontière de sécurité fondamentalement meilleure : l'application ne touche jamais aux identifiants, ne stocke jamais de hash de mot de passe, et n'a jamais à implémenter le MFA elle-même.

---

## Ce que nous avons construit

Notre plateforme tourne sur cinq nœuds bare-metal — quatre ThinkPads et un MacBook Pro — avec k3s comme distribution Kubernetes. Dès le premier workload, nous avons choisi une approche d'identité unique : **Authentik** comme fournisseur d'identité auto-hébergé, avec chaque application configurée pour utiliser OIDC.

```
                    ┌──────────────────────────┐
                    │         Authentik         │
                    │   auth.devandre.sbs       │
                    │                           │
                    │  Users  Groups  Flows      │
                    │  TOTP   Sessions  Policies │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
           OAuth2             OpenID Connect      Proxy
              │                  │                  │
   ┌──────────▼─────┐  ┌────────▼──────┐  ┌───────▼──────┐
   │ ArgoCD         │  │ Open WebUI    │  │ Jitsi Meet   │
   │ Harbor         │  │ Grafana       │  │ (forward auth)│
   │ Plane          │  │ Backstage     │  └──────────────┘
   │ Vaultwarden    │  │ n8n           │
   │ ERPNext        │  │ Temporal      │
   └────────────────┘  └───────────────┘
```

Chaque application de la plateforme — plus de quinze — s'authentifie via une seule page de login avec TOTP. Il n'y a pas de base de mots de passe par application. Aucune application ne stocke d'identifiants. Il n'y a pas de connecteur LDAP, pas d'agent de sync, aucun composant on-premises de quelque sorte.

Le flux pour un utilisateur accédant à toute ressource protégée est identique quelle que soit l'application qu'il ouvre :

```
L'utilisateur ouvre ArgoCD / Grafana / Harbor / n'importe quelle app
              │
              │  redirection 302 vers Authentik
              ▼
      Page de login Authentik
              │
              │  mot de passe + TOTP
              ▼
      JWT émis avec les claims :
        sub: andre
        groups: ["authentik Admins"]
        email: kanmegnea@...
              │
              │  redirection retour avec un code
              ▼
      L'application échange le code contre un token
              │
              │  lit le claim groups
              ▼
      Accès accordé (palier admin ou utilisateur)
```

---

## Comparaison fonctionnalité par fonctionnalité

| Capacité | LDAP/AD d'entreprise | Microsoft Entra ID | Notre pile Authentik |
|---|---|---|---|
| Magasin d'utilisateurs | AD DS | Entra ID | Authentik (adossé à PostgreSQL) |
| Protocole d'auth | Kerberos / LDAP | OAuth2 / OIDC / SAML | OAuth2 / OIDC |
| MFA | Produit séparé (Duo, ADFS) | Entra MFA | Authentik TOTP (intégré) |
| SSO | Fédéré / complexe | Natif | Natif |
| Accès par groupe | Groupes AD → RBAC app | Groupes Entra → RBAC app | Groupes Authentik → RBAC app |
| Domaine Windows | Requis | Optionnel | Sans objet |
| Stockage de mot de passe app | Par app | Par app (hérité) | Jamais — IDP seulement |
| Auto-hébergé | Oui (AD DS) | Non | Oui |
| Conception cloud-native | Non | Oui | Oui |
| Politiques d'accès conditionnel | Non | Oui (premium) | Basique (moteur de politiques Authentik) |
| Charge opérationnelle | Élevée (AD DC, GPO, réplication) | Faible (managé) | Moyenne (auto-exploité) |
| Verrouillage fournisseur | Microsoft | Microsoft | Aucun |
| RGPD / résidence des données | Complexe | Données dans les DC Microsoft | Contrôle total (on-prem) |

La colonne protocole est là où réside la vraie différence. Kerberos et LDAP ont été conçus pour un monde où chaque application vivait à l'intérieur d'un périmètre réseau et pouvait joindre un contrôleur de domaine directement. OIDC a été conçu pour un monde où les applications sont distribuées, peuvent tourner dans le cloud, et ne peuvent pas présumer d'une adjacence réseau à un fournisseur d'identité. Notre pile a été construite pour ce second monde dès le premier jour.

---

## La seule chose que LDAP fait encore et qu'OIDC ne fait pas

Il y a une raison honnête pour laquelle LDAP n'a pas simplement disparu : certaines applications ne parlent pas OIDC et ne le feront jamais. Commutateurs réseau, appliances de stockage, vieux concentrateurs VPN, modules ERP hérités, imprimantes avec contrôles d'accès — beaucoup de ces appareils parlent LDAP et rien d'autre.

Authentik gère ce cas avec un **outpost LDAP** optionnel : un composant sidecar qui traduit les requêtes LDAP contre le magasin d'utilisateurs Authentik. Si nous avons un jour besoin d'authentifier un appareil qui ne comprend que LDAP, nous n'avons pas besoin d'exécuter un annuaire séparé. Authentik expose ses utilisateurs et groupes en LDAP tandis que le vrai magasin reste OIDC-natif.

Nous n'avons pas encore eu besoin de cette fonctionnalité. Chaque application que nous avons déployée — dont ERPNext (RH), Matrix Synapse (chat), Jitsi Meet (vidéo), Plane (gestion de projet) et Vaultwarden (mots de passe) — a un support OIDC natif. L'outpost LDAP existe comme repli pour le cas d'intégration hérité, pas comme chemin principal.

---

## Le compromis opérationnel que nous acceptons

Exploiter un fournisseur d'identité auto-hébergé n'est pas gratuit. Les compromis honnêtes par rapport à un service managé comme Entra ID sont :

**Point unique de défaillance.** Authentik est un seul pod dans notre cluster. Si le namespace `auth` tombe — pendant une mise à jour Kubernetes, une reconstruction de stockage, une panne de nœud — chaque application protégée par SSO devient injoignable jusqu'à sa reprise. C'est pourquoi chaque application critique a un compte admin local break-glass (`~/.argocd-admin`, `~/.grafana-admin`, etc.) stocké sur le contrôleur pour les urgences.

**Nous exploitons les mises à jour.** Entra ID se met à jour lui-même. Nous planifions les mises à jour d'Authentik, les testons en staging, et les déployons manuellement. C'est quelques heures de travail par version majeure, pas une charge continue, mais c'est du travail que les clients d'Entra ID ne font pas.

**Pas d'équivalent d'Accès conditionnel.** L'Accès conditionnel d'Entra ID permet de dire *« exiger le MFA uniquement quand l'utilisateur est hors du réseau d'entreprise »* ou *« bloquer le login depuis certains pays »*. Authentik a un moteur de politiques capable d'exprimer des règles similaires, mais l'outillage est moins mature et requiert plus de configuration manuelle.

Pour un cluster de niveau homelab servant une équipe d'une personne, ces compromis sont tout à fait raisonnables. Pour une organisation avec des exigences de conformité et une équipe d'exploitation IT, l'alternative managée mérite son coût.

---

## Pourquoi cette architecture compte spécifiquement pour Kubernetes

Kubernetes a son propre modèle d'authentification, et il s'aligne naturellement avec OIDC plutôt que LDAP. Le serveur d'API peut être configuré pour accepter directement les tokens OIDC — ce qui signifie que le même JWT qui accorde l'accès à Grafana ou ArgoCD peut aussi servir à lancer des commandes `kubectl`. L'appartenance aux groupes de l'utilisateur, émise par Authentik au moment du login, circule dans le RBAC Kubernetes sans aucun job de synchronisation.

```
L'utilisateur se connecte via Authentik
         │
         │  JWT avec le claim groups
         ▼
kubectl --token=<jwt> get pods
         │
         │  Le serveur d'API valide le token contre
         │  l'endpoint de découverte OIDC d'Authentik
         ▼
RBAC : groupe "authentik Admins" → ClusterRole cluster-admin
```

Sous LDAP ou Active Directory, atteindre le même résultat requiert un pont : soit un démon de sync LDAP-vers-RBAC-Kubernetes, soit l'intégration Entra ID via un plugin spécifique à Microsoft. Avec OIDC natif à la fois pour Authentik et Kubernetes, il n'y a pas de pont à maintenir.

---

## Résumé

La plupart des entreprises se modernisent *vers* ce que nous avons. Elles exécutent Entra ID sur Active Directory sur LDAP, soulevant progressivement les applications des couches anciennes vers la plus récente, dépensant de l'effort d'ingénierie à chaque étape en migration, en couches de compatibilité et en agents de sync.

Nous avons commencé par le haut. Chaque application parle OIDC. Chaque utilisateur s'authentifie une fois via Authentik et reçoit un token qui fonctionne partout. Il n'y a pas d'annuaire on-premises, pas de Kerberos, pas de connecteur LDAP, pas de dépendance fournisseur.

Le compromis est que nous exploitons la plateforme d'identité nous-mêmes plutôt que de la payer comme un service. Pour une plateforme Kubernetes auto-hébergée, c'est un choix simple et conscient — pas une contrainte.

La pile de protocoles vers laquelle les entreprises convergent après 25 ans d'évolution est la seule que nous ayons jamais exploitée.
