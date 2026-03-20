import { z } from 'zod';

// =============================================================================
// GEO Content Engine — Central Configuration
// =============================================================================
// Single source of truth. Every component reads from this config.
// =============================================================================

export const TemplateConfigSchema = z.object({
  brand: z.object({
    name: z.string(),
    legalName: z.string(),
    tagline: z.string(),
    description: z.string().max(160),
    disambiguatingDescription: z.string(),
    url: z.string().url(),
    email: z.string().email(),
    logoPath: z.string(),
    ogImagePath: z.string(),
    foundingDate: z.string(),
    locale: z.string().default('en_US'),
    timezone: z.string().default('America/Chicago'),
  }),
  businessType: z.object({
    schemaOrgType: z.string(),
    serviceTypes: z.array(z.string()),
    areaServed: z.object({
      type: z.enum(['Country', 'State', 'City']),
      name: z.string(),
    }),
    knowsAbout: z.array(z.string()),
  }),
  offices: z.array(z.object({
    name: z.string(),
    phone: z.string(),
    street: z.string(),
    city: z.string(),
    region: z.string(),
    postalCode: z.string(),
    country: z.string().default('US'),
  })),
  social: z.object({
    facebook: z.string().optional(),
    instagram: z.string().optional(),
    linkedin: z.string().optional(),
    twitter: z.string().optional(),
    youtube: z.string().optional(),
  }),
  analytics: z.object({
    gtmId: z.string().optional(),
    ga4Id: z.string().optional(),
    clarityId: z.string().optional(),
    posthogKey: z.string().optional(),
    bingVerification: z.string().optional(),
  }),
  crm: z.object({
    provider: z.enum(['ghl', 'hubspot', 'webhook', 'none']),
    pipelineId: z.string().optional(),
    stages: z.record(z.string(), z.string()).optional(),
  }),
  leadRouting: z.object({
    dqField: z.string(),
    dqValue: z.string(),
    webhookUrl: z.string().optional(),
    defaultSource: z.string().default('website'),
    assignTo: z.string().optional(),
  }),
  pseo: z.object({
    regionLabel: z.string().default('state'),
    localityLabel: z.string().default('city'),
    minLocalityPopulation: z.number().default(50000),
    majorLocalityPopulation: z.number().default(75000),
  }),
  content: z.object({
    primaryCta: z.object({
      text: z.string(),
      href: z.string(),
      trackingPrefix: z.string(),
    }),
    secondaryCta: z.object({
      text: z.string(),
      href: z.string(),
    }).optional(),
    brokerDisclaimer: z.string().optional(),
    complianceNotes: z.array(z.string()).default([]),
    copywritingFramework: z.enum(['ac', 'pas', 'aida', 'custom']).default('ac'),
  }),
  theme: z.object({
    fontFamily: z.string().default('Poppins'),
    fontWeights: z.array(z.string()).default(['400', '700']),
    colors: z.object({
      navy: z.string().default('#0B1F3A'),
      primary: z.string().default('#2563EB'),
      accent: z.string().default('#F59E0B'),
    }),
  }),
  audienceResearch: z.object({
    searchKeywords: z.array(z.string()),
    redditSubreddits: z.array(z.string()),
    redditSearchTerms: z.array(z.string()),
    excludeQueries: z.array(z.string()),
  }),
  brain: z.object({
    model: z.string().default('intfloat/e5-base-v2'),
    searchMode: z.enum(['vector', 'fulltext', 'hybrid']).default('hybrid'),
    reranker: z.string().default('cross-encoder/ms-marco-MiniLM-L-6-v2'),
  }),
});

export type TemplateConfig = z.infer<typeof TemplateConfigSchema>;

// =============================================================================
// PROJECT CONFIG — Scotty's Gardening Lab
// =============================================================================

const config: TemplateConfig = {
  brand: {
    name: "Scotty's Gardening Lab",
    legalName: "Scotty's Gardening Lab",
    tagline: "Dirt Is Dead. Soil Is Alive.",
    description: "Scotty's Gardening Lab grows nutrient-dense food using living soil and fermentation in Spring Branch, TX. Shop salad mix, kimchi, duck eggs, and more.",
    disambiguatingDescription: "Scotty's Gardening Lab is a regenerative agriculture operation in Spring Branch, Texas, producing nutrient-dense food through living soil science and lacto-fermentation. Not affiliated with any other gardening or laboratory businesses.",
    url: "https://scottysgardeninglab.com",
    email: "hello@scottysgardeninglab.com",
    logoPath: "/favicon.svg",
    ogImagePath: "/og-image.jpg",
    foundingDate: "2026",
    locale: "en_US",
    timezone: "America/Chicago",
  },

  businessType: {
    schemaOrgType: "LocalBusiness",
    serviceTypes: ["Regenerative Agriculture", "Fermented Foods", "Farm-to-Table Produce"],
    areaServed: { type: "City", name: "Spring Branch, Texas" },
    knowsAbout: [
      "Regenerative Agriculture",
      "Living Soil",
      "Fermentation",
      "Nutrient Density",
      "Composting",
      "Prokaryotic Association",
      "No-Till Farming",
      "Lacto-Fermentation",
    ],
  },

  offices: [
    {
      name: "Farm & Lab",
      phone: "+1-000-000-0000",
      street: "Spring Branch",
      city: "Spring Branch",
      region: "TX",
      postalCode: "78070",
      country: "US",
    },
  ],

  social: {
    instagram: "https://www.instagram.com/scottysgardeninglab",
  },

  analytics: {
    ga4Id: "G-DHRD5J7VRW",
  },

  crm: {
    provider: "none",
  },

  leadRouting: {
    dqField: "location",
    dqValue: "outside-tx",
    defaultSource: "website",
  },

  pseo: {
    regionLabel: "state",
    localityLabel: "city",
    minLocalityPopulation: 10000,
    majorLocalityPopulation: 25000,
  },

  content: {
    primaryCta: {
      text: "Get Living Food",
      href: "#menu",
      trackingPrefix: "menu",
    },
    secondaryCta: {
      text: "Join the Decay Cycle",
      href: "#compost",
    },
    complianceNotes: [],
    copywritingFramework: "ac",
  },

  theme: {
    fontFamily: "Space Grotesk",
    fontWeights: ["400", "700", "900"],
    colors: {
      navy: "#18181B",      // carbon
      primary: "#CCFF00",   // sprout
      accent: "#F5F5F0",    // isotope
    },
  },

  audienceResearch: {
    searchKeywords: [
      "living soil farming",
      "regenerative agriculture Texas",
      "fermented kimchi Spring Branch",
      "nutrient dense food Texas",
      "no-till farming Houston area",
      "lacto-fermentation benefits",
      "composting Spring Branch TX",
    ],
    redditSubreddits: ["composting", "gardening", "fermentation", "regenerativeag", "NoTillGrowers"],
    redditSearchTerms: ["living soil", "nutrient density", "fermentation preservation", "soil biology"],
    excludeQueries: ["scotty's gardening lab", "scottysgardeninglab"],
  },

  brain: {
    model: "intfloat/e5-base-v2",
    searchMode: "hybrid",
    reranker: "cross-encoder/ms-marco-MiniLM-L-6-v2",
  },
};

// Validate at import time
export default TemplateConfigSchema.parse(config);
