#!/usr/bin/env python3
"""
GEO Content Engine — Embedding Pipeline

3-level chunking for blog content:
  Level 1 (blog_post)      — summary embedding of the entire article
  Level 2 (blog_section)   — FULL H2 section text (no truncation!)
  Level 3 (blog_paragraph) — individual paragraphs with sliding-window context

Usage:
  python3 scripts/brain/embed.py --source blog   # Embed blog posts
  python3 scripts/brain/embed.py --source all     # Everything
  python3 scripts/brain/embed.py --stats           # Show corpus stats
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Config (from config.py — no hardcoded values)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import DB_URL, ACTIVE_MODEL, get_model_config, BATCH_SIZE

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Model loading (lazy singleton)
# ---------------------------------------------------------------------------
_model = None
_tokenizer = None


def get_model():
    """Load the active embedding model. Supports local HuggingFace models."""
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    cfg = get_model_config()

    if cfg["type"] == "local":
        import torch
        from transformers import AutoModel, AutoTokenizer

        print(f"Loading {ACTIVE_MODEL} ...")
        _tokenizer = AutoTokenizer.from_pretrained(ACTIVE_MODEL)
        _model = AutoModel.from_pretrained(ACTIVE_MODEL)
        _model.eval()
        print(f"  Model loaded ({cfg['dim']}-dim, max {cfg['max_tokens']} tokens)")
    elif cfg["type"] == "openai":
        # Defer to embed_texts_openai — no model object needed
        _model = "openai"
        _tokenizer = None
    elif cfg["type"] == "cohere":
        _model = "cohere"
        _tokenizer = None
    else:
        raise ValueError(f"Unsupported model type: {cfg['type']}")

    return _model, _tokenizer


def embed_texts(texts: list[str], is_query: bool = False) -> np.ndarray:
    """Embed a list of texts with the active model. Handles prefixes automatically."""
    cfg = get_model_config()
    model, tokenizer = get_model()

    if cfg["type"] == "local":
        return _embed_texts_local(texts, is_query, model, tokenizer, cfg)
    elif cfg["type"] == "openai":
        return _embed_texts_openai(texts, cfg)
    elif cfg["type"] == "cohere":
        return _embed_texts_cohere(texts, is_query, cfg)
    else:
        raise ValueError(f"Unsupported model type: {cfg['type']}")


def _embed_texts_local(
    texts: list[str], is_query: bool, model, tokenizer, cfg: dict
) -> np.ndarray:
    """Embed with a local HuggingFace model (e5, nomic, etc.)."""
    import torch
    import torch.nn.functional as F

    prefix = cfg.get("query_prefix", "") if is_query else cfg.get("passage_prefix", "")
    prefixed = [f"{prefix}{t}" if prefix else t for t in texts]

    max_tokens = cfg.get("max_tokens", 512)
    all_embeddings = []

    for i in range(0, len(prefixed), BATCH_SIZE):
        batch = prefixed[i : i + BATCH_SIZE]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=max_tokens,
            return_tensors="pt",
        )
        with torch.no_grad():
            outputs = model(**inputs)

        # Mean pooling with attention mask
        attn = inputs["attention_mask"].unsqueeze(-1)
        emb = (outputs.last_hidden_state * attn).sum(1) / attn.sum(1)

        if cfg.get("normalize", True):
            emb = F.normalize(emb, p=2, dim=1)

        all_embeddings.append(emb.numpy())

    return np.vstack(all_embeddings)


def _embed_texts_openai(texts: list[str], cfg: dict) -> np.ndarray:
    """Embed with OpenAI API."""
    import openai

    client = openai.OpenAI()
    all_embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embeddings.create(model=ACTIVE_MODEL, input=batch)
        batch_embs = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embs)

    return np.array(all_embeddings, dtype=np.float32)


def _embed_texts_cohere(texts: list[str], is_query: bool, cfg: dict) -> np.ndarray:
    """Embed with Cohere API."""
    import cohere

    client = cohere.Client()
    input_types = cfg.get("input_types", {})
    input_type = input_types.get("query") if is_query else input_types.get("passage")

    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embed(texts=batch, model=ACTIVE_MODEL, input_type=input_type)
        all_embeddings.extend(response.embeddings)

    return np.array(all_embeddings, dtype=np.float32)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def text_hash(text: str) -> str:
    """SHA-256 hash truncated to 32 chars for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def clean_mdx(body: str) -> str:
    """Strip MDX components and markdown links from body text."""
    # Remove self-closing MDX components: <ComponentName ... />
    text = re.sub(r"<[A-Z]\w+[^>]*/>", "", body)
    # Remove block MDX components: <Component>...</Component>
    text = re.sub(r"<[A-Z]\w+[^>]*>.*?</[A-Z]\w+>", "", text, flags=re.DOTALL)
    # Convert markdown links to just text: [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def parse_frontmatter(content: str) -> tuple[dict, str] | None:
    """Parse YAML-ish frontmatter and return (fields_dict, body)."""
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not fm_match:
        return None
    fm_text, body = fm_match.group(1), fm_match.group(2)

    fields = {}
    # Title
    m = re.search(r'^title:\s*"?(.+?)"?\s*$', fm_text, re.MULTILINE)
    fields["title"] = m.group(1).strip('"').strip("'") if m else ""

    # Status
    m = re.search(r"^status:\s*(\w+)", fm_text, re.MULTILINE)
    fields["status"] = m.group(1) if m else "draft"

    # Category
    m = re.search(r'^category:\s*"?(.+?)"?\s*$', fm_text, re.MULTILINE)
    fields["category"] = m.group(1).strip('"').strip("'") if m else ""

    # Cluster
    m = re.search(r'^cluster:\s*"?(.+?)"?\s*$', fm_text, re.MULTILINE)
    fields["cluster"] = m.group(1).strip('"').strip("'") if m else ""

    # Cluster role
    m = re.search(r'^clusterRole:\s*"?(.+?)"?\s*$', fm_text, re.MULTILINE)
    fields["cluster_role"] = m.group(1).strip('"').strip("'") if m else ""

    # Target keyword
    m = re.search(r'^targetKeyword:\s*"?(.+?)"?\s*$', fm_text, re.MULTILINE)
    fields["target_keyword"] = m.group(1).strip('"').strip("'") if m else ""

    return fields, body


# ---------------------------------------------------------------------------
# Content Loaders — 3-Level Blog Chunking
# ---------------------------------------------------------------------------


def load_blog_posts() -> list[dict]:
    """
    Load blog posts with 3-level chunking:
      Level 1 (blog_post)      — title + H2 titles + first 2000 chars
      Level 2 (blog_section)   — FULL H2 section text (NO truncation!)
      Level 3 (blog_paragraph) — individual paragraphs with sliding-window context
    """
    blog_dir = REPO_ROOT / "content" / "blog"
    if not blog_dir.exists():
        print(f"  Blog directory not found: {blog_dir}")
        return []

    docs = []

    for mdx_file in sorted(blog_dir.glob("*.mdx")):
        content = mdx_file.read_text()
        parsed = parse_frontmatter(content)
        if not parsed:
            continue

        fields, body = parsed
        title = fields["title"] or mdx_file.stem
        slug = mdx_file.stem
        status = fields["status"]
        cluster = fields["cluster"]

        clean_body = clean_mdx(body)

        # Split into H2 sections
        # sections[0] = intro (text before first ##)
        # sections[1:] = each starts with the H2 title line
        raw_sections = re.split(r"^##\s+", clean_body, flags=re.MULTILINE)

        # Collect H2 titles for Level 1 summary
        section_titles = []
        for i, sec in enumerate(raw_sections[1:], 1):
            sec_lines = sec.split("\n", 1)
            section_titles.append(sec_lines[0].strip())

        # -------------------------------------------------------------------
        # Level 1: blog_post — summary embedding
        # -------------------------------------------------------------------
        summary_parts = [title]
        if section_titles:
            summary_parts.append("Sections: " + ", ".join(section_titles))
        summary_parts.append(clean_body[:2000])
        summary_text = "\n".join(summary_parts)

        docs.append({
            "content_type": "blog_post",
            "source_id": f"blog:{slug}:summary",
            "title": title,
            "text": summary_text,
            "metadata": {
                "slug": slug,
                "status": status,
                "level": 1,
                "cluster": cluster,
                "cluster_role": fields.get("cluster_role", ""),
                "target_keyword": fields.get("target_keyword", ""),
                "section_count": len(section_titles),
            },
            "topic_cluster": cluster or None,
            "is_published": status == "published",
        })

        # -------------------------------------------------------------------
        # Level 2 & 3: Sections and Paragraphs
        # -------------------------------------------------------------------
        for i, section in enumerate(raw_sections):
            section = section.strip()
            if len(section) < 50:
                continue

            if i == 0:
                # Intro section (before first H2)
                section_title = "Introduction"
                section_text = section
            else:
                lines = section.split("\n", 1)
                section_title = lines[0].strip()
                section_text = lines[1].strip() if len(lines) > 1 else ""

            if not section_text or len(section_text) < 50:
                continue

            # Level 2: blog_section — FULL section text, NO TRUNCATION
            full_section_text = f"{title} — {section_title}. {section_text}"

            docs.append({
                "content_type": "blog_section",
                "source_id": f"blog:{slug}:s{i}",
                "title": f"{title} — {section_title}",
                "text": full_section_text,
                "metadata": {
                    "slug": slug,
                    "section_index": i,
                    "section_title": section_title,
                    "parent_id": f"blog:{slug}:summary",
                    "level": 2,
                    "status": status,
                },
                "topic_cluster": cluster or None,
                "is_published": status == "published",
            })

            # Level 3: blog_paragraph — individual paragraphs with context
            paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
            prev_paragraph = ""

            for j, para in enumerate(paragraphs):
                if len(para) < 50:
                    # Still store as context for next paragraph
                    prev_paragraph = para
                    continue

                # Build paragraph text with sliding-window context
                context_parts = [f"{title} — {section_title}."]
                if prev_paragraph:
                    context_parts.append(prev_paragraph)
                context_parts.append(para)
                para_text = " ".join(context_parts)

                docs.append({
                    "content_type": "blog_paragraph",
                    "source_id": f"blog:{slug}:s{i}:p{j}",
                    "title": f"{title} — {section_title}",
                    "text": para_text,
                    "metadata": {
                        "slug": slug,
                        "section_index": i,
                        "paragraph_index": j,
                        "parent_id": f"blog:{slug}:s{i}",
                        "level": 3,
                        "status": status,
                    },
                    "topic_cluster": cluster or None,
                    "is_published": status == "published",
                })

                prev_paragraph = para

    return docs


# ---------------------------------------------------------------------------
# Database Operations
# ---------------------------------------------------------------------------


def get_generation_id(cur) -> int:
    """Get the active embedding generation ID for the current model."""
    cur.execute(
        "SELECT id FROM brain_embedding_generations WHERE model_name = %s AND is_active = true",
        (ACTIVE_MODEL,),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    # Create one if missing
    cfg = get_model_config()
    cur.execute(
        """
        INSERT INTO brain_embedding_generations (model_name, model_dim, is_active)
        VALUES (%s, %s, true)
        ON CONFLICT (model_name) DO UPDATE SET is_active = true
        RETURNING id
        """,
        (ACTIVE_MODEL, cfg["dim"]),
    )
    return cur.fetchone()[0]


def upsert_documents(conn, docs: list[dict], source_type: str):
    """Upsert documents and their embeddings. Skips unchanged content via hash."""
    if not docs:
        return

    cur = conn.cursor()
    generation_id = get_generation_id(cur)

    # Load existing hashes for change detection
    content_types = list({d["content_type"] for d in docs})
    existing_hashes = {}
    for ct in content_types:
        cur.execute(
            "SELECT source_id, text_hash FROM brain_documents WHERE content_type = %s",
            (ct,),
        )
        for row in cur.fetchall():
            existing_hashes[row[0]] = row[1]

    # Filter to changed docs
    new_docs = []
    for doc in docs:
        h = text_hash(doc["text"])
        if doc["source_id"] in existing_hashes and existing_hashes[doc["source_id"]] == h:
            continue
        doc["_hash"] = h
        new_docs.append(doc)

    if not new_docs:
        print(f"  {source_type}: {len(docs)} docs, 0 changed — skipping")
        return

    print(f"  {source_type}: {len(new_docs)}/{len(docs)} docs need embedding ...")

    # Generate embeddings
    texts = [d["text"] for d in new_docs]
    embeddings = embed_texts(texts)

    # Upsert each document + embedding
    for i, doc in enumerate(new_docs):
        emb_list = embeddings[i].tolist()
        meta_json = json.dumps(doc.get("metadata", {}))
        topic_cluster = doc.get("topic_cluster")
        is_published = doc.get("is_published", True)

        cur.execute(
            """
            INSERT INTO brain_documents
                (content_type, source_id, title, text, text_hash, metadata,
                 topic_cluster, is_published)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (content_type, source_id) DO UPDATE SET
                title = EXCLUDED.title,
                text = EXCLUDED.text,
                text_hash = EXCLUDED.text_hash,
                metadata = EXCLUDED.metadata,
                topic_cluster = EXCLUDED.topic_cluster,
                is_published = EXCLUDED.is_published,
                updated_at = NOW()
            RETURNING id
            """,
            (
                doc["content_type"],
                doc["source_id"],
                doc["title"],
                doc["text"],
                doc["_hash"],
                meta_json,
                topic_cluster,
                is_published,
            ),
        )
        doc_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO brain_embeddings (document_id, embedding, model_version, generation_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (document_id, model_version) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                generation_id = EXCLUDED.generation_id,
                created_at = NOW()
            """,
            (doc_id, str(emb_list), ACTIVE_MODEL, generation_id),
        )

    # Update source tracking
    cur.execute(
        """
        INSERT INTO brain_sources (source_type, last_indexed_at, document_count)
        VALUES (%s, NOW(), %s)
        ON CONFLICT (source_type) DO UPDATE SET
            last_indexed_at = NOW(),
            document_count = EXCLUDED.document_count
        """,
        (source_type, len(docs)),
    )

    # Update generation document count
    cur.execute(
        """
        UPDATE brain_embedding_generations
        SET document_count = (SELECT COUNT(*) FROM brain_embeddings WHERE generation_id = %s)
        WHERE id = %s
        """,
        (generation_id, generation_id),
    )

    conn.commit()
    print(f"  {source_type}: {len(new_docs)} docs embedded and stored")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def show_stats(conn):
    """Display corpus statistics."""
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
    print(f"\n  Embeddings: {emb_count}")

    cur.execute(
        "SELECT model_name, model_dim, is_active, document_count "
        "FROM brain_embedding_generations ORDER BY is_active DESC"
    )
    gens = cur.fetchall()
    if gens:
        print(f"\n  Models:")
        for name, dim, active, dc in gens:
            flag = " (active)" if active else ""
            print(f"    {name:30s} {dim:>4}-dim  {dc:>5} docs{flag}")

    cur.execute(
        "SELECT source_type, last_indexed_at, document_count "
        "FROM brain_sources ORDER BY source_type"
    )
    sources = cur.fetchall()
    if sources:
        print(f"\n  Sources:")
        for st, ts, dc in sources:
            ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts else "never"
            print(f"    {st:25s} {dc:>5} docs  (indexed {ts_str})")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

LOADERS = {
    "blog": ("blog", load_blog_posts),
}


def main():
    parser = argparse.ArgumentParser(
        description="GEO Content Engine — Embedding Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/brain/embed.py --source blog   # Embed blog posts
  python3 scripts/brain/embed.py --source all     # Everything
  python3 scripts/brain/embed.py --stats           # Show corpus stats
        """,
    )
    parser.add_argument(
        "--source",
        choices=list(LOADERS.keys()) + ["all"],
        default="all",
        help="Content source to embed (default: all)",
    )
    parser.add_argument("--stats", action="store_true", help="Show corpus statistics")
    args = parser.parse_args()

    try:
        conn = psycopg2.connect(DB_URL, sslmode="require")
        psycopg2.extras.register_uuid()
    except Exception as e:
        print(f"ERROR: Could not connect to database — {e}")
        sys.exit(1)

    if args.stats:
        show_stats(conn)
        conn.close()
        return

    cfg = get_model_config()
    print("GEO Content Engine — Embedding Pipeline")
    print(f"  Model: {ACTIVE_MODEL} ({cfg['dim']}-dim)")
    print()

    sources = list(LOADERS.keys()) if args.source == "all" else [args.source]

    for source in sources:
        source_type, loader = LOADERS[source]
        docs = loader()
        print(f"Loaded {len(docs)} {source_type} documents (3-level chunking)")
        upsert_documents(conn, docs, source_type)

    show_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
