#!/usr/bin/env python3
"""
GEO Content Engine — Cannibalization Detection

Finds blog posts competing for the same semantic space by comparing
Level 1 (blog_post summary) embeddings pairwise.

Usage:
  python3 scripts/brain/cannibalize.py --all              # Full catalog scan
  python3 scripts/brain/cannibalize.py --query "keyword"   # Check specific topic
"""

import argparse
import sys
import warnings

import numpy as np
import psycopg2

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import DB_URL, ACTIVE_MODEL, CANNIBALIZATION_THRESHOLDS, get_model_config, BATCH_SIZE

# ---------------------------------------------------------------------------
# Model (lazy singleton for --query mode)
# ---------------------------------------------------------------------------
_model = None
_tokenizer = None


def get_model():
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


def embed_query(text: str) -> np.ndarray:
    """Embed a single query and return as numpy array."""
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
        return emb[0].numpy()

    elif cfg["type"] == "openai":
        import openai

        client = openai.OpenAI()
        response = client.embeddings.create(model=ACTIVE_MODEL, input=[text])
        return np.array(response.data[0].embedding, dtype=np.float32)

    elif cfg["type"] == "cohere":
        import cohere

        client = cohere.Client()
        input_types = cfg.get("input_types", {})
        response = client.embed(
            texts=[text], model=ACTIVE_MODEL, input_type=input_types.get("query", "search_query")
        )
        return np.array(response.embeddings[0], dtype=np.float32)

    else:
        raise ValueError(f"Unsupported model type: {cfg['type']}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm > 0 else 0.0


def severity_label(score: float) -> str:
    """Map a similarity score to a severity label."""
    t = CANNIBALIZATION_THRESHOLDS
    if score >= t["near_duplicate"]:
        return "NEAR_DUPLICATE"
    elif score >= t["high_cannibal"]:
        return "HIGH_CANNIBAL"
    elif score >= t["moderate_overlap"]:
        return "MODERATE_OVERLAP"
    return "OK"


def action_for_severity(label: str) -> str:
    """Suggest an action based on severity."""
    return {
        "NEAR_DUPLICATE": "MERGE or REDIRECT",
        "HIGH_CANNIBAL": "DIFFERENTIATE (adjust angle/keywords)",
        "MODERATE_OVERLAP": "REVIEW (may be fine if different intent)",
    }.get(label, "")


# ---------------------------------------------------------------------------
# Full catalog scan
# ---------------------------------------------------------------------------


def scan_all(conn):
    """Load all blog_post (Level 1) embeddings and compute pairwise similarity."""
    cur = conn.cursor()

    # Get all blog_post summaries with their embeddings
    cur.execute(
        """
        SELECT bd.source_id, bd.title, bd.metadata, be.embedding
        FROM brain_documents bd
        JOIN brain_embeddings be ON be.document_id = bd.id
        WHERE bd.content_type = 'blog_post'
        ORDER BY bd.source_id
        """
    )
    rows = cur.fetchall()

    if len(rows) < 2:
        print(f"Only {len(rows)} blog_post document(s) found. Need at least 2 for comparison.")
        return

    print(f"Loaded {len(rows)} blog_post embeddings")
    print(f"Computing pairwise similarity matrix ({len(rows) * (len(rows) - 1) // 2} pairs) ...\n")

    # Parse embeddings from pgvector string format
    posts = []
    for source_id, title, metadata, embedding in rows:
        if isinstance(embedding, str):
            vec = np.array([float(x) for x in embedding.strip("[]").split(",")], dtype=np.float32)
        else:
            vec = np.array(embedding, dtype=np.float32)

        slug = metadata.get("slug", source_id) if metadata else source_id
        posts.append({
            "source_id": source_id,
            "title": title,
            "slug": slug,
            "embedding": vec,
        })

    # Compute pairwise similarities
    min_threshold = CANNIBALIZATION_THRESHOLDS["moderate_overlap"]
    pairs = []

    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            sim = cosine_similarity(posts[i]["embedding"], posts[j]["embedding"])
            if sim >= min_threshold:
                label = severity_label(sim)
                pairs.append({
                    "score": sim,
                    "severity": label,
                    "a": posts[i],
                    "b": posts[j],
                })

    # Sort by score descending
    pairs.sort(key=lambda x: x["score"], reverse=True)

    if not pairs:
        print("No cannibalization detected. All posts are sufficiently distinct.")
        return

    # Group by severity for summary
    severity_counts = {}
    for p in pairs:
        severity_counts[p["severity"]] = severity_counts.get(p["severity"], 0) + 1

    print(f"{'=' * 70}")
    print(f"  Cannibalization Report — {len(pairs)} pair(s) flagged")
    print(f"{'=' * 70}")
    for sev in ["NEAR_DUPLICATE", "HIGH_CANNIBAL", "MODERATE_OVERLAP"]:
        if sev in severity_counts:
            print(f"  {sev:20s} {severity_counts[sev]:>3} pair(s)")
    print()

    for p in pairs:
        action = action_for_severity(p["severity"])
        print(f'{p["severity"]} ({p["score"]:.2f}): "{p["a"]["title"]}" <-> "{p["b"]["title"]}"')
        print(f'  slugs: {p["a"]["slug"]}, {p["b"]["slug"]}')
        print(f"  action: {action}")
        print()


# ---------------------------------------------------------------------------
# Query check
# ---------------------------------------------------------------------------


def check_query(conn, query: str):
    """Embed a query and find the most similar blog_post documents."""
    print(f'Checking topic: "{query}"\n')

    vec = embed_query(query)
    vec_list = vec.tolist()
    vec_str = str(vec_list)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT bd.source_id, bd.title, bd.metadata,
               1 - (be.embedding <=> %s::vector) AS similarity
        FROM brain_documents bd
        JOIN brain_embeddings be ON be.document_id = bd.id
        WHERE bd.content_type = 'blog_post'
        ORDER BY be.embedding <=> %s::vector
        LIMIT 10
        """,
        (vec_str, vec_str),
    )

    rows = cur.fetchall()
    if not rows:
        print("No blog_post documents found in the brain.")
        return

    print(f"Top matches for this topic:")
    print(f"{'=' * 70}")

    min_threshold = CANNIBALIZATION_THRESHOLDS["moderate_overlap"]
    flagged = 0

    for i, (source_id, title, metadata, similarity) in enumerate(rows, 1):
        sim = float(similarity)
        slug = metadata.get("slug", source_id) if metadata else source_id
        label = severity_label(sim)

        bar_len = int(sim * 20)
        bar = "\u2588" * bar_len

        flag = f"  ** {label}" if sim >= min_threshold else ""
        print(f"\n{i}. {title}")
        print(f"   Similarity: {sim:.4f} {bar}{flag}")
        print(f"   slug: {slug}")

        if sim >= min_threshold:
            flagged += 1

    print(f"\n{'=' * 70}")
    if flagged > 0:
        print(
            f"WARNING: {flagged} existing post(s) overlap with this topic. "
            f"Consider differentiating or merging before writing new content."
        )
    else:
        print("No significant overlap found. Safe to proceed with new content.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="GEO Content Engine — Cannibalization Detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/brain/cannibalize.py --all
  python3 scripts/brain/cannibalize.py --query "business line of credit vs term loan"
        """,
    )
    parser.add_argument("--all", action="store_true", help="Full catalog pairwise scan")
    parser.add_argument("--query", type=str, help="Check specific topic for overlap")
    args = parser.parse_args()

    if not args.all and not args.query:
        parser.print_help()
        sys.exit(0)

    try:
        conn = psycopg2.connect(DB_URL, sslmode="require")
    except Exception as e:
        print(f"ERROR: Could not connect to database — {e}")
        sys.exit(1)

    if args.all:
        scan_all(conn)
    elif args.query:
        check_query(conn, args.query)

    conn.close()


if __name__ == "__main__":
    main()
