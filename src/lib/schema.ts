/**
 * JSON-LD Schema generators — all data sourced from template.config.ts
 */

import {
  getBrand,
  getSiteUrl,
  getBusinessType,
  getOffices,
  getSocial,
} from './config';

type SchemaObject = Record<string, any>;

const ORG_ID = () => `${getSiteUrl()}/#organization`;
const WEBSITE_ID = () => `${getSiteUrl()}/#website`;

/**
 * Combine multiple schema objects into a single @graph array.
 */
export function graphSchema(...items: SchemaObject[]): SchemaObject {
  return {
    '@context': 'https://schema.org',
    '@graph': items.map(({ '@context': _, ...rest }) => rest),
  };
}

/**
 * Organization schema built from config.
 */
export function organizationSchema(): SchemaObject {
  const brand = getBrand();
  const biz = getBusinessType();
  const offices = getOffices();
  const social = getSocial();
  const siteUrl = getSiteUrl();

  const sameAs = [
    social.facebook,
    social.instagram,
    social.linkedin,
    social.twitter,
    social.youtube,
  ].filter((url): url is string => url !== undefined);

  return {
    '@context': 'https://schema.org',
    '@type': biz.schemaOrgType,
    '@id': ORG_ID(),
    name: brand.name,
    alternateName: brand.legalName,
    description: brand.description,
    disambiguatingDescription: brand.disambiguatingDescription,
    url: siteUrl,
    logo: `${siteUrl}${brand.logoPath}`,
    foundingDate: brand.foundingDate,
    knowsAbout: biz.knowsAbout,
    areaServed: {
      '@type': biz.areaServed.type,
      name: biz.areaServed.name,
    },
    serviceType: biz.serviceTypes,
    address: offices.map((office) => ({
      '@type': 'PostalAddress',
      streetAddress: office.street,
      addressLocality: office.city,
      addressRegion: office.region,
      postalCode: office.postalCode,
      addressCountry: office.country,
    })),
    contactPoint: offices.map((office) => ({
      '@type': 'ContactPoint',
      telephone: office.phone,
      contactType: 'sales',
    })),
    email: brand.email,
    sameAs,
    slogan: brand.tagline,
  };
}

/**
 * WebSite schema.
 */
export function websiteSchema(): SchemaObject {
  const brand = getBrand();
  const siteUrl = getSiteUrl();

  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': WEBSITE_ID(),
    name: brand.name,
    url: siteUrl,
    publisher: { '@id': ORG_ID() },
    potentialAction: {
      '@type': 'SearchAction',
      target: `${siteUrl}/blog?q={search_term_string}`,
      'query-input': 'required name=search_term_string',
    },
  };
}

/**
 * WebPage schema.
 */
export function webPageSchema(
  url: string,
  name: string,
  description: string,
  dateModified?: string,
): SchemaObject {
  const schema: SchemaObject = {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    '@id': url,
    url,
    name,
    description,
    isPartOf: { '@id': WEBSITE_ID() },
    publisher: { '@id': ORG_ID() },
  };

  if (dateModified) {
    schema.dateModified = dateModified;
  }

  return schema;
}

/**
 * Article schema with Speakable selectors for AI engines.
 */
export function articleSchema(article: {
  url: string;
  title: string;
  description: string;
  datePublished: string;
  dateModified?: string;
  author: string;
  image?: string;
}): SchemaObject {
  const siteUrl = getSiteUrl();

  const schema: SchemaObject = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: article.title,
    description: article.description,
    url: article.url,
    datePublished: article.datePublished,
    dateModified: article.dateModified || article.datePublished,
    author: {
      '@type': 'Organization',
      name: article.author,
      url: siteUrl,
    },
    publisher: { '@id': ORG_ID() },
    isPartOf: { '@id': WEBSITE_ID() },
    mainEntityOfPage: { '@id': article.url },
    speakable: {
      '@type': 'SpeakableSpecification',
      cssSelector: ['article h1', '[data-speakable]'],
    },
  };

  if (article.image) {
    schema.image = article.image;
  }

  return schema;
}

/**
 * BreadcrumbList schema.
 */
export function breadcrumbSchema(
  items: { name: string; url: string }[],
): SchemaObject {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

/**
 * FAQPage schema.
 */
export function faqSchema(
  faqs: { question: string; answer: string }[],
): SchemaObject {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map((faq) => ({
      '@type': 'Question',
      name: faq.question,
      acceptedAnswer: {
        '@type': 'Answer',
        text: faq.answer,
      },
    })),
  };
}

/**
 * DefinedTerm schema for AI engine definition cards.
 */
export function definedTermSchema(
  term: string,
  definition: string,
  url: string,
): SchemaObject {
  return {
    '@context': 'https://schema.org',
    '@type': 'DefinedTerm',
    name: term,
    description: definition,
    url,
    inDefinedTermSet: {
      '@type': 'DefinedTermSet',
      name: getBrand().name,
      url: getSiteUrl(),
    },
  };
}

/**
 * Dataset schema for structured data tables.
 */
export function datasetSchema(
  name: string,
  description: string,
  url: string,
  columns: string[],
): SchemaObject {
  return {
    '@context': 'https://schema.org',
    '@type': 'Dataset',
    name,
    description,
    url,
    creator: { '@id': ORG_ID() },
    variableMeasured: columns.map((col) => ({
      '@type': 'PropertyValue',
      name: col,
    })),
  };
}

/**
 * ClaimReview schema for contrarian content.
 */
export function claimReviewSchema(
  claim: string,
  verdict: string,
  url: string,
): SchemaObject {
  return {
    '@context': 'https://schema.org',
    '@type': 'ClaimReview',
    url,
    claimReviewed: claim,
    author: { '@id': ORG_ID() },
    reviewRating: {
      '@type': 'Rating',
      ratingValue: verdict,
      bestRating: 'True',
      worstRating: 'False',
      alternateName: verdict,
    },
    itemReviewed: {
      '@type': 'Claim',
      name: claim,
    },
  };
}
