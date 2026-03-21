import pytest
from unittest.mock import patch, MagicMock


def test_gpu_client_returns_none_on_timeout():
    from scripts.clawrank.scotty.sources import GpuModelClient
    client = GpuModelClient("http://unreachable:9999/test", timeout=0.1)
    result = client.call({"query": "test"})
    assert result is None


def test_gpu_client_returns_json_on_success():
    from scripts.clawrank.scotty.sources import GpuModelClient
    client = GpuModelClient("http://localhost:8002/intent", timeout=10)
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"intent": "informational"})
        mock_post.return_value.raise_for_status = lambda: None
        result = client.call({"query": "how to compost"})
    assert result == {"intent": "informational"}


def test_brain_search_builds_correct_command():
    from scripts.clawrank.scotty.sources import BrainSearchClient
    client = BrainSearchClient()
    cmd = client._build_command("how to compost", top_k=5)
    assert "search.py" in " ".join(cmd)
    assert "--json" in cmd


def test_competitor_data_loads():
    from scripts.clawrank.scotty.sources import CompetitorData
    data = CompetitorData()
    competitors = data.load()
    assert len(competitors) == 20
    assert competitors[0]["domain"]
