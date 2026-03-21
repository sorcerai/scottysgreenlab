"""Convert ClawRankDocument to JSON for the /learn/ pipeline.

Handles all output files:
1. content/learn/{slug}.json — individual article (what the slug page reads)
2. src/data/pseo-questions-final.json — index entry with excerpt (what the index page reads)
3. data/content-pipeline/clawrank-batch-{n}.json — batch archive
"""
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Journal/org homepage URLs for common sources
SOURCE_URLS: dict[str, str] = {
    "Nature Microbiology": "https://www.nature.com/nmicrobiol/",
    "Nature": "https://www.nature.com/",
    "Science": "https://www.science.org/",
    "Cell": "https://www.cell.com/",
    "PNAS": "https://www.pnas.org/",
    "Frontiers in Microbiology": "https://www.frontiersin.org/journals/microbiology",
    "Gut Microbes": "https://www.tandfonline.com/toc/kgmi20/current",
    "The Lancet Gastroenterology & Hepatology": "https://www.thelancet.com/journals/langas/home",
    "The Lancet": "https://www.thelancet.com/",
    "Human Microbiome Project": "https://hmpdacc.org/",
    "Journal of Agricultural and Food Chemistry": "https://pubs.acs.org/journal/jafcau",
    "American Society for Microbiology": "https://asm.org/",
    "USDA Agricultural Research Service": "https://www.ars.usda.gov/",
    "USDA Natural Resources Conservation Service": "https://www.nrcs.usda.gov/conservation-basics/natural-resource-concerns/soils/soil-biology",
    "USDA": "https://www.usda.gov/",
    "Texas A&M AgriLife Extension": "https://agrilifeextension.tamu.edu/",
    "Journal of Applied Microbiology": "https://academic.oup.com/jambio",
    "Environmental Microbiome": "https://environmentalmicrobiome.biomedcentral.com/",
    "Soil Biology and Biochemistry": "https://www.sciencedirect.com/journal/soil-biology-and-biochemistry",
    "PubMed": "https://pubmed.ncbi.nlm.nih.gov/",
    "Frontiers in Agronomy": "https://www.frontiersin.org/journals/agronomy",
}


def _enrich_source_urls(sources: list[dict]) -> list[dict]:
    """Add URLs to sources that only have publisher names."""
    for src in sources:
        if not src.get("url") and src.get("publisher") in SOURCE_URLS:
            src["url"] = SOURCE_URLS[src["publisher"]]
    return sources


def _extract_excerpt(body: str, max_len: int = 200) -> str:
    """Extract a clean excerpt from article body for the index page."""
    paragraphs = body.split("\n\n")
    for p in paragraphs:
        p = p.strip()
        # Skip headings, empty lines, blockquotes
        if not p or p.startswith("#") or p.startswith(">"):
            continue
        # Strip markdown formatting for clean display
        clean = re.sub(r"\*+(.+?)\*+", r"\1", p)  # bold/italic
        clean = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", clean)  # links
        if len(clean) > 50:
            return clean[:max_len]
    return body[:max_len]


def publish_article(article_json: dict) -> dict[str, str]:
    """Full publish pipeline: create article JSON, update index, write batch.

    Args:
        article_json: Scottynized stage-12 output with frontmatter, body, citations

    Returns:
        dict with paths: {article_path, index_path, batch_path}
    """
    fm = article_json.get("frontmatter", {})
    body = article_json.get("body", "")
    citations = article_json.get("citations", [])
    slug = fm.get("slug", "")

    if not slug or not body:
        raise ValueError("Article must have frontmatter.slug and body")

    # Build sources with URLs
    sources = []
    for c in citations:
        src = {
            "title": c.get("text", "")[:120],
            "url": c.get("url", ""),
            "publisher": c.get("source", ""),
        }
        sources.append(src)
    sources = _enrich_source_urls(sources)

    # 1. Write content/learn/{slug}.json (what the slug page reads)
    learn_dir = PROJECT_ROOT / "content" / "learn"
    learn_dir.mkdir(parents=True, exist_ok=True)

    learn_article = {
        "slug": slug,
        "question": fm.get("title", ""),
        "pillar": fm.get("category", "").lower().replace(" & ", "-").replace(" ", "-") if fm.get("category") else "general",
        "title": fm.get("title", ""),
        "metaDescription": fm.get("description", ""),
        "content": body,
        "sources": sources,
        "scottyQuotes": [],
        "wordCount": len(body.split()),
    }

    article_path = learn_dir / f"{slug}.json"
    article_path.write_text(json.dumps(learn_article, indent=2, ensure_ascii=False))

    # 2. Update pseo-questions-final.json (what the index page reads)
    excerpt = _extract_excerpt(body)
    pillar = learn_article["pillar"]
    # Normalize pillar to match existing pillars
    pillar_map = {
        "fermentation-gut-health": "fermentation",
        "regenerative-agriculture": "regenerative-agriculture",
        "soil-science-biology": "soil-science",
        "soil-science": "soil-science",
        "community-gardening": "community-gardening",
        "food-system": "food-system",
        "composting": "composting",
        "fermentation": "fermentation",
    }
    pillar = pillar_map.get(pillar, pillar)

    index_entry = {
        "question": fm.get("title", ""),
        "slug": slug,
        "pillar": pillar,
        "keywords": fm.get("secondaryKeywords", [fm.get("targetKeyword", "")]),
        "relevance_score": 0.95,
        "has_transcript_match": True,
        "matched_titles": [],
        "semantic_matches": [{
            "source_id": f"clawrank:{slug}",
            "title": fm.get("title", ""),
            "excerpt": excerpt,
            "vector_score": 0.95,
            "rerank_score": 0.95,
        }],
        "best_rerank_score": 0.95,
        "best_vector_score": 0.95,
        "has_strong_match": True,
        "answer": body,
        "sources": [s.get("url", "") for s in sources if s.get("url")],
    }

    index_path = PROJECT_ROOT / "src" / "data" / "pseo-questions-final.json"
    existing = json.loads(index_path.read_text()) if index_path.exists() else []
    existing = [q for q in existing if q["slug"] != slug]
    existing.append(index_entry)
    index_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

    # 3. Write batch archive
    batch_dir = PROJECT_ROOT / "data" / "content-pipeline"
    batch_dir.mkdir(parents=True, exist_ok=True)
    # Find next batch number
    existing_batches = list(batch_dir.glob("clawrank-batch-*.json"))
    next_idx = len(existing_batches)
    batch_path = batch_dir / f"clawrank-batch-{next_idx}.json"
    batch_path.write_text(json.dumps([index_entry], indent=2, ensure_ascii=False))

    return {
        "article_path": str(article_path),
        "index_path": str(index_path),
        "batch_path": str(batch_path),
    }


# Keep legacy functions for backwards compat
def document_to_json(doc) -> dict[str, Any]:
    """Convert ClawRankDocument to pseo-questions-final.json schema."""
    matched = getattr(doc, "matched_transcripts", []) or []
    best_rerank = max((m.get("rerank_score", 0) for m in matched), default=0.0)
    best_vector = max((m.get("vector_score", 0) for m in matched), default=0.0)
    return {
        "question": doc.title,
        "slug": doc.slug,
        "pillar": getattr(doc, "pillar", "") or doc.content_type,
        "keywords": doc.secondary_keywords or [doc.target_keyword] if doc.target_keyword else [],
        "relevance_score": doc.scores.get("relevance", 0.0) if doc.scores else 0.0,
        "has_transcript_match": len(matched) > 0,
        "matched_titles": [m.get("title", "") for m in matched[:3]],
        "semantic_matches": matched,
        "best_rerank_score": best_rerank,
        "best_vector_score": best_vector,
        "has_strong_match": best_rerank >= 0.85,
        "answer": doc.body_markdown,
        "sources": [c.url for c in doc.citations] if doc.citations else [],
    }


def append_to_questions_index(entry: dict, path: Path | None = None) -> None:
    """Add a new entry to pseo-questions-final.json."""
    path = path or (PROJECT_ROOT / "src" / "data" / "pseo-questions-final.json")
    existing = json.loads(path.read_text()) if path.exists() else []
    existing = [q for q in existing if q["slug"] != entry["slug"]]
    existing.append(entry)
    path.write_text(json.dumps(existing, indent=2))


def write_batch(entries: list[dict], batch_dir: Path | None = None, batch_index: int = 0) -> Path:
    """Write a batch of entries to data/content-pipeline/."""
    batch_dir = batch_dir or (PROJECT_ROOT / "data" / "content-pipeline")
    batch_dir.mkdir(parents=True, exist_ok=True)
    out_path = batch_dir / f"clawrank-batch-{batch_index}.json"
    out_path.write_text(json.dumps(entries, indent=2))
    return out_path
