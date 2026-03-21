# ClawRank Customization for Scotty's Green Lab

**Date:** 2026-03-21
**Status:** Approved
**Approach:** B — Clean Port with Shared Core

## Summary

Port ClawRank's 23-stage content pipeline into scottysgreenlab as a full content engine. Copy the core engine from the nautix-website reference implementation. Write a fresh domain layer purpose-built for scottysgreenlab's Astro + JSON architecture, brain database, GPU model servers, and Scotty's voice.

## Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Scope | Full content engine (Option C) | New content generation + refresh + competitive monitoring + scheduling |
| LLM strategy | Mixed CLI (`gemini -p` light, `claude -p` heavy) + GPU models | No direct API; matches nautix pattern with GPU model enhancement |
| Publishing output | JSON into existing `/learn/` pipeline (Option A) | Keep everything uniform with current Astro architecture |
| Content types | All 8: how_to, pillar, comparison, gap_fill, deep_dive, listicle, seasonal, contrarian | Full coverage of gardening/composting/fermentation domain |
| Architecture | Approach B — shared core + fresh domain layer | Nautix MDX/Next.js assumptions would break Astro + JSON output |
| Scheduling | Both scheduled + manual | Daily research scans, weekly deep runs, manual triggers |

## File Structure

```
scripts/clawrank/
├── core/                      # Copied from nautix (engine)
│   ├── models.py              # ClawRankDocument, StageResult, etc.
│   ├── config_loader.py       # CRConfig dataclasses + validation
│   ├── prompts_loader.py      # PromptManager, variable rendering
│   ├── evolution.py           # JSONL lesson store, time-decay
│   ├── acpx_adapter.py        # Hybrid LLM routing (gemini -p, claude -p)
│   └── pipeline/
│       ├── executor.py        # Stage handler dispatch
│       └── stages.py          # 23 stage enum, gates, phases (executor.py contains orchestration)
│
├── scotty/                    # Fresh domain layer
│   ├── adapter.py             # Bridge: ClawRank <-> scottysgreenlab infra
│   ├── voice.py               # Load scotty-voice-profile.md -> prompt blocks
│   ├── sources.py             # GPU model clients + brain search + competitors
│   ├── publish.py             # ClawRankDocument -> JSON for /learn/ pipeline
│   ├── world_state.py         # Brain DB queries (pgvector, entity graph)
│   └── compliance.py          # Quality gates, banned phrases, voice enforcement
│
├── config.scotty.yaml         # Scottysgreenlab-specific config
├── prompts.scotty.yaml        # Custom prompts with voice blocks
├── run.py                     # CLI entry point (auto/batch/research modes)
├── decide.py                  # Decision engine (what to write next)
└── daily-run.sh               # Cron wrapper for scheduled runs
```

## Core Engine (From Nautix — Copy and Modify)

Files from `/repos/nautix-website/scripts/clawrank/` into `scripts/clawrank/core/`. None are verbatim copies — each requires scottysgreenlab-specific modifications noted below.

| File | ~Lines | Copy Status | Modifications Needed |
|------|--------|-------------|---------------------|
| models.py | 322 | Copy + modify | Replace nautix fields (ac_post_type, related_industries) with scotty fields (pillar, matched_transcripts, has_strong_match). Add `seasonal` to any content type references. |
| config_loader.py | 285 | Copy + modify | Add `brain` section (connection_env, database_id), `gpu_models` section (intent_classifier, query_fanout, sentiment, reranker, embedder URLs), `llm.heavy_backend` field for per-stage backend routing. |
| prompts_loader.py | 167 | Copy as-is | No modifications needed — generic template engine. |
| evolution.py | 223 | Copy as-is | No modifications needed — generic JSONL store. |
| acpx_adapter.py | ~700 | Copy + modify | Add per-stage backend routing (default_backend for light stages, heavy_backend for stages 12,13,15,20). Add `call_gpu_model(endpoint, payload)` method for HTTP calls to DEJAN servers. Add graceful degradation: GPU model failures return None, stage falls back to LLM-only. |
| pipeline/executor.py | 475 | Copy + modify | Executor contains orchestration + checkpoint/resume + gate handling (no separate runner.py exists in nautix). Wire scotty adapter calls into stage handlers. |
| pipeline/stages.py | 523 | Copy + modify | Add `seasonal` to ContentType enum + URL_PATTERNS + SCHEMA_MAP. Remove inapplicable nautix types (pricing, integration, alternatives). |

**Note:** No `pipeline/runner.py` — orchestration logic lives in `executor.py` (the `PipelineExecutor` class handles sequential execution, checkpointing, and gates).

**Also from nautix (copy + modify):**
| File | ~Lines | Purpose |
|------|--------|---------|
| discover.py | ~1883 | Competitive discovery utilities — needed for Stage 7. Modify competitor URLs and crawl patterns for gardening domain. |

## 23-Stage Pipeline

### Phase A: Niche Discovery (1-2)
- Stage 1: NICHE_INIT — Parse niche (regenerative ag, composting, fermentation, soil science)
- Stage 2: NICHE_DECOMPOSE — Topic clusters, entity extraction, audience segmentation

### Phase B: Keyword Intelligence (3-6)
- Stage 3: KEYWORD_STRATEGY — Search strategy from 6 seed keywords
- Stage 4: KEYWORD_COLLECT — **Query fan-out server (8789)** expands keywords + autocomplete + PAA
- Stage 5: KEYWORD_SCREEN [GATE] — **Intent classifier (8002)** screens and classifies intent
- Stage 6: ENTITY_EXTRACT — Extract entities (plants, techniques, bacteria, soil amendments)

### Phase C: Competitive Intelligence (7-8)
- Stage 7: COMPETITOR_ANALYSIS — Crawl 20 tracked competitors from competitors.json
- Stage 8: CONTENT_PLAN — Map clusters to 8 content types, prioritize, calendar

### Phase D: Deep Research (9-11)
- Stage 9: RESEARCH_BRIEF [GATE] — Per-piece brief with brain search for matching transcripts
- Stage 10: DATA_COLLECT — Mine transcript chunks, gov/academic sources
- Stage 11: EVIDENCE_BUILD — **Qwen3 reranker (8788)** ranks evidence by relevance

### Phase E: Content Generation (12-13)
- Stage 12: CONTENT_DRAFT — **claude -p** generates article in Scotty's voice (900s timeout)
- Stage 13: CONTENT_REFINE — **claude -p** refines based on quality scores

### Phase F: SEO/GEO Optimization (14-15)
- Stage 14: SEO_OPTIMIZE — Schema hints, meta tags, internal links to /learn/ slugs
- Stage 15: GEO_OPTIMIZE — Answer targets, attribution patterns, freshness signals

### Phase G: Quality Assurance (16-19)
- Stage 16: QUALITY_GATE [GATE] — compliance.py (6-dimension scoring, 75-point threshold)
- Stage 17: EDITORIAL_REVIEW — **Sentiment analyzer (8002)** checks tone against Scotty's voice
- Stage 18: CONTENT_REVISION — Revise based on review feedback
- Stage 19: LINK_VERIFY — Verify external links (noncritical)

### Phase H: Publishing (20-23)
- Stage 20: FRAMEWORK_ADAPT — ClawRankDocument -> JSON matching pseo-questions-final.json schema
- Stage 21: SITEMAP_GEN — Sitemap/robots hints (noncritical)
- Stage 22: PUBLISH — Write to data/content-pipeline/ + trigger brain embed
- Stage 23: KNOWLEDGE_ARCHIVE — Extract lessons to artifacts/clawrank/kb/lessons.jsonl

## Domain Layer Detail

### adapter.py
Central bridge between ClawRank core and scottysgreenlab infrastructure:
- `load_voice_rules()` -> reads src/data/scotty-voice-profile.md, returns prompt block
- `search_brain(query, top_k)` -> hybrid search (vector 0.7 + fulltext 0.3) against 1,720 transcript chunks
- `check_cannibalization(slug, embedding)` -> cosine similarity > 0.85 against existing articles
- `find_content_gaps()` -> topics competitors cover that Scotty doesn't
- `existing_articles()` -> parse pseo-questions-final.json for dedup/linking
- `internal_link_map()` -> build link catalog from /learn/ slugs + product pages
- `product_data()` -> 4 products (Living Soil Salad Mix, Fermented Kimchi, Escabeche, Spicy Radishes)
- `entity_graph()` -> query brain_entities (13 entities) + relationships (20)

### voice.py
Parses scotty-voice-profile.md into structured prompt blocks:
- Vocabulary fingerprint (bacteria 737x, pile 712x, soil 565x, y'all 462x)
- Banned phrases (delve, landscape, leverage, comprehensive, game-changer)
- Tone: conversational-scientific, Texas dialect, first-person experience
- Injected into stages 12, 13, 17, 18

### sources.py
HTTP clients for GPU models + brain subprocess:
- IntentClassifier (100.66.51.21:8002) -> Stage 5
- QueryFanout (100.66.51.21:8789) -> Stage 4
- SentimentAnalyzer (100.66.51.21:8002) -> Stage 17
- Reranker (100.66.51.21:8788) -> Stage 11
- BrainSearch -> subprocess wrapper for scripts/brain/search.py
- CompetitorData -> loads src/data/competitors.json (20 domains)

**Graceful degradation:** All GPU model clients have a `timeout=10s` and return `None` on connection failure. Stage behavior when GPU model is unavailable:
- Stage 4 (QueryFanout down): falls back to LLM-only keyword expansion via gemini -p
- Stage 5 (IntentClassifier down): falls back to LLM-based intent classification via gemini -p
- Stage 11 (Reranker down): skip reranking, use raw vector similarity scores
- Stage 17 (Sentiment down): skip sentiment check, rely on LLM editorial review only

### publish.py
Converts ClawRankDocument -> JSON matching existing pipeline:
- Full output schema per article: {question, slug, pillar, answer, sources, best_rerank_score, matched_transcripts, keywords, relevance_score, has_transcript_match, semantic_matches, best_vector_score, has_strong_match}
- Writes article JSON to data/content-pipeline/ batches
- Updates src/data/pseo-questions-final.json (the index that Astro reads for /learn/)
- Triggers scripts/brain/embed.py to index new content in brain DB

### world_state.py
Queries Ghost PostgreSQL (wiixc9eeb7) via psycopg2. Connection via env var BRAIN_DB_URL (matches existing scripts/brain/config.py convention).

Key queries:
- Document counts by type: `SELECT content_type, COUNT(*) FROM brain_documents GROUP BY content_type`
- Entity graph: `SELECT name, entity_type FROM brain_entities` + relationships via brain_entity_relationships (source_entity_id, target_entity_id, relationship_type, weight)
- Cannibalization: join brain_documents + brain_embeddings, cosine similarity > 0.85 threshold
- Competitor gaps: compare scotty content embeddings vs competitor domain content
- Article coverage by pillar: count articles per pillar from pseo-questions-final.json
- Embedding coverage: `SELECT d.id, e.embedding IS NOT NULL FROM brain_documents d LEFT JOIN brain_embeddings e ON e.document_id = d.id`

Brain DB schema reference:
- brain_documents: id, content_type, source_id, title, text, text_hash, metadata (jsonb), content_freshness, quality_score, topic_cluster, is_published, created_at, updated_at, tsv (tsvector)
- brain_embeddings: document_id, embedding (vector 768-dim), model, generation_id
- brain_entities: id, name, entity_type (Concept|Product|Geography|Organization), description
- brain_entity_relationships: id, source_entity_id, target_entity_id, relationship_type, weight, metadata

### compliance.py
Reimplements quality scoring for JSON output (existing content-quality.py is MDX-oriented and checks for MDX components like TLDRBlock/CTABlock). compliance.py adapts the same 6-dimension framework for ClawRank's JSON articles:
- Structural completeness (20%): word count (1500-3500), min H2 sections (3), FAQ items (4-8)
- SEO readiness (20%): title length (40-60 chars), meta desc (120-155 chars), internal links (3-8)
- Citation readiness (20%): data points (5+), named entities (3+), source attributions
- Content depth (15%): scenarios (2+), number density per 1k words (3+)
- Readability (10%): avg sentence length (<=20 words), paragraph length (<=75 words)
- Compliance (15%): Scotty-specific rules (no synthetic fertilizer claims, science-backed only, Houston/Spring Branch accuracy)
- 75-point publishing threshold
- Returns: {passed: bool, score: float, violations: list, dimension_scores: dict}

## Configuration

### config.scotty.yaml
Key settings:
- project.name: scottysgreenlab
- niche.topic: regenerative agriculture, composting, fermentation, soil science
- niche.entities: 4 products (no duck eggs)
- niche.geo_targets: Spring Branch TX, Houston TX
- llm.default_backend: gemini (light stages), llm.heavy_backend: claude (stages 12,13,15,20)
- gpu_models: intent_classifier (8002), query_fanout (8789), sentiment (8002), reranker (8788)
- brain.connection_env: BRAIN_DB_URL (matches existing scripts/brain/config.py)
- brain.database_id: wiixc9eeb7
- content.enabled_types: [how_to, pillar, comparison, gap_fill, deep_dive, listicle, seasonal, contrarian]
- publish.target_framework: astro
- publish.output_format: json
- publish.output_dir: data/content-pipeline/

### prompts.scotty.yaml
Reusable blocks:
- niche_constraint: 4 products, 6 pillars, Spring Branch TX context
- quality_standard: banned AI-slop + Scotty's voice rules
- geo_optimization: answer targets mentioning Scotty's Gardening Lab
- internal_linking: /learn/{slug} URL patterns

## Scheduling

### daily-run.sh
- Daily 6am CT: `run.py --mode research --auto-approve --backend gemini` (stages 1-8, scan for opportunities)
- Weekly Monday 2am CT: `run.py --mode auto --auto-approve --backend gemini` (full pipeline)
- Logs to artifacts/clawrank/logs/
- Prunes logs > 30 days

### Manual Triggers
- `python scripts/clawrank/run.py --mode auto` — decide.py picks action
- `python scripts/clawrank/run.py --mode batch --brief <path>` — write specific brief
- `python scripts/clawrank/run.py --mode research --keyword "hot composting houston"` — research specific topic (new CLI flag, not in nautix — needs implementation in run.py)
- `python scripts/clawrank/run.py --from-stage 12 --to-stage 23` — resume from checkpoint

## Artifacts Directory

```
artifacts/clawrank/
├── briefs/            # Research briefs (output of stages 1-8)
├── drafts/            # In-progress ClawRankDocuments
├── kb/
│   └── lessons.jsonl  # Evolution store
├── logs/              # Run logs
├── checkpoints/       # Stage checkpoint files for resume
└── decisions/         # Decision engine output
```

## Brain Database Integration

Database: scottysgreenlab-brain (wiixc9eeb7) on Timescale Cloud
- 1,720 transcript documents (359 videos, 428 sections, 933 paragraphs)
- 1,720 e5-base-v2 embeddings (768-dim)
- 13 entities, 20 relationships
- 20 competitor domains mapped
- Tables: brain_documents, brain_embeddings, brain_embedding_generations, brain_entities, brain_entity_relationships, brain_sources

ClawRank reads from brain for:
- Transcript evidence during research (stages 9-11)
- Cannibalization detection (world_state)
- Content gap analysis (world_state)

ClawRank writes to brain:
- New article embeddings after publishing (stage 22 triggers embed.py)
- New entities discovered during entity extraction (stage 6)
- Updated topic clusters (stages 1-2)
