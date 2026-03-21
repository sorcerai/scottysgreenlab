import pytest

def test_document_to_json_has_required_fields():
    from scripts.clawrank.scotty.publish import document_to_json
    from scripts.clawrank.core.models import ClawRankDocument
    doc = ClawRankDocument(
        id="test-1", content_type="how_to",
        title="How to Start Composting", slug="how-to-start-composting",
        body_markdown="Full article body here.", target_keyword="how to start composting",
    )
    doc.pillar = "composting"
    result = document_to_json(doc)
    required = ["question", "slug", "pillar", "keywords", "relevance_score",
                "has_transcript_match", "semantic_matches", "best_rerank_score",
                "best_vector_score", "has_strong_match"]
    for field in required:
        assert field in result, f"Missing field: {field}"

def test_document_to_json_slug_format():
    from scripts.clawrank.scotty.publish import document_to_json
    from scripts.clawrank.core.models import ClawRankDocument
    doc = ClawRankDocument(id="t", content_type="how_to", title="Test", slug="test-slug")
    result = document_to_json(doc)
    assert result["slug"] == "test-slug"
