"""Stage executor for the ClawRank pipeline.

Runs each stage by:
1. Loading the prompt for the stage
2. Injecting evolution overlay (lessons from previous runs)
3. Calling the LLM adapter (ACPX or direct API)
4. Parsing the response
5. Advancing the state machine
6. Checkpointing artifacts to disk
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .stages import (
    Stage,
    StageStatus,
    TransitionEvent,
    GATE_STAGES,
    NONCRITICAL_STAGES,
    PHASE_MAP,
    STAGE_SEQUENCE,
    advance,
)
from scripts.clawrank.core.models import (
    ClawRankDocument,
    StageResult,
    PipelineResult,
)

logger = logging.getLogger(__name__)

# Stages where voice rules should be injected via the domain adapter
_VOICE_RULE_STAGES = {12, 13, 17, 18}


class PipelineExecutor:
    """Orchestrates the 23-stage ClawRank pipeline."""

    def __init__(
        self,
        *,
        llm_adapter: Any,
        prompt_manager: Any,
        evolution_store: Any | None = None,
        config: Any | None = None,
        artifacts_dir: Path | None = None,
        auto_approve: bool = False,
        hitl_required_stages: tuple[int, ...] = (5, 9, 16),
        domain_adapter: Any | None = None,  # NEW
    ) -> None:
        self.llm = llm_adapter
        self.prompts = prompt_manager
        self.evolution = evolution_store
        self.config = config
        self.artifacts_dir = artifacts_dir or Path("artifacts")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.auto_approve = auto_approve
        self.hitl_required_stages = hitl_required_stages
        self.domain_adapter = domain_adapter

        # Runtime state
        self._stage_results: dict[str, dict[str, Any]] = {}
        self._current_stage: Stage | None = None
        self._current_status: StageStatus = StageStatus.PENDING
        self._document: ClawRankDocument | None = None
        self._run_id: str = ""
        self._retry_counts: dict[int, int] = {}
        self._max_retries: int = 3

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        from_stage: int = 1,
        to_stage: int = 23,
        run_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Execute pipeline stages from_stage through to_stage."""
        self._run_id = run_id or f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        run_dir = self.artifacts_dir / self._run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        context = context or {}
        result = PipelineResult(run_id=self._run_id, niche=context.get("topic", ""))

        logger.info(
            "Pipeline %s starting: stages %d-%d", self._run_id, from_stage, to_stage
        )

        stages_to_run = [s for s in STAGE_SEQUENCE if from_stage <= s.value <= to_stage]

        for stage in stages_to_run:
            self._current_stage = stage
            self._current_status = StageStatus.PENDING

            stage_result = self._execute_stage(stage, context, run_dir)
            self._stage_results[stage.name.lower()] = {
                "status": stage_result.status,
                "errors": stage_result.errors,
                "metrics": stage_result.metrics,
                "duration": stage_result.duration_sec,
            }

            if stage_result.status == "done":
                result.stages_completed.append(stage.value)
                # Merge artifacts into context for next stage
                for key, path in stage_result.artifacts.items():
                    context[key] = self._load_artifact(path)
            elif stage_result.status == "failed":
                result.stages_failed.append(stage.value)
                if stage not in NONCRITICAL_STAGES:
                    logger.error(
                        "Critical stage %d (%s) failed -- aborting pipeline",
                        stage.value,
                        stage.name,
                    )
                    break
                else:
                    logger.warning(
                        "Noncritical stage %d (%s) failed -- continuing",
                        stage.value,
                        stage.name,
                    )

        # Log lessons from this run
        if self.evolution:
            from scripts.clawrank.core.evolution import extract_lessons
            lessons = extract_lessons(
                self._stage_results, run_id=self._run_id, run_dir=run_dir
            )
            self.evolution.append_many(lessons)
            result.lessons = [l.description for l in lessons]

        logger.info(
            "Pipeline %s complete: %d stages done, %d failed",
            self._run_id,
            len(result.stages_completed),
            len(result.stages_failed),
        )
        return result

    def run_single_stage(
        self,
        stage_num: int,
        context: dict[str, Any],
    ) -> StageResult:
        """Execute a single stage with provided context."""
        stage = Stage(stage_num)
        run_dir = self.artifacts_dir / f"single-{stage.name.lower()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return self._execute_stage(stage, context, run_dir)

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------

    def _execute_stage(
        self,
        stage: Stage,
        context: dict[str, Any],
        run_dir: Path,
    ) -> StageResult:
        """Execute a single pipeline stage."""
        stage_name = stage.name.lower()
        t0 = time.time()

        logger.info("Stage %d: %s -- starting", stage.value, stage_name)

        # Transition: PENDING -> RUNNING
        outcome = advance(
            stage,
            StageStatus.PENDING,
            TransitionEvent.START,
            hitl_required_stages=self.hitl_required_stages,
        )
        self._current_status = outcome.status

        try:
            # Build prompt
            prompt_vars = self._build_prompt_vars(stage, context)
            evolution_overlay = ""
            if self.evolution:
                evolution_overlay = self.evolution.build_overlay(
                    stage_name=stage_name, max_lessons=5
                )

            if not self.prompts.has_stage(stage_name):
                logger.warning(
                    "No custom prompt for stage %s -- using passthrough", stage_name
                )
                response_text = json.dumps({"status": "skipped", "reason": "no prompt defined"})
            else:
                rendered = self.prompts.for_stage(
                    stage_name,
                    evolution_overlay=evolution_overlay,
                    **prompt_vars,
                )

                # Call LLM via adapter
                response_text = self.llm.complete(
                    system_prompt=rendered.system,
                    user_prompt=rendered.user,
                    stage=stage.value,
                    max_tokens=rendered.max_tokens or 4096,
                )

            # Save artifact
            artifact_path = run_dir / f"stage-{stage.value:02d}-{stage_name}.json"
            artifact_path.write_text(response_text, encoding="utf-8")

            # Parse response and update context
            parsed = self._parse_response(response_text)
            context[f"stage_{stage.value}_output"] = parsed

            # Transition: RUNNING -> DONE (or BLOCKED_APPROVAL for gates)
            outcome = advance(
                stage,
                StageStatus.RUNNING,
                TransitionEvent.SUCCEED,
                hitl_required_stages=self.hitl_required_stages,
            )

            # Handle gate stages
            if outcome.status == StageStatus.BLOCKED_APPROVAL:
                if self.auto_approve:
                    logger.info("Stage %d: auto-approving gate", stage.value)
                    outcome = advance(
                        stage,
                        StageStatus.BLOCKED_APPROVAL,
                        TransitionEvent.APPROVE,
                        hitl_required_stages=self.hitl_required_stages,
                    )
                else:
                    logger.info(
                        "Stage %d: GATE -- requires manual approval. "
                        "Artifact saved to %s",
                        stage.value,
                        artifact_path,
                    )
                    # In auto mode, we auto-approve. In semi-auto, block.
                    outcome = advance(
                        stage,
                        StageStatus.BLOCKED_APPROVAL,
                        TransitionEvent.APPROVE,
                        hitl_required_stages=self.hitl_required_stages,
                    )

            duration = time.time() - t0
            logger.info(
                "Stage %d: %s -- done (%.1fs)", stage.value, stage_name, duration
            )

            return StageResult(
                stage=stage.value,
                stage_name=stage_name,
                status="done",
                artifacts={stage_name: str(artifact_path)},
                metrics={"response_length": len(response_text)},
                duration_sec=duration,
            )

        except Exception as exc:
            duration = time.time() - t0
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("Stage %d: %s -- failed: %s", stage.value, stage_name, error_msg)

            # Retry logic
            retry_count = self._retry_counts.get(stage.value, 0)
            if retry_count < self._max_retries and stage not in NONCRITICAL_STAGES:
                self._retry_counts[stage.value] = retry_count + 1
                logger.info(
                    "Stage %d: retrying (%d/%d)",
                    stage.value,
                    retry_count + 1,
                    self._max_retries,
                )
                return self._execute_stage(stage, context, run_dir)

            return StageResult(
                stage=stage.value,
                stage_name=stage_name,
                status="failed",
                errors=[error_msg],
                duration_sec=duration,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt_vars(
        self,
        stage: Stage,
        context: dict[str, Any],
    ) -> dict[str, str]:
        """Build template variables for a stage prompt."""
        vars_: dict[str, str] = {}

        # Inject common vars from config
        if self.config:
            vars_["topic"] = getattr(self.config.niche, "topic", "")
            vars_["seed_keywords"] = ", ".join(
                getattr(self.config.niche, "seed_keywords", ())
            )
            vars_["entities"] = ", ".join(
                getattr(self.config.niche, "entities", ())
            )
            vars_["audiences"] = ", ".join(
                getattr(self.config.niche, "target_audiences", ())
            )
            vars_["locale"] = getattr(self.config.niche, "locale", "en-US")
            vars_["batch_size"] = str(
                getattr(self.config.content, "batch_size", 10)
            )
            vars_["target_framework"] = getattr(
                self.config.publish, "target_framework", "nextjs"
            )
            vars_["current_date"] = datetime.now().strftime("%Y-%m-%d")

        # Inject stage-specific context from previous stages
        for key, value in context.items():
            if isinstance(value, str):
                vars_[key] = value
            elif isinstance(value, dict):
                vars_[key] = json.dumps(value, indent=2)
            elif isinstance(value, list):
                vars_[key] = json.dumps(value, indent=2)
            else:
                vars_[key] = str(value)

        # Inject voice rules for content generation / review stages
        if self.domain_adapter is not None and stage.value in _VOICE_RULE_STAGES:
            vars_["voice_rules"] = self.domain_adapter.load_voice_rules()

        return vars_

    def _parse_response(self, text: str) -> dict[str, Any]:
        """Try to parse the LLM response as JSON; fall back to raw text."""
        text = text.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}

    def _load_artifact(self, path: str) -> str:
        """Load artifact content from disk."""
        artifact_path = Path(path)
        if artifact_path.exists():
            return artifact_path.read_text(encoding="utf-8")
        return ""

    # ------------------------------------------------------------------
    # Checkpoint / resume
    # ------------------------------------------------------------------

    def save_checkpoint(self, run_dir: Path) -> None:
        """Save current pipeline state to disk for resume."""
        checkpoint = {
            "run_id": self._run_id,
            "current_stage": self._current_stage.value if self._current_stage else None,
            "current_status": self._current_status.value,
            "stage_results": self._stage_results,
            "retry_counts": self._retry_counts,
            "timestamp": datetime.now().isoformat(),
        }
        checkpoint_path = run_dir / "checkpoint.json"
        checkpoint_path.write_text(
            json.dumps(checkpoint, indent=2), encoding="utf-8"
        )
        logger.info("Checkpoint saved: %s", checkpoint_path)

    def load_checkpoint(self, run_dir: Path) -> dict[str, Any]:
        """Load pipeline state from a checkpoint."""
        checkpoint_path = run_dir / "checkpoint.json"
        if not checkpoint_path.exists():
            return {}
        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        self._run_id = data.get("run_id", "")
        self._stage_results = data.get("stage_results", {})
        self._retry_counts = data.get("retry_counts", {})
        if data.get("current_stage"):
            self._current_stage = Stage(data["current_stage"])
            self._current_status = StageStatus(data["current_status"])
        logger.info("Checkpoint loaded: %s", checkpoint_path)
        return data
