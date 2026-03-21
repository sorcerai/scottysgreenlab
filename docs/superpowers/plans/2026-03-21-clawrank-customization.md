# ClawRank Customization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port ClawRank's 23-stage content pipeline into scottysgreenlab with a fresh domain layer for Astro JSON output, brain DB, GPU models, and Scotty's voice.

**Architecture:** Copy core engine from nautix-website (models, pipeline, config loader, prompts loader, evolution, LLM adapter) into `scripts/clawrank/core/`. Build fresh domain layer in `scripts/clawrank/scotty/` that bridges the core to scottysgreenlab's infrastructure (brain DB, voice profile, GPU models, JSON output for /learn/ pipeline).

**Tech Stack:** Python 3.11+, psycopg2 (brain DB), requests (GPU model HTTP clients), PyYAML (config), argparse (CLI). No new dependencies beyond what scripts/brain/ already uses.

**Spec:** `docs/superpowers/specs/2026-03-21-clawrank-customization-design.md`

**Source reference:** `/Users/ariapramesi/repos/nautix-website/scripts/clawrank/`

---

## File Map

### Core Engine (copy + modify from nautix)
| File | Source | Modifications |
|------|--------|---------------|
| `scripts/clawrank/core/__init__.py` | New | Empty init |
| `scripts/clawrank/core/models.py` | nautix `models.py` (322 lines) | Replace `ac_post_type` with `pillar`, `related_industries` with `matched_transcripts`. Add `has_strong_match: bool = False`. Add `seasonal` content type handling. |
| `scripts/clawrank/core/config_loader.py` | nautix `config_loader.py` (459 lines) | Add `BrainConfig`, `GpuModelsConfig` dataclasses. Add `brain` and `gpu_models` sections to `CRConfig`. Add `llm.heavy_backend` field. |
| `scripts/clawrank/core/prompts_loader.py` | nautix `prompts_loader.py` (167 lines) | Change default prompts path to `prompts.scotty.yaml`. No other changes. |
| `scripts/clawrank/core/evolution.py` | nautix `evolution.py` (223 lines) | No changes. |
| `scripts/clawrank/core/acpx_adapter.py` | nautix `acpx_adapter.py` (701 lines) | Add per-stage backend routing (default_backend vs heavy_backend). Add `call_gpu_model(url, payload)` method with 10s timeout + graceful fallback. |
| `scripts/clawrank/core/pipeline/__init__.py` | New | Empty init |
| `scripts/clawrank/core/pipeline/executor.py` | nautix `pipeline/executor.py` (399 lines) | Wire scotty adapter calls into `_build_prompt_vars`. Add GPU model calls in relevant stages. |
| `scripts/clawrank/core/pipeline/stages.py` | nautix `pipeline/stages.py` (412 lines) | Add `SEASONAL` to `ContentType` enum. Remove inapplicable types (PRICING, INTEGRATION, ALTERNATIVES). Update URL_PATTERNS and SCHEMA_MAP. |
| `scripts/clawrank/core/discover.py` | nautix `discover.py` (~1883 lines) | Copy competitive discovery utilities for Stage 7. Modify competitor URLs and crawl patterns for gardening domain. |

### Domain Layer (fresh code)
| File | Purpose |
|------|---------|
| `scripts/clawrank/scotty/__init__.py` | Empty init |
| `scripts/clawrank/scotty/voice.py` | Parse scotty-voice-profile.md into prompt injection blocks |
| `scripts/clawrank/scotty/sources.py` | HTTP clients for GPU models (8002, 8789, 8788) + brain search subprocess |
| `scripts/clawrank/scotty/world_state.py` | Brain DB queries via psycopg2 |
| `scripts/clawrank/scotty/adapter.py` | Central bridge: ClawRank core <-> scottysgreenlab infra |
| `scripts/clawrank/scotty/compliance.py` | 6-dimension quality scoring adapted for JSON articles |
| `scripts/clawrank/scotty/publish.py` | ClawRankDocument -> JSON for pseo-questions-final.json |

### Config & Entry Points
| File | Purpose |
|------|---------|
| `scripts/clawrank/config.scotty.yaml` | Project-specific YAML config |
| `scripts/clawrank/prompts.scotty.yaml` | Custom prompts with Scotty's voice blocks |
| `scripts/clawrank/run.py` | CLI entry point (auto/batch/research/--keyword modes) |
| `scripts/clawrank/decide.py` | Decision engine (what to write next) |
| `scripts/clawrank/daily-run.sh` | Cron wrapper for scheduled runs |

### Tests
| File | Covers |
|------|--------|
| `tests/clawrank/test_voice.py` | Voice profile parsing |
| `tests/clawrank/test_sources.py` | GPU model clients (mocked HTTP) |
| `tests/clawrank/test_world_state.py` | Brain DB queries (mocked psycopg2) |
| `tests/clawrank/test_compliance.py` | Quality scoring dimensions |
| `tests/clawrank/test_publish.py` | JSON output schema |
| `tests/clawrank/test_config.py` | Config loading + new sections |
| `tests/clawrank/test_stages.py` | Stage enum + seasonal type |
| `tests/clawrank/test_adapter.py` | Adapter method orchestration |
| `tests/clawrank/test_models.py` | Model field defaults + scotty-specific fields |
| `tests/clawrank/test_decide.py` | Decision engine logic (briefs exist -> WRITE, no briefs -> RESEARCH) |
| `tests/clawrank/test_run.py` | CLI arg parsing including --dry-run and --verbose |

---

## Task 1: Scaffold Directory Structure

**Files:**
- Create: `scripts/clawrank/core/__init__.py`
- Create: `scripts/clawrank/core/pipeline/__init__.py`
- Create: `scripts/clawrank/scotty/__init__.py`
- Create: `scripts/clawrank/__init__.py`
- Create: `tests/clawrank/__init__.py`
- Create: `artifacts/clawrank/briefs/.gitkeep`
- Create: `artifacts/clawrank/drafts/.gitkeep`
- Create: `artifacts/clawrank/kb/.gitkeep`
- Create: `artifacts/clawrank/logs/.gitkeep`
- Create: `artifacts/clawrank/checkpoints/.gitkeep`
- Create: `artifacts/clawrank/decisions/.gitkeep`

- [ ] **Step 1: Create all directories and init files**

```bash
mkdir -p scripts/clawrank/core/pipeline
mkdir -p scripts/clawrank/scotty
mkdir -p tests/clawrank
mkdir -p artifacts/clawrank/{briefs,drafts,kb,logs,checkpoints,decisions}
touch scripts/clawrank/__init__.py
touch scripts/clawrank/core/__init__.py
touch scripts/clawrank/core/pipeline/__init__.py
touch scripts/clawrank/scotty/__init__.py
touch tests/clawrank/__init__.py
touch artifacts/clawrank/{briefs,drafts,kb,logs,checkpoints,decisions}/.gitkeep
```

- [ ] **Step 2: Verify structure**

Run: `find scripts/clawrank -type f | sort`

Expected: All init files and directories present.

- [ ] **Step 3: Commit**

```bash
git add scripts/clawrank/ tests/clawrank/ artifacts/clawrank/
git commit -m "scaffold: clawrank directory structure"
```

---

## Task 2: Copy and Modify Core Engine — stages.py

**Files:**
- Source: `/Users/ariapramesi/repos/nautix-website/scripts/clawrank/pipeline/stages.py`
- Create: `scripts/clawrank/core/pipeline/stages.py`
- Test: `tests/clawrank/test_stages.py`

- [ ] **Step 1: Write test for ContentType enum including SEASONAL**

```python
# tests/clawrank/test_stages.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ariapramesi/repos/scottysgreenlab && python -m pytest tests/clawrank/test_stages.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: Copy stages.py from nautix and modify**

Copy `/Users/ariapramesi/repos/nautix-website/scripts/clawrank/pipeline/stages.py` to `scripts/clawrank/core/pipeline/stages.py`.

Modifications:
1. Add `SEASONAL = "seasonal"` to `ContentType` enum
2. Remove `PRICING`, `INTEGRATION`, `ALTERNATIVES` from `ContentType`
3. Add `ContentType.SEASONAL: "/learn/{slug}"` to `URL_PATTERNS`
4. Add `ContentType.SEASONAL: ("Article", "BreadcrumbList", "FAQPage")` to `SCHEMA_MAP`
5. Update all existing URL_PATTERNS to use `/learn/{slug}` format instead of nautix patterns

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ariapramesi/repos/scottysgreenlab && python -m pytest tests/clawrank/test_stages.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/core/pipeline/stages.py tests/clawrank/test_stages.py
git commit -m "feat: add stages.py with SEASONAL type, scotty URL patterns"
```

---

## Task 3: Copy and Modify Core Engine — models.py

**Files:**
- Source: `/Users/ariapramesi/repos/nautix-website/scripts/clawrank/models.py`
- Create: `scripts/clawrank/core/models.py`

- [ ] **Step 1: Copy models.py from nautix and modify**

Copy to `scripts/clawrank/core/models.py`.

Modifications:
1. In `ClawRankDocument`: replace `ac_post_type: str = ""` with `pillar: str = ""`
2. Replace `related_industries: list[str] = field(default_factory=list)` with `matched_transcripts: list[dict] = field(default_factory=list)`
3. Add `has_strong_match: bool = False` field to ClawRankDocument
4. Keep `related_products`, `brief_id` as-is (still useful)
5. In `ContentPlanItem`: same replacements (`ac_post_type` -> `pillar`, `related_industries` -> `matched_transcripts`)

- [ ] **Step 2: Verify import works**

Run: `cd /Users/ariapramesi/repos/scottysgreenlab && python -c "from scripts.clawrank.core.models import ClawRankDocument; d = ClawRankDocument(id='test', content_type='how_to'); print(d.pillar, d.matched_transcripts, d.has_strong_match)"`

Expected: `'' [] False`

- [ ] **Step 3: Write test file for models**

```python
# tests/clawrank/test_models.py
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
    assert not hasattr(ClawRankDocument, "ac_post_type") or "ac_post_type" not in ClawRankDocument.__dataclass_fields__

def test_clawrank_document_no_related_industries():
    from scripts.clawrank.core.models import ClawRankDocument
    assert not hasattr(ClawRankDocument, "related_industries") or "related_industries" not in ClawRankDocument.__dataclass_fields__
```

- [ ] **Step 3: Commit**

```bash
git add scripts/clawrank/core/models.py
git commit -m "feat: add models.py with scotty-specific fields"
```

---

## Task 4: Copy Core Engine — prompts_loader.py and evolution.py

**Files:**
- Source: nautix `prompts_loader.py` (167 lines), `evolution.py` (223 lines)
- Create: `scripts/clawrank/core/prompts_loader.py`, `scripts/clawrank/core/evolution.py`

- [ ] **Step 1: Copy prompts_loader.py**

Copy to `scripts/clawrank/core/prompts_loader.py`.

One change: update default prompts path from `"prompts.nautix.yaml"` to point to `Path(__file__).parent.parent / "prompts.scotty.yaml"`.

- [ ] **Step 2: Copy evolution.py as-is**

Copy to `scripts/clawrank/core/evolution.py`. No modifications needed.

- [ ] **Step 3: Verify imports**

Run: `python -c "from scripts.clawrank.core.prompts_loader import PromptManager; print('OK')"`
Run: `python -c "from scripts.clawrank.core.evolution import EvolutionStore, LessonEntry; print('OK')"`

Expected: Both print OK

- [ ] **Step 4: Commit**

```bash
git add scripts/clawrank/core/prompts_loader.py scripts/clawrank/core/evolution.py
git commit -m "feat: add prompts_loader and evolution (core engine)"
```

---

## Task 5: Copy and Modify Core Engine — config_loader.py

**Files:**
- Source: nautix `config_loader.py` (459 lines)
- Create: `scripts/clawrank/core/config_loader.py`
- Test: `tests/clawrank/test_config.py`

- [ ] **Step 1: Write test for new config sections**

```python
# tests/clawrank/test_config.py
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
    assert "intent_classifier" in vars(cfg.gpu_models) or hasattr(cfg.gpu_models, "intent_classifier")
    assert cfg.gpu_models.reranker == "http://100.66.51.21:8788/rerank"


def test_config_loads_heavy_backend():
    from scripts.clawrank.core.config_loader import CRConfig
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.dump(MINIMAL_CONFIG, f)
        f.flush()
        cfg = CRConfig.load(f.name, check_paths=False)
    assert cfg.llm.heavy_backend == "claude"
    assert cfg.llm.default_backend == "gemini"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/clawrank/test_config.py -v`

Expected: FAIL

- [ ] **Step 3: Copy config_loader.py and add new sections**

Copy nautix `config_loader.py` to `scripts/clawrank/core/config_loader.py`.

Add these new frozen dataclasses:

```python
@dataclass(frozen=True)
class BrainConfig:
    connection_env: str = "BRAIN_DB_URL"
    database_id: str = ""

@dataclass(frozen=True)
class GpuModelsConfig:
    intent_classifier: str = ""
    query_fanout: str = ""
    sentiment: str = ""
    reranker: str = ""
    embedder: str = "local://e5-base-v2"
```

Add to `LlmConfig`:
```python
    default_backend: str = "gemini"
    heavy_backend: str = "claude"
```

Add to `CRConfig`:
```python
    brain: BrainConfig = field(default_factory=BrainConfig)
    gpu_models: GpuModelsConfig = field(default_factory=GpuModelsConfig)
```

Update `from_dict()` to parse `brain` and `gpu_models` sections from YAML.

For `provider: "cli"`, skip the `base_url`/`api_key_env` requirement (same as ACPX provider skip).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/clawrank/test_config.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/core/config_loader.py tests/clawrank/test_config.py
git commit -m "feat: add config_loader with brain + gpu_models sections"
```

---

## Task 6: Copy and Modify Core Engine — acpx_adapter.py

**Files:**
- Source: nautix `acpx_adapter.py` (701 lines)
- Create: `scripts/clawrank/core/acpx_adapter.py`

- [ ] **Step 1: Copy acpx_adapter.py and add per-stage routing + GPU model support**

Copy to `scripts/clawrank/core/acpx_adapter.py`.

Modifications:

1. Add `heavy_backend` param to `__init__`:
```python
def __init__(
    self,
    backend: str = "gemini",
    heavy_backend: str = "claude",  # NEW
    session_prefix: str = "clawrank",
    max_retries: int = 3,
    retry_delay: float = 2.0,
    claude_model: str = "",
) -> None:
    self.heavy_backend = heavy_backend
```

2. Define `LONG_STAGES` constant (already exists in nautix but verify): `LONG_STAGES = {12, 13, 15, 20}` at module level.

3. Modify `complete()` routing: if `stage in LONG_STAGES` and `self.heavy_backend != self.backend`, route to heavy_backend instead:
```python
def complete(self, system_prompt, user_prompt, stage, max_tokens=4096, no_wait=False):
    effective_backend = self.heavy_backend if stage in LONG_STAGES else self.backend
    # Route based on effective_backend
```

3. Add GPU model method:
```python
def call_gpu_model(self, url: str, payload: dict, timeout: float = 10.0) -> dict | None:
    """HTTP POST to GPU model endpoint. Returns None on failure (graceful degradation)."""
    import requests
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None
```

- [ ] **Step 2: Verify import and basic functionality**

Run: `python -c "from scripts.clawrank.core.acpx_adapter import AcpxLLMAdapter; a = AcpxLLMAdapter(backend='gemini', heavy_backend='claude'); print(a.heavy_backend)"`

Expected: `claude`

- [ ] **Step 3: Commit**

```bash
git add scripts/clawrank/core/acpx_adapter.py
git commit -m "feat: add acpx_adapter with per-stage routing + GPU model support"
```

---

## Task 7: Copy Core Engine — pipeline/executor.py

**Files:**
- Source: nautix `pipeline/executor.py` (399 lines)
- Create: `scripts/clawrank/core/pipeline/executor.py`

- [ ] **Step 1: Copy executor.py**

Copy to `scripts/clawrank/core/pipeline/executor.py`.

Modifications:
1. Update imports to use `scripts.clawrank.core.*` paths
2. Add optional `domain_adapter` param to `__init__`:
```python
def __init__(self, *, llm_adapter, prompt_manager, evolution_store=None,
             config=None, artifacts_dir=None, auto_approve=False,
             hitl_required_stages=(5, 9, 16),
             domain_adapter=None):  # NEW
    self.domain_adapter = domain_adapter
```
3. In `_build_prompt_vars()`, if `self.domain_adapter` is set, call `adapter.load_voice_rules()` and inject into vars for stages 12, 13, 17, 18.

- [ ] **Step 2: Verify import**

Run: `python -c "from scripts.clawrank.core.pipeline.executor import PipelineExecutor; print('OK')"`

Expected: OK

- [ ] **Step 3: Commit**

```bash
git add scripts/clawrank/core/pipeline/executor.py
git commit -m "feat: add pipeline executor with domain adapter support"
```

---

## Task 8: Copy and Modify Core Engine — discover.py

**Files:**
- Source: `/Users/ariapramesi/repos/nautix-website/scripts/clawrank/discover.py`
- Create: `scripts/clawrank/core/discover.py`

- [ ] **Step 1: Copy discover.py from nautix**

Copy to `scripts/clawrank/core/discover.py`.

Modifications:
1. Update competitor URL patterns for gardening domain (replace lending/finance URLs with gardening/agriculture)
2. Update crawl patterns to match `src/data/competitors.json` structure (20 gardening competitors)
3. Update imports to reference `scripts.clawrank.core.*` paths

- [ ] **Step 2: Verify import**

Run: `python -c "from scripts.clawrank.core.discover import *; print('OK')"`

Expected: OK (may warn about missing dependencies — that's fine at this stage)

- [ ] **Step 3: Commit**

```bash
git add scripts/clawrank/core/discover.py
git commit -m "feat: add discover.py — competitive discovery for Stage 7"
```

---

## Task 9: Create scotty/voice.py (was Task 8)

**Files:**
- Create: `scripts/clawrank/scotty/voice.py`
- Test: `tests/clawrank/test_voice.py`

- [ ] **Step 1: Write failing test**

```python
# tests/clawrank/test_voice.py
import pytest
from pathlib import Path

VOICE_PROFILE_PATH = Path("src/data/scotty-voice-profile.md")


def test_voice_profile_exists():
    assert VOICE_PROFILE_PATH.exists()


def test_load_voice_returns_dict():
    from scripts.clawrank.scotty.voice import load_voice_profile
    profile = load_voice_profile(VOICE_PROFILE_PATH)
    assert isinstance(profile, dict)


def test_voice_has_banned_phrases():
    from scripts.clawrank.scotty.voice import load_voice_profile
    profile = load_voice_profile(VOICE_PROFILE_PATH)
    assert "banned_phrases" in profile
    assert len(profile["banned_phrases"]) > 0


def test_voice_has_tone_rules():
    from scripts.clawrank.scotty.voice import load_voice_profile
    profile = load_voice_profile(VOICE_PROFILE_PATH)
    assert "tone_rules" in profile


def test_build_voice_block_returns_string():
    from scripts.clawrank.scotty.voice import load_voice_profile, build_voice_block
    profile = load_voice_profile(VOICE_PROFILE_PATH)
    block = build_voice_block(profile)
    assert isinstance(block, str)
    assert len(block) > 100
    assert "y'all" in block.lower() or "bacteria" in block.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/clawrank/test_voice.py -v`

Expected: FAIL

- [ ] **Step 3: Implement voice.py**

```python
# scripts/clawrank/scotty/voice.py
"""Parse Scotty's voice profile into prompt injection blocks."""
from pathlib import Path
import re


def load_voice_profile(path: Path) -> dict:
    """Parse scotty-voice-profile.md into structured dict."""
    text = path.read_text()

    # Extract vocabulary fingerprint (top words with frequencies)
    vocab = []
    vocab_match = re.findall(r"(\w+)\s*[\(\[](\d+)x?[\)\]]", text[:5000])
    for word, count in vocab_match[:20]:
        vocab.append({"word": word, "count": int(count)})

    # Extract banned phrases from quality standard patterns
    banned = [
        "delve", "landscape", "leverage", "comprehensive guide",
        "game-changer", "synergy", "cutting-edge", "robust",
        "streamline", "paradigm", "holistic approach",
    ]

    # Extract tone rules from profile sections
    tone_rules = []
    if "casual" in text.lower() and "scientific" in text.lower():
        tone_rules.append("conversational-scientific blend")
    if "y'all" in text:
        tone_rules.append("Texas dialect — use y'all naturally")
    if "first-person" in text.lower() or "my " in text[:2000]:
        tone_rules.append("first-person experience, not third-person authority")
    tone_rules.append("teaching cadence: short claim, medium explanation, punchy payoff")
    tone_rules.append("low-pressure closer, never hard-sell")

    # Extract signature phrases
    sig_phrases = []
    sig_match = re.findall(r'"([^"]{5,50})"', text[:10000])
    sig_phrases = sig_match[:10] if sig_match else []

    # Extract key concepts
    concepts = []
    for concept in ["living soil", "prokaryotic association", "law of returns",
                    "lacto-fermentation", "nutrient density", "regenerative"]:
        if concept.lower() in text.lower():
            concepts.append(concept)

    return {
        "vocabulary": vocab,
        "banned_phrases": banned,
        "tone_rules": tone_rules,
        "signature_phrases": sig_phrases,
        "key_concepts": concepts,
        "raw_text": text,
    }


def build_voice_block(profile: dict) -> str:
    """Build prompt injection block from voice profile."""
    lines = ["## Scotty's Voice Rules", ""]
    lines.append("You are writing as Scotty from Scotty's Gardening Lab in Spring Branch, TX.")
    lines.append("")

    lines.append("### Tone")
    for rule in profile["tone_rules"]:
        lines.append(f"- {rule}")
    lines.append("")

    lines.append("### Key Vocabulary (use these naturally)")
    for v in profile["vocabulary"][:10]:
        lines.append(f"- {v['word']} ({v['count']}x in transcripts)")
    lines.append("")

    lines.append("### Key Concepts (weave in where relevant)")
    for c in profile["key_concepts"]:
        lines.append(f"- {c}")
    lines.append("")

    lines.append("### BANNED Phrases (never use these)")
    for b in profile["banned_phrases"]:
        lines.append(f"- \"{b}\"")
    lines.append("")

    lines.append("### Signature Phrases (use sparingly)")
    for s in profile["signature_phrases"][:5]:
        lines.append(f"- \"{s}\"")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/clawrank/test_voice.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/scotty/voice.py tests/clawrank/test_voice.py
git commit -m "feat: add voice.py — parse Scotty's voice profile into prompt blocks"
```

---

## Task 9: Create scotty/sources.py

**Files:**
- Create: `scripts/clawrank/scotty/sources.py`
- Test: `tests/clawrank/test_sources.py`

- [ ] **Step 1: Write failing test**

```python
# tests/clawrank/test_sources.py
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
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"intent": "informational"},
        )
        mock_post.return_value.raise_for_status = lambda: None
        result = client.call({"query": "how to compost"})
    assert result == {"intent": "informational"}


def test_brain_search_builds_correct_command():
    from scripts.clawrank.scotty.sources import BrainSearchClient
    client = BrainSearchClient()
    cmd = client._build_command("how to compost", top_k=5)
    assert "search.py" in cmd[1] or "search.py" in " ".join(cmd)
    assert "--json" in cmd


def test_competitor_data_loads():
    from scripts.clawrank.scotty.sources import CompetitorData
    data = CompetitorData()
    competitors = data.load()
    assert len(competitors) == 20
    assert competitors[0]["domain"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/clawrank/test_sources.py -v`

Expected: FAIL

- [ ] **Step 3: Implement sources.py**

```python
# scripts/clawrank/scotty/sources.py
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
        result = self.call({
            "query": query,
            "documents": documents,
            "top_k": top_k,
        })
        return result.get("results") if result else None


class BrainSearchClient:
    """Subprocess wrapper for scripts/brain/search.py."""

    def __init__(self):
        self.script = PROJECT_ROOT / "scripts" / "brain" / "search.py"

    def _build_command(self, query: str, top_k: int = 10, content_type: str | None = None) -> list[str]:
        cmd = ["python3", str(self.script), query, "--json"]
        if content_type:
            cmd.extend(["--type", content_type])
        # Note: search.py uses SEARCH_CONFIG.max_results (default 10).
        # top_k is used by the caller to limit results after search returns.
        return cmd

    def search(self, query: str, top_k: int = 10, content_type: str | None = None) -> list[dict]:
        cmd = self._build_command(query, top_k, content_type)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT))
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/clawrank/test_sources.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/scotty/sources.py tests/clawrank/test_sources.py
git commit -m "feat: add sources.py — GPU model clients + brain search + competitors"
```

---

## Task 10: Create scotty/world_state.py

**Files:**
- Create: `scripts/clawrank/scotty/world_state.py`
- Test: `tests/clawrank/test_world_state.py`

- [ ] **Step 1: Write failing test (mocked DB)**

```python
# tests/clawrank/test_world_state.py
import pytest
from unittest.mock import patch, MagicMock


def test_collect_returns_dict():
    from scripts.clawrank.scotty.world_state import collect_brain_state
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.return_value = [("transcript_video", 359)]
    mock_cursor.description = [("content_type",), ("count",)]

    with patch("scripts.clawrank.scotty.world_state._get_connection", return_value=mock_conn):
        state = collect_brain_state()
    assert isinstance(state, dict)
    assert "total_docs" in state


def test_state_has_expected_keys():
    from scripts.clawrank.scotty.world_state import collect_brain_state
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchall.side_effect = [
        [("transcript_video", 359), ("transcript_section", 428)],  # doc counts
        [("Concept", 6), ("Product", 5)],  # entity counts
        [(3,)],  # cannibalization count
    ]
    mock_cursor.fetchone.return_value = (787,)
    mock_cursor.description = [("a",), ("b",)]

    with patch("scripts.clawrank.scotty.world_state._get_connection", return_value=mock_conn):
        state = collect_brain_state()
    assert "by_type" in state
    assert "entity_counts" in state
    assert "cannibalization_count" in state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/clawrank/test_world_state.py -v`

Expected: FAIL

- [ ] **Step 3: Implement world_state.py**

```python
# scripts/clawrank/scotty/world_state.py
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

            # Cannibalization count (cosine > 0.85 between blog_post embeddings)
            cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT a.id
                    FROM brain_documents a
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/clawrank/test_world_state.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/scotty/world_state.py tests/clawrank/test_world_state.py
git commit -m "feat: add world_state.py — brain DB snapshot for decision engine"
```

---

## Task 11: Create scotty/compliance.py

**Files:**
- Create: `scripts/clawrank/scotty/compliance.py`
- Test: `tests/clawrank/test_compliance.py`

- [ ] **Step 1: Write failing test**

```python
# tests/clawrank/test_compliance.py
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
    assert len(violations) >= 3  # delve, comprehensive guide, landscape


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/clawrank/test_compliance.py -v`

Expected: FAIL

- [ ] **Step 3: Implement compliance.py**

Create `scripts/clawrank/scotty/compliance.py` implementing the 6-dimension quality scorer adapted for JSON articles (not MDX). Each dimension function takes the article dict and returns (score: float 0-100, checks: list). `score_article()` computes the weighted total and returns `{weighted_score, passed, dimension_scores, violations}`.

Weights: structural 0.20, seo 0.20, citation 0.20, depth 0.15, readability 0.10, compliance 0.15.
Gate threshold: 75.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/clawrank/test_compliance.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/scotty/compliance.py tests/clawrank/test_compliance.py
git commit -m "feat: add compliance.py — 6-dimension quality scoring for JSON articles"
```

---

## Task 12: Create scotty/publish.py

**Files:**
- Create: `scripts/clawrank/scotty/publish.py`
- Test: `tests/clawrank/test_publish.py`

- [ ] **Step 1: Write failing test**

```python
# tests/clawrank/test_publish.py
import pytest


def test_document_to_json_has_required_fields():
    from scripts.clawrank.scotty.publish import document_to_json
    from scripts.clawrank.core.models import ClawRankDocument
    doc = ClawRankDocument(
        id="test-1",
        content_type="how_to",
        title="How to Start Composting",
        slug="how-to-start-composting",
        body_markdown="Full article body here.",
        target_keyword="how to start composting",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/clawrank/test_publish.py -v`

Expected: FAIL

- [ ] **Step 3: Implement publish.py**

```python
# scripts/clawrank/scotty/publish.py
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
        "keywords": doc.secondary_keywords or [doc.target_keyword],
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
    # Replace if slug already exists
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/clawrank/test_publish.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/scotty/publish.py tests/clawrank/test_publish.py
git commit -m "feat: add publish.py — ClawRankDocument to JSON for /learn/ pipeline"
```

---

## Task 13: Create scotty/adapter.py

**Files:**
- Create: `scripts/clawrank/scotty/adapter.py`
- Test: `tests/clawrank/test_adapter.py`

- [ ] **Step 1: Write failing test**

```python
# tests/clawrank/test_adapter.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_adapter_has_all_methods():
    from scripts.clawrank.scotty.adapter import ScottyAdapter
    adapter = ScottyAdapter.__new__(ScottyAdapter)
    methods = ["load_voice_rules", "search_brain", "check_cannibalization",
               "find_content_gaps", "existing_articles", "internal_link_map",
               "product_data", "entity_graph"]
    for m in methods:
        assert hasattr(adapter, m), f"Missing method: {m}"


def test_product_data_returns_4_products():
    from scripts.clawrank.scotty.adapter import ScottyAdapter
    adapter = ScottyAdapter()
    products = adapter.product_data()
    assert len(products) == 4  # No duck eggs
    names = [p.get("name", p.get("title", "")) for p in products]
    assert not any("duck" in n.lower() for n in names)


def test_load_voice_rules_returns_string():
    from scripts.clawrank.scotty.adapter import ScottyAdapter
    adapter = ScottyAdapter()
    voice = adapter.load_voice_rules()
    assert isinstance(voice, str)
    assert len(voice) > 100


def test_existing_articles_returns_list():
    from scripts.clawrank.scotty.adapter import ScottyAdapter
    adapter = ScottyAdapter()
    articles = adapter.existing_articles()
    assert isinstance(articles, list)
    assert len(articles) > 0  # pseo-questions-final.json has 200+ entries


def test_internal_link_map_returns_dict():
    from scripts.clawrank.scotty.adapter import ScottyAdapter
    adapter = ScottyAdapter()
    links = adapter.internal_link_map()
    assert isinstance(links, dict)
    assert len(links) > 0
    # All values should be /learn/ URLs
    for slug, url in links.items():
        assert "/learn/" in url


def test_search_brain_with_mock():
    from scripts.clawrank.scotty.adapter import ScottyAdapter
    adapter = ScottyAdapter()
    with patch.object(adapter, "_brain_client") as mock_brain:
        mock_brain.search.return_value = [{"title": "test", "similarity": 0.9}]
        results = adapter.search_brain("composting", top_k=5)
    assert len(results) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/clawrank/test_adapter.py -v`

Expected: FAIL

- [ ] **Step 3: Implement adapter.py**

Create `scripts/clawrank/scotty/adapter.py` — the central bridge class `ScottyAdapter` that:
- `__init__()`: loads voice profile, initializes sources, caches products
- `load_voice_rules()`: calls `voice.load_voice_profile()` + `build_voice_block()`
- `search_brain(query, top_k)`: calls `BrainSearchClient.search()`
- `check_cannibalization(slug, embedding)`: subprocess to `scripts/brain/cannibalize.py --query`
- `find_content_gaps()`: subprocess to `scripts/brain/gaps.py`
- `existing_articles()`: loads `pseo-questions-final.json`
- `internal_link_map()`: builds dict of slug -> URL from existing articles + products
- `product_data()`: loads from `src/data/products.ts` (parse TypeScript exports) or falls back to brain entities where entity_type='Product'. Filters out duck eggs.
- `entity_graph()`: queries brain_entities + brain_entity_relationships

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/clawrank/test_adapter.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/scotty/adapter.py tests/clawrank/test_adapter.py
git commit -m "feat: add adapter.py — central bridge between ClawRank and scottysgreenlab"
```

---

## Task 14: Create config.scotty.yaml

**Files:**
- Create: `scripts/clawrank/config.scotty.yaml`

- [ ] **Step 1: Write config file**

Write the full YAML config as specified in the design doc (section 4). All values defined — project name, niche (4 products, no duck eggs), runtime (America/Chicago), brain (BRAIN_DB_URL env var, wiixc9eeb7), gpu_models (4 endpoints), LLM (cli provider, gemini default, claude heavy), content (8 types with word counts), publish (astro, json, data/content-pipeline/).

- [ ] **Step 2: Validate config loads**

Run: `python -c "from scripts.clawrank.core.config_loader import CRConfig; c = CRConfig.load('scripts/clawrank/config.scotty.yaml', check_paths=False); print(c.project.name, c.brain.database_id)"`

Expected: `scottysgreenlab wiixc9eeb7`

- [ ] **Step 3: Commit**

```bash
git add scripts/clawrank/config.scotty.yaml
git commit -m "feat: add config.scotty.yaml — scottysgreenlab ClawRank config"
```

---

## Task 15: Create prompts.scotty.yaml

**Files:**
- Create: `scripts/clawrank/prompts.scotty.yaml`

- [ ] **Step 1: Write prompts file**

Create the full prompts YAML with:
- `blocks`: niche_constraint (4 products, 6 pillars, Spring Branch TX), quality_standard (banned phrases + Scotty voice), geo_optimization (answer targets), internal_linking (/learn/{slug} patterns)
- `stages`: at minimum customize stages 1, 9, 10, 11, 12, 14, 20 with scottysgreenlab-specific prompts. Other stages can use generic prompts.
- `content_type_templates`: templates for all 8 content types

Reference nautix's `prompts.nautix.yaml` for structure but replace all domain content.

- [ ] **Step 2: Validate prompts load**

Run: `python -c "from scripts.clawrank.core.prompts_loader import PromptManager; pm = PromptManager('scripts/clawrank/prompts.scotty.yaml'); print(pm.stage_names())"`

Expected: List of stage names

- [ ] **Step 3: Commit**

```bash
git add scripts/clawrank/prompts.scotty.yaml
git commit -m "feat: add prompts.scotty.yaml — Scotty's voice + domain prompts"
```

---

## Task 16: Create run.py (CLI Entry Point)

**Files:**
- Create: `scripts/clawrank/run.py`
- Test: `tests/clawrank/test_run.py`

- [ ] **Step 1: Write failing test for CLI parsing**

```python
# tests/clawrank/test_run.py
import pytest


def test_parse_args_mode_auto():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto"])
    assert args.mode == "auto"


def test_parse_args_mode_research_with_keyword():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "research", "--keyword", "hot composting houston"])
    assert args.mode == "research"
    assert args.keyword == "hot composting houston"


def test_parse_args_backend_default():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto"])
    assert args.backend == "gemini"


def test_parse_args_from_to_stage():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "batch", "--from-stage", "12", "--to-stage", "23"])
    assert args.from_stage == 12
    assert args.to_stage == 23


def test_parse_args_dry_run():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto", "--dry-run"])
    assert args.dry_run is True


def test_parse_args_verbose():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto", "--verbose"])
    assert args.verbose is True


def test_parse_args_dry_run_default_false():
    from scripts.clawrank.run import parse_args
    args = parse_args(["--mode", "auto"])
    assert args.dry_run is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/clawrank/test_run.py -v`

Expected: FAIL

- [ ] **Step 3: Implement run.py**

Create `scripts/clawrank/run.py` modeled on nautix `run.py` (720 lines) but adapted:
- Path constants point to scottysgreenlab directories
- `parse_args()` function (extracted for testing) with all CLI flags including `--keyword` (new), `--dry-run`, `--verbose`
- `main()` dispatches to: `cmd_stages`, `cmd_validate`, `cmd_world_state`, `cmd_decide`, `cmd_auto`, `cmd_batch`, `cmd_research`
- `cmd_research` supports `--keyword` flag for single-topic research
- Uses `ScottyAdapter` as domain adapter
- Initializes `AcpxLLMAdapter` with config's default_backend and heavy_backend

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/clawrank/test_run.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/clawrank/run.py tests/clawrank/test_run.py
git commit -m "feat: add run.py — CLI entry point with auto/batch/research/keyword modes"
```

---

## Task 17: Create decide.py (Decision Engine)

**Files:**
- Create: `scripts/clawrank/decide.py`

- [ ] **Step 1: Implement decide.py**

Create a simplified decision engine that:
- Takes world state dict as input
- Checks for unprocessed briefs in `artifacts/clawrank/briefs/`
- If briefs exist: recommend WRITE (stages 9-23) with highest-priority brief
- If no briefs: recommend RESEARCH (stages 1-8) targeting the pillar with lowest article count
- Returns: `{"action": "write"|"research", "target": str, "reason": str}`

Keep it simple — nautix's `decide.py` is 2400 lines but most of that is nautix business logic. Start with ~100 lines.

- [ ] **Step 2: Write tests for decide.py**

```python
# tests/clawrank/test_decide.py
import pytest
import tempfile
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
    # Should target lowest-coverage pillar
    assert "soil" in result["target"].lower() or "science" in result["target"].lower()
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/clawrank/test_decide.py -v`

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/clawrank/decide.py tests/clawrank/test_decide.py
git commit -m "feat: add decide.py — simple decision engine for content planning"
```

---

## Task 18: Create daily-run.sh

**Files:**
- Create: `scripts/clawrank/daily-run.sh`

- [ ] **Step 1: Write cron wrapper**

```bash
#!/usr/bin/env bash
# ClawRank daily runner for scottysgreenlab
# Cron entries:
#   0 6 * * * /path/to/daily-run.sh research
#   0 2 * * 1 /path/to/daily-run.sh auto

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$PROJECT_ROOT/artifacts/clawrank/logs"
mkdir -p "$LOG_DIR"

MODE="${1:-auto}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/run-${MODE}-${TIMESTAMP}.log"

cd "$PROJECT_ROOT"

python3 scripts/clawrank/run.py \
    --mode "$MODE" \
    --auto-approve \
    --backend gemini \
    2>&1 | tee "$LOG_FILE"

# Prune logs older than 30 days
find "$LOG_DIR" -name "run-*.log" -mtime +30 -delete 2>/dev/null || true
```

- [ ] **Step 2: Make executable**

Run: `chmod +x scripts/clawrank/daily-run.sh`

- [ ] **Step 3: Commit**

```bash
git add scripts/clawrank/daily-run.sh
git commit -m "feat: add daily-run.sh — cron wrapper for scheduled ClawRank runs"
```

---

## Task 19: Integration Smoke Test

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/ariapramesi/repos/scottysgreenlab && python -m pytest tests/clawrank/ -v`

Expected: All tests pass

- [ ] **Step 2: Validate config + prompts load together**

Run: `python -c "
from scripts.clawrank.core.config_loader import CRConfig
from scripts.clawrank.core.prompts_loader import PromptManager
from scripts.clawrank.scotty.adapter import ScottyAdapter
cfg = CRConfig.load('scripts/clawrank/config.scotty.yaml', check_paths=False)
pm = PromptManager('scripts/clawrank/prompts.scotty.yaml')
adapter = ScottyAdapter()
print(f'Config: {cfg.project.name}')
print(f'Stages: {len(pm.stage_names())}')
print(f'Products: {len(adapter.product_data())}')
print(f'Voice: {len(adapter.load_voice_rules())} chars')
"`

Expected: Config loads, prompts load, adapter returns 4 products and voice block.

- [ ] **Step 3: Validate CLI help**

Run: `python scripts/clawrank/run.py --help`

Expected: Help output showing all modes and flags

- [ ] **Step 4: Dry run**

Run: `python scripts/clawrank/run.py --mode auto --dry-run --verbose`

Expected: Prints what it would do without executing LLM calls

- [ ] **Step 5: Commit any fixes**

```bash
git add -A scripts/clawrank/ tests/clawrank/
git commit -m "fix: integration smoke test fixes"
```

---

## Task 20: Final Commit and Summary

- [ ] **Step 1: Run full test suite one more time**

Run: `python -m pytest tests/clawrank/ -v --tb=short`

Expected: All pass

- [ ] **Step 2: Verify file count**

Run: `find scripts/clawrank -name "*.py" -o -name "*.yaml" -o -name "*.sh" | wc -l`

Expected: ~18 files (9 core, 6 scotty, run.py, decide.py, daily-run.sh, 2 yaml configs)

- [ ] **Step 3: Summary commit**

```bash
git add -A
git commit -m "feat: complete ClawRank customization for scottysgreenlab

23-stage content pipeline with:
- Core engine (models, pipeline, config, prompts, evolution, LLM adapter)
- Scotty domain layer (voice, sources, world_state, adapter, compliance, publish)
- GPU model integration (intent classifier, query fanout, sentiment, reranker)
- Brain DB integration (pgvector search, cannibalization, gaps)
- CLI with auto/batch/research/keyword modes
- Cron wrapper for daily scans + weekly deep runs
- 9 test files covering all domain layer modules"
```
