import pytest

def test_clawrank_document_has_pillar():
    from scripts.clawrank.core.models import ClawRankDocument
    doc = ClawRankDocument(id="t", content_type="how_to")
    assert doc.pillar == ""

def test_clawrank_document_has_matched_transcripts():
    from scripts.clawrank.core.models import ClawRankDocument
    doc = ClawRankDocument(id="t", content_type="how_to")
    assert doc.matched_transcripts == []

def test_clawrank_document_has_strong_match_default_false():
    from scripts.clawrank.core.models import ClawRankDocument
    doc = ClawRankDocument(id="t", content_type="how_to")
    assert doc.has_strong_match is False

def test_clawrank_document_no_ac_post_type():
    from scripts.clawrank.core.models import ClawRankDocument
    assert "ac_post_type" not in ClawRankDocument.__dataclass_fields__

def test_clawrank_document_no_related_industries():
    from scripts.clawrank.core.models import ClawRankDocument
    assert "related_industries" not in ClawRankDocument.__dataclass_fields__
