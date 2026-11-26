// Swizzle-wrap of DocBreadcrumbs: prepend a "you are here" pillar badge so a reader
// always knows which pillar (Platform vs Information System) they're in.
import React from 'react';
import OriginalDocBreadcrumbs from '@theme-original/DocBreadcrumbs';
import type DocBreadcrumbsType from '@theme/DocBreadcrumbs';
import type {WrapperProps} from '@docusaurus/types';
import Link from '@docusaurus/Link';
import {useLocation} from '@docusaurus/router';

type Props = WrapperProps<typeof DocBreadcrumbsType>;

function PillarBadge(): React.ReactElement | null {
  const {pathname} = useLocation();
  // pathname is baseUrl-prefixed, e.g. /minicloud-platform-docs/platform/...
  let pillar:
    | {label: string; color: string; to: string}
    | null = null;
  if (pathname.includes('/is/')) {
    pillar = {label: 'Information System', color: '#7c3aed', to: '/is/insurance-platform/architecture-at-a-glance'};
  } else if (pathname.includes('/platform/')) {
    pillar = {label: 'Platform', color: '#0e7490', to: '/platform'};
  }
  if (!pillar) return null;
  return (
    <Link
      to={pillar.to}
      title={`You are in the ${pillar.label} pillar`}
      style={{
        display: 'inline-block',
        marginBottom: 10,
        padding: '2px 11px',
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        letterSpacing: 0.2,
        color: pillar.color,
        border: `1px solid ${pillar.color}`,
        background: 'transparent',
        textDecoration: 'none',
      }}>
      {pillar.label}
    </Link>
  );
}

export default function DocBreadcrumbsWrapper(props: Props): React.ReactElement {
  return (
    <>
      <PillarBadge />
      <OriginalDocBreadcrumbs {...props} />
    </>
  );
}
