/**
 * Comparison definitions — populated per-project.
 */

export interface Comparison {
  slug: string;
  productASlugs: string[];
  productBSlug: string;
  title: string;
  seoTitle: string;
  seoDescription: string;
  keyDifferences: string[];
}

export const COMPARISONS: Comparison[] = [];

export function getComparisonBySlug(slug: string): Comparison | undefined {
  return COMPARISONS.find((c) => c.slug === slug);
}

export function getAllComparisons(): Comparison[] {
  return COMPARISONS;
}

export function getAllComparisonSlugs(): string[] {
  return COMPARISONS.map((c) => c.slug);
}
