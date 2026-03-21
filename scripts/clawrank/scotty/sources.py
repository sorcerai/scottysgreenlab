"""Data source clients: GPU models, brain search, competitors."""
import json
import subprocess
from pathlib import Path
from typing import Any
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class GpuModelClient:
    """Generic HTTP client for GPU model endpoints. Returns None on failure."""

    def __init__(self, url: str, timeout: float = 10.0):
        self.url = url
        self.timeout = timeout

    def call(self, payload: dict) -> dict | None:
        try:
            resp = requests.post(self.url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None


class IntentClassifier(GpuModelClient):
    def __init__(self, url: str = "http://100.66.51.21:8002/intent"):
        super().__init__(url)

    def classify(self, query: str) -> str | None:
        result = self.call({"query": query})
        return result.get("intent") if result else None


class QueryFanout(GpuModelClient):
    def __init__(self, url: str = "http://100.66.51.21:8789/fanout"):
        super().__init__(url)

    def expand(self, query: str, top_k: int = 10) -> list[str]:
        result = self.call({"query": query, "top_k": top_k})
        return result.get("queries", []) if result else []


class SentimentAnalyzer(GpuModelClient):
    def __init__(self, url: str = "http://100.66.51.21:8002/sentiment"):
        super().__init__(url)

    def analyze(self, text: str) -> dict | None:
        return self.call({"text": text[:2000]})


class Reranker(GpuModelClient):
    def __init__(self, url: str = "http://100.66.51.21:8788/rerank"):
        super().__init__(url)

    def rerank(self, query: str, documents: list[str], top_k: int = 5) -> list[dict] | None:
        result = self.call({"query": query, "documents": documents, "top_k": top_k})
        return result.get("results") if result else None


class BrainSearchClient:
    """Subprocess wrapper for scripts/brain/search.py."""

    def __init__(self):
        self.script = PROJECT_ROOT / "scripts" / "brain" / "search.py"

    def _build_command(self, query: str, top_k: int = 10, content_type: str | None = None) -> list[str]:
        cmd = ["python3", str(self.script), query, "--json"]
        if content_type:
            cmd.extend(["--type", content_type])
        return cmd

    def search(self, query: str, top_k: int = 10, content_type: str | None = None) -> list[dict]:
        cmd = self._build_command(query, top_k, content_type)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(PROJECT_ROOT),
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            return []
        except Exception:
            return []


class CompetitorData:
    """Load competitor profiles from src/data/competitors.json."""

    def __init__(self):
        self.path = PROJECT_ROOT / "src" / "data" / "competitors.json"

    def load(self) -> list[dict]:
        return json.loads(self.path.read_text())
