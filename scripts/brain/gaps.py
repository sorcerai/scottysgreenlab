#!/usr/bin/env python3
"""
GEO Content Engine — Content Gap Analysis

Embeds target queries and checks how well the existing brain corpus
covers each topic. Flags gaps by severity.

Usage:
  python3 scripts/brain/gaps.py "query 1" "query 2" "query 3"
  python3 scripts/brain/gaps.py --file queries.txt   # One query per line
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

from config import DB_URL, ACTIVE_MODEL, CONTENT_GAP_THRESHOLD, get_model_config, BATCH_SIZE

# ---------------------------------------------------------------------------
# Model (lazy singleton)
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


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed multiple query texts. Returns (N, dim) array."""
    cfg = get_model_config()
    model, tokenizer = get_model()

    if cfg["type"] == "local":
        import torch
        import torch.nn.functional as F

        prefix = cfg.get("query_prefix", "")
        prefixed = [f"{prefix}{t}" if prefix else t for t in texts]
        max_tokens = cfg.get("max_tokens", 512)

        all_embeddings = []
        for i in range(0, len(prefixed), BATCH_SIZE):
            batch = prefixed[i : i + BATCH_SIZE]
            inputs = tokenizer(
                batch, padding=True, truncation=True, max_length=max_tokens, return_tensors="pt"
            )
            with torch.no_grad():
                outputs = model(**inputs)
            attn = inputs["attention_mask"].unsqueeze(-1)
            emb = (outputs.last_hidden_state * attn).sum(1) / attn.sum(1)
            if cfg.get("normalize", True):
                emb = F.normalize(emb, p=2, dim=1)
            all_embeddings.append(emb.numpy())
        return np.vstack(all_embeddings)

    elif cfg["type"] == "openai":
        import openai

        client = openai.OpenAI()
        all_embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            response = client.embeddings.create(model=ACTIVE_MODEL, input=batch)
            batch_embs = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embs)
        return np.array(all_embeddings, dtype=np.float32)

    elif cfg["type"] == "cohere":
        import cohere

        client = cohere.Client()
        input_types = cfg.get("input_types", {})
        all_embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            response = client.embed(
                texts=batch, model=ACTIVE_MODEL, input_type=input_types.get("query", "search_query")
            )
            all_embeddings.extend(response.embeddings)
        return np.array(all_embeddings, dtype=np.float32)

    else:
        raise ValueError(f"Unsupported model type: {cfg['type']}")


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


def severity_label(score: float) -> str:
    """Classify gap severity based on best-match score."""
    if score < 0.50:
        return "HIGH"
    elif score < CONTENT_GAP_THRESHOLD:
        return "MEDIUM"
    else:
        return "LOW"


def analyse_gaps(conn, queries: list[str]):
    """Embed queries and find best matches in the brain."""
    cur = conn.cursor()

    # Check we have documents
    cur.execute("SELECT COUNT(*) FROM brain_documents")
    doc_count = cur.fetchone()[0]
    if doc_count == 0:
        print("No documents in the brain. Run embed.py first.")
        return

    print(f"Analysing {len(queries)} queries against {doc_count} documents ...\n")

    # Embed all queries
    embeddings = embed_texts(queries)

    results = []
    for i, query in enumerate(queries):
        vec = embeddings[i].tolist()
        vec_str = str(vec)

        cur.execute(
            """
            SELECT bd.title, bd.source_id,
                   1 - (be.embedding <=> %s::vector) AS similarity
            FROM brain_documents bd
            JOIN brain_embeddings be ON be.document_id = bd.id
            ORDER BY be.embedding <=> %s::vector
            LIMIT 1
            """,
            (vec_str, vec_str),
        )
        row = cur.fetchone()

        if row:
            best_title, best_source, best_sim = row[0], row[1], float(row[2])
        else:
            best_title, best_source, best_sim = "(none)", "", 0.0

        sev = severity_label(best_sim)
        results.append({
            "query": query,
            "best_title": best_title,
            "best_source": best_source,
            "score": best_sim,
            "severity": sev,
        })

    # Sort by score ascending (worst gaps first)
    results.sort(key=lambda x: x["score"])

    # Print table
    _print_table(results)

    # Summary
    high = sum(1 for r in results if r["severity"] == "HIGH")
    medium = sum(1 for r in results if r["severity"] == "MEDIUM")
    low = sum(1 for r in results if r["severity"] == "LOW")

    print(f"\nSummary: {high} HIGH, {medium} MEDIUM, {low} LOW")
    if high > 0:
        print(f"  {high} topic(s) have virtually no coverage — create new content.")
    if medium > 0:
        print(f"  {medium} topic(s) are partially covered — consider dedicated articles.")


def _print_table(results: list[dict]):
    """Print a formatted table of gap analysis results."""
    # Column widths
    sev_w = 8
    query_w = min(40, max(len(r["query"]) for r in results) + 2) if results else 30
    match_w = min(35, max(len(r["best_title"]) for r in results) + 2) if results else 20
    score_w = 8

    # Header
    divider = f"+{'-' * (sev_w + 2)}+{'-' * (query_w + 2)}+{'-' * (match_w + 2)}+{'-' * (score_w + 2)}+"
    print(divider)
    print(
        f"| {'Severity':^{sev_w}} | {'Query':^{query_w}} | {'Best Match':^{match_w}} | {'Score':^{score_w}} |"
    )
    print(divider)

    for r in results:
        sev = r["severity"]
        query = r["query"][:query_w]
        match = r["best_title"][:match_w]
        score = f"{r['score']:.2f}"

        print(f"| {sev:<{sev_w}} | {query:<{query_w}} | {match:<{match_w}} | {score:>{score_w}} |")

    print(divider)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="GEO Content Engine — Content Gap Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/brain/gaps.py "revenue based financing" "equipment leasing vs buying" "SBA 504 loan"
  python3 scripts/brain/gaps.py --file target-queries.txt
        """,
    )
    parser.add_argument("queries", nargs="*", help="Target queries to check")
    parser.add_argument("--file", type=str, help="File with queries (one per line)")
    args = parser.parse_args()

    queries = list(args.queries) if args.queries else []

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"ERROR: File not found: {args.file}")
            sys.exit(1)
        with open(file_path) as f:
            file_queries = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        queries.extend(file_queries)

    if not queries:
        parser.print_help()
        sys.exit(0)

    try:
        conn = psycopg2.connect(DB_URL, sslmode="require")
    except Exception as e:
        print(f"ERROR: Could not connect to database — {e}")
        sys.exit(1)

    analyse_gaps(conn, queries)
    conn.close()


if __name__ == "__main__":
    main()
