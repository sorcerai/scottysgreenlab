-- =============================================================================
-- GEO Content Engine — Brain Database Schema
-- Requires: PostgreSQL 14+ with pgvector extension
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Documents — all content chunks live here
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS brain_documents (
    id SERIAL PRIMARY KEY,
    content_type VARCHAR(50) NOT NULL,     -- blog_post, blog_section, blog_paragraph, product, region, kb_chunk
    source_id VARCHAR(200) NOT NULL,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    text_hash VARCHAR(32) NOT NULL,
    metadata JSONB DEFAULT '{}',
    content_freshness TIMESTAMPTZ DEFAULT NOW(),
    quality_score REAL DEFAULT 0.0,
    topic_cluster VARCHAR(100),
    is_published BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(content_type, source_id)
);

-- Auto-generated full-text search vector (weighted: title=A, body=B)
ALTER TABLE brain_documents ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(text, '')), 'B')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_brain_documents_tsv ON brain_documents USING gin(tsv);
CREATE INDEX IF NOT EXISTS idx_brain_documents_metadata ON brain_documents USING gin(metadata jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_brain_documents_type ON brain_documents(content_type);
CREATE INDEX IF NOT EXISTS idx_brain_documents_freshness ON brain_documents(content_freshness DESC);
CREATE INDEX IF NOT EXISTS idx_brain_documents_quality ON brain_documents(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_brain_documents_cluster ON brain_documents(topic_cluster);

-- ---------------------------------------------------------------------------
-- Embeddings — vector storage with multi-model support
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS brain_embeddings (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES brain_documents(id) ON DELETE CASCADE,
    embedding vector(768),                 -- Adjust dimension per model config
    model_version VARCHAR(100) NOT NULL,
    generation_id INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, model_version)
);

-- Note: HNSW index is NOT created by default — only needed at 5K+ embeddings.
-- When needed: CREATE INDEX idx_brain_hnsw ON brain_embeddings USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=128);

-- ---------------------------------------------------------------------------
-- Embedding Generations — for model migration without downtime
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS brain_embedding_generations (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL UNIQUE,
    model_dim INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    document_count INTEGER DEFAULT 0
);

-- Active embeddings view
CREATE OR REPLACE VIEW brain_active_embeddings AS
SELECT be.*
FROM brain_embeddings be
JOIN brain_embedding_generations beg ON be.generation_id = beg.id
WHERE beg.is_active = true;

-- ---------------------------------------------------------------------------
-- Source Tracking — when each content type was last indexed
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS brain_sources (
    source_type VARCHAR(50) PRIMARY KEY,
    last_indexed_at TIMESTAMPTZ,
    document_count INTEGER DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Entity Graph — relational knowledge graph (no Apache AGE needed)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS brain_entities (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,      -- Product, Vertical, Geography, Concept, Person
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(200),
    description TEXT,
    url VARCHAR(500),
    aliases TEXT[] DEFAULT '{}',
    properties JSONB DEFAULT '{}',
    same_as TEXT[] DEFAULT '{}',           -- Wikipedia/Wikidata URLs for AI engine entity linking
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_type, slug)
);

CREATE TABLE IF NOT EXISTS brain_entity_relationships (
    id SERIAL PRIMARY KEY,
    source_entity_id INTEGER REFERENCES brain_entities(id) ON DELETE CASCADE,
    target_entity_id INTEGER REFERENCES brain_entities(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL, -- serves_vertical, available_in, competes_with, part_of, related_to, best_for
    weight REAL DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    UNIQUE(source_entity_id, target_entity_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_entity_rels_source ON brain_entity_relationships(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_rels_target ON brain_entity_relationships(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_rels_type ON brain_entity_relationships(relationship_type);
CREATE INDEX IF NOT EXISTS idx_entities_type ON brain_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_slug ON brain_entities(slug);
