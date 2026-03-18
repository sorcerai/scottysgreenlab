/**
 * Product definitions — Scotty's Gardening Lab
 */

export interface Product {
  id: string;
  slug: string;
  displayName: string;
  shortName: string;
  tagline: string;
  description: string;
  seoTitle: string;
  seoDescription: string;
  features: string[];
  benefits: string[];
  faqs: { question: string; answer: string }[];
  customFields?: Record<string, unknown>;
}

export const PRODUCTS: Product[] = [
  {
    id: 'living-soil-salad-mix',
    slug: 'living-soil-salad-mix',
    displayName: 'Living Soil Salad Mix',
    shortName: 'Salad Mix',
    tagline: 'Grown in soil with full prokaryotic association',
    description: 'Nutrient-dense salad greens grown in living soil with billions of beneficial microorganisms per gram. No synthetic fertilizers, no tilling — just real soil biology producing food the way nature intended.',
    seoTitle: 'Living Soil Salad Mix | Scotty\'s Gardening Lab',
    seoDescription: 'Nutrient-dense salad mix grown in living soil with full prokaryotic association. Up to 300% higher nutrient density. Spring Branch, TX.',
    features: ['Full prokaryotic association', 'No-till grown', 'Lab-tested nutrient density', 'Harvested same-day'],
    benefits: ['Up to 300% higher nutrient density', 'Bio-available vitamins and minerals', 'Supports local regenerative agriculture'],
    faqs: [
      { question: 'How is your salad mix different from store-bought?', answer: 'Our greens are grown in living soil with full prokaryotic association — billions of beneficial microorganisms feeding the plants bio-available nutrients. Lab-tested at up to 300% higher nutrient density compared to conventional produce.' },
    ],
    customFields: { price: '$8.00', unit: 'bag' },
  },
  {
    id: 'fermented-kimchi',
    slug: 'fermented-kimchi',
    displayName: 'Fermented Kimchi (16oz)',
    shortName: 'Kimchi',
    tagline: 'A seven-vegetable biodiversity bomb',
    description: 'Lacto-fermented kimchi made with seven vegetables. 100% fermentation-derived sourness — no vinegar. Packed with Lactobacillus bacteria that support gut microbiome diversity.',
    seoTitle: 'Lacto-Fermented Kimchi | Scotty\'s Gardening Lab',
    seoDescription: 'Probiotic-rich lacto-fermented kimchi. Seven vegetables, no vinegar, living bacteria. Handcrafted in Spring Branch, TX.',
    features: ['Seven-vegetable blend', 'No vinegar — pure lacto-fermentation', 'Living Lactobacillus cultures', 'Small-batch crafted'],
    benefits: ['Supports gut microbiome diversity', 'Probiotic-rich living food', 'Natural preservation without heat processing'],
    faqs: [
      { question: 'Why no vinegar in your kimchi?', answer: 'We use lacto-fermentation — naturally occurring Lactobacillus bacteria convert sugars into lactic acid. This creates genuine sourness and preserves the food while keeping beneficial bacteria alive. Vinegar kills the bacteria.' },
    ],
    customFields: { price: '$12.00', unit: '16oz jar' },
  },
  {
    id: 'escabeche',
    slug: 'escabeche',
    displayName: 'Escabeche',
    shortName: 'Escabeche',
    tagline: 'Crunchy, spicy, and alive',
    description: 'Lacto-fermented escabeche with jalapenos, onions, and carrots. The bacteria ring on the bottom proves it\'s working. A living condiment that delivers probiotics with every bite.',
    seoTitle: 'Fermented Escabeche | Scotty\'s Gardening Lab',
    seoDescription: 'Lacto-fermented escabeche — jalapenos, onions, carrots. Probiotic-rich, naturally preserved. Spring Branch, TX.',
    features: ['Jalapenos, onions, carrots', 'Lacto-fermented — no vinegar', 'Visible bacteria ring', 'Crunchy texture preserved'],
    benefits: ['Living probiotic condiment', 'Adds gut-healthy bacteria to any meal', 'Traditional preservation method'],
    faqs: [
      { question: 'What is the ring at the bottom?', answer: 'That\'s the bacteria ring — a visible colony of Lactobacillus. It proves the escabeche is alive and actively fermenting. It\'s safe and beneficial.' },
    ],
    customFields: { price: '$10.00', unit: 'jar' },
  },
  {
    id: 'spicy-radishes',
    slug: 'spicy-radishes',
    displayName: 'Spicy Radishes (Bunch)',
    shortName: 'Radishes',
    tagline: 'Pulled from the ground this morning',
    description: 'Same-day harvested radishes from living soil. Grown without synthetic fertilizers or tilling. The soil biology produces radishes with intense flavor and maximum nutrient availability.',
    seoTitle: 'Living Soil Radishes | Scotty\'s Gardening Lab',
    seoDescription: 'Same-day harvested spicy radishes from living soil. No synthetic fertilizers, no-till. Spring Branch, TX.',
    features: ['Same-day harvest', 'Living soil grown', 'No synthetic fertilizers', 'No-till practice'],
    benefits: ['Peak freshness and flavor', 'Higher nutrient density', 'Supports soil regeneration'],
    faqs: [
      { question: 'When are the radishes harvested?', answer: 'Same day you pick them up. We pull them from living soil that morning to ensure peak freshness and maximum nutrient availability.' },
    ],
    customFields: { price: '$4.00', unit: 'bunch' },
  },
  {
    id: 'duck-eggs',
    slug: 'duck-eggs',
    displayName: 'Pasture-Raised Duck Eggs',
    shortName: 'Duck Eggs',
    tagline: 'The result of carbon capping and happy ducks',
    description: 'Pasture-raised duck eggs from ducks living on regeneratively managed land. Rich in omega-3s and fat-soluble vitamins. Part of the closed-loop carbon cycle at Scotty\'s Gardening Lab.',
    seoTitle: 'Pasture-Raised Duck Eggs | Scotty\'s Gardening Lab',
    seoDescription: 'Pasture-raised duck eggs from regeneratively managed land. Rich in omega-3s. Seasonal availability. Spring Branch, TX.',
    features: ['Pasture-raised on regenerative land', 'Part of closed-loop carbon cycle', 'Rich yolks', 'Seasonal availability'],
    benefits: ['Higher omega-3 content', 'Rich in fat-soluble vitamins', 'Supports regenerative land management'],
    faqs: [
      { question: 'Why duck eggs instead of chicken?', answer: 'Duck eggs have larger yolks with more fat-soluble vitamins and omega-3s. Our ducks are part of the regenerative cycle — they forage on the land and their waste feeds the soil biology.' },
    ],
    customFields: { price: 'seasonal', unit: 'dozen' },
  },
];

export function getProductBySlug(slug: string): Product | undefined {
  return PRODUCTS.find((p) => p.slug === slug);
}

export function getAllProductSlugs(): string[] {
  return PRODUCTS.map((p) => p.slug);
}

export function getProductById(id: string): Product | undefined {
  return PRODUCTS.find((p) => p.id === id);
}
