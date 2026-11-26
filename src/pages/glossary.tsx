import React from 'react';
import Layout from '@theme/Layout';
import GlossaryBrowser from '@site/src/components/GlossaryBrowser';

export default function GlossaryPage(): React.ReactElement {
  return (
    <Layout
      title="Glossary"
      description="The minicloud / ktayl-solution vocabulary — platform, access & identity, delivery, data, security, reliability and compliance terms, searchable in one place.">
      <main className="container margin-vert--lg" style={{maxWidth: 860}}>
        <h1>Glossary</h1>
        <p style={{color: 'var(--ifm-color-emphasis-700)', marginBottom: 20}}>
          A cross-pillar reference for the vocabulary used across these docs — the{' '}
          <strong>Platform</strong> (shared technical capabilities) and the{' '}
          <strong>Information System</strong> (the insurance business apps). Filter by keyword or pick a
          category; each term is linkable by its anchor.
        </p>
        <GlossaryBrowser />
      </main>
    </Layout>
  );
}
