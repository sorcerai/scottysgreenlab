"""
GEO Content Engine — Brain Configuration

Model registry and search settings. All values read from env vars with sensible defaults.
"""

import os

# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

EMBEDDING_MODELS = {
    "nomic-embed-text-v1.5": {
        "type": "local",
        "dim": 768,
        "max_tokens": 8192,
        "query_prefix": "search_query: ",
        "passage_prefix": "search_document: ",
        "matryoshka_dims": [64, 128, 256, 512, 768],
        "normalize": True,
    },
    "e5-base-v2": {
        "type": "local",
        "dim": 768,
        "max_tokens": 512,
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "matryoshka_dims": None,
        "normalize": True,
    },
    "text-embedding-3-small": {
        "type": "openai",
        "dim": 1536,
        "max_tokens": 8191,
        "query_prefix": None,
        "passage_prefix": None,
        "matryoshka_dims": [256, 512, 1024, 1536],
        "normalize": True,
    },
    "embed-v3": {
        "type": "cohere",
        "dim": 1024,
        "max_tokens": 512,
        "input_types": {"query": "search_query", "passage": "search_document"},
        "normalize": True,
    },
}

# ---------------------------------------------------------------------------
# Environment-driven config
# ---------------------------------------------------------------------------

DB_URL = os.environ.get("BRAIN_DB_URL")
if not DB_URL:
    raise EnvironmentError(
        "BRAIN_DB_URL is required. Set it to your PostgreSQL connection string.\n"
        "Example: export BRAIN_DB_URL='postgresql://user:pass@host:5432/dbname'"
    )

ACTIVE_MODEL = os.environ.get("BRAIN_MODEL", "intfloat/e5-base-v2")
SEARCH_MODE = os.environ.get("BRAIN_SEARCH_MODE", "hybrid")  # vector, fulltext, hybrid
RERANKER = os.environ.get("BRAIN_RERANKER", "http://100.66.51.21:8002/predict/qwen-rerank")

# ---------------------------------------------------------------------------
# Search parameters
# ---------------------------------------------------------------------------

SEARCH_CONFIG = {
    "hybrid_k": 60,                # RRF smoothing constant
    "vector_weight": 0.7,
    "fulltext_weight": 0.3,
    "max_candidates": 50,          # Retrieved before re-ranking
    "max_results": 10,             # Returned after re-ranking
    "freshness_decay": 0.00385,    # Half-life ~180 days
    "freshness_weight": 0.2,       # Blend with similarity
}

# ---------------------------------------------------------------------------
# Analysis thresholds
# ---------------------------------------------------------------------------

CANNIBALIZATION_THRESHOLDS = {
    "near_duplicate": 0.95,
    "high_cannibal": 0.85,
    "moderate_overlap": 0.75,
}

CONTENT_GAP_THRESHOLD = 0.70

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_model_config():
    """Get config for the active embedding model."""
    if ACTIVE_MODEL not in EMBEDDING_MODELS:
        raise ValueError(f"Unknown model: {ACTIVE_MODEL}. Available: {list(EMBEDDING_MODELS.keys())}")
    return EMBEDDING_MODELS[ACTIVE_MODEL]

BATCH_SIZE = 32
