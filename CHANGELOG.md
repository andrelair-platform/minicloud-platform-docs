# Changelog

## [0.1.3](https://github.com/andrelair-platform/minicloud-platform-docs/compare/minicloud-platform-docs-v0.1.2...minicloud-platform-docs-v0.1.3) (2026-11-01)


### Features

* **architecture:** C4 Component views — subsystem deep-dives ([#278](https://github.com/andrelair-platform/minicloud-platform-docs/issues/278)) ([912b594](https://github.com/andrelair-platform/minicloud-platform-docs/commit/912b594a1c66c1a47c76f524238bb6321927b9e1))
* **architecture:** C4 request + observability flows; retire the HTML poster ([#281](https://github.com/andrelair-platform/minicloud-platform-docs/issues/281)) ([75320dc](https://github.com/andrelair-platform/minicloud-platform-docs/commit/75320dc326ff7745d1bb1512ea706a98d0b0033e))
* **docs:** add --live ArgoCD health overlay to the SI delivery generator ([#325](https://github.com/andrelair-platform/minicloud-platform-docs/issues/325)) ([d82a3fc](https://github.com/andrelair-platform/minicloud-platform-docs/commit/d82a3fc9ed21790ea6562b928af77ebe4496f670))
* **docs:** add capability-maturity column to the SI delivery board ([#326](https://github.com/andrelair-platform/minicloud-platform-docs/issues/326)) ([2d3ac28](https://github.com/andrelair-platform/minicloud-platform-docs/commit/2d3ac285c76168592864b8e77c735f5dcd0d80a9))
* **docs:** auto-generate the SI Delivery Board (built vs to-build) ([#323](https://github.com/andrelair-platform/minicloud-platform-docs/issues/323)) ([7a30bfb](https://github.com/andrelair-platform/minicloud-platform-docs/commit/7a30bfb8e1ba5f1dc24bf88a9e8c0711da0f2a6e))
* **docs:** first-pass domain maturity estimates on the SI delivery board ([#328](https://github.com/andrelair-platform/minicloud-platform-docs/issues/328)) ([527715a](https://github.com/andrelair-platform/minicloud-platform-docs/commit/527715a04bcc4e21bef0186dbce0e289cd83bcb0))
* **docs:** first-pass maturity for the 3 greenfield blind-spot domains ([#330](https://github.com/andrelair-platform/minicloud-platform-docs/issues/330)) ([ce56294](https://github.com/andrelair-platform/minicloud-platform-docs/commit/ce562946760aa05899cb35f1b49f5fe93ab3f36f))
* **docs:** split Platform + Information System into distinct route sections (/platform, /is) ([#289](https://github.com/andrelair-platform/minicloud-platform-docs/issues/289)) ([8c3da8e](https://github.com/andrelair-platform/minicloud-platform-docs/commit/8c3da8e3be1cb04a3c9d6d39719db684efc615a7))


### Bug Fixes

* **data:** reconcile register — SIEM/SOC/Vuln-Mgmt were wrongly LIVE ([#334](https://github.com/andrelair-platform/minicloud-platform-docs/issues/334)) ([ddfd56f](https://github.com/andrelair-platform/minicloud-platform-docs/commit/ddfd56f3dcd1558fedc349f32ee2ce8bb7663738))
* **data:** reconcile the whole Cybersecurity & IAM cluster (domain 18) ([#335](https://github.com/andrelair-platform/minicloud-platform-docs/issues/335)) ([c9e7259](https://github.com/andrelair-platform/minicloud-platform-docs/commit/c9e7259621768e5880dd1cea1b0a0c48225e2a40))
* **docs:** inline diagram images were 404 on the live site ([#284](https://github.com/andrelair-platform/minicloud-platform-docs/issues/284)) ([8d4b9c3](https://github.com/andrelair-platform/minicloud-platform-docs/commit/8d4b9c368f84f1ef39c0e27d45c691ba8f68fe93))
* **docs:** root redirect → /platform (no trailing slash); rename docs-is/is → apps ([#290](https://github.com/andrelair-platform/minicloud-platform-docs/issues/290)) ([6f4bdc4](https://github.com/andrelair-platform/minicloud-platform-docs/commit/6f4bdc4bf90afc05c178302aab57ede2bde52a66))

## [0.1.2](https://github.com/andrelair-platform/minicloud-platform-docs/compare/minicloud-platform-docs-v0.1.1...minicloud-platform-docs-v0.1.2) (2026-10-17)


### Features

* **architecture:** C4 system design of the platform (Structurizr, as code) ([#276](https://github.com/andrelair-platform/minicloud-platform-docs/issues/276)) ([5d38e74](https://github.com/andrelair-platform/minicloud-platform-docs/commit/5d38e7411611ef630742871e1ca29b0cb6cb4ead))
* **architecture:** multi-level architecture docs (Platform ↔ IS) ([#272](https://github.com/andrelair-platform/minicloud-platform-docs/issues/272)) ([81afb89](https://github.com/andrelair-platform/minicloud-platform-docs/commit/81afb89aad8ebe85fd002c968d68fdee6c5631bb))
* **architecture:** platform capability view + fixed topology + physical view ([#274](https://github.com/andrelair-platform/minicloud-platform-docs/issues/274)) ([b3d5afe](https://github.com/andrelair-platform/minicloud-platform-docs/commit/b3d5afea33139bf33e3fc7ff210867bd7cdabdf3))
* **copilot:** add minicloud Copilot — M365 equivalent on self-hosted stack ([#260](https://github.com/andrelair-platform/minicloud-platform-docs/issues/260)–[#265](https://github.com/andrelair-platform/minicloud-platform-docs/issues/265)) ([#113](https://github.com/andrelair-platform/minicloud-platform-docs/issues/113)) ([5ca48a5](https://github.com/andrelair-platform/minicloud-platform-docs/commit/5ca48a5b8e5dcedc5d0c8f1d69b11ccde8bd4ea9))
* **diagrams:** comprehensive platform poster; retire the HTML poster ([#267](https://github.com/andrelair-platform/minicloud-platform-docs/issues/267)) ([2a0244f](https://github.com/andrelair-platform/minicloud-platform-docs/commit/2a0244fe3ea20ffecf1ed664cb2b9b02c217c0cb))
* minicloud brand identity + two-pillar navigation ([#225](https://github.com/andrelair-platform/minicloud-platform-docs/issues/225)) ([2ed425a](https://github.com/andrelair-platform/minicloud-platform-docs/commit/2ed425a40cfa8d13b4fbb8455c39d9a3f2fb664b))


### Bug Fixes

* **blog:** set feedOptions limit:false to include all posts in RSS feed ([#118](https://github.com/andrelair-platform/minicloud-platform-docs/issues/118)) ([868da22](https://github.com/andrelair-platform/minicloud-platform-docs/commit/868da22a5407412a93947b2da82b35557cb60ce7))
* **diagrams:** self-contained SVGs so they open standalone in a browser ([#269](https://github.com/andrelair-platform/minicloud-platform-docs/issues/269)) ([3342fbe](https://github.com/andrelair-platform/minicloud-platform-docs/commit/3342fbebb1632a75b63e7153889545f54016ec97))
* Information System navbar lands on the insurance blueprint, not intro ([#226](https://github.com/andrelair-platform/minicloud-platform-docs/issues/226)) ([1575feb](https://github.com/andrelair-platform/minicloud-platform-docs/commit/1575feb4de3ec3d8d1e0318de895856268b14bf7))
* neutral home + symmetric pillars ([#227](https://github.com/andrelair-platform/minicloud-platform-docs/issues/227)) ([c7a4015](https://github.com/andrelair-platform/minicloud-platform-docs/commit/c7a401527096409ab0f38f03ed8427512d713d79))
* **sidebar:** remove duplicate Insurance Platform section ([6ce01c2](https://github.com/andrelair-platform/minicloud-platform-docs/commit/6ce01c26e3e2c12172cc25135cd17fb54df062af))

## [0.1.1](https://github.com/andrelair-platform/minicloud-platform-docs/compare/minicloud-platform-docs-v0.1.0...minicloud-platform-docs-v0.1.1) (2026-08-14)


### Features

* **blog:** enable blog and publish first post ([87d490c](https://github.com/andrelair-platform/minicloud-platform-docs/commit/87d490c38fac9ceafb2a3f5f3e8125fdac485b27))
* **catalog:** add Backstage catalog-info.yaml (Phase 18) ([fe782d1](https://github.com/andrelair-platform/minicloud-platform-docs/commit/fe782d177d621c8c5a9c80cd4921a7788fc32ce1))
* **cert:** add BC01 sprint log, retrospectives and risk register ([78c1862](https://github.com/andrelair-platform/minicloud-platform-docs/commit/78c18629a9ae10fd95a7194a13f66efea9134b77))
* **cert:** Sprint 1 backlog — BMAD story IDs + GitHub Milestone link ([4a75fbd](https://github.com/andrelair-platform/minicloud-platform-docs/commit/4a75fbdb184cb95ca90fac9d89d3e99088b18bb8))
* **cert:** Sprint 1 backlog — BMAD story IDs + GitHub Milestone link ([4a75fbd](https://github.com/andrelair-platform/minicloud-platform-docs/commit/4a75fbdb184cb95ca90fac9d89d3e99088b18bb8))
* **cert:** Sprint 1 backlog — BMAD story IDs + GitHub Milestone link ([c00952b](https://github.com/andrelair-platform/minicloud-platform-docs/commit/c00952b01259ddd0ce0b99acc374c09660865ac2))
* **docs:** BMAD workflow — Engineering Standards documentation ([83235cc](https://github.com/andrelair-platform/minicloud-platform-docs/commit/83235cc2eed0a4f8fe67d29c30321b511c434c51))
* **docs:** BMAD workflow — Engineering Standards documentation ([83235cc](https://github.com/andrelair-platform/minicloud-platform-docs/commit/83235cc2eed0a4f8fe67d29c30321b511c434c51))
* **docs:** BMAD workflow documentation — engineering standard ([918a606](https://github.com/andrelair-platform/minicloud-platform-docs/commit/918a6060f02a537ff6fae99fff2dd873d7ac58a6))
* **governance:** add project governance standard with RACI template and CERT-1 matrix ([7c18d40](https://github.com/andrelair-platform/minicloud-platform-docs/commit/7c18d4013a13f1d63d799b1848978a124501f4d5))
* **i18n:** add French locale with language switcher and translated blog post ([64dd067](https://github.com/andrelair-platform/minicloud-platform-docs/commit/64dd067a786f7238837a338014b233c53e3547d0))


### Bug Fixes

* **blog:** correct LinkedIn profile URL in authors.yml ([8f4701f](https://github.com/andrelair-platform/minicloud-platform-docs/commit/8f4701f8218ce51ac809cec6259b66dd4aa63e2e))
* **blog:** fix MDX truncate marker and add authors.yml ([4203bb0](https://github.com/andrelair-platform/minicloud-platform-docs/commit/4203bb04882b9d2216589eaf06c6a23b067e7d2b))
* correct phi3-financial description — Modelfile not fine-tuning ([d71aac0](https://github.com/andrelair-platform/minicloud-platform-docs/commit/d71aac08b42883c9a9d9ebe630ada56a9f788dda))
* correct web search env var names in RAG runbook; note Open WebUI uses PostgreSQL ([196d928](https://github.com/andrelair-platform/minicloud-platform-docs/commit/196d928ac1bf101602b0072c4a7e3bf44b805e19))
* **docs:** add Flowise to AI diagram and business apps URL table ([75cf2cf](https://github.com/andrelair-platform/minicloud-platform-docs/commit/75cf2cf789c9ff1a716e4c7fa66ce179d0215595))
* **docs:** remove all HDI references — replace with ktayl-solution or generic sector terms ([71b15af](https://github.com/andrelair-platform/minicloud-platform-docs/commit/71b15af6dcb282d561768b9160c6d830e60278fa))
* **docs:** remove Ollama — embeddings use OpenAI text-embedding-3-small via LiteLLM ([d901f13](https://github.com/andrelair-platform/minicloud-platform-docs/commit/d901f13dd9d48a684655061299732bef0d7ad823))
* **langfuse:** remove stale No SSO limitation, update to OIDC-only note ([535cdc7](https://github.com/andrelair-platform/minicloud-platform-docs/commit/535cdc78059ad9dc7817422d11c71e4653ab418c))
* **nav:** correct Docusaurus doc IDs for Phase 23 and Phase 24 (strip numeric prefix) ([892bf13](https://github.com/andrelair-platform/minicloud-platform-docs/commit/892bf132e4fcb5f5a1cd4e97c82abf2bf9e5a399))
* **nav:** Phase 21 real observability docs, Phase 16 correct label, remove duplicates and misplacements ([db7faa3](https://github.com/andrelair-platform/minicloud-platform-docs/commit/db7faa34cf3d084deae20479354462b1c214dcd1))
* **sidebar:** update phase-3-ingress → phase-6-ingress doc id ([d445511](https://github.com/andrelair-platform/minicloud-platform-docs/commit/d445511ca926ee5e6acf807936db121880ec9935))

## Changelog

All notable changes to minicloud-platform-docs are documented here.

This file is maintained by [release-please](https://github.com/googleapis/release-please).
