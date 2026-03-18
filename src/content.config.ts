/**
 * Astro Content Collections — Blog
 *
 * Blog posts live in content/blog/ as MDX files.
 * The embed.py script also reads from this directory.
 */

import { defineCollection, z } from 'astro:content';

const blog = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    date: z.string(),
    updated: z.string().optional(),
    author: z.string().default("Scotty's Gardening Lab"),
    authorTitle: z.string().default('Team'),
    category: z.string().default('General'),
    tags: z.array(z.string()).default([]),
    targetKeyword: z.string().default(''),
    secondaryKeywords: z.array(z.string()).default([]),
    relatedProducts: z.array(z.string()).default([]),
    relatedVerticals: z.array(z.string()).default([]),
    status: z.enum(['draft', 'review', 'published']).default('draft'),
    cluster: z.string().optional(),
    clusterRole: z.enum(['pillar', 'spoke']).optional(),
  }),
});

export const collections = { blog };
