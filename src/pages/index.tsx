import React from 'react';
import {Redirect} from '@docusaurus/router';
import useBaseUrl from '@docusaurus/useBaseUrl';

// Docs no longer live at the site root — the two pillars are mounted at /platform and /is.
// Send the root to the Platform pillar (the larger entry point); the navbar then exposes both + Blog.
export default function Home(): React.ReactElement {
  return <Redirect to={useBaseUrl('/platform/')} />;
}
