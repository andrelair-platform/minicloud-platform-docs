import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'minicloud',
  tagline: 'A self-hosted enterprise information system — the platform and the applications running on it',
  favicon: 'img/favicon.png',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://andrelair-platform.github.io',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/minicloud-platform-docs/',

  // GitHub pages deployment config.
  organizationName: 'andrelair-platform',
  projectName: 'minicloud-platform-docs',
  trailingSlash: false,

  onBrokenLinks: 'throw',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'fr'],
    localeConfigs: {
      en: { label: 'English', htmlLang: 'en' },
      fr: { label: 'Français', htmlLang: 'fr' },
    },
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: '/',
        },
        blog: {
          showReadingTime: true,
          blogSidebarTitle: 'Recent Posts',
          blogSidebarCount: 'ALL',
          postsPerPage: 10,
          feedOptions: {
            type: 'rss',
            limit: false,
          },
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    // minicloud social card (LinkedIn/OG preview)
    image: 'img/minicloud-social-card.png',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'minicloud',
      logo: {
        alt: 'minicloud',
        src: 'img/minicloud-logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'platformSidebar',
          position: 'left',
          label: 'Platform',
        },
        {
          type: 'docSidebar',
          sidebarId: 'isSidebar',
          position: 'left',
          label: 'Information System',
        },
        {
          to: '/blog',
          label: 'Blog',
          position: 'left',
        },
        {
          href: 'https://www.devandre.sbs',
          label: 'Portfolio',
          position: 'right',
        },
        {
          type: 'localeDropdown',
          position: 'right',
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
            {label: 'GitOps (ArgoCD)', to: '/platform-roadmap/phase-12-gitops'},
            {label: 'Monitoring', to: '/platform-roadmap/phase-8-monitoring'},
          ],
        },
        {
          title: 'André Kanmegne',
          items: [
            {label: 'Portfolio', href: 'https://www.devandre.sbs'},
            {label: 'Blog', to: '/blog'},
            {label: 'GitHub', href: 'https://github.com/AndreLiar'},
            {label: 'LinkedIn', href: 'https://www.linkedin.com/in/andre-kanmegne-dev'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} minicloud — André Kanmegne. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
