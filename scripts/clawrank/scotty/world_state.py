"""Brain database queries for world state snapshot."""
import json
import os
from pathlib import Path
from typing import Any
import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _get_connection():
    url = os.environ.get("BRAIN_DB_URL")
    if not url:
        raise EnvironmentError("BRAIN_DB_URL not set")
    return psycopg2.connect(url)


def collect_brain_state() -> dict[str, Any]:
    """Snapshot the brain database for the decision engine."""
    conn = _get_connection()
    state: dict[str, Any] = {}
    try:
        with conn.cursor() as cur:
            # Document counts by type
            cur.execute("SELECT content_type, COUNT(*) FROM brain_documents GROUP BY content_type ORDER BY count DESC")
            by_type = {row[0]: row[1] for row in cur.fetchall()}
            state["by_type"] = by_type
            state["total_docs"] = sum(by_type.values())

            # Entity counts by type
            cur.execute("SELECT entity_type, COUNT(*) FROM brain_entities GROUP BY entity_type ORDER BY count DESC")
            state["entity_counts"] = {row[0]: row[1] for row in cur.fetchall()}

            # Cannibalization count (cosine > 0.85)
            cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT a.id FROM brain_documents a
                    JOIN brain_embeddings ae ON ae.document_id = a.id
                    JOIN brain_documents b ON b.content_type = a.content_type AND b.id > a.id
                    JOIN brain_embeddings be ON be.document_id = b.id
                    WHERE a.content_type = 'transcript_video'
                    AND 1 - (ae.embedding <=> be.embedding) > 0.85
                    LIMIT 100
                ) sub
            """)
            row = cur.fetchone()
            state["cannibalization_count"] = row[0] if row else 0
    finally:
        conn.close()

    # Article coverage from pseo-questions-final.json
    questions_path = PROJECT_ROOT / "src" / "data" / "pseo-questions-final.json"
    if questions_path.exists():
        questions = json.loads(questions_path.read_text())
        pillar_counts: dict[str, int] = {}
        for q in questions:
            p = q.get("pillar", "unknown")
            pillar_counts[p] = pillar_counts.get(p, 0) + 1
        state["articles_by_pillar"] = pillar_counts
        state["total_articles"] = len(questions)
    else:
        state["articles_by_pillar"] = {}
        state["total_articles"] = 0
    return state
