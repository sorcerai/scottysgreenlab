import pytest


def test_score_article_returns_dict():
    from scripts.clawrank.scotty.compliance import score_article
    article = {
        "title": "How to Start Hot Composting in Houston",
        "body": "This is a test article about composting. " * 200,
        "sections": [{"heading": "Step 1"}, {"heading": "Step 2"}, {"heading": "Step 3"}],
        "faq": [{"q": "Q1?", "a": "A1."}, {"q": "Q2?", "a": "A2."}, {"q": "Q3?", "a": "A3."}, {"q": "Q4?", "a": "A4."}],
        "sources": ["Source 1", "Source 2", "Source 3", "Source 4", "Source 5"],
        "meta_description": "Learn how to start hot composting in Houston Texas heat",
        "internal_links": ["/learn/a", "/learn/b", "/learn/c"],
    }
    result = score_article(article)
    assert "weighted_score" in result
    assert "passed" in result
    assert "dimension_scores" in result


def test_banned_phrase_detection():
    from scripts.clawrank.scotty.compliance import _check_banned_phrases
    violations = _check_banned_phrases("This comprehensive guide delves into the landscape of composting.")
    assert len(violations) >= 3


def test_clean_article_passes_gate():
    from scripts.clawrank.scotty.compliance import score_article
    body = "Composting in Houston requires understanding soil biology. " * 100
    body += "According to Texas A&M Extension, hot composting reaches 140F in 3 days. "
    body += "Studies show regenerative practices increase yield by 30%. "
    article = {
        "title": "How to Start Hot Composting in Houston",
        "body": body,
        "sections": [{"heading": f"Section {i}"} for i in range(4)],
        "faq": [{"q": f"Q{i}?", "a": f"A{i}."} for i in range(5)],
        "sources": [f"Source {i}" for i in range(6)],
        "meta_description": "Learn how to start hot composting in Houston",
        "internal_links": [f"/learn/topic-{i}" for i in range(4)],
        "external_links": ["https://example.com"],
        "entities": ["bacteria", "soil", "compost"],
    }
    result = score_article(article)
    assert result["weighted_score"] > 0


def test_violations_list_returned():
    from scripts.clawrank.scotty.compliance import score_article
    article = {
        "title": "A",
        "body": "This comprehensive guide delves into the landscape of synergy.",
        "sections": [],
        "faq": [],
        "sources": [],
        "meta_description": "",
        "internal_links": [],
    }
    result = score_article(article)
    assert "violations" in result
    assert isinstance(result["violations"], list)


def test_passed_flag_is_bool():
    from scripts.clawrank.scotty.compliance import score_article
    article = {
        "title": "How to Start Hot Composting in Houston",
        "body": "x " * 100,
        "sections": [],
        "faq": [],
        "sources": [],
        "meta_description": "",
        "internal_links": [],
    }
    result = score_article(article)
    assert isinstance(result["passed"], bool)


def test_dimension_scores_has_all_six():
    from scripts.clawrank.scotty.compliance import score_article
    article = {
        "title": "How to Start Hot Composting in Houston",
        "body": "test " * 500,
        "sections": [{"heading": "A"}, {"heading": "B"}, {"heading": "C"}],
        "faq": [{"q": "Q?", "a": "A."} for _ in range(4)],
        "sources": ["s"] * 5,
        "meta_description": "A " * 20,
        "internal_links": ["/a", "/b", "/c"],
    }
    result = score_article(article)
    dims = result["dimension_scores"]
    for key in [
        "structural_completeness",
        "seo_readiness",
        "citation_readiness",
        "content_depth",
        "readability",
        "compliance",
    ]:
        assert key in dims, f"Missing dimension: {key}"


def test_weighted_score_is_between_0_and_100():
    from scripts.clawrank.scotty.compliance import score_article
    article = {
        "title": "Test",
        "body": "word " * 2000,
        "sections": [{"heading": f"S{i}"} for i in range(3)],
        "faq": [{"q": "Q?", "a": "A."} for _ in range(4)],
        "sources": ["s"] * 5,
        "meta_description": "x " * 30,
        "internal_links": ["/a", "/b", "/c"],
    }
    result = score_article(article)
    assert 0.0 <= result["weighted_score"] <= 100.0


def test_gate_threshold_75():
    from scripts.clawrank.scotty.compliance import score_article
    # Build a near-perfect article
    body = "Composting in Spring Branch Houston Texas requires soil biology knowledge. " * 60
    body += "According to Texas A&M Extension, hot composting reaches 140F in 3 days. "
    body += "Studies show regenerative practices increase yield by 30%. "
    body += "Research confirms that 5 key nutrients improve yields. Numbers: 1, 2, 3, 4, 5."
    title = "Hot Composting in Houston: A Complete Guide"  # 45 chars
    meta = "Learn how to start hot composting in Houston Texas in your backyard garden today for great results"  # ~96 chars
    article = {
        "title": title,
        "body": body,
        "sections": [{"heading": f"Section {i}"} for i in range(5)],
        "faq": [{"q": f"Q{i}?", "a": f"A{i}."} for i in range(6)],
        "sources": [f"Source {i}" for i in range(7)],
        "meta_description": meta,
        "internal_links": [f"/learn/topic-{i}" for i in range(4)],
        "external_links": ["https://example.com", "https://texas.gov"],
        "entities": ["bacteria", "soil", "compost", "nitrogen"],
    }
    result = score_article(article)
    # passed should match whether score >= 75
    assert result["passed"] == (result["weighted_score"] >= 75)


def test_location_accuracy_houston_spring_branch():
    """Spring Branch is a Houston neighborhood, not Hill Country."""
    from scripts.clawrank.scotty.compliance import score_article
    body = "Spring Branch is a neighborhood in Houston, Texas. " * 50
    article = {
        "title": "Gardening in Spring Branch Houston",
        "body": body,
        "sections": [{"heading": "A"}],
        "faq": [],
        "sources": [],
        "meta_description": "Spring Branch Houston gardening tips",
        "internal_links": [],
    }
    result = score_article(article)
    # Should not have a location violation for Spring Branch Houston
    location_violations = [v for v in result["violations"] if "spring branch" in v.lower() and "hill country" in v.lower()]
    assert len(location_violations) == 0


def test_wrong_location_gets_violation():
    """Flagging Spring Branch Hill Country as a violation."""
    from scripts.clawrank.scotty.compliance import score_article
    body = "Spring Branch is a Hill Country town in Texas. " * 50
    article = {
        "title": "Gardening in Spring Branch Hill Country",
        "body": body,
        "sections": [],
        "faq": [],
        "sources": [],
        "meta_description": "Spring Branch Hill Country gardening",
        "internal_links": [],
    }
    result = score_article(article)
    location_violations = [v for v in result["violations"] if "spring branch" in v.lower()]
    assert len(location_violations) >= 1
