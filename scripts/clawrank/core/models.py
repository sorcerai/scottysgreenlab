"""ClawRank data models.

ClawRankDocument is the universal intermediate format. Content flows through
the pipeline as structured data before being adapted to framework-specific output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Keyword models
# ---------------------------------------------------------------------------

@dataclass
class Keyword:
    """Single keyword with metadata."""
    keyword: str
    volume: int = 0
    difficulty: float = 0.0
    intent: str = "informational"        # informational, commercial, transactional
    cpc: float = 0.0
    source: str = ""                     # autocomplete, paa, competitor, academic, forum


@dataclass
class KeywordCluster:
    """Clustered keywords targeting the same page."""
    id: str
    primary_keyword: str
    keywords: list[Keyword] = field(default_factory=list)
    intent: str = "informational"
    content_type: str = "glossary"
    priority_score: float = 0.0
    estimated_volume: int = 0
    estimated_difficulty: float = 0.0
    entities: list[str] = field(default_factory=list)
    target_url: str = ""


# ---------------------------------------------------------------------------
# Entity models
# ---------------------------------------------------------------------------

@dataclass
class Entity:
    """Named entity in the niche (tool, brand, person, concept)."""
    name: str
    type: str = "tool"                   # tool, brand, person, concept, audience
    aliases: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    comparison_pairs: list[tuple[str, str]] = field(default_factory=list)
    content_opportunities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Evidence models
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    """Verified citation / source reference."""
    title: str
    url: str
    source_type: str = "web"             # web, academic, government, api, expert
    author: str = ""
    date: str = ""
    snippet: str = ""                    # Relevant excerpt
    verified: bool = False
    verification_method: str = ""        # manual, automated, crossref, etc.


@dataclass
class EvidenceCard:
    """Structured evidence from research."""
    claim: str                           # The specific, verifiable claim
    data_point: str = ""                 # e.g., "$45/month", "34% growth"
    source: Citation | None = None
    confidence: float = 1.0              # 0-1
    is_original: bool = False            # True if we compiled/analyzed this ourselves
    methodology: str = ""                # How we derived this


@dataclass
class ExpertQuote:
    """Real expert quote with attribution."""
    quote: str
    author: str
    title: str = ""                      # Author's title/role
    source_url: str = ""                 # Where the quote was found
    date: str = ""


# ---------------------------------------------------------------------------
# Content models -- the core ClawRankDocument
# ---------------------------------------------------------------------------

@dataclass
class SEOMeta:
    """SEO metadata for a content piece."""
    title_tag: str = ""                  # <60 chars
    meta_description: str = ""           # <155 chars
    canonical_url: str = ""
    og_title: str = ""
    og_description: str = ""
    og_image: str = ""
    twitter_card: str = "summary_large_image"
    robots: str = "index, follow"


@dataclass
class SchemaMarkup:
    """JSON-LD schema markup."""
    type: str                            # Article, Product, HowTo, etc.
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class InternalLink:
    """Internal link to another page on the site."""
    target_url: str
    anchor_text: str
    link_type: str = "contextual"        # contextual, breadcrumb, related, glossary
    position: str = ""                   # "first_200_words", "body", "footer"


@dataclass
class ContentSection:
    """A section of content with heading and body."""
    heading: str
    heading_level: int = 2               # H2 = 2, H3 = 3
    body: str = ""                       # Markdown content
    answer_target: bool = False          # Is this the GEO answer target?
    claims: list[EvidenceCard] = field(default_factory=list)


@dataclass
class FAQItem:
    """Single FAQ question/answer pair."""
    question: str
    answer: str


@dataclass
class ClawRankDocument:
    """Universal intermediate format for all content.

    This is the core data structure. Content flows through the pipeline
    as a ClawRankDocument, accumulating data at each stage, before being
    adapted to framework-specific output in Stage 20.
    """
    # Identity
    id: str                              # Unique content ID (e.g., "cmp-sba-vs-rbf")
    content_type: str                    # comparison, glossary, pillar, etc.
    cluster_id: str = ""                 # Source keyword cluster ID

    # Content
    title: str = ""                      # H1 headline
    slug: str = ""                       # URL slug
    target_url: str = ""                 # Full URL path
    body_markdown: str = ""              # Full body in Markdown
    sections: list[ContentSection] = field(default_factory=list)
    faq: list[FAQItem] = field(default_factory=list)
    word_count: int = 0

    # SEO
    seo: SEOMeta = field(default_factory=SEOMeta)
    schema_markup: list[SchemaMarkup] = field(default_factory=list)
    internal_links: list[InternalLink] = field(default_factory=list)
    target_keyword: str = ""
    secondary_keywords: list[str] = field(default_factory=list)

    # Research & Evidence
    evidence: list[EvidenceCard] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    expert_quotes: list[ExpertQuote] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)

    # Entities
    entities: list[str] = field(default_factory=list)
    entity_data: dict[str, Entity] = field(default_factory=dict)

    # Quality scores (set by quality gate)
    scores: dict[str, float] = field(default_factory=dict)
    quality_verdict: str = ""            # publish, revise, rewrite
    review_comments: list[dict[str, str]] = field(default_factory=list)

    # Pipeline metadata
    stage_history: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    run_id: str = ""
    batch_index: int = 0

    # Pillar/cluster relationships
    pillar_parent: str = ""              # URL of parent pillar page
    spoke_children: list[str] = field(default_factory=list)
    sibling_pages: list[str] = field(default_factory=list)

    # Scotty-specific
    pillar: str = ""                     # content pillar (e.g., "composting", "fermentation")
    related_products: list[str] = field(default_factory=list)
    matched_transcripts: list[dict] = field(default_factory=list)  # matched TikTok transcript chunks from brain DB
    has_strong_match: bool = False       # True if a strong transcript match was found
    brief_id: str = ""

    def update_timestamp(self) -> None:
        self.updated_at = datetime.now().isoformat()

    def add_stage(self, stage_name: str) -> None:
        self.stage_history.append(f"{stage_name}:{datetime.now().isoformat()}")
        self.update_timestamp()

    def total_citations(self) -> int:
        return len(self.citations) + sum(
            1 for e in self.evidence if e.source is not None
        )

    def citation_density(self) -> float:
        """Citations per 500 words."""
        if self.word_count == 0:
            return 0.0
        return (self.total_citations() / self.word_count) * 500


# ---------------------------------------------------------------------------
# Content plan models
# ---------------------------------------------------------------------------

@dataclass
class ContentPlanItem:
    """Single item in the content calendar."""
    priority: int
    cluster_id: str
    content_type: str
    title: str
    target_keyword: str
    target_url: str
    word_count_target: int
    entities: list[str] = field(default_factory=list)
    pillar_parent: str = ""
    research_requirements: list[str] = field(default_factory=list)
    schema_types: list[str] = field(default_factory=list)
    # Scotty-specific
    pillar: str = ""                     # content pillar (e.g., "composting", "fermentation")
    related_products: list[str] = field(default_factory=list)
    matched_transcripts: list[dict] = field(default_factory=list)  # matched TikTok transcript chunks from brain DB


@dataclass
class ContentPlan:
    """Full content plan for a pipeline run."""
    items: list[ContentPlanItem] = field(default_factory=list)
    total_planned: int = 0
    batch_size: int = 10
    current_batch: list[str] = field(default_factory=list)  # cluster IDs

    def get_batch(self, batch_index: int = 0) -> list[ContentPlanItem]:
        start = batch_index * self.batch_size
        end = start + self.batch_size
        return self.items[start:end]


# ---------------------------------------------------------------------------
# Niche analysis models
# ---------------------------------------------------------------------------

@dataclass
class NicheAnalysis:
    """Output of niche initialization and decomposition."""
    summary: str = ""
    market_maturity: str = ""            # emerging, growing, mature, saturated
    content_opportunity: str = ""        # high, medium, low
    subtopics: list[str] = field(default_factory=list)
    entity_categories: dict[str, list[str]] = field(default_factory=dict)
    data_sources: list[str] = field(default_factory=list)
    competitive_landscape: str = ""
    recommended_content_types: list[str] = field(default_factory=list)
    estimated_total_pages: str = ""


@dataclass
class TopicCluster:
    """A topic cluster with pillar and spokes."""
    pillar: str
    pillar_content_type: str = "pillar"
    spokes: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline result models
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    stage: int
    stage_name: str
    status: str = "done"
    artifacts: dict[str, str] = field(default_factory=dict)  # name -> file path
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_sec: float = 0.0


@dataclass
class PipelineResult:
    """Aggregate result from a full pipeline run."""
    run_id: str
    niche: str
    stages_completed: list[int] = field(default_factory=list)
    stages_failed: list[int] = field(default_factory=list)
    documents_generated: list[str] = field(default_factory=list)  # document IDs
    total_words: int = 0
    total_citations: int = 0
    avg_quality_score: float = 0.0
    lessons: list[str] = field(default_factory=list)
