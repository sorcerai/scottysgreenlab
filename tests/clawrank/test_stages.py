import pytest


def test_content_type_has_seasonal():
    from scripts.clawrank.core.pipeline.stages import ContentType
    assert hasattr(ContentType, "SEASONAL")


def test_content_type_no_pricing():
    from scripts.clawrank.core.pipeline.stages import ContentType
    assert not hasattr(ContentType, "PRICING")


def test_content_type_no_integration():
    from scripts.clawrank.core.pipeline.stages import ContentType
    assert not hasattr(ContentType, "INTEGRATION")


def test_content_type_no_alternatives():
    from scripts.clawrank.core.pipeline.stages import ContentType
    assert not hasattr(ContentType, "ALTERNATIVES")


def test_stage_enum_has_23_stages():
    from scripts.clawrank.core.pipeline.stages import Stage
    assert len(Stage) == 23


def test_gate_stages():
    from scripts.clawrank.core.pipeline.stages import Stage, GATE_STAGES
    assert Stage.KEYWORD_SCREEN in GATE_STAGES
    assert Stage.RESEARCH_BRIEF in GATE_STAGES
    assert Stage.QUALITY_GATE in GATE_STAGES


def test_noncritical_stages():
    from scripts.clawrank.core.pipeline.stages import Stage, NONCRITICAL_STAGES
    assert Stage.LINK_VERIFY in NONCRITICAL_STAGES
    assert Stage.SITEMAP_GEN in NONCRITICAL_STAGES
    assert Stage.KNOWLEDGE_ARCHIVE in NONCRITICAL_STAGES


def test_url_patterns_has_seasonal():
    from scripts.clawrank.core.pipeline.stages import ContentType, URL_PATTERNS
    assert ContentType.SEASONAL in URL_PATTERNS


def test_schema_map_has_seasonal():
    from scripts.clawrank.core.pipeline.stages import ContentType, SCHEMA_MAP
    assert ContentType.SEASONAL in SCHEMA_MAP
