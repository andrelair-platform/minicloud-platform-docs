import React from 'react';
import {Redirect} from '@docusaurus/router';
import useBaseUrl from '@docusaurus/useBaseUrl';

// Docs no longer live at the site root — the two pillars are mounted at /platform and /is.
// Send the root to the Platform pillar (the larger entry point); the navbar then exposes both + Blog.
// NOTE: no trailing slash — the site sets `trailingSlash: false`, so the route is `/platform`
// (a trailing `/platform/` 404s). Keep this in sync with that config.
export default function Home(): React.ReactElement {
  return <Redirect to={useBaseUrl('/platform')} />;
}
