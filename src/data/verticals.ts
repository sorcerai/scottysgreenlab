/**
 * Vertical (niche) definitions — Scotty's Gardening Lab
 */

export interface Vertical {
  id: string;
  slug: string;
  displayName: string;
  description: string;
  bestProductSlugs: string[];
  metadata?: Record<string, unknown>;
}

export const VERTICALS: Vertical[] = [
  {
    id: 'regenerative-agriculture',
    slug: 'regenerative-agriculture',
    displayName: 'Regenerative Agriculture',
    description: 'No-till, living soil farming that rebuilds soil biology and sequesters carbon while producing nutrient-dense food.',
    bestProductSlugs: ['living-soil-salad-mix', 'spicy-radishes', 'duck-eggs'],
  },
  {
    id: 'fermentation',
    slug: 'fermentation-preservation',
    displayName: 'Fermentation & Preservation',
    description: 'Lacto-fermented foods crafted using natural Lactobacillus bacteria. No vinegar, no heat — living food that supports gut health.',
    bestProductSlugs: ['fermented-kimchi', 'escabeche'],
  },
  {
    id: 'soil-science',
    slug: 'soil-science',
    displayName: 'Soil Science & Biology',
    description: 'The science of prokaryotic association, carbon cycling, and building soil immune systems through composting and no-till practices.',
    bestProductSlugs: ['living-soil-salad-mix', 'spicy-radishes'],
  },
];

export function getVerticalBySlug(slug: string): Vertical | undefined {
  return VERTICALS.find((v) => v.slug === slug);
}

export function getAllVerticalSlugs(): string[] {
  return VERTICALS.map((v) => v.slug);
}

export function getVerticalById(id: string): Vertical | undefined {
  return VERTICALS.find((v) => v.id === id);
}
