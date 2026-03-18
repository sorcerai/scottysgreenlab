#!/usr/bin/env python3
"""
GEO Content Engine — Hybrid Search CLI

Supports vector, full-text, and hybrid (RRF fusion) search modes
with optional cross-encoder re-ranking and freshness scoring.

Usage:
  python3 scripts/brain/search.py "query"
  python3 scripts/brain/search.py "query" --mode hybrid
  python3 scripts/brain/search.py "query" --mode vector
  python3 scripts/brain/search.py "query" --mode fulltext
  python3 scripts/brain/search.py "query" --type blog_section --limit 10
  python3 scripts/brain/search.py --related "blog:my-post:summary"
  python3 scripts/brain/search.py --stats
  python3 scripts/brain/search.py "query" --json
"""

import argparse
import json
import math
import sys
import warnings
from datetime import datetime, timezone

import numpy as np
import psycopg2

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import (
    DB_URL,
    ACTIVE_MODEL,
    RERANKER,
    SEARCH_CONFIG,
    SEARCH_MODE,
    get_model_config,
    BATCH_SIZE,
)

# ---------------------------------------------------------------------------
# Model (lazy singleton — shared with embed.py logic)
# ---------------------------------------------------------------------------
_model = None
_tokenizer = None


def get_model():
    """Load the active embedding model for query embedding."""
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    cfg = get_model_config()

    if cfg["type"] == "local":
        import torch
        from transformers import AutoModel, AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(ACTIVE_MODEL)
        _model = AutoModel.from_pretrained(ACTIVE_MODEL)
        _model.eval()
    elif cfg["type"] == "openai":
        _model = "openai"
        _tokenizer = None
    elif cfg["type"] == "cohere":
        _model = "cohere"
        _tokenizer = None

    return _model, _tokenizer


def embed_query(text: str) -> list[float]:
    """Embed a single query string, returning a list of floats."""
    cfg = get_model_config()
    model, tokenizer = get_model()

    if cfg["type"] == "local":
        import torch
        import torch.nn.functional as F

        prefix = cfg.get("query_prefix", "")
        prefixed = f"{prefix}{text}" if prefix else text
        max_tokens = cfg.get("max_tokens", 512)

        inputs = tokenizer(
            [prefixed], padding=True, truncation=True, max_length=max_tokens, return_tensors="pt"
        )
        with torch.no_grad():
            outputs = model(**inputs)
        attn = inputs["attention_mask"].unsqueeze(-1)
        emb = (outputs.last_hidden_state * attn).sum(1) / attn.sum(1)
        if cfg.get("normalize", True):
            emb = F.normalize(emb, p=2, dim=1)
        return emb[0].numpy().tolist()

    elif cfg["type"] == "openai":
        import openai

        client = openai.OpenAI()
        response = client.embeddings.create(model=ACTIVE_MODEL, input=[text])
        return response.data[0].embedding

    elif cfg["type"] == "cohere":
        import cohere

        client = cohere.Client()
        input_types = cfg.get("input_types", {})
        response = client.embed(
            texts=[text], model=ACTIVE_MODEL, input_type=input_types.get("query", "search_query")
        )
        return response.embeddings[0]

    else:
        raise ValueError(f"Unsupported model type: {cfg['type']}")


# ---------------------------------------------------------------------------
# Search modes
# ---------------------------------------------------------------------------


def vector_search(
    conn, vec: list[float], content_type: str = None, limit: int = 10
) -> list[dict]:
    """Pure cosine similarity search."""
    cur = conn.cursor()
    vec_str = str(vec)

    params = {"vec": vec_str, "content_type": content_type, "limit": limit}

    cur.execute(
        """
        SELECT bd.id, bd.content_type, bd.source_id, bd.title,
               LEFT(bd.text, 400) AS excerpt,
               1 - (be.embedding <=> %(vec)s::vector) AS similarity,
               bd.metadata, bd.content_freshness, bd.quality_score
        FROM brain_documents bd
        JOIN brain_embeddings be ON be.document_id = bd.id
        WHERE (%(content_type)s IS NULL OR bd.content_type = %(content_type)s)
        ORDER BY be.embedding <=> %(vec)s::vector
        LIMIT %(limit)s
        """,
        params,
    )
    return _rows_to_results(cur.fetchall())


def fulltext_search(
    conn, query_text: str, content_type: str = None, limit: int = 10
) -> list[dict]:
    """Pure BM25-style full-text search via tsvector."""
    cur = conn.cursor()

    params = {"query_text": query_text, "content_type": content_type, "limit": limit}

    cur.execute(
        """
        SELECT bd.id, bd.content_type, bd.source_id, bd.title,
               LEFT(bd.text, 400) AS excerpt,
               ts_rank_cd(bd.tsv, query) AS similarity,
               bd.metadata, bd.content_freshness, bd.quality_score
        FROM brain_documents bd, plainto_tsquery('english', %(query_text)s) query
        WHERE bd.tsv @@ query
        AND (%(content_type)s IS NULL OR bd.content_type = %(content_type)s)
        ORDER BY ts_rank_cd(bd.tsv, query) DESC
        LIMIT %(limit)s
        """,
        params,
    )
    return _rows_to_results(cur.fetchall())


def hybrid_search(
    conn, query_text: str, vec: list[float], content_type: str = None, limit: int = 10
) -> list[dict]:
    """RRF (Reciprocal Rank Fusion) combining vector + full-text search."""
    cur = conn.cursor()

    k = SEARCH_CONFIG["hybrid_k"]
    max_candidates = SEARCH_CONFIG["max_candidates"]
    vec_str = str(vec)

    params = {
        "vec": vec_str,
        "query_text": query_text,
        "content_type": content_type,
        "max_candidates": max_candidates,
        "k": k,
        "limit": limit,
    }

    cur.execute(
        """
        WITH vector_results AS (
            SELECT bd.id,
                   ROW_NUMBER() OVER (ORDER BY be.embedding <=> %(vec)s::vector) AS vrank
            FROM brain_documents bd
            JOIN brain_embeddings be ON be.document_id = bd.id
            WHERE (%(content_type)s IS NULL OR bd.content_type = %(content_type)s)
            ORDER BY be.embedding <=> %(vec)s::vector
            LIMIT %(max_candidates)s
        ),
        fulltext_results AS (
            SELECT bd.id,
                   ROW_NUMBER() OVER (ORDER BY ts_rank_cd(bd.tsv, query) DESC) AS frank
            FROM brain_documents bd, plainto_tsquery('english', %(query_text)s) query
            WHERE bd.tsv @@ query
            AND (%(content_type)s IS NULL OR bd.content_type = %(content_type)s)
            ORDER BY ts_rank_cd(bd.tsv, query) DESC
            LIMIT %(max_candidates)s
        )
        SELECT COALESCE(v.id, f.id) AS doc_id,
               COALESCE(1.0 / (%(k)s + v.vrank), 0) +
               COALESCE(1.0 / (%(k)s + f.frank), 0) AS rrf_score
        FROM vector_results v
        FULL OUTER JOIN fulltext_results f ON v.id = f.id
        ORDER BY rrf_score DESC
        LIMIT %(limit)s
        """,
        params,
    )

    rrf_rows = cur.fetchall()
    if not rrf_rows:
        return []

    # Fetch full document data for the RRF result IDs
    doc_ids = [row[0] for row in rrf_rows]
    rrf_scores = {row[0]: float(row[1]) for row in rrf_rows}

    cur.execute(
        """
        SELECT bd.id, bd.content_type, bd.source_id, bd.title,
               LEFT(bd.text, 400) AS excerpt,
               bd.metadata, bd.content_freshness, bd.quality_score
        FROM brain_documents bd
        WHERE bd.id = ANY(%(ids)s)
        """,
        {"ids": doc_ids},
    )

    docs_by_id = {}
    for row in cur.fetchall():
        docs_by_id[row[0]] = {
            "id": row[0],
            "type": row[1],
            "source_id": row[2],
            "title": row[3],
            "excerpt": row[4],
            "similarity": rrf_scores.get(row[0], 0),
            "metadata": row[5] if row[5] else {},
            "freshness": row[6],
            "quality_score": float(row[7]) if row[7] else 0.0,
        }

    # Preserve RRF ordering
    results = []
    for doc_id in doc_ids:
        if doc_id in docs_by_id:
            results.append(docs_by_id[doc_id])

    return results


def _rows_to_results(rows) -> list[dict]:
    """Convert raw DB rows to result dicts."""
    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "type": row[1],
            "source_id": row[2],
            "title": row[3],
            "excerpt": row[4],
            "similarity": round(float(row[5]), 4) if row[5] else 0.0,
            "metadata": row[6] if row[6] else {},
            "freshness": row[7],
            "quality_score": float(row[8]) if row[8] else 0.0,
        })
    return results


# ---------------------------------------------------------------------------
# Post-processing: freshness & re-ranking
# ---------------------------------------------------------------------------


def apply_freshness(results: list[dict]) -> list[dict]:
    """Blend freshness score into similarity for time-sensitive ranking."""
    decay = SEARCH_CONFIG["freshness_decay"]
    weight = SEARCH_CONFIG["freshness_weight"]
    now = datetime.now(timezone.utc)

    for r in results:
        if r.get("freshness"):
            days_old = (now - r["freshness"]).days
            freshness_factor = math.exp(-decay * max(days_old, 0))
            base_sim = r["similarity"]
            r["similarity"] = round((1 - weight) * base_sim + weight * freshness_factor, 4)

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results


def rerank_results(results: list[dict], query: str) -> list[dict]:
    """Re-rank results using either an HTTP reranker endpoint or a local cross-encoder.

    If BRAIN_RERANKER starts with 'http', uses the HTTP endpoint (e.g. Qwen3-Reranker-4B
    via llama-server or FastAPI proxy). Otherwise, loads a local SentenceTransformers
    CrossEncoder model.
    """
    if not RERANKER or not results:
        return results

    passages = [r["excerpt"].replace("\n", " ") for r in results]

    # HTTP-based reranker (e.g. llama-server / FastAPI proxy)
    if RERANKER.startswith("http"):
        try:
            import urllib.request

            payload = json.dumps({"query": query, "documents": passages})
            req = urllib.request.Request(
                RERANKER,
                data=payload.encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())

            # Support both llama-server format (results[].relevance_score)
            # and common reranker API format (results[].score or scores[])
            if "results" in data:
                for item in data["results"]:
                    idx = item.get("index", item.get("idx", 0))
                    score = item.get("relevance_score", item.get("score", 0.0))
                    if idx < len(results):
                        results[idx]["rerank_score"] = float(score)
            elif "scores" in data:
                for i, score in enumerate(data["scores"]):
                    if i < len(results):
                        results[i]["rerank_score"] = float(score)

            results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        except Exception as e:
            print(f"  Warning: HTTP reranker failed ({e}), returning unranked results")

        return results

    # Local cross-encoder model
    try:
        from sentence_transformers import CrossEncoder

        reranker = CrossEncoder(RERANKER)
        pairs = [(query, p) for p in passages]
        scores = reranker.predict(pairs)

        for i, score in enumerate(scores):
            results[i]["rerank_score"] = float(score)

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    except ImportError:
        # sentence-transformers not installed — skip re-ranking
        pass
    except Exception:
        # Model loading or inference failed — skip silently
        pass

    return results


# ---------------------------------------------------------------------------
# Related documents
# ---------------------------------------------------------------------------


def find_related(conn, source_id: str, limit: int = 10) -> list[dict]:
    """Find documents similar to an existing document by source_id."""
    cur = conn.cursor()

    cur.execute(
        """
        SELECT be.embedding, bd.content_type
        FROM brain_embeddings be
        JOIN brain_documents bd ON be.document_id = bd.id
        WHERE bd.source_id = %s
        LIMIT 1
        """,
        (source_id,),
    )
    row = cur.fetchone()
    if not row:
        print(f"Document not found: {source_id}")
        return []

    emb = row[0]

    cur.execute(
        """
        SELECT bd.id, bd.content_type, bd.source_id, bd.title,
               LEFT(bd.text, 400) AS excerpt,
               1 - (be.embedding <=> %s::vector) AS similarity,
               bd.metadata, bd.content_freshness, bd.quality_score
        FROM brain_documents bd
        JOIN brain_embeddings be ON be.document_id = bd.id
        WHERE bd.source_id != %s
        ORDER BY be.embedding <=> %s::vector
        LIMIT %s
        """,
        (emb, source_id, emb, limit),
    )
    return _rows_to_results(cur.fetchall())


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def show_stats(conn):
    """Display brain corpus statistics."""
    cur = conn.cursor()

    cur.execute(
        "SELECT content_type, COUNT(*) FROM brain_documents GROUP BY content_type ORDER BY count DESC"
    )
    rows = cur.fetchall()
    total = sum(r[1] for r in rows)

    print(f"\n{'=' * 55}")
    print(f"  Brain Corpus — {total} documents")
    print(f"{'=' * 55}")
    for ct, count in rows:
        print(f"  {ct:25s} {count:>6}")

    cur.execute("SELECT COUNT(*) FROM brain_embeddings")
    emb_count = cur.fetchone()[0]
    print(f"\n  Embeddings: {emb_count}  (model: {ACTIVE_MODEL})")

    cur.execute(
        "SELECT source_type, last_indexed_at, document_count "
        "FROM brain_sources ORDER BY source_type"
    )
    for st, ts, dc in cur.fetchall():
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts else "never"
        print(f"  {st:25s} {dc:>5} docs  (indexed {ts_str})")

    print()


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def print_results(results: list[dict], query: str, content_type: str = None, mode: str = "hybrid"):
    """Pretty-print search results."""
    if not results:
        print("No results found.")
        return

    print(f'\nSearch: "{query}"')
    print(f"Mode: {mode}" + (f"  |  Filter: {content_type}" if content_type else ""))
    print(f"{'=' * 70}")

    for i, r in enumerate(results, 1):
        sim = r["similarity"]
        # Scale bar: for RRF scores (usually < 0.05), normalise to max in results
        max_sim = max(x["similarity"] for x in results) or 1
        bar_len = int((sim / max_sim) * 20) if max_sim > 0 else 0
        sim_bar = "\u2588" * bar_len

        print(f"\n{i}. [{r['type']}] {r['title']}")
        print(f"   Score: {sim:.4f} {sim_bar}")
        if r.get("rerank_score") is not None:
            print(f"   Rerank: {r['rerank_score']:.4f}")
        print(f"   ID: {r['source_id']}")

        excerpt = r["excerpt"].replace("\n", " ")[:250]
        print(f"   {excerpt}...")

        # Show metadata highlights
        meta = r.get("metadata", {})
        if meta.get("slug"):
            print(f"   slug: {meta['slug']}", end="")
            if meta.get("level"):
                print(f"  level: {meta['level']}", end="")
            if meta.get("section_title"):
                print(f"  section: {meta['section_title']}", end="")
            print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="GEO Content Engine — Hybrid Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/brain/search.py "best practices for GEO"
  python3 scripts/brain/search.py "invoice factoring" --mode vector --type blog_section
  python3 scripts/brain/search.py --related "blog:my-post:summary" --limit 5
  python3 scripts/brain/search.py --stats
        """,
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument(
        "--mode",
        choices=["vector", "fulltext", "hybrid"],
        default=SEARCH_MODE,
        help=f"Search mode (default: {SEARCH_MODE})",
    )
    parser.add_argument(
        "--type",
        choices=["blog_post", "blog_section", "blog_paragraph"],
        help="Filter by content type",
    )
    parser.add_argument("--limit", type=int, default=SEARCH_CONFIG["max_results"], help="Max results")
    parser.add_argument("--related", type=str, help="Find documents related to source_id")
    parser.add_argument("--stats", action="store_true", help="Show brain stats")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--no-rerank", action="store_true", help="Skip cross-encoder re-ranking"
    )
    parser.add_argument(
        "--no-freshness", action="store_true", help="Skip freshness scoring"
    )
    args = parser.parse_args()

    try:
        conn = psycopg2.connect(DB_URL, sslmode="require")
    except Exception as e:
        print(f"ERROR: Could not connect to database — {e}")
        sys.exit(1)

    if args.stats:
        show_stats(conn)
        conn.close()
        return

    if args.related:
        results = find_related(conn, args.related, args.limit)
        if not args.no_freshness:
            results = apply_freshness(results)
    elif args.query:
        mode = args.mode

        if mode == "vector":
            vec = embed_query(args.query)
            results = vector_search(conn, vec, args.type, args.limit)
        elif mode == "fulltext":
            results = fulltext_search(conn, args.query, args.type, args.limit)
        elif mode == "hybrid":
            vec = embed_query(args.query)
            results = hybrid_search(conn, args.query, vec, args.type, args.limit)
        else:
            results = []

        # Post-processing
        if not args.no_freshness and mode != "hybrid":
            # Freshness already baked into hybrid via recency; apply to pure modes
            results = apply_freshness(results)

        if not args.no_rerank and results:
            results = rerank_results(results, args.query)
    else:
        parser.print_help()
        conn.close()
        return

    conn.close()

    # Output
    if args.json:
        # Serialise — drop non-JSON-friendly fields
        output = []
        for r in results:
            out = dict(r)
            out.pop("freshness", None)
            output.append(out)
        print(json.dumps(output, indent=2, default=str))
    else:
        query_label = args.query or f"related to {args.related}"
        print_results(results, query_label, args.type, args.mode)


if __name__ == "__main__":
    main()
