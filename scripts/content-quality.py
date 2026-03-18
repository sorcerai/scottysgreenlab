#!/usr/bin/env python3
"""Content Quality Engine — configurable scoring, validation, and quality gating.

Automated quality scoring for MDX blog content across 6 weighted dimensions.
All thresholds, weights, and compliance rules are read from quality-config.json.

Usage:
  python3 scripts/content-quality.py content/blog/my-post.mdx          # Score single file
  python3 scripts/content-quality.py --all                              # Score all MDX files
  python3 scripts/content-quality.py --gate content/blog/my-post.mdx   # Gate check (exit 1 = blocked)
  python3 scripts/content-quality.py --all --decay                      # Find stale content
  python3 scripts/content-quality.py --all --csv                        # CSV output
  python3 scripts/content-quality.py --all --json                       # JSON output
  python3 scripts/content-quality.py --status draft                     # Filter by status
  python3 scripts/content-quality.py --ruleset financial_services file.mdx  # Override ruleset
  python3 scripts/content-quality.py --help                             # Show help
"""
from __future__ import annotations

import sys
import os
import re
import json
import glob as globmod
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONTENT_DIR = os.path.join(PROJECT_ROOT, 'content', 'blog')
QUALITY_CONFIG = os.path.join(PROJECT_ROOT, 'data', 'content-pipeline', 'quality-config.json')
TRACKING_DIR = os.path.join(PROJECT_ROOT, 'data', 'content-pipeline', 'tracking')

# All 9 MDX components in the template system
ALL_COMPONENTS = [
    'TLDRBlock', 'CTABlock', 'FAQSection', 'ComparisonTable',
    'DirectAnswerBlock', 'StatisticBlock', 'ExpertQuoteBlock',
    'UpdateBanner', 'MethodologySection',
]

REQUIRED_FIELDS = [
    'title', 'description', 'date', 'author', 'category', 'tags',
    'targetKeyword', 'status',
]


# =====================================================================
# Configuration
# =====================================================================

def load_config() -> dict:
    """Load quality-config.json. Falls back to embedded defaults."""
    if os.path.exists(QUALITY_CONFIG):
        with open(QUALITY_CONFIG) as f:
            return json.load(f)
    return _default_config()


def _default_config() -> dict:
    """Embedded defaults — used only when quality-config.json is missing."""
    return {
        'publish_gate_threshold': 75,
        'weights': {
            'structural_completeness': 0.20,
            'seo_readiness': 0.20,
            'citation_readiness': 0.20,
            'content_depth': 0.15,
            'readability': 0.10,
            'compliance': 0.15,
        },
        'thresholds': {
            'structural': {
                'min_word_count': 1500,
                'max_word_count': 3500,
                'required_components': ['TLDRBlock', 'FAQSection'],
                'min_cta_blocks': 2,
                'min_h2_sections': 3,
            },
            'seo': {
                'title_min_length': 40,
                'title_max_length': 60,
                'meta_desc_min_length': 120,
                'meta_desc_max_length': 155,
                'min_internal_links': 3,
                'max_internal_links': 8,
                'min_external_links': 1,
            },
            'citation': {
                'min_data_points': 5,
                'min_faq_items': 4,
                'max_faq_items': 8,
                'min_named_entities': 3,
            },
            'depth': {
                'min_scenarios': 2,
                'min_number_density_per_1k': 3,
            },
            'readability': {
                'max_avg_sentence_length': 20,
                'max_paragraph_words': 75,
                'max_filler_density_per_1k': 5,
                'max_passive_voice_pct': 10,
            },
        },
        'compliance_rulesets': {
            'general': {
                'banned_phrases': [
                    'guaranteed approval', 'guaranteed funding',
                    'no risk', '100% approval', 'instant approval',
                ],
                'required_disclaimers': [],
                'rate_rules': {'must_be_range': True, 'no_guarantees': True},
            },
        },
        'active_ruleset': 'general',
        'decay': {
            'stale_threshold_days': 180,
            'outdated_threshold_days': 365,
        },
    }


def get_ruleset(config: dict, override: str | None = None) -> dict:
    """Get the active compliance ruleset from config."""
    rulesets = config.get('compliance_rulesets', {})
    name = override or config.get('active_ruleset', 'general')
    return rulesets.get(name, rulesets.get('general', {}))


# =====================================================================
# Frontmatter parser (stdlib only, no pyyaml)
# =====================================================================

def parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Split MDX into (frontmatter_dict, body_content)."""
    if not raw.startswith('---'):
        return {}, raw
    parts = raw.split('---', 2)
    if len(parts) < 3:
        return {}, raw

    fm: dict = {}
    current_key: str | None = None
    current_list: list | None = None

    for line in parts[1].strip().split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('- ') and current_key is not None:
            val = stripped[2:].strip().strip('"').strip("'")
            if current_list is None:
                current_list = []
                fm[current_key] = current_list
            current_list.append(val)
            continue
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            current_key = key
            current_list = None
            if value == '[]':
                fm[key] = []
            elif value.startswith('[') and value.endswith(']'):
                items = value[1:-1].split(',')
                fm[key] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
            elif value:
                fm[key] = value
            else:
                fm[key] = value

    return fm, parts[2].strip()


# =====================================================================
# Text extraction utilities
# =====================================================================

def strip_mdx_to_text(body: str) -> str:
    """Strip JSX/HTML/MDX syntax to get plain text for analysis."""
    text = body
    # Remove self-closing JSX components
    text = re.sub(r'<\w+[^>]*/>', '', text)
    # Remove JSX components with content
    text = re.sub(r'<\w+[\s\S]*?(?:/>|</\w+>)', '', text)
    # Remove remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    # Remove JSX expressions
    text = re.sub(r'\{[^}]*\}', ' ', text)
    # Remove markdown link syntax, keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove markdown formatting
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Remove heading markers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def count_words(text: str) -> int:
    return len(text.split())


def get_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sentences = re.split(r'[.!?]+(?=\s|$)', text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip().split()) >= 3]


def get_paragraphs(body: str) -> list[str]:
    """Split body into paragraphs (by blank lines)."""
    cleaned = re.sub(r'<\w+[\s\S]*?(?:/>|</\w+>)', '', body)
    paras = re.split(r'\n\s*\n', cleaned)
    result = []
    for p in paras:
        p = p.strip()
        if p and not p.startswith('#') and not p.startswith('<') and not p.startswith('```'):
            p = re.sub(r'\*\*([^*]+)\*\*', r'\1', p)
            p = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', p)
            if len(p.split()) >= 5:
                result.append(p)
    return result


# =====================================================================
# Dimension Scorers
# Each returns (score_0_to_100, list_of_check_results)
# =====================================================================

def score_structural_completeness(fm: dict, body: str, config: dict) -> tuple[float, list[dict]]:
    """Score structural completeness: frontmatter, components, word count, sections."""
    checks = []
    t = config.get('thresholds', {}).get('structural', {})

    # Frontmatter completeness
    missing = [f for f in REQUIRED_FIELDS if not fm.get(f)]
    pct = (len(REQUIRED_FIELDS) - len(missing)) / len(REQUIRED_FIELDS) * 100
    if missing:
        checks.append({'name': 'frontmatter_complete', 'status': 'FAIL',
                        'detail': f'Missing: {", ".join(missing)}', 'score': pct})
    else:
        checks.append({'name': 'frontmatter_complete', 'status': 'PASS',
                        'detail': f'All {len(REQUIRED_FIELDS)} required fields present', 'score': 100})

    # Required components (TLDRBlock, FAQSection by default)
    required_components = t.get('required_components', ['TLDRBlock', 'FAQSection'])
    for comp in required_components:
        has_comp = f'<{comp}' in body
        checks.append({'name': f'{comp}_present', 'status': 'PASS' if has_comp else 'FAIL',
                        'detail': f'{comp} {"present" if has_comp else "missing"}',
                        'score': 100 if has_comp else 0})

    # CTABlock count with unique trackingIds
    cta_count = len(re.findall(r'<CTABlock', body))
    min_ctas = t.get('min_cta_blocks', 2)
    tracking_ids = re.findall(r'trackingId="([^"]+)"', body)
    unique_ids = len(set(tracking_ids))

    if cta_count >= min_ctas and unique_ids >= min_ctas:
        checks.append({'name': 'cta_blocks', 'status': 'PASS',
                        'detail': f'{cta_count} CTABlocks with {unique_ids} unique trackingIds',
                        'score': 100})
    elif cta_count >= min_ctas and unique_ids < min_ctas:
        checks.append({'name': 'cta_blocks', 'status': 'WARN',
                        'detail': f'{cta_count} CTABlocks but only {unique_ids} unique trackingIds (need {min_ctas})',
                        'score': 60})
    elif cta_count == 1:
        checks.append({'name': 'cta_blocks', 'status': 'WARN',
                        'detail': f'1 CTABlock (need {min_ctas})', 'score': 50})
    else:
        checks.append({'name': 'cta_blocks', 'status': 'FAIL',
                        'detail': f'No CTABlocks (need {min_ctas})', 'score': 0})

    # H2 sections
    h2s = re.findall(r'^##\s+(.+)', body, re.MULTILINE)
    h2_min = t.get('min_h2_sections', 3)
    if len(h2s) >= h2_min:
        checks.append({'name': 'h2_structure', 'status': 'PASS',
                        'detail': f'{len(h2s)} H2 sections', 'score': 100})
    elif len(h2s) >= 2:
        checks.append({'name': 'h2_structure', 'status': 'WARN',
                        'detail': f'{len(h2s)} H2 sections (recommend {h2_min}+)', 'score': 60})
    else:
        checks.append({'name': 'h2_structure', 'status': 'FAIL',
                        'detail': f'{len(h2s)} H2 sections (minimum {h2_min})', 'score': 20})

    # Word count
    text = strip_mdx_to_text(body)
    wc = count_words(text)
    wc_min = t.get('min_word_count', 1500)
    wc_max = t.get('max_word_count', 3500)
    if wc_min <= wc <= wc_max:
        checks.append({'name': 'word_count', 'status': 'PASS',
                        'detail': f'{wc:,} words (target: {wc_min:,}-{wc_max:,})', 'score': 100})
    elif wc < 500:
        checks.append({'name': 'word_count', 'status': 'FAIL',
                        'detail': f'{wc:,} words (minimum 500)', 'score': max(0, wc / 500 * 30)})
    elif wc < wc_min:
        checks.append({'name': 'word_count', 'status': 'WARN',
                        'detail': f'{wc:,} words (target: {wc_min:,}-{wc_max:,})', 'score': 60})
    else:
        checks.append({'name': 'word_count', 'status': 'WARN',
                        'detail': f'{wc:,} words (target: {wc_min:,}-{wc_max:,})', 'score': 70})

    # Bonus: additional components present
    bonus_components = ['DirectAnswerBlock', 'StatisticBlock', 'ExpertQuoteBlock']
    bonus_found = [c for c in bonus_components if f'<{c}' in body]
    if bonus_found:
        checks.append({'name': 'bonus_components', 'status': 'PASS',
                        'detail': f'Bonus: {", ".join(bonus_found)}',
                        'score': min(100, len(bonus_found) * 35)})

    avg_score = sum(c['score'] for c in checks) / len(checks) if checks else 0
    return avg_score, checks


def score_seo_readiness(fm: dict, body: str, config: dict) -> tuple[float, list[dict]]:
    """Score SEO signals: title, description, keywords, links, headings."""
    checks = []
    t = config.get('thresholds', {}).get('seo', {})

    # Title length
    title = fm.get('title', '')
    title_len = len(title)
    t_min = t.get('title_min_length', 40)
    t_max = t.get('title_max_length', 60)
    if t_min <= title_len <= t_max:
        checks.append({'name': 'title_length', 'status': 'PASS',
                        'detail': f'{title_len} chars (target: {t_min}-{t_max})', 'score': 100})
    elif title_len < t_min:
        checks.append({'name': 'title_length', 'status': 'WARN',
                        'detail': f'{title_len} chars (target: {t_min}-{t_max})', 'score': 50})
    elif title_len <= t_max + 10:
        checks.append({'name': 'title_length', 'status': 'WARN',
                        'detail': f'{title_len} chars (target: {t_min}-{t_max})', 'score': 70})
    else:
        checks.append({'name': 'title_length', 'status': 'WARN',
                        'detail': f'{title_len} chars (too long, target: {t_min}-{t_max})', 'score': 40})

    # Meta description length
    desc = fm.get('description', '')
    desc_len = len(desc)
    d_min = t.get('meta_desc_min_length', 120)
    d_max = t.get('meta_desc_max_length', 155)
    if desc_len == 0:
        checks.append({'name': 'meta_description', 'status': 'FAIL',
                        'detail': 'Missing meta description', 'score': 0})
    elif d_min <= desc_len <= d_max:
        checks.append({'name': 'meta_description', 'status': 'PASS',
                        'detail': f'{desc_len} chars (target: {d_min}-{d_max})', 'score': 100})
    elif desc_len < d_min:
        checks.append({'name': 'meta_description', 'status': 'WARN',
                        'detail': f'{desc_len} chars (target: {d_min}-{d_max})', 'score': 50})
    else:
        checks.append({'name': 'meta_description', 'status': 'WARN',
                        'detail': f'{desc_len} chars (target: {d_min}-{d_max})', 'score': 60})

    # Target keyword checks
    keyword = fm.get('targetKeyword', '').lower()
    if keyword:
        # Keyword in title
        kw_in_title = keyword in title.lower()
        checks.append({'name': 'keyword_in_title', 'status': 'PASS' if kw_in_title else 'WARN',
                        'detail': f'"{keyword}" {"found" if kw_in_title else "NOT found"} in title',
                        'score': 100 if kw_in_title else 30})

        # Keyword in first 100 words
        text = strip_mdx_to_text(body)
        first_100 = ' '.join(text.split()[:100]).lower()
        kw_in_first = keyword in first_100
        checks.append({'name': 'keyword_in_first_100', 'status': 'PASS' if kw_in_first else 'WARN',
                        'detail': f'"{keyword}" {"found" if kw_in_first else "NOT found"} in first 100 words',
                        'score': 100 if kw_in_first else 40})

        # Keyword in H2
        h2s = re.findall(r'^##\s+(.+)', body, re.MULTILINE)
        kw_in_h2 = any(keyword in h.lower() for h in h2s)
        checks.append({'name': 'keyword_in_h2', 'status': 'PASS' if kw_in_h2 else 'WARN',
                        'detail': f'"{keyword}" {"found" if kw_in_h2 else "NOT found"} in H2',
                        'score': 100 if kw_in_h2 else 50})
    else:
        checks.append({'name': 'target_keyword', 'status': 'FAIL',
                        'detail': 'No targetKeyword in frontmatter', 'score': 0})

    # Internal links (markdown links to /blog/ or relative, or href= internal links)
    md_internal = re.findall(r'\[(?:[^\]]+)\]\((/[^)]+)\)', body)
    jsx_internal = re.findall(r'href="(/[^"]+)"', body)
    internal = list(set(md_internal + jsx_internal))
    int_min = t.get('min_internal_links', 3)
    int_max = t.get('max_internal_links', 8)
    if int_min <= len(internal) <= int_max:
        checks.append({'name': 'internal_links', 'status': 'PASS',
                        'detail': f'{len(internal)} internal links (target: {int_min}-{int_max})',
                        'score': 100})
    elif len(internal) > int_max:
        checks.append({'name': 'internal_links', 'status': 'WARN',
                        'detail': f'{len(internal)} internal links (target: {int_min}-{int_max})',
                        'score': 70})
    elif len(internal) > 0:
        checks.append({'name': 'internal_links', 'status': 'WARN',
                        'detail': f'{len(internal)} internal links (minimum {int_min})',
                        'score': max(20, len(internal) / int_min * 60)})
    else:
        checks.append({'name': 'internal_links', 'status': 'FAIL',
                        'detail': f'0 internal links (minimum {int_min})', 'score': 0})

    # External links
    ext_md = re.findall(r'\[(?:[^\]]+)\]\((https?://[^)]+)\)', body)
    ext_jsx = re.findall(r'href="(https?://[^"]+)"', body)
    external = list(set(ext_md + ext_jsx))
    ext_min = t.get('min_external_links', 1)
    if len(external) >= ext_min:
        checks.append({'name': 'external_links', 'status': 'PASS',
                        'detail': f'{len(external)} external links', 'score': 100})
    else:
        checks.append({'name': 'external_links', 'status': 'WARN',
                        'detail': f'{len(external)} external links (recommend {ext_min}+)',
                        'score': 40 if len(external) > 0 else 0})

    # Heading hierarchy (no skipped levels)
    headings = re.findall(r'^(#{1,6})\s+', body, re.MULTILINE)
    levels = [len(h) for h in headings]
    hierarchy_ok = True
    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1] + 1:
            hierarchy_ok = False
            break
    checks.append({'name': 'heading_hierarchy', 'status': 'PASS' if hierarchy_ok else 'WARN',
                    'detail': f'Heading hierarchy {"valid" if hierarchy_ok else "has skipped levels"}',
                    'score': 100 if hierarchy_ok else 60})

    # Slug check (URL-friendly)
    slug = fm.get('slug', '')
    if not slug:
        # Slug is derived from filename, so this is informational
        checks.append({'name': 'slug_check', 'status': 'PASS',
                        'detail': 'Slug derived from filename', 'score': 100})
    elif re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', slug):
        checks.append({'name': 'slug_check', 'status': 'PASS',
                        'detail': f'Slug "{slug}" is URL-friendly', 'score': 100})
    else:
        checks.append({'name': 'slug_check', 'status': 'WARN',
                        'detail': f'Slug "{slug}" may not be URL-friendly', 'score': 50})

    avg_score = sum(c['score'] for c in checks) / len(checks) if checks else 0
    return avg_score, checks


def score_citation_readiness(fm: dict, body: str, config: dict) -> tuple[float, list[dict]]:
    """Score GEO/AEO citation-readiness: data density, attribution, entities, FAQ depth."""
    checks = []
    t = config.get('thresholds', {}).get('citation', {})

    # Named data points: specific numbers with context
    data_points = re.findall(
        r'\d+\.?\d*%|\$[\d,]+[KkMmBb]?\+?|\d{1,3}(?:,\d{3})+|\d+ (?:days?|hours?|months?|years?|weeks?|minutes?)',
        body
    )
    dp_min = t.get('min_data_points', 5)
    dp_count = len(data_points)
    if dp_count >= dp_min * 2:
        dp_score = 100
    elif dp_count >= dp_min:
        dp_score = 60 + (dp_count - dp_min) / max(1, dp_min) * 40
    else:
        dp_score = max(0, dp_count / max(1, dp_min) * 60)
    checks.append({'name': 'named_data_points',
                    'status': 'PASS' if dp_count >= dp_min else 'WARN',
                    'detail': f'{dp_count} data points (minimum {dp_min})',
                    'score': dp_score})

    # Attribution phrases
    attr_patterns = [
        'according to', 'data shows', 'research from', 'based on', 'source:',
        'per the', 'study by', 'report from', 'survey found', 'analysis shows',
        'statistics show', 'research indicates',
    ]
    body_lower = body.lower()
    attr_count = sum(1 for p in attr_patterns if p in body_lower)
    attr_min = 2
    if attr_count >= 4:
        attr_score = 100
    elif attr_count >= attr_min:
        attr_score = 60 + (attr_count - attr_min) / 2 * 20
    else:
        attr_score = max(0, attr_count / max(1, attr_min) * 60)
    checks.append({'name': 'attribution_phrases',
                    'status': 'PASS' if attr_count >= attr_min else 'WARN',
                    'detail': f'{attr_count} attribution phrases',
                    'score': attr_score})

    # Named entities (proper nouns, organizations, products)
    # Generic patterns — not hardcoded to any specific industry
    ent_min = t.get('min_named_entities', 3)
    # Look for capitalized multi-word names (heuristic for proper nouns)
    proper_nouns = re.findall(r'(?<!\. )(?<!\n)[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', body)
    # Also count common organizational patterns
    org_patterns = re.findall(r'(?:Inc\.|LLC|Corp\.|Ltd\.|Association|Bureau|Department|Administration|Commission|Agency)', body)
    # Acronyms (2+ uppercase letters)
    acronyms = re.findall(r'\b[A-Z]{2,}\b', body)
    # Deduplicate
    all_entities = set()
    for pn in proper_nouns:
        all_entities.add(pn.strip())
    for a in acronyms:
        if a not in ('THE', 'AND', 'FOR', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'ARE', 'HAS', 'HIS', 'HOW', 'ITS', 'MAY', 'NEW', 'NOW', 'OLD', 'SEE', 'WAY', 'WHO', 'DID', 'GET', 'LET', 'SAY', 'SHE', 'TOO', 'USE', 'FAQ', 'MDX', 'CSS', 'HTML', 'JSX', 'URL', 'API'):
            all_entities.add(a)
    entity_count = len(all_entities)
    if entity_count >= ent_min:
        ent_score = min(100, 70 + entity_count * 3)
    else:
        ent_score = max(0, entity_count / max(1, ent_min) * 70)
    checks.append({'name': 'named_entities',
                    'status': 'PASS' if entity_count >= ent_min else 'WARN',
                    'detail': f'{entity_count} named entities (minimum {ent_min})',
                    'score': ent_score})

    # FAQ item count
    faq_min = t.get('min_faq_items', 4)
    faq_max = t.get('max_faq_items', 8)
    faq_match = re.search(r'<FAQSection\s+questions=\{?\[', body)
    if faq_match:
        faq_block_start = faq_match.start()
        faq_questions = body[faq_block_start:].count('"question"') + body[faq_block_start:].count('question:')
        if faq_min <= faq_questions <= faq_max:
            faq_score = 100
        elif faq_questions > faq_max:
            faq_score = 80
        elif faq_questions >= 1:
            faq_score = max(30, faq_questions / faq_min * 70)
        else:
            faq_score = 20
        checks.append({'name': 'faq_items',
                        'status': 'PASS' if faq_questions >= faq_min else 'WARN',
                        'detail': f'{faq_questions} FAQ items (target: {faq_min}-{faq_max})',
                        'score': faq_score})
    else:
        checks.append({'name': 'faq_items', 'status': 'FAIL',
                        'detail': 'No FAQSection component found', 'score': 0})

    # Bonus: StatisticBlock with source attribution
    stat_blocks = re.findall(r'<StatisticBlock', body)
    has_stat_source = bool(re.search(r'<StatisticBlock[^>]*source=', body))
    if stat_blocks:
        stat_score = 100 if has_stat_source else 70
        checks.append({'name': 'statistic_blocks',
                        'status': 'PASS',
                        'detail': f'{len(stat_blocks)} StatisticBlock(s){"" if has_stat_source else " (add source attr for full credit)"}',
                        'score': stat_score})

    # TLDRBlock items count (speakable content)
    tldr_match = re.search(r'<TLDRBlock\s+items=\{?\[', body)
    if tldr_match:
        tldr_block = body[tldr_match.start():tldr_match.start() + 2000]
        tldr_items = len(re.findall(r'"[^"]{10,}"', tldr_block))
        tldr_min = 4
        if tldr_items >= tldr_min:
            tldr_score = 100
        else:
            tldr_score = max(0, tldr_items / max(1, tldr_min) * 70)
        checks.append({'name': 'tldr_citable_items',
                        'status': 'PASS' if tldr_items >= tldr_min else 'WARN',
                        'detail': f'{tldr_items} TLDR items (minimum {tldr_min})',
                        'score': tldr_score})

    avg_score = sum(c['score'] for c in checks) / len(checks) if checks else 0
    return avg_score, checks


def score_content_depth(fm: dict, body: str, config: dict) -> tuple[float, list[dict]]:
    """Score content depth: scenarios, number density, comparisons, unique angle."""
    checks = []
    t = config.get('thresholds', {}).get('depth', {})

    # Concrete scenarios
    scenario_patterns = [
        r'for example', r'for instance', r'consider a', r"let's say",
        r'scenario', r'case study', r'in practice', r'imagine',
        r'picture this', r'here\'s what that looks like',
        r'real.world example', r'suppose',
    ]
    scenario_count = sum(1 for p in scenario_patterns if re.search(p, body, re.IGNORECASE))
    min_scenarios = t.get('min_scenarios', 2)
    if scenario_count >= min_scenarios:
        scenario_score = 100
    elif scenario_count >= 1:
        scenario_score = 60
    else:
        scenario_score = 20
    checks.append({'name': 'scenarios',
                    'status': 'PASS' if scenario_count >= min_scenarios else 'WARN',
                    'detail': f'{scenario_count} scenario markers (minimum {min_scenarios})',
                    'score': scenario_score})

    # Number density (per 1000 words)
    text = strip_mdx_to_text(body)
    wc = count_words(text)
    numbers = re.findall(r'\d+\.?\d*%|\$[\d,]+[KkMmBb]?', body)
    density = len(numbers) / max(1, wc) * 1000
    min_density = t.get('min_number_density_per_1k', 3)
    if density >= min_density * 3:
        num_score = 100
    elif density >= min_density:
        num_score = 70
    elif density >= min_density * 0.5:
        num_score = 40
    else:
        num_score = 20
    checks.append({'name': 'number_density',
                    'status': 'PASS' if density >= min_density else 'WARN',
                    'detail': f'{len(numbers)} numbers ({density:.1f}/1K words, minimum {min_density})',
                    'score': num_score})

    # Comparison data present
    has_table = '<ComparisonTable' in body
    has_comparison_h2 = bool(re.search(r'^##.*(?:vs\.?|versus|compared?|comparison)', body, re.MULTILINE | re.IGNORECASE))
    has_list_comparison = bool(re.search(r'\*\*(?:Option|Choice|Alternative|Approach|Method|Plan)', body))
    comp_present = has_table or has_comparison_h2 or has_list_comparison
    comp_score = 100 if has_table else (70 if has_comparison_h2 or has_list_comparison else 30)
    checks.append({'name': 'comparison_data',
                    'status': 'PASS' if comp_present else 'WARN',
                    'detail': f'ComparisonTable: {"yes" if has_table else "no"}, comparison structure: {"yes" if has_comparison_h2 or has_list_comparison else "no"}',
                    'score': comp_score})

    # Unique angle detection
    unique_signals = 0
    if re.search(r'most (?:people|businesses|owners|companies) (?:think|believe|assume)', body, re.IGNORECASE):
        unique_signals += 1
    if re.search(r'(?:contrary to|despite|surprisingly|counterintuit)', body, re.IGNORECASE):
        unique_signals += 1
    if re.search(r'(?:the real|what.*don\'t tell|the truth|nobody)', body, re.IGNORECASE):
        unique_signals += 1
    if re.search(r'(?:insider|behind the scenes|what we see|in our experience)', body, re.IGNORECASE):
        unique_signals += 1
    if re.search(r'(?:common (?:myth|misconception|mistake)|myth)', body, re.IGNORECASE):
        unique_signals += 1
    checks.append({'name': 'unique_angle',
                    'status': 'PASS' if unique_signals >= 2 else 'WARN',
                    'detail': f'{unique_signals} uniqueness signals',
                    'score': min(100, unique_signals * 30 + 10)})

    avg_score = sum(c['score'] for c in checks) / len(checks) if checks else 0
    return avg_score, checks


def score_readability(fm: dict, body: str, config: dict) -> tuple[float, list[dict]]:
    """Score readability: sentence length, paragraph size, filler words, passive voice."""
    checks = []
    t = config.get('thresholds', {}).get('readability', {})
    text = strip_mdx_to_text(body)
    wc = count_words(text)

    # Average sentence length
    sentences = get_sentences(text)
    max_avg_sent = t.get('max_avg_sentence_length', 20)
    if sentences:
        avg_sent = sum(len(s.split()) for s in sentences) / len(sentences)
        if avg_sent <= max_avg_sent * 0.75:
            sent_score = 100
        elif avg_sent <= max_avg_sent:
            sent_score = 70
        else:
            sent_score = max(20, 100 - (avg_sent - max_avg_sent) * 10)
        checks.append({'name': 'avg_sentence_length',
                        'status': 'PASS' if avg_sent <= max_avg_sent else 'WARN',
                        'detail': f'{avg_sent:.1f} words/sentence (max {max_avg_sent})',
                        'score': sent_score})
    else:
        checks.append({'name': 'avg_sentence_length', 'status': 'WARN',
                        'detail': 'Could not parse sentences', 'score': 50})

    # Max paragraph length
    paragraphs = get_paragraphs(body)
    max_para_words = t.get('max_paragraph_words', 75)
    if paragraphs:
        max_para = max(len(p.split()) for p in paragraphs)
        long_paras = sum(1 for p in paragraphs if len(p.split()) > max_para_words)
        if max_para <= max_para_words * 0.67:
            para_score = 100
        elif max_para <= max_para_words:
            para_score = 70
        else:
            para_score = max(20, 100 - (max_para - max_para_words))
        checks.append({'name': 'paragraph_length',
                        'status': 'PASS' if max_para <= max_para_words else 'WARN',
                        'detail': f'Longest: {max_para} words, {long_paras} over {max_para_words}',
                        'score': para_score})
    else:
        checks.append({'name': 'paragraph_length', 'status': 'PASS',
                        'detail': 'No long paragraphs detected', 'score': 80})

    # Filler words
    filler_words = [
        'very', 'really', 'just', 'basically', 'actually',
        'literally', 'simply', 'obviously', 'clearly', 'definitely',
    ]
    max_filler_per_1k = t.get('max_filler_density_per_1k', 5)
    text_words = text.lower().split()
    filler_count = sum(1 for w in text_words if w.strip('.,!?;:') in filler_words)
    filler_per_1k = filler_count / max(1, wc) * 1000
    if filler_per_1k <= max_filler_per_1k:
        filler_score = 100
    elif filler_per_1k <= max_filler_per_1k * 2:
        filler_score = 60
    else:
        filler_score = max(10, 100 - filler_per_1k * 5)

    found_fillers = {}
    for w in filler_words:
        cnt = sum(1 for tw in text_words if tw.strip('.,!?;:') == w)
        if cnt > 0:
            found_fillers[w] = cnt
    filler_detail = ', '.join(f'{w}({c})' for w, c in sorted(found_fillers.items(), key=lambda x: -x[1])[:5])
    checks.append({'name': 'filler_words',
                    'status': 'PASS' if filler_per_1k <= max_filler_per_1k else 'WARN',
                    'detail': f'{filler_count} fillers ({filler_per_1k:.1f}/1K words) -- {filler_detail or "none"}',
                    'score': filler_score})

    # Passive voice estimation
    passive_patterns = [
        r'\b(?:is|are|was|were|been|being|be)\s+(?:\w+ed|known|given|shown|made|found|seen|done|taken|told|built|set)\b',
    ]
    passive_count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in passive_patterns)
    total_sentences = len(sentences) if sentences else 1
    passive_pct = passive_count / total_sentences * 100
    pv_max = t.get('max_passive_voice_pct', 10)
    if passive_pct <= pv_max:
        pv_score = 100
    elif passive_pct <= pv_max * 2:
        pv_score = 60
    else:
        pv_score = 30
    checks.append({'name': 'passive_voice',
                    'status': 'PASS' if passive_pct <= pv_max else 'WARN',
                    'detail': f'{passive_pct:.0f}% passive voice ({passive_count}/{total_sentences} sentences)',
                    'score': pv_score})

    avg_score = sum(c['score'] for c in checks) / len(checks) if checks else 0
    return avg_score, checks


def score_compliance(fm: dict, body: str, config: dict, ruleset_override: str | None = None) -> tuple[float, list[dict]]:
    """Score compliance: banned phrases, disclaimers, rate accuracy."""
    checks = []
    rules = get_ruleset(config, ruleset_override)

    # Banned phrases (zero tolerance)
    full_text = (body + ' ' + fm.get('description', '') + ' ' + fm.get('title', '')).lower()
    banned = rules.get('banned_phrases', [])
    violations = []
    for phrase in banned:
        if phrase.lower() in full_text:
            violations.append(phrase)

    if violations:
        checks.append({'name': 'banned_phrases', 'status': 'FAIL',
                        'detail': f'Violations: {", ".join(violations)}', 'score': 0})
    else:
        checks.append({'name': 'banned_phrases', 'status': 'PASS',
                        'detail': f'No banned phrases ({len(banned)} checked)', 'score': 100})

    # Required disclaimers
    required_disclaimers = rules.get('required_disclaimers', [])
    if required_disclaimers:
        missing_disclaimers = []
        for disc in required_disclaimers:
            disc_lower = disc.lower() if isinstance(disc, str) else disc.get('pattern', '').lower()
            disc_text = disc if isinstance(disc, str) else disc.get('pattern', '')
            found = disc_lower in full_text
            if not found:
                missing_disclaimers.append(disc_text)
        if missing_disclaimers:
            checks.append({'name': 'required_disclaimers', 'status': 'FAIL',
                            'detail': f'Missing: {", ".join(missing_disclaimers)}', 'score': 0})
        else:
            checks.append({'name': 'required_disclaimers', 'status': 'PASS',
                            'detail': f'All {len(required_disclaimers)} disclaimers present', 'score': 100})

    # Rate rules
    rate_rules = rules.get('rate_rules', {})
    if rate_rules.get('no_guarantees'):
        guarantee_patterns = [
            r'guaranteed?\s+rate', r'locked.in\s+rate', r'rate\s+(?:is|will be)\s+\d',
        ]
        guarantee_found = []
        for p in guarantee_patterns:
            if re.search(p, body, re.IGNORECASE):
                guarantee_found.append(p)
        if guarantee_found:
            checks.append({'name': 'rate_guarantees', 'status': 'FAIL',
                            'detail': 'Rate guarantee language detected', 'score': 0})
        else:
            checks.append({'name': 'rate_guarantees', 'status': 'PASS',
                            'detail': 'No rate guarantee issues', 'score': 100})

    if rate_rules.get('must_be_range'):
        # Find rate mentions: single rates like "5% APR" without range context
        single_rates = re.findall(r'(?<!\d[-\u2013])\b(\d+\.?\d*)\s*%\s*(?:APR|rate|interest)', body, re.IGNORECASE)
        range_rates = re.findall(r'(\d+\.?\d*)\s*[-\u2013]\s*(\d+\.?\d*)\s*%', body)
        if single_rates and not range_rates:
            checks.append({'name': 'rate_ranges', 'status': 'WARN',
                            'detail': f'Found single rates without ranges (rates should be ranges)',
                            'score': 40})
        elif range_rates or not single_rates:
            checks.append({'name': 'rate_ranges', 'status': 'PASS',
                            'detail': 'Rate mentions use ranges or no rates mentioned', 'score': 100})

    # If no specific checks were added beyond banned phrases, add a general pass
    if len(checks) == 1 and not required_disclaimers and not rate_rules:
        checks.append({'name': 'general_compliance', 'status': 'PASS',
                        'detail': 'General compliance checks passed', 'score': 100})

    avg_score = sum(c['score'] for c in checks) / len(checks) if checks else 0
    return avg_score, checks


# =====================================================================
# Master scoring orchestrator
# =====================================================================

def score_article(filepath: str, config: dict, ruleset_override: str | None = None) -> dict:
    """Score a single article across all dimensions."""
    if not os.path.exists(filepath):
        return {'error': f'File not found: {filepath}', 'total_score': 0, 'grade': 'F'}

    with open(filepath) as f:
        raw = f.read()

    fm, body = parse_frontmatter(raw)
    if not fm:
        return {'error': 'Could not parse frontmatter', 'total_score': 0, 'grade': 'F'}

    slug = os.path.basename(filepath).replace('.mdx', '')
    text = strip_mdx_to_text(body)
    word_count = count_words(text)

    # Score each dimension
    dimension_scores = {}
    all_checks = {}

    struct_score, struct_checks = score_structural_completeness(fm, body, config)
    dimension_scores['structural_completeness'] = struct_score
    all_checks['structural_completeness'] = struct_checks

    seo_score, seo_checks = score_seo_readiness(fm, body, config)
    dimension_scores['seo_readiness'] = seo_score
    all_checks['seo_readiness'] = seo_checks

    cite_score, cite_checks = score_citation_readiness(fm, body, config)
    dimension_scores['citation_readiness'] = cite_score
    all_checks['citation_readiness'] = cite_checks

    depth_score, depth_checks = score_content_depth(fm, body, config)
    dimension_scores['content_depth'] = depth_score
    all_checks['content_depth'] = depth_checks

    read_score, read_checks = score_readability(fm, body, config)
    dimension_scores['readability'] = read_score
    all_checks['readability'] = read_checks

    comp_score, comp_checks = score_compliance(fm, body, config, ruleset_override)
    dimension_scores['compliance'] = comp_score
    all_checks['compliance'] = comp_checks

    # Calculate weighted total
    weights = config.get('weights', {})
    total_weight = sum(weights.get(dim, 1.0 / 6) for dim in dimension_scores)
    total_score = sum(
        dimension_scores[dim] * weights.get(dim, 1.0 / 6)
        for dim in dimension_scores
    ) / total_weight

    # Grade
    grade = 'F'
    thresholds = {'A': 90, 'B': 75, 'C': 60, 'D': 45, 'F': 0}
    for g, threshold in sorted(thresholds.items(), key=lambda x: x[1], reverse=True):
        if total_score >= threshold:
            grade = g
            break

    # Publish gate
    gate_threshold = config.get('publish_gate_threshold', 75)
    gate_passed = True
    gate_blockers = []

    if total_score < gate_threshold:
        gate_passed = False
        gate_blockers.append(f'Score {total_score:.0f} < minimum {gate_threshold}')

    # Compliance is binary for the gate: ANY banned phrase = fail
    for c in all_checks.get('compliance', []):
        if c['name'] == 'banned_phrases' and c['status'] == 'FAIL':
            gate_passed = False
            gate_blockers.append(f'Zero-tolerance: {c["detail"]}')
        if c['name'] == 'required_disclaimers' and c['status'] == 'FAIL':
            gate_passed = False
            gate_blockers.append(f'Missing disclaimer: {c["detail"]}')

    # Structural requirements for gate
    for c in all_checks.get('structural_completeness', []):
        if c['status'] == 'FAIL' and c['name'] in ('TLDRBlock_present', 'FAQSection_present'):
            gate_passed = False
            gate_blockers.append(f'Required component: {c["detail"]}')

    # Top improvement opportunities
    improvements = []
    for dim, dim_checks in all_checks.items():
        for c in dim_checks:
            if c['status'] in ('FAIL', 'WARN') and c['score'] < 60:
                improvements.append({
                    'dimension': dim,
                    'check': c['name'],
                    'current_score': c['score'],
                    'detail': c['detail'],
                    'impact': weights.get(dim, 0.15) * (100 - c['score']),
                })
    improvements.sort(key=lambda x: x['impact'], reverse=True)

    return {
        'slug': slug,
        'filepath': filepath,
        'title': fm.get('title', ''),
        'status': fm.get('status', 'unknown'),
        'word_count': word_count,
        'date': fm.get('date', ''),
        'total_score': round(total_score, 1),
        'grade': grade,
        'gate_passed': gate_passed,
        'gate_blockers': gate_blockers,
        'dimension_scores': {k: round(v, 1) for k, v in dimension_scores.items()},
        'dimension_weights': {k: round(v, 2) for k, v in weights.items()},
        'checks': {dim: checks_list for dim, checks_list in all_checks.items()},
        'top_improvements': improvements[:5],
        'scored_at': datetime.now().isoformat(),
    }


# =====================================================================
# Content Decay Detection
# =====================================================================

def detect_decay(filepath: str, config: dict) -> dict | None:
    """Check if an article shows signs of content decay."""
    decay_cfg = config.get('decay', {})
    stale_days = decay_cfg.get('stale_threshold_days', 180)
    outdated_days = decay_cfg.get('outdated_threshold_days', 365)

    with open(filepath) as f:
        raw = f.read()
    fm, body = parse_frontmatter(raw)
    if not fm or fm.get('status') != 'published':
        return None

    slug = os.path.basename(filepath).replace('.mdx', '')
    date_str = fm.get('date', '')
    updated_str = fm.get('updated', date_str)
    signals = []

    # Age-based checks
    if updated_str:
        try:
            updated_date = datetime.strptime(updated_str, '%Y-%m-%d')
            age_days = (datetime.now() - updated_date).days

            if age_days > outdated_days:
                signals.append({
                    'type': 'age', 'severity': 'high',
                    'detail': f'Last updated {age_days} days ago (outdated threshold: {outdated_days})',
                })
            elif age_days > stale_days:
                signals.append({
                    'type': 'age', 'severity': 'medium',
                    'detail': f'Last updated {age_days} days ago (stale threshold: {stale_days})',
                })
        except ValueError:
            pass

    # Date sensitivity (stale year references)
    full_text = body + ' ' + fm.get('title', '') + ' ' + fm.get('description', '')
    year_matches = re.findall(r'202[0-9]', full_text)
    current_year = datetime.now().year
    stale_years = [y for y in year_matches if int(y) < current_year - 1]
    if stale_years:
        signals.append({
            'type': 'date_reference', 'severity': 'high',
            'detail': f'Contains stale year references: {", ".join(set(stale_years))}',
        })

    # "Current" language without recent update
    current_patterns = ['current rates', 'right now', 'as of 202', 'this year', 'this quarter']
    for pattern in current_patterns:
        if pattern.lower() in full_text.lower():
            if updated_str:
                try:
                    updated_date = datetime.strptime(updated_str, '%Y-%m-%d')
                    if (datetime.now() - updated_date).days > 90:
                        signals.append({
                            'type': 'temporal_language', 'severity': 'medium',
                            'detail': f'Uses "{pattern}" but last updated {updated_str}',
                        })
                        break
                except ValueError:
                    pass

    # Performance-based checks from tracking digests
    if os.path.isdir(TRACKING_DIR):
        perf_data = _load_performance_history(slug, TRACKING_DIR)
        if len(perf_data) >= 2:
            recent = perf_data[-1]
            previous = perf_data[-2]
            prev_impressions = previous.get('impressions', 0)
            cur_impressions = recent.get('impressions', 0)
            if prev_impressions > 50:
                change = (cur_impressions - prev_impressions) / max(prev_impressions, 1) * 100
                if change <= -20:
                    signals.append({
                        'type': 'performance', 'severity': 'medium',
                        'detail': f'Impressions dropped {change:.0f}% ({prev_impressions} -> {cur_impressions})',
                    })

    if not signals:
        return None

    max_severity = 'low'
    for s in signals:
        if s['severity'] == 'high':
            max_severity = 'high'
            break
        elif s['severity'] == 'medium':
            max_severity = 'medium'

    action = 'review'
    if max_severity == 'high':
        action = 'rewrite'
    elif max_severity == 'medium':
        action = 'update'

    return {
        'slug': slug,
        'title': fm.get('title', ''),
        'date': date_str,
        'updated': updated_str,
        'signals': signals,
        'max_severity': max_severity,
        'recommended_action': action,
    }


def _load_performance_history(slug: str, tracking_dir: str) -> list[dict]:
    """Load GSC performance data for a slug from digest files."""
    if not os.path.isdir(tracking_dir):
        return []
    digests = sorted(globmod.glob(os.path.join(tracking_dir, 'digest-*.json')))
    history = []
    for digest_path in digests:
        try:
            with open(digest_path) as f:
                digest = json.load(f)
            for article in digest.get('articles', []):
                if article.get('slug') == slug:
                    gsc = article.get('gsc_data', {})
                    history.append({
                        'date': digest.get('date', ''),
                        'clicks': gsc.get('clicks', 0),
                        'impressions': gsc.get('impressions', 0),
                        'avg_position': gsc.get('avg_position', 0),
                    })
                    break
        except (json.JSONDecodeError, OSError):
            continue
    return history


# =====================================================================
# Output formatters
# =====================================================================

STATUS_ICONS = {'PASS': '\u2705', 'WARN': '\u26a0\ufe0f ', 'FAIL': '\u274c'}


def _bar(score: float, width: int = 10) -> str:
    """Render a progress bar."""
    filled = int(score / 100 * width)
    return '\u2588' * filled + '\u2591' * (width - filled)


def _weighted_score(score: float, weight: float, max_points: int) -> float:
    """Calculate the weighted score contribution."""
    return score / 100 * max_points


def print_report(report: dict) -> None:
    """Print human-readable quality report."""
    if 'error' in report:
        print(f'\nERROR: {report["error"]}')
        return

    slug = report.get('slug', 'unknown')
    total = report.get('total_score', 0)
    gate = report.get('gate_passed', False)

    print()
    print(f'\u2550' * 55)
    print(f'  QUALITY REPORT: {slug}')
    print(f'\u2550' * 55)
    print()
    gate_label = '\u2705 PASS' if gate else '\u274c BLOCKED'
    print(f'  Overall Score: {total:.0f}/100  {gate_label}')

    if report.get('gate_blockers'):
        print()
        for blocker in report['gate_blockers']:
            print(f'  \u274c BLOCKER: {blocker}')

    print()

    # Dimension breakdown with bars
    weights = report.get('dimension_weights', {})
    dim_scores = report.get('dimension_scores', {})
    dim_labels = {
        'structural_completeness': 'Structural Completeness',
        'seo_readiness': 'SEO Readiness',
        'citation_readiness': 'Citation Readiness',
        'content_depth': 'Content Depth',
        'readability': 'Readability',
        'compliance': 'Compliance',
    }

    for dim_key, label in dim_labels.items():
        score = dim_scores.get(dim_key, 0)
        weight = weights.get(dim_key, 0)
        max_pts = int(weight * 100)
        weighted = _weighted_score(score, weight, max_pts)
        bar = _bar(score)
        print(f'  {label:<25} {bar}  {weighted:.0f}/{max_pts}')

        # Show individual checks
        dim_checks = report.get('checks', {}).get(dim_key, [])
        for c in dim_checks:
            icon = STATUS_ICONS.get(c['status'], '  ')
            print(f'    {icon} {c["detail"]}')

        print()

    # Top improvements
    if report.get('top_improvements'):
        print(f'  Top Improvements (by impact):')
        for i, imp in enumerate(report['top_improvements'][:5], 1):
            print(f'    {i}. {imp["check"]} ({imp["dimension"]}) -- {imp["detail"]}')
        print()

    print(f'  Status: {report.get("status", "unknown")}  |  Words: {report.get("word_count", 0):,}  |  Grade: {report.get("grade", "F")}')
    print()


def print_decay_report(decay: dict) -> None:
    """Print content decay report for a single article."""
    sev_map = {'low': 'INFO', 'medium': 'WARN', 'high': 'ALERT'}
    sev_icon = {'low': '\u2139\ufe0f ', 'medium': '\u26a0\ufe0f ', 'high': '\U0001f6a8'}
    sev = decay.get('max_severity', 'low')
    print(f'\n  {sev_icon.get(sev, "")}[{sev_map[sev]}] {decay["slug"]}')
    print(f'    Published: {decay["date"]}  |  Updated: {decay["updated"]}')
    print(f'    Action: {decay["recommended_action"].upper()}')
    for s in decay['signals']:
        print(f'    - [{s["severity"].upper()}] {s["detail"]}')


def output_csv_header() -> str:
    return 'slug,status,word_count,total_score,grade,gate,structural,seo,citation,depth,readability,compliance'


def output_csv_row(report: dict) -> str:
    d = report.get('dimension_scores', {})
    return ','.join([
        report.get('slug', ''),
        report.get('status', ''),
        str(report.get('word_count', 0)),
        f'{report.get("total_score", 0):.1f}',
        report.get('grade', 'F'),
        'pass' if report.get('gate_passed') else 'fail',
        f'{d.get("structural_completeness", 0):.0f}',
        f'{d.get("seo_readiness", 0):.0f}',
        f'{d.get("citation_readiness", 0):.0f}',
        f'{d.get("content_depth", 0):.0f}',
        f'{d.get("readability", 0):.0f}',
        f'{d.get("compliance", 0):.0f}',
    ])


def print_summary(reports: list[dict]) -> None:
    """Print summary for multi-file runs."""
    scores = [r['total_score'] for r in reports if 'error' not in r]
    grade_counts: dict[str, int] = {}
    for r in reports:
        g = r.get('grade', 'F')
        grade_counts[g] = grade_counts.get(g, 0) + 1
    gate_pass = sum(1 for r in reports if r.get('gate_passed'))
    gate_fail = len(reports) - gate_pass

    print(f'\n{"=" * 55}')
    print(f'  SUMMARY: {len(reports)} articles scored')
    if scores:
        print(f'  Average Score: {sum(scores) / len(scores):.0f}/100')
        print(f'  Range: {min(scores):.0f} - {max(scores):.0f}')
    grade_str = ', '.join(f'{g}:{c}' for g, c in sorted(grade_counts.items()))
    print(f'  Grade Distribution: {grade_str}')
    print(f'  Publish Gate: {gate_pass} pass, {gate_fail} blocked')
    print(f'{"=" * 55}')


def show_help() -> None:
    """Print help message."""
    print(__doc__)
    print('Arguments:')
    print('  <file.mdx>                    Score a single file')
    print('  --all                         Score all MDX files in content/blog/')
    print('  --gate <file.mdx>             Publish gate check (exit 1 if blocked)')
    print('  --status <draft|review|pub>   Filter by frontmatter status')
    print('  --ruleset <name>              Override active compliance ruleset')
    print('  --decay                       Detect stale/outdated content')
    print('  --csv                         Output as CSV')
    print('  --json                        Output as JSON')
    print('  --help                        Show this help message')
    print()
    print('Available rulesets (from quality-config.json):')
    config = load_config()
    for name in config.get('compliance_rulesets', {}):
        marker = ' (active)' if name == config.get('active_ruleset') else ''
        print(f'  - {name}{marker}')
    print()


# =====================================================================
# Main
# =====================================================================

def main():
    args = sys.argv[1:]
    files: list[str] = []
    validate_all = False
    status_filter: str | None = None
    ruleset_override: str | None = None
    json_output = False
    csv_output = False
    gate_mode = False
    decay_check = False

    if '--help' in args or '-h' in args:
        show_help()
        sys.exit(0)

    i = 0
    while i < len(args):
        if args[i] == '--all':
            validate_all = True
        elif args[i] == '--status' and i + 1 < len(args):
            status_filter = args[i + 1]
            i += 1
        elif args[i] == '--ruleset' and i + 1 < len(args):
            ruleset_override = args[i + 1]
            i += 1
        elif args[i] == '--json':
            json_output = True
        elif args[i] == '--csv':
            csv_output = True
        elif args[i] == '--gate':
            gate_mode = True
        elif args[i] == '--decay':
            decay_check = True
        elif not args[i].startswith('--'):
            files.append(args[i])
        i += 1

    # Resolve files
    if validate_all or (not files and not gate_mode):
        if not os.path.isdir(CONTENT_DIR):
            print(f'Content directory not found: {CONTENT_DIR}')
            print('No MDX files to process.')
            sys.exit(0)
        mdx_files = sorted(globmod.glob(os.path.join(CONTENT_DIR, '*.mdx')))
        if status_filter:
            filtered = []
            for f in mdx_files:
                with open(f) as fh:
                    raw = fh.read()
                fm, _ = parse_frontmatter(raw)
                if fm.get('status') == status_filter:
                    filtered.append(f)
            mdx_files = filtered
        files = mdx_files

    resolved: list[str] = []
    for f in files:
        if os.path.isabs(f):
            resolved.append(f)
        elif os.path.exists(f):
            resolved.append(os.path.abspath(f))
        else:
            candidate = os.path.join(PROJECT_ROOT, f)
            resolved.append(candidate if os.path.exists(candidate) else os.path.abspath(f))
    files = resolved

    if not files:
        print('No MDX files to process.')
        sys.exit(0)

    config = load_config()

    # Validate ruleset override
    if ruleset_override:
        available = list(config.get('compliance_rulesets', {}).keys())
        if ruleset_override not in available:
            print(f'Unknown ruleset: {ruleset_override}')
            print(f'Available: {", ".join(available)}')
            sys.exit(1)

    # Content decay mode
    if decay_check:
        print(f'\n=== Content Decay Detection ===')
        decay_results = []
        for filepath in files:
            result = detect_decay(filepath, config)
            if result:
                decay_results.append(result)

        if json_output:
            print(json.dumps(decay_results, indent=2))
        elif csv_output:
            print('slug,date,updated,severity,action,signals')
            for d in decay_results:
                sig_text = '; '.join(s['detail'] for s in d['signals'])
                print(f'{d["slug"]},{d["date"]},{d["updated"]},{d["max_severity"]},{d["recommended_action"]},"{sig_text}"')
        elif decay_results:
            for d in sorted(decay_results, key=lambda x: {'high': 0, 'medium': 1, 'low': 2}[x['max_severity']]):
                print_decay_report(d)
            print(f'\n  {len(decay_results)} articles flagged for review')
        else:
            print('  No content decay detected.')
        sys.exit(0)

    # Score mode
    all_reports = []
    any_gate_fail = False

    for filepath in files:
        report = score_article(filepath, config, ruleset_override)
        all_reports.append(report)
        if gate_mode and not report.get('gate_passed', True):
            any_gate_fail = True

    # Output
    if json_output:
        print(json.dumps(all_reports, indent=2, default=str))
    elif csv_output:
        print(output_csv_header())
        for r in all_reports:
            print(output_csv_row(r))
    else:
        for r in all_reports:
            print_report(r)

        # Summary for multi-file runs
        if len(all_reports) > 1:
            print_summary(all_reports)

    # Exit code
    if gate_mode:
        sys.exit(1 if any_gate_fail else 0)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
