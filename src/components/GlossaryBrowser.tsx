import React, {useMemo, useState} from 'react';
import Link from '@docusaurus/Link';
import ReactMarkdown from 'react-markdown';
import rawTerms from '@site/src/data/glossary.json';

type Term = {category: string; term: string; definition: string};
const DATA = rawTerms as Term[];
const CATEGORIES = Array.from(new Set(DATA.map((t) => t.category)));

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

// Render a definition's markdown; internal links go through Docusaurus <Link> (baseUrl-aware),
// and we unwrap the auto <p> so it flows inside <dd>.
const mdComponents = {
  a: ({href, children}: {href?: string; children?: React.ReactNode}) => (
    <Link to={href || '#'}>{children}</Link>
  ),
  p: ({children}: {children?: React.ReactNode}) => <>{children}</>,
};

export default function GlossaryBrowser(): React.ReactElement {
  const [q, setQ] = useState('');
  const [cat, setCat] = useState<string>('All');
  const needle = q.trim().toLowerCase();

  const filtered = useMemo(
    () =>
      DATA.filter(
        (t) =>
          (cat === 'All' || t.category === cat) &&
          (!needle ||
            t.term.toLowerCase().includes(needle) ||
            t.definition.toLowerCase().includes(needle)),
      ),
    [needle, cat],
  );

  const groups = CATEGORIES.map((c) => ({
    c,
    items: filtered.filter((t) => t.category === c),
  })).filter((g) => g.items.length > 0);

  return (
    <div>
      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={`Filter ${DATA.length} terms…`}
        aria-label="Filter glossary terms"
        style={{
          width: '100%',
          padding: '12px 14px',
          fontSize: 16,
          borderRadius: 10,
          border: '1px solid var(--ifm-color-emphasis-300)',
          marginBottom: 14,
          background: 'var(--ifm-background-surface-color)',
        }}
      />

      <div style={{display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 22}}>
        {['All', ...CATEGORIES].map((c) => {
          const count = c === 'All' ? DATA.length : DATA.filter((t) => t.category === c).length;
          const active = cat === c;
          return (
            <button
              key={c}
              type="button"
              onClick={() => setCat(c)}
              style={{
                padding: '6px 13px',
                borderRadius: 999,
                fontSize: 13,
                cursor: 'pointer',
                border: '1px solid ' + (active ? '#0e7490' : 'var(--ifm-color-emphasis-300)'),
                background: active ? '#0e7490' : 'transparent',
                color: active ? '#fff' : 'inherit',
              }}>
              {c} <span style={{opacity: 0.65}}>{count}</span>
            </button>
          );
        })}
      </div>

      {filtered.length === 0 && (
        <p style={{color: 'var(--ifm-color-emphasis-600)'}}>No term matches “{q}”.</p>
      )}

      {groups.map((g) => (
        <section key={g.c} style={{marginBottom: 28}}>
          <h2
            id={slug(g.c)}
            style={{
              fontSize: 13,
              textTransform: 'uppercase',
              letterSpacing: 1,
              color: '#0e7490',
              borderBottom: '1px solid var(--ifm-color-emphasis-200)',
              paddingBottom: 6,
              marginBottom: 4,
            }}>
            {g.c} <span style={{opacity: 0.6}}>· {g.items.length}</span>
          </h2>
          <dl style={{margin: 0}}>
            {g.items.map((t) => (
              <div
                key={t.term}
                id={slug(t.term)}
                style={{padding: '11px 0', borderBottom: '1px solid var(--ifm-color-emphasis-100)'}}>
                <dt style={{fontWeight: 700, marginBottom: 3}}>{t.term}</dt>
                <dd style={{margin: 0, color: 'var(--ifm-color-emphasis-800)', lineHeight: 1.6}}>
                  <ReactMarkdown components={mdComponents}>{t.definition}</ReactMarkdown>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}
