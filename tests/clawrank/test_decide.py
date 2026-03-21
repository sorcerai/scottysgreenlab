import pytest
import json
from pathlib import Path


def test_decide_returns_write_when_briefs_exist(tmp_path):
    from scripts.clawrank.decide import decide
    brief_dir = tmp_path / "briefs"
    brief_dir.mkdir()
    (brief_dir / "brief-001.json").write_text(json.dumps({
        "title": "Test Brief", "target_keyword": "composting", "content_type": "how_to"
    }))
    result = decide(
        world_state={"articles_by_pillar": {"composting": 50}, "total_articles": 200},
        briefs_dir=brief_dir,
    )
    assert result["action"] == "write"


def test_decide_returns_research_when_no_briefs(tmp_path):
    from scripts.clawrank.decide import decide
    brief_dir = tmp_path / "briefs"
    brief_dir.mkdir()
    result = decide(
        world_state={
            "articles_by_pillar": {"composting": 50, "fermentation": 10, "soil-science": 5},
            "total_articles": 65,
        },
        briefs_dir=brief_dir,
    )
    assert result["action"] == "research"
    assert "soil" in result["target"].lower()
