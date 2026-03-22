"""
scotty/compliance.py -- Quality scoring for JSON articles (6-dimension framework).

This is the JSON-native counterpart to content-quality.py (which is MDX-oriented).
Scores an article dict across 6 weighted dimensions and returns a pass/fail gate result.

Dimensions and weights:
    structural_completeness  0.20  word count, H2 sections, FAQ items
    seo_readiness            0.20  title length, meta desc length, internal/external links
    citation_readiness       0.20  data points, named entities, source attributions
    content_depth            0.15  scenarios, number density
    readability              0.10  avg sentence length, paragraph length
    compliance               0.15  banned phrases, science-backed only, location accuracy

Gate threshold: 75 (out of 100)

Input article dict keys:
    title           str
    body            str
    sections        list[{heading: str}]
    faq             list[{q: str, a: str}]
    sources         list[str]
    meta_description str
    internal_links  list[str]
    external_links  list[str]   (optional)
    entities        list[str]   (optional)
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GATE_THRESHOLD = 75

WEIGHTS: dict[str, float] = {
    "structural_completeness": 0.20,
    "seo_readiness": 0.20,
    "citation_readiness": 0.20,
    "content_depth": 0.15,
    "readability": 0.10,
    "compliance": 0.15,
}

# Banned AI-slop phrases (case-insensitive)
BANNED_PHRASES: list[str] = [
    "delve",
    "delves",
    "landscape",
    "leverage",
    "comprehensive guide",
    "game-changer",
    "game changer",
    "synergy",
    "cutting-edge",
    "cutting edge",
    "robust",
    "streamline",
    "streamlines",
    "paradigm",
    "holistic approach",
    "in today's",
    "in the world of",
    "it's important to note",
    "it is important to note",
    "it's worth noting",
    "it is worth noting",
    "as an ai",
    "as a language model",
]

# Spring Branch is a Houston neighborhood, NOT a Hill Country town.
# The phrase "Spring Branch" followed by Hill Country context is a violation.
_SPRING_BRANCH_BAD_PATTERN = re.compile(
    r"spring branch.{0,60}hill country",
    re.IGNORECASE,
)

# Gut microbiome biology: soil bacteria do NOT permanently colonize the gut.
# Ban phrases that claim colonization / seeding / repopulation.
_GUT_COLONIZE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"repopulates?\s+(?:your\s+)?gut", re.IGNORECASE),
    re.compile(r"seeds?\s+(?:your\s+)?gut\s+microbiome", re.IGNORECASE),
    re.compile(r"colonizes?\s+(?:your\s+)?gut", re.IGNORECASE),
]

# Product category accuracy: kimchi is a FERMENTATION product, not a living soil product.
# Flag "kimchi" appearing within 80 chars of "living soil".
_KIMCHI_LIVING_SOIL_PATTERN = re.compile(
    r"kimchi.{0,80}living\s+soil|living\s+soil.{0,80}kimchi",
    re.IGNORECASE,
)

# Structural thresholds
MIN_WORD_COUNT = 1500
MAX_WORD_COUNT = 3500
MIN_H2_SECTIONS = 3
MIN_FAQ_ITEMS = 4
MAX_FAQ_ITEMS = 8

# SEO thresholds
TITLE_MIN = 40
TITLE_MAX = 60
META_MIN = 120
META_MAX = 155
MIN_INTERNAL_LINKS = 3
MAX_INTERNAL_LINKS = 8
MIN_EXTERNAL_LINKS = 1

# Citation thresholds
MIN_DATA_POINTS = 5
MIN_NAMED_ENTITIES = 3

# Depth thresholds
MIN_SCENARIOS = 2
NUMBER_DENSITY_PER_1K = 3

# Readability thresholds
MAX_AVG_SENTENCE_WORDS = 20
MAX_PARAGRAPH_WORDS = 75


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _word_count(text: str) -> int:
    return len(text.split())


def _get_sentences(text: str) -> list[str]:
    """Split text into non-trivial sentences."""
    sentences = re.split(r"[.!?]+(?=\s|$)", text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip().split()) >= 3]


def _get_paragraphs(text: str) -> list[str]:
    """Split body into paragraphs by blank lines; skip headings."""
    paras = re.split(r"\n\s*\n", text)
    result = []
    for p in paras:
        p = p.strip()
        if p and not p.startswith("#") and len(p.split()) >= 5:
            result.append(p)
    return result


def _count_numbers(text: str) -> int:
    """Count standalone numbers (integers and decimals) in text."""
    return len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))


def _count_data_points(text: str) -> int:
    """
    Rough count of factual data points: numbers, percentages, temperatures,
    named statistics, and attribution phrases like 'according to' or 'studies show'.
    """
    numbers = _count_numbers(text)
    attributions = len(re.findall(
        r"\b(?:according to|studies show|research (?:shows|confirms|suggests)|"
        r"data shows|survey found|report found)\b",
        text,
        re.IGNORECASE,
    ))
    return numbers + attributions


def _count_scenarios(text: str) -> int:
    """
    Count scenario/example markers: 'for example', 'such as', 'if you',
    'imagine', 'consider', 'in a case where', etc.
    """
    return len(re.findall(
        r"\b(?:for example|such as|if you|imagine|consider|in a case where|"
        r"for instance|let's say)\b",
        text,
        re.IGNORECASE,
    ))


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _check_banned_phrases(text: str) -> list[str]:
    """
    Return a list of banned phrases found in text (case-insensitive).
    Each entry is the matched phrase.
    """
    found = []
    lower_text = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in lower_text:
            found.append(phrase)
    return found


# ---------------------------------------------------------------------------
# Dimension scorers — each returns (score_0_100, list_of_violation_strings)
# ---------------------------------------------------------------------------

def _score_structural_completeness(article: dict) -> tuple[float, list[str]]:
    """Word count 1500-3500, min H2 sections 3, FAQ items 4-8."""
    violations: list[str] = []
    scores: list[float] = []

    body = article.get("body", "")
    wc = _word_count(body)

    # Word count
    if MIN_WORD_COUNT <= wc <= MAX_WORD_COUNT:
        scores.append(100.0)
    elif wc < MIN_WORD_COUNT:
        ratio = wc / MIN_WORD_COUNT
        scores.append(max(0.0, ratio * 100))
        violations.append(f"word_count too low: {wc} (min {MIN_WORD_COUNT})")
    else:
        # Over max -- mild penalty
        overage = (wc - MAX_WORD_COUNT) / MAX_WORD_COUNT
        scores.append(max(50.0, 100.0 - overage * 50))
        violations.append(f"word_count too high: {wc} (max {MAX_WORD_COUNT})")

    # H2 sections
    sections = article.get("sections", [])
    n_sections = len(sections)
    if n_sections >= MIN_H2_SECTIONS:
        scores.append(100.0)
    else:
        ratio = n_sections / MIN_H2_SECTIONS if MIN_H2_SECTIONS else 0
        scores.append(ratio * 100)
        violations.append(f"sections too few: {n_sections} (min {MIN_H2_SECTIONS})")

    # FAQ items
    faq = article.get("faq", [])
    n_faq = len(faq)
    if MIN_FAQ_ITEMS <= n_faq <= MAX_FAQ_ITEMS:
        scores.append(100.0)
    elif n_faq < MIN_FAQ_ITEMS:
        ratio = n_faq / MIN_FAQ_ITEMS if MIN_FAQ_ITEMS else 0
        scores.append(ratio * 100)
        violations.append(f"faq_items too few: {n_faq} (min {MIN_FAQ_ITEMS})")
    else:
        scores.append(80.0)
        violations.append(f"faq_items too many: {n_faq} (max {MAX_FAQ_ITEMS})")

    return sum(scores) / len(scores), violations


def _score_seo_readiness(article: dict) -> tuple[float, list[str]]:
    """Title 40-60 chars, meta desc 120-155, internal links 3-8, external links 1+."""
    violations: list[str] = []
    scores: list[float] = []

    title = article.get("title", "")
    title_len = len(title)
    if TITLE_MIN <= title_len <= TITLE_MAX:
        scores.append(100.0)
    elif title_len < TITLE_MIN:
        ratio = title_len / TITLE_MIN if TITLE_MIN else 0
        scores.append(max(0.0, ratio * 100))
        violations.append(f"title too short: {title_len} chars (min {TITLE_MIN})")
    else:
        overage = (title_len - TITLE_MAX) / TITLE_MAX
        scores.append(max(50.0, 100.0 - overage * 100))
        violations.append(f"title too long: {title_len} chars (max {TITLE_MAX})")

    meta = article.get("meta_description", "")
    meta_len = len(meta)
    if META_MIN <= meta_len <= META_MAX:
        scores.append(100.0)
    elif meta_len < META_MIN:
        ratio = meta_len / META_MIN if META_MIN else 0
        scores.append(max(0.0, ratio * 100))
        violations.append(f"meta_description too short: {meta_len} chars (min {META_MIN})")
    else:
        overage = (meta_len - META_MAX) / META_MAX
        scores.append(max(50.0, 100.0 - overage * 100))
        violations.append(f"meta_description too long: {meta_len} chars (max {META_MAX})")

    internal_links = article.get("internal_links", [])
    n_int = len(internal_links)
    if MIN_INTERNAL_LINKS <= n_int <= MAX_INTERNAL_LINKS:
        scores.append(100.0)
    elif n_int < MIN_INTERNAL_LINKS:
        ratio = n_int / MIN_INTERNAL_LINKS if MIN_INTERNAL_LINKS else 0
        scores.append(ratio * 100)
        violations.append(f"internal_links too few: {n_int} (min {MIN_INTERNAL_LINKS})")
    else:
        scores.append(70.0)
        violations.append(f"internal_links too many: {n_int} (max {MAX_INTERNAL_LINKS})")

    external_links = article.get("external_links", [])
    n_ext = len(external_links)
    if n_ext >= MIN_EXTERNAL_LINKS:
        scores.append(100.0)
    else:
        scores.append(0.0)
        violations.append(f"external_links missing (min {MIN_EXTERNAL_LINKS})")

    return sum(scores) / len(scores), violations


def _score_citation_readiness(article: dict) -> tuple[float, list[str]]:
    """Data points 5+, named entities 3+, source attributions."""
    violations: list[str] = []
    scores: list[float] = []

    body = article.get("body", "")

    # Data points (numbers + attribution phrases in body)
    data_points = _count_data_points(body)
    if data_points >= MIN_DATA_POINTS:
        scores.append(100.0)
    else:
        ratio = data_points / MIN_DATA_POINTS if MIN_DATA_POINTS else 0
        scores.append(ratio * 100)
        violations.append(f"data_points too few: {data_points} (min {MIN_DATA_POINTS})")

    # Named entities (from article dict or extracted from body)
    entities = article.get("entities", [])
    n_entities = len(entities)
    if n_entities >= MIN_NAMED_ENTITIES:
        scores.append(100.0)
    else:
        ratio = n_entities / MIN_NAMED_ENTITIES if MIN_NAMED_ENTITIES else 0
        scores.append(ratio * 100)
        violations.append(f"named_entities too few: {n_entities} (min {MIN_NAMED_ENTITIES})")

    # Source attributions
    sources = article.get("sources", [])
    n_sources = len(sources)
    if n_sources >= MIN_DATA_POINTS:
        scores.append(100.0)
    else:
        ratio = n_sources / MIN_DATA_POINTS if MIN_DATA_POINTS else 0
        scores.append(ratio * 100)
        if n_sources == 0:
            violations.append("sources missing")
        else:
            violations.append(f"sources too few: {n_sources} (min {MIN_DATA_POINTS})")

    return sum(scores) / len(scores), violations


def _score_content_depth(article: dict) -> tuple[float, list[str]]:
    """Scenarios 2+, number density 3+ per 1k words."""
    violations: list[str] = []
    scores: list[float] = []

    body = article.get("body", "")
    wc = _word_count(body)

    # Scenarios
    n_scenarios = _count_scenarios(body)
    if n_scenarios >= MIN_SCENARIOS:
        scores.append(100.0)
    else:
        ratio = n_scenarios / MIN_SCENARIOS if MIN_SCENARIOS else 0
        scores.append(ratio * 100)
        violations.append(f"scenarios too few: {n_scenarios} (min {MIN_SCENARIOS})")

    # Number density per 1k words
    n_numbers = _count_numbers(body)
    density = (n_numbers / wc * 1000) if wc > 0 else 0
    if density >= NUMBER_DENSITY_PER_1K:
        scores.append(100.0)
    else:
        ratio = density / NUMBER_DENSITY_PER_1K if NUMBER_DENSITY_PER_1K else 0
        scores.append(ratio * 100)
        violations.append(
            f"number_density too low: {density:.1f}/1k words (min {NUMBER_DENSITY_PER_1K})"
        )

    return sum(scores) / len(scores), violations


def _score_readability(article: dict) -> tuple[float, list[str]]:
    """Avg sentence <= 20 words, paragraph <= 75 words."""
    violations: list[str] = []
    scores: list[float] = []

    body = article.get("body", "")

    # Avg sentence length
    sentences = _get_sentences(body)
    if sentences:
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
    else:
        avg_len = 0

    if avg_len <= MAX_AVG_SENTENCE_WORDS:
        scores.append(100.0)
    else:
        overage = (avg_len - MAX_AVG_SENTENCE_WORDS) / MAX_AVG_SENTENCE_WORDS
        scores.append(max(0.0, 100.0 - overage * 100))
        violations.append(f"avg_sentence_length too long: {avg_len:.1f} words (max {MAX_AVG_SENTENCE_WORDS})")

    # Paragraph word count
    paragraphs = _get_paragraphs(body)
    long_paras = [p for p in paragraphs if _word_count(p) > MAX_PARAGRAPH_WORDS]
    if not long_paras:
        scores.append(100.0)
    else:
        ratio = 1.0 - (len(long_paras) / len(paragraphs)) if paragraphs else 0
        scores.append(max(0.0, ratio * 100))
        violations.append(
            f"{len(long_paras)} paragraph(s) exceed {MAX_PARAGRAPH_WORDS} words"
        )

    return sum(scores) / len(scores), violations


def _score_compliance(article: dict) -> tuple[float, list[str]]:
    """Banned phrases, science-backed only, Houston/Spring Branch accuracy."""
    violations: list[str] = []
    scores: list[float] = []

    # Combine all text for phrase checks
    title = article.get("title", "")
    body = article.get("body", "")
    meta = article.get("meta_description", "")
    full_text = f"{title} {body} {meta}"

    # Banned phrases
    found_phrases = _check_banned_phrases(full_text)
    if not found_phrases:
        scores.append(100.0)
    else:
        penalty = min(100.0, len(found_phrases) * 15)
        scores.append(max(0.0, 100.0 - penalty))
        for phrase in found_phrases:
            violations.append(f"banned_phrase: \"{phrase}\"")

    # Location accuracy: Spring Branch is in Houston, not Hill Country
    if _SPRING_BRANCH_BAD_PATTERN.search(full_text):
        scores.append(0.0)
        violations.append(
            "location_error: Spring Branch is a Houston neighborhood, not a Hill Country town"
        )
    else:
        scores.append(100.0)

    # Gut microbiome biology: ban claims that soil bacteria colonizes/seeds/repopulates the gut
    gut_violations_found: list[str] = []
    for pattern in _GUT_COLONIZE_PATTERNS:
        match = pattern.search(full_text)
        if match:
            gut_violations_found.append(match.group())
    if gut_violations_found:
        scores.append(0.0)
        for phrase in gut_violations_found:
            violations.append(
                f'biology_error: "{phrase}" -- soil bacteria do NOT colonize the gut; '
                "they share DNA via horizontal gene transfer with resident microbes"
            )
    else:
        scores.append(100.0)

    # Product category accuracy: kimchi is fermentation, NOT living soil
    if _KIMCHI_LIVING_SOIL_PATTERN.search(full_text):
        scores.append(0.0)
        violations.append(
            "product_category_error: kimchi is a FERMENTATION product, not a living soil product -- "
            "living soil products are: Living Soil Salad Mix, Spicy Radishes"
        )
    else:
        scores.append(100.0)

    return sum(scores) / len(scores), violations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_article(article: dict) -> dict:
    """
    Score a JSON article dict across 6 dimensions.

    Returns:
        {
            "weighted_score": float,   # 0-100
            "passed": bool,            # True if weighted_score >= GATE_THRESHOLD (75)
            "dimension_scores": dict,  # {dimension: score_0_100}
            "violations": list[str],   # all violations collected
        }
    """
    dimension_results: dict[str, tuple[float, list[str]]] = {
        "structural_completeness": _score_structural_completeness(article),
        "seo_readiness": _score_seo_readiness(article),
        "citation_readiness": _score_citation_readiness(article),
        "content_depth": _score_content_depth(article),
        "readability": _score_readability(article),
        "compliance": _score_compliance(article),
    }

    dimension_scores: dict[str, float] = {}
    all_violations: list[str] = []

    weighted_score = 0.0
    for dim, (score, viols) in dimension_results.items():
        dimension_scores[dim] = round(score, 2)
        weighted_score += score * WEIGHTS[dim]
        all_violations.extend(viols)

    weighted_score = round(weighted_score, 2)

    return {
        "weighted_score": weighted_score,
        "passed": weighted_score >= GATE_THRESHOLD,
        "dimension_scores": dimension_scores,
        "violations": all_violations,
    }
