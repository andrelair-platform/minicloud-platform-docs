// Swizzled (ejected) from @docusaurus/theme-classic 3.10.0 to inject the Carnets
// newsletter subscribe banner at the top of the blog index (first page only).
import React from 'react';
import clsx from 'clsx';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import {
  PageMetadata,
  HtmlClassNameProvider,
  ThemeClassNames,
} from '@docusaurus/theme-common';
import BlogLayout from '@theme/BlogLayout';
import BlogListPaginator from '@theme/BlogListPaginator';
import SearchMetadata from '@theme/SearchMetadata';
import BlogPostItems from '@theme/BlogPostItems';
import BlogListPageStructuredData from '@theme/BlogListPage/StructuredData';
import type {Props} from '@theme/BlogListPage';
import CarnetsSubscribe from '@site/src/components/CarnetsSubscribe';

function BlogListPageMetadata(props: Props): React.ReactElement {
  const {metadata} = props;
  const {
    siteConfig: {title: siteTitle},
  } = useDocusaurusContext();
  const {blogDescription, blogTitle, permalink} = metadata;
  const isBlogOnlyMode = permalink === '/';
  const title = isBlogOnlyMode ? siteTitle : blogTitle;
  return (
    <>
      <PageMetadata title={title} description={blogDescription} />
      <SearchMetadata tag="blog_posts_list" />
    </>
  );
}

function SubscribeBanner(): React.ReactElement {
  const {
    i18n: {currentLocale},
  } = useDocusaurusContext();
  const fr = currentLocale === 'fr';
  const heading = fr ? 'Carnets de MiniCloud' : 'Carnets de MiniCloud';
  const sub = fr
    ? 'Recevoir un e-mail à chaque nouvel article — le choix, le compromis, et ce que j’ai pu vérifier.'
    : 'Get an email on every new post — the choice, the trade-off, and what I could verify.';
  const labels = fr
    ? {
        placeholder: 'vous@exemple.com',
        button: "S'abonner",
        sending: 'Envoi…',
        done: 'Presque fini — vérifiez votre boîte mail pour confirmer votre abonnement.',
        error: "Une erreur s'est produite. Merci de réessayer dans un instant.",
        privacy:
          "J'utilise votre e-mail uniquement pour envoyer les nouveaux articles. Aucun pistage, aucun partage — désabonnement en un clic.",
      }
    : {
        placeholder: 'you@example.com',
        button: 'Subscribe',
        sending: 'Sending…',
        done: 'Almost there — check your email to confirm your subscription.',
        error: 'Something went wrong. Please try again in a moment.',
        privacy:
          'I only use your email to send new posts. No tracking, no sharing — unsubscribe in one click.',
      };
  return (
    <div
      style={{
        border: '1px solid #e2e8ee',
        background: '#f7f9fb',
        borderRadius: 12,
        padding: '18px 20px',
        marginBottom: '2rem',
      }}>
      <div style={{fontSize: 17, fontWeight: 700, color: '#14212b'}}>{heading}</div>
      <div style={{color: '#4a5a66', fontSize: 14, margin: '4px 0 2px'}}>{sub}</div>
      <CarnetsSubscribe labels={labels} />
    </div>
  );
}

function BlogListPageContent(props: Props): React.ReactElement {
  const {metadata, items, sidebar} = props;
  const isFirstPage = !metadata.page || metadata.page === 1;
  return (
    <BlogLayout sidebar={sidebar}>
      {isFirstPage && <SubscribeBanner />}
      <BlogPostItems items={items} />
      <BlogListPaginator metadata={metadata} />
    </BlogLayout>
  );
}

export default function BlogListPage(props: Props): React.ReactElement {
  return (
    <HtmlClassNameProvider
      className={clsx(
        ThemeClassNames.wrapper.blogPages,
        ThemeClassNames.page.blogListPage,
      )}>
      <BlogListPageMetadata {...props} />
      <BlogListPageStructuredData {...props} />
      <BlogListPageContent {...props} />
    </HtmlClassNameProvider>
  );
}
