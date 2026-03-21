"""Self-learning / evolution system for ClawRank.

Tracks lessons learned across pipeline runs -- what worked, what failed,
what to avoid. Lessons are injected into prompts so future runs benefit
from past experience.
"""

from __future__ import annotations

import json
import math
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LessonCategory:
    """Lesson categories for ClawRank pipeline."""
    SYSTEM = "system"              # Infrastructure/config issues
    KEYWORDS = "keywords"          # Keyword research issues
    RESEARCH = "research"          # Data collection/evidence issues
    CONTENT = "content"            # Content generation issues
    SEO = "seo"                    # SEO/GEO optimization issues
    QUALITY = "quality"            # Quality gate failures
    PUBLISHING = "publishing"      # Framework adapter/deploy issues
    PIPELINE = "pipeline"          # Pipeline flow issues


@dataclass
class LessonEntry:
    stage: str
    category: str
    severity: str                  # error, warning, info
    description: str
    timestamp: str = ""
    run_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class EvolutionStore:
    """JSONL-backed persistent lesson store with time-decay weighting."""

    HALF_LIFE_DAYS = 30.0
    MAX_AGE_DAYS = 90.0

    def __init__(self, store_dir: Path) -> None:
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.store_dir / "lessons.jsonl"

    def append(self, lesson: LessonEntry) -> None:
        with self._file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(lesson)) + "\n")

    def append_many(self, lessons: list[LessonEntry]) -> None:
        if not lessons:
            return
        with self._file.open("a", encoding="utf-8") as f:
            for lesson in lessons:
                f.write(json.dumps(asdict(lesson)) + "\n")
        logger.info("Appended %d lessons to evolution store", len(lessons))

    def _load_all(self) -> list[LessonEntry]:
        if not self._file.exists():
            return []
        entries = []
        for line in self._file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entries.append(LessonEntry(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return entries

    def _weight(self, entry: LessonEntry, stage_name: str = "") -> float:
        """Time-decay weight with stage boost."""
        try:
            ts = datetime.fromisoformat(entry.timestamp)
            age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
        except (ValueError, TypeError):
            age_days = self.MAX_AGE_DAYS

        if age_days > self.MAX_AGE_DAYS:
            return 0.0

        weight = math.exp(-age_days * math.log(2) / self.HALF_LIFE_DAYS)

        # Stage match boost
        if stage_name and entry.stage == stage_name:
            weight *= 2.0

        # Severity boost
        if entry.severity == "error":
            weight *= 1.5

        return weight

    def build_overlay(
        self,
        stage_name: str = "",
        max_lessons: int = 5,
    ) -> str:
        """Build a markdown overlay of top lessons for prompt injection."""
        entries = self._load_all()
        if not entries:
            return ""

        scored = [
            (self._weight(e, stage_name), e) for e in entries
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [(w, e) for w, e in scored[:max_lessons] if w > 0.01]

        if not top:
            return ""

        lines = ["## Lessons from Previous Runs\n"]
        for weight, entry in top:
            lines.append(
                f"- **[{entry.severity.upper()}]** ({entry.category}/{entry.stage}): "
                f"{entry.description}"
            )
        return "\n".join(lines)


def extract_lessons(
    results: dict[str, Any],
    *,
    run_id: str = "",
    run_dir: Path | None = None,
) -> list[LessonEntry]:
    """Extract lessons from pipeline stage results."""
    lessons: list[LessonEntry] = []

    for stage_name, result in results.items():
        if not isinstance(result, dict):
            continue

        status = result.get("status", "done")
        errors = result.get("errors", [])
        scores = result.get("scores", {})

        # Failed stages
        if status == "failed":
            category = _categorize_stage(stage_name)
            for error in errors:
                lessons.append(LessonEntry(
                    stage=stage_name,
                    category=category,
                    severity="error",
                    description=f"Stage failed: {error}",
                    run_id=run_id,
                ))

        # Quality gate rejections
        if stage_name == "quality_gate" and result.get("verdict") == "rewrite":
            issues = result.get("issues", [])
            for issue in issues:
                if isinstance(issue, dict) and issue.get("severity") == "critical":
                    lessons.append(LessonEntry(
                        stage=stage_name,
                        category=LessonCategory.QUALITY,
                        severity="error",
                        description=issue.get("description", "Quality gate critical issue"),
                        run_id=run_id,
                    ))

        # Low scores
        for metric, value in scores.items():
            if isinstance(value, (int, float)):
                if metric == "ai_slop" and value > 0.5:
                    lessons.append(LessonEntry(
                        stage=stage_name,
                        category=LessonCategory.CONTENT,
                        severity="warning",
                        description=f"High AI-slop score ({value:.2f}) -- content sounds too generic",
                        run_id=run_id,
                    ))
                elif metric in ("eeat", "originality", "geo") and value < 0.5:
                    lessons.append(LessonEntry(
                        stage=stage_name,
                        category=LessonCategory.QUALITY,
                        severity="warning",
                        description=f"Low {metric} score ({value:.2f}) -- needs improvement",
                        run_id=run_id,
                    ))

    return lessons


def _categorize_stage(stage_name: str) -> str:
    """Map stage names to lesson categories."""
    keyword_stages = {"keyword_strategy", "keyword_collect", "keyword_screen", "entity_extract"}
    research_stages = {"research_brief", "data_collect", "evidence_build"}
    content_stages = {"content_draft", "content_refine", "editorial_review", "content_revision"}
    seo_stages = {"seo_optimize", "geo_optimize"}
    quality_stages = {"quality_gate", "link_verify"}
    publish_stages = {"framework_adapt", "sitemap_gen", "publish"}

    if stage_name in keyword_stages:
        return LessonCategory.KEYWORDS
    if stage_name in research_stages:
        return LessonCategory.RESEARCH
    if stage_name in content_stages:
        return LessonCategory.CONTENT
    if stage_name in seo_stages:
        return LessonCategory.SEO
    if stage_name in quality_stages:
        return LessonCategory.QUALITY
    if stage_name in publish_stages:
        return LessonCategory.PUBLISHING
    return LessonCategory.PIPELINE
