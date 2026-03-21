import pytest
import tempfile
import yaml
from pathlib import Path

MINIMAL_CONFIG = {
    "project": {"name": "scottysgreenlab"},
    "niche": {
        "topic": "regenerative agriculture",
        "domains": ["scottysgardeninglab.com"],
        "seed_keywords": ["composting"],
        "target_audiences": ["home gardeners"],
        "entities": ["Living Soil Salad Mix"],
        "locale": "en-US",
        "geo_targets": ["Spring Branch TX"],
    },
    "runtime": {"timezone": "America/Chicago"},
    "knowledge_base": {"backend": "markdown", "root": "artifacts/clawrank/kb"},
    "llm": {
        "provider": "cli",
        "default_backend": "gemini",
        "heavy_backend": "claude",
    },
    "brain": {
        "connection_env": "BRAIN_DB_URL",
        "database_id": "wiixc9eeb7",
    },
    "gpu_models": {
        "intent_classifier": "http://100.66.51.21:8002/intent",
        "reranker": "http://100.66.51.21:8788/rerank",
    },
}

def test_config_loads_brain_section():
    from scripts.clawrank.core.config_loader import CRConfig
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.dump(MINIMAL_CONFIG, f)
        f.flush()
        cfg = CRConfig.load(f.name, check_paths=False)
    assert cfg.brain.connection_env == "BRAIN_DB_URL"
    assert cfg.brain.database_id == "wiixc9eeb7"

def test_config_loads_gpu_models_section():
    from scripts.clawrank.core.config_loader import CRConfig
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.dump(MINIMAL_CONFIG, f)
        f.flush()
        cfg = CRConfig.load(f.name, check_paths=False)
    assert cfg.gpu_models.reranker == "http://100.66.51.21:8788/rerank"
    assert cfg.gpu_models.intent_classifier == "http://100.66.51.21:8002/intent"

def test_config_loads_heavy_backend():
    from scripts.clawrank.core.config_loader import CRConfig
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.dump(MINIMAL_CONFIG, f)
        f.flush()
        cfg = CRConfig.load(f.name, check_paths=False)
    assert cfg.llm.heavy_backend == "claude"
    assert cfg.llm.default_backend == "gemini"
