import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import inventory from '../data/inventory.json';
import questionsData from '../data/pseo-questions-final.json';

export function GET(context: APIContext) {
  const learnItems = (questionsData as any[]).map(q => ({
    title: q.question,
    description: q.semantic_matches?.[0]?.excerpt?.slice(0, 200) || q.question,
    link: `/learn/${q.slug}`,
    pubDate: new Date('2026-03-19'),
  }));

  const productItems = (inventory as any).items.map((item: any) => ({
    title: item.name,
    description: item.description,
    link: '/#menu',
    pubDate: new Date((inventory as any).batch_no),
  }));

  return rss({
    title: "Scotty's Gardening Lab",
    description: "Regenerative agriculture lab growing nutrient-dense food through living soil science and lacto-fermentation in Spring Branch, TX.",
    site: context.site!,
    items: [...learnItems, ...productItems],
  });
}
