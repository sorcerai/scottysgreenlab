"""Convert ClawRankDocument to JSON for the /learn/ pipeline."""
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

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
