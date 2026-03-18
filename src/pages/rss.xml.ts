import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import inventory from '../data/inventory.json';

export function GET(context: APIContext) {
  return rss({
    title: "Scotty's Gardening Lab",
    description: "Regenerative agriculture lab growing nutrient-dense food through living soil science and lacto-fermentation in Spring Branch, TX.",
    site: context.site!,
    items: inventory.items.map(item => ({
      title: item.name,
      description: item.description,
      link: '/#menu',
      pubDate: new Date(inventory.batch_no),
    })),
  });
}
