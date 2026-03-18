/**
 * Region definitions — Scotty's Gardening Lab
 * Local operation: Spring Branch, TX only.
 */

export interface Region {
  id: string;
  slug: string;
  displayName: string;
  abbreviation: string;
  population?: number;
  metadata?: Record<string, unknown>;
}

export const REGIONS: Region[] = [
  { id: 'texas', slug: 'texas', displayName: 'Texas', abbreviation: 'TX', population: 30029572 },
];

export function getRegionBySlug(slug: string): Region | undefined {
  return REGIONS.find((r) => r.slug === slug);
}

export function getAllRegionSlugs(): string[] {
  return REGIONS.map((r) => r.slug);
}

export function getRegionById(id: string): Region | undefined {
  return REGIONS.find((r) => r.id === id);
}
