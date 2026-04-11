import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'Mini Cloud Platform',
  tagline: 'Bare-metal infrastructure — MAAS, Kubernetes, GitOps',
  favicon: 'img/favicon.ico',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://AndreLiar.github.io',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/minicloud-platform-docs/',

  // GitHub pages deployment config.
  organizationName: 'AndreLiar',
  projectName: 'minicloud-platform-docs',
  trailingSlash: false,

  onBrokenLinks: 'throw',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: '/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    // Replace with your project's social card
    image: 'img/docusaurus-social-card.jpg',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Mini Cloud Platform',
      logo: {
        alt: 'Mini Cloud Platform',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'tutorialSidebar',
          position: 'left',
          label: 'Documentation',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Phase 0 — MAAS',
          items: [
            {label: 'Objective', to: '/phase-0-maas/objective'},
            {label: 'Architecture', to: '/phase-0-maas/architecture'},
            {label: 'Hardware', to: '/phase-0-maas/hardware'},
            {label: 'Troubleshooting', to: '/phase-0-maas/troubleshooting'},
          ],
        },
        {
          title: 'Platform Roadmap',
          items: [
            {label: 'Overview', to: '/platform-roadmap/roadmap-overview'},
            {label: 'Kubernetes (k3s)', to: '/platform-roadmap/phase-1-kubernetes'},
            {label: 'GitOps (ArgoCD)', to: '/platform-roadmap/phase-6-gitops'},
            {label: 'Monitoring', to: '/platform-roadmap/phase-4-monitoring'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Mini Cloud Platform. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
