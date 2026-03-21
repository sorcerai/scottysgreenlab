#!/usr/bin/env python3
"""ClawRank for Scotty's Green Lab -- Autonomous content engine.

Usage:
  python3 scripts/clawrank/run.py --mode auto        # Daily: world state -> decide -> write 1 article
  python3 scripts/clawrank/run.py --mode batch        # Batch: write from existing briefs
  python3 scripts/clawrank/run.py --mode research     # Research only: stages 1-8, output briefs
  python3 scripts/clawrank/run.py --world-state       # Just build world state snapshot
  python3 scripts/clawrank/run.py --decide            # Just run decision engine
  python3 scripts/clawrank/run.py --stages            # List all pipeline stages
  python3 scripts/clawrank/run.py --validate          # Validate config file

Environment:
  Requires ACPX CLI: npm install -g acpx
  Config: scripts/clawrank/config.scotty.yaml
  Prompts: scripts/clawrank/prompts.scotty.yaml
  Output: data/content-pipeline/ (JSON drafts)
  Lessons: artifacts/clawrank/kb/lessons/ (evolution store)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Resolve project root (scottysgreenlab/) and ensure it's on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CONFIG_PATH = SCRIPTS_DIR / "config.scotty.yaml"
PROMPTS_PATH = SCRIPTS_DIR / "prompts.scotty.yaml"
OUTPUT_DIR = PROJECT_ROOT / "data" / "content-pipeline"
LESSONS_DIR = PROJECT_ROOT / "artifacts" / "clawrank" / "kb" / "lessons"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "clawrank"
BRIEFS_DIR = PROJECT_ROOT / "data" / "content-pipeline" / "briefs"

logger = logging.getLogger("clawrank")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments. Extracted for testability."""
    parser = argparse.ArgumentParser(
        prog="clawrank",
        description="ClawRank for Scotty's Green Lab -- Autonomous SEO/GEO content engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")

    # Mode flags (mutually exclusive group for the 'big' modes)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mode",
        choices=["auto", "batch", "research"],
        default=None,
        help="Pipeline mode: auto (daily), batch (from briefs), research (stages 1-8)",
    )
    mode_group.add_argument(
        "--world-state",
        action="store_true",
        help="Build world state snapshot only",
    )
    mode_group.add_argument(
        "--decide",
        action="store_true",
        help="Run decision engine only",
    )
    mode_group.add_argument(
        "--stages",
        action="store_true",
        help="List all pipeline stages",
    )
    mode_group.add_argument(
        "--validate",
        action="store_true",
        help="Validate config file",
    )

    # Research keyword (only meaningful with --mode research)
    parser.add_argument(
        "--keyword",
        type=str,
        default=None,
        help="Seed keyword for research mode (e.g. 'hot composting houston')",
    )

    # Pipeline options
    parser.add_argument(
        "--config", "-c",
        default=str(CONFIG_PATH),
        help="Config YAML path",
    )
    parser.add_argument(
        "--from-stage",
        type=int,
        default=None,
        help="Start from a specific stage number (1-23)",
    )
    parser.add_argument(
        "--to-stage",
        type=int,
        default=None,
        help="Stop at a specific stage number (1-23)",
    )
    parser.add_argument(
        "--brief",
        type=str,
        default=None,
        help="Path to a specific brief JSON file (for batch/single mode)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve gate stages (skip HITL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only, don't execute LLM calls",
    )
    parser.add_argument(
        "--backend",
        choices=["claude", "codex", "gemini"],
        default="gemini",
        help="LLM backend (default: gemini via direct CLI)",
    )
    parser.add_argument(
        "--output", "-o",
        default=str(OUTPUT_DIR),
        help="Output directory for generated content",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Dispatch
    if args.stages:
        return cmd_stages()
    if args.validate:
        return cmd_validate(args.config)
    if args.world_state:
        return cmd_world_state(args)
    if args.decide:
        return cmd_decide(args)
    if args.mode == "auto":
        return cmd_auto(args)
    if args.mode == "batch":
        return cmd_batch(args)
    if args.mode == "research":
        return cmd_research(args)

    # Default: show help
    import argparse as _ap
    _ap.ArgumentParser(
        prog="clawrank",
        description="ClawRank for Scotty's Green Lab -- Autonomous SEO/GEO content engine",
    ).print_help()
    return 0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_stages() -> int:
    """Print all pipeline stages."""
    from scripts.clawrank.core.pipeline.stages import PHASE_MAP, STAGE_SEQUENCE, GATE_STAGES

    print("\nClawRank Pipeline -- 23 Stages\n")
    for phase_name, stages in PHASE_MAP.items():
        print(f"  {phase_name}")
        for stage in stages:
            gate = " [GATE]" if stage in GATE_STAGES else ""
            print(f"    {stage.value:2d}. {stage.name}{gate}")
    print(f"\n  Total: {len(STAGE_SEQUENCE)} stages\n")
    return 0


def cmd_validate(config_path: str) -> int:
    """Validate a ClawRank config file."""
    import yaml

    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        print(f"Config file not found: {path}")
        return 1

    with path.open() as f:
        data = yaml.safe_load(f) or {}

    from scripts.clawrank.config_loader import validate_config
    result = validate_config(data, project_root=path.parent, check_paths=True)

    if result.ok:
        print(f"Config is valid: {path}")
        for w in result.warnings:
            print(f"  WARNING: {w}")
        return 0
    else:
        print(f"Config has errors: {path}")
        for e in result.errors:
            print(f"  ERROR: {e}")
        for w in result.warnings:
            print(f"  WARNING: {w}")
        return 1


def cmd_world_state(args: argparse.Namespace) -> int:
    """Build a world state snapshot of the Scotty's Green Lab content ecosystem."""
    print("\n--- World State Snapshot ---\n")
    t0 = time.time()

    snapshot: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "project_root": str(PROJECT_ROOT),
    }

    # Count existing articles (JSON in data/content-pipeline/)
    article_dir = OUTPUT_DIR
    if article_dir.exists():
        json_files = list(article_dir.glob("*.json"))
        snapshot["articles_total"] = len(json_files)
        print(f"  Published articles: {len(json_files)}")
    else:
        snapshot["articles_total"] = 0
        print("  Published articles: 0 (directory not found)")

    # Count existing briefs
    if BRIEFS_DIR.exists():
        brief_files = list(BRIEFS_DIR.glob("*.json"))
        snapshot["briefs_total"] = len(brief_files)
        print(f"  Content briefs: {len(brief_files)}")
    else:
        snapshot["briefs_total"] = 0
        print("  Content briefs: 0")

    # Check evolution store
    if LESSONS_DIR.exists():
        lessons_file = LESSONS_DIR / "lessons.jsonl"
        if lessons_file.exists():
            lesson_count = sum(1 for line in lessons_file.read_text().splitlines() if line.strip())
            snapshot["lessons_count"] = lesson_count
            print(f"  Evolution lessons: {lesson_count}")
        else:
            snapshot["lessons_count"] = 0
            print("  Evolution lessons: 0")
    else:
        snapshot["lessons_count"] = 0
        print("  Evolution lessons: 0 (directory not found)")

    # Pillar coverage from pseo-questions-final.json
    questions_path = PROJECT_ROOT / "src" / "data" / "pseo-questions-final.json"
    if questions_path.exists():
        questions = json.loads(questions_path.read_text())
        pillar_counts: dict[str, int] = {}
        for q in questions:
            p = q.get("pillar", "unknown")
            pillar_counts[p] = pillar_counts.get(p, 0) + 1
        snapshot["articles_by_pillar"] = pillar_counts
        snapshot["total_articles"] = len(questions)
        print(f"  Questions indexed: {len(questions)} across {len(pillar_counts)} pillars")
    else:
        snapshot["articles_by_pillar"] = {}
        snapshot["total_articles"] = 0

    # Save snapshot
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = ARTIFACTS_DIR / f"world-state-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"\n  Snapshot saved: {snapshot_path}")
    print(f"  Elapsed: {elapsed:.1f}s\n")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    """Run the decision engine to select the next content action."""
    print("\n--- Decision Engine ---\n")

    # Load world state (most recent)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshots = sorted(ARTIFACTS_DIR.glob("world-state-*.json"), reverse=True)
    if not snapshots:
        print("  No world state found. Run --world-state first.")
        return 1

    snapshot = json.loads(snapshots[0].read_text())
    print(f"  Using snapshot: {snapshots[0].name}")
    print(f"  Total articles: {snapshot.get('total_articles', 0)}")
    print(f"  Briefs available: {snapshot.get('briefs_total', 0)}")

    from scripts.clawrank.decide import decide
    result = decide(
        world_state=snapshot,
        briefs_dir=BRIEFS_DIR,
    )

    print(f"\n  Recommended action: {result['action'].upper()}")
    print(f"  Target: {result['target']}")
    print(f"  Reason: {result['reason']}")

    # Save decision
    decision = {**result, "timestamp": datetime.now().isoformat()}
    decision_path = ARTIFACTS_DIR / f"decision-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    decision_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")
    print(f"  Decision saved: {decision_path}\n")
    return 0


def cmd_auto(args: argparse.Namespace) -> int:
    """Auto mode: world state -> decide -> execute."""
    print("\n=== ClawRank Auto Mode ===\n")
    t0 = time.time()

    # Step 1: Check LLM backends
    from scripts.clawrank.core.acpx_adapter import check_backends_installed, AcpxLLMAdapter

    backends = check_backends_installed()
    if not backends.get("acpx") and not backends.get("claude_cli"):
        print("ERROR: No LLM backend found.")
        print("Install ACPX (npm install -g acpx) or Claude CLI")
        return 1

    # Step 2: Load config
    config = _load_config(args.config)
    if config is None:
        return 1

    # Step 3: Build world state
    print("Step 1/5: Building world state...")
    cmd_world_state(args)

    # Step 4: Run decision engine
    print("Step 2/5: Running decision engine...")
    cmd_decide(args)

    # Step 5: Load most recent decision
    decisions = sorted(ARTIFACTS_DIR.glob("decision-*.json"), reverse=True)
    if not decisions:
        print("ERROR: No decision found after running decision engine.")
        return 1

    decision = json.loads(decisions[0].read_text())
    action = decision.get("action", "")
    print(f"\nStep 3/5: Executing action: {action}")

    if args.dry_run:
        print("\n  [DRY RUN] Would execute the pipeline. Stopping here.")
        return 0

    # Step 6: Initialize pipeline
    llm = AcpxLLMAdapter(
        backend=args.backend,
        session_prefix="clawrank-scotty",
    )
    from scripts.clawrank.core.prompts_loader import PromptManager
    from scripts.clawrank.core.evolution import EvolutionStore
    from scripts.clawrank.core.pipeline.executor import PipelineExecutor

    prompts = PromptManager()
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    evolution = EvolutionStore(LESSONS_DIR)

    executor = PipelineExecutor(
        llm_adapter=llm,
        prompt_manager=prompts,
        evolution_store=evolution,
        config=config,
        artifacts_dir=ARTIFACTS_DIR,
        auto_approve=args.auto_approve,
        hitl_required_stages=config.security.hitl_required_stages,
    )

    # Step 7: Execute based on decision
    context: dict[str, Any] = {
        "topic": config.niche.topic,
        "current_date": datetime.now().strftime("%Y-%m-%d"),
    }

    if action == "write":
        brief_path = decision.get("target", "")
        if brief_path:
            brief = json.loads(Path(brief_path).read_text())
            context.update(_brief_to_context(brief))
            from_stage = args.from_stage or 9
            to_stage = args.to_stage or 23
        else:
            from_stage = args.from_stage or 1
            to_stage = args.to_stage or 23

        print(f"\nStep 4/5: Running pipeline stages {from_stage}-{to_stage}...")
        result = executor.run(
            from_stage=from_stage,
            to_stage=to_stage,
            context=context,
        )

    elif action == "research":
        from_stage = args.from_stage or 1
        to_stage = args.to_stage or 8
        if args.keyword:
            context["seed_keyword"] = args.keyword
        print(f"\nStep 4/5: Running research stages {from_stage}-{to_stage}...")
        result = executor.run(
            from_stage=from_stage,
            to_stage=to_stage,
            context=context,
        )

    else:
        print(f"  Unknown action: {action}")
        return 1

    # Step 8: Summary
    elapsed = time.time() - t0
    print(f"\nStep 5/5: Summary")
    print(f"  Run ID: {result.run_id}")
    print(f"  Stages completed: {result.stages_completed}")
    print(f"  Stages failed: {result.stages_failed}")
    if result.lessons:
        print(f"  Lessons learned: {len(result.lessons)}")
        for lesson in result.lessons[:3]:
            print(f"    - {lesson}")
    print(f"  Total elapsed: {elapsed:.1f}s")

    _log_run_summary(result, elapsed)
    print("\n=== ClawRank Auto Mode Complete ===\n")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Batch mode: write from existing briefs."""
    print("\n=== ClawRank Batch Mode ===\n")

    from scripts.clawrank.core.acpx_adapter import check_backends_installed, AcpxLLMAdapter

    backends = check_backends_installed()
    if not backends.get("acpx") and not backends.get("claude_cli"):
        print("ERROR: No LLM backend found. Install ACPX or Claude CLI.")
        return 1

    config = _load_config(args.config)
    if config is None:
        return 1

    # Find briefs to process
    if args.brief:
        brief_files = [Path(args.brief)]
    elif BRIEFS_DIR.exists():
        brief_files = sorted(BRIEFS_DIR.glob("brief-*.json"), reverse=True)
        unprocessed = []
        for bf in brief_files:
            try:
                brief = json.loads(bf.read_text())
                if brief.get("status") != "published":
                    unprocessed.append(bf)
            except (json.JSONDecodeError, KeyError):
                unprocessed.append(bf)
        brief_files = unprocessed
    else:
        print("No briefs found. Run --mode research first.")
        return 1

    if not brief_files:
        print("No unprocessed briefs found.")
        return 0

    print(f"  Found {len(brief_files)} briefs to process\n")

    if args.dry_run:
        for bf in brief_files:
            print(f"  [DRY RUN] Would process: {bf.name}")
        return 0

    # Initialize pipeline
    llm = AcpxLLMAdapter(backend=args.backend, session_prefix="clawrank-scotty")
    from scripts.clawrank.core.prompts_loader import PromptManager
    from scripts.clawrank.core.evolution import EvolutionStore
    from scripts.clawrank.core.pipeline.executor import PipelineExecutor

    prompts = PromptManager()
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    evolution = EvolutionStore(LESSONS_DIR)

    executor = PipelineExecutor(
        llm_adapter=llm,
        prompt_manager=prompts,
        evolution_store=evolution,
        config=config,
        artifacts_dir=ARTIFACTS_DIR,
        auto_approve=args.auto_approve,
        hitl_required_stages=config.security.hitl_required_stages,
    )

    results = []
    for bf in brief_files:
        print(f"  Processing: {bf.name}")
        brief = json.loads(bf.read_text())
        context = _brief_to_context(brief)
        context["topic"] = config.niche.topic
        context["current_date"] = datetime.now().strftime("%Y-%m-%d")

        from_stage = args.from_stage or 9
        to_stage = args.to_stage or 23

        result = executor.run(
            from_stage=from_stage,
            to_stage=to_stage,
            context=context,
        )
        results.append(result)
        print(f"    Stages completed: {result.stages_completed}")
        if result.stages_failed:
            print(f"    Stages failed: {result.stages_failed}")

    print(f"\n  Batch complete: {len(results)} briefs processed")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    """Research mode: stages 1-8 only, output briefs."""
    print("\n=== ClawRank Research Mode ===\n")

    from scripts.clawrank.core.acpx_adapter import check_backends_installed, AcpxLLMAdapter

    backends = check_backends_installed()
    if not backends.get("acpx") and not backends.get("claude_cli"):
        print("ERROR: No LLM backend found. Install ACPX or Claude CLI.")
        return 1

    config = _load_config(args.config)
    if config is None:
        return 1

    if args.dry_run:
        print("  [DRY RUN] Would run research stages 1-8")
        return 0

    llm = AcpxLLMAdapter(backend=args.backend, session_prefix="clawrank-scotty")
    from scripts.clawrank.core.prompts_loader import PromptManager
    from scripts.clawrank.core.evolution import EvolutionStore
    from scripts.clawrank.core.pipeline.executor import PipelineExecutor

    prompts = PromptManager()
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    evolution = EvolutionStore(LESSONS_DIR)

    executor = PipelineExecutor(
        llm_adapter=llm,
        prompt_manager=prompts,
        evolution_store=evolution,
        config=config,
        artifacts_dir=ARTIFACTS_DIR,
        auto_approve=args.auto_approve,
        hitl_required_stages=config.security.hitl_required_stages,
    )

    context: dict[str, Any] = {
        "topic": config.niche.topic,
        "current_date": datetime.now().strftime("%Y-%m-%d"),
    }
    if args.keyword:
        context["seed_keyword"] = args.keyword

    from_stage = args.from_stage or 1
    to_stage = args.to_stage or 8

    print(f"  Running research stages {from_stage}-{to_stage}...")
    result = executor.run(
        from_stage=from_stage,
        to_stage=to_stage,
        context=context,
    )

    print(f"\n  Research complete")
    print(f"  Run ID: {result.run_id}")
    print(f"  Stages completed: {result.stages_completed}")
    if result.stages_failed:
        print(f"  Stages failed: {result.stages_failed}")
    print(f"  Artifacts: {ARTIFACTS_DIR / result.run_id}")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config(config_path: str) -> Any:
    """Load and validate the ClawRank config."""
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        if CONFIG_PATH.exists():
            path = CONFIG_PATH
        else:
            print(f"Config file not found: {config_path}")
            print("Create config.scotty.yaml in scripts/clawrank/")
            return None

    try:
        from scripts.clawrank.config_loader import CRConfig
        config = CRConfig.load(path, check_paths=False)
        logger.info("Config loaded: %s", path)
        return config
    except Exception as exc:
        print(f"Config error: {exc}")
        return None


def _brief_to_context(brief: dict[str, Any]) -> dict[str, Any]:
    """Convert a content pipeline brief to executor context variables."""
    context: dict[str, Any] = {}

    context["title"] = brief.get("title", brief.get("seo_title", ""))
    context["target_keyword"] = brief.get("target_keyword", brief.get("primary_keyword", ""))
    context["content_type"] = brief.get("content_type", brief.get("type", "how_to"))
    context["ac_post_type"] = brief.get("ac_post_type", brief.get("post_type", "how-to"))
    context["word_count_target"] = str(brief.get("word_count_target", brief.get("target_words", 2000)))
    context["target_url"] = brief.get("target_url", "")

    # Slug from title if not provided
    if not context["target_url"] and context["title"]:
        slug = context["title"].lower()
        slug = slug.replace(" ", "-").replace("'", "").replace('"', "")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        slug = slug.strip("-")
        context["target_url"] = f"/learn/{slug}"

    # Research data
    context["research_brief"] = json.dumps(brief.get("research", {}), indent=2)
    context["evidence"] = json.dumps(brief.get("evidence", {}), indent=2)
    context["competitor_content"] = json.dumps(brief.get("competitors", {}), indent=2)
    context["entity_data"] = json.dumps(brief.get("entities", {}), indent=2)

    # Products and topics
    context["related_products"] = ", ".join(brief.get("related_products", []))
    context["related_topics"] = ", ".join(brief.get("related_topics", []))

    # Brief ID
    context["brief_id"] = brief.get("id", brief.get("brief_id", ""))

    return context


def _log_run_summary(result: Any, elapsed: float) -> None:
    """Log a run summary to the lessons directory."""
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": result.run_id,
        "niche": getattr(result, "niche", "scottysgreenlab"),
        "stages_completed": result.stages_completed,
        "stages_failed": result.stages_failed,
        "documents_generated": getattr(result, "documents_generated", 0),
        "lessons": getattr(result, "lessons", []),
        "elapsed_seconds": round(elapsed, 1),
        "timestamp": datetime.now().isoformat(),
    }
    summary_path = LESSONS_DIR / f"run-{result.run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Run summary saved: %s", summary_path)


if __name__ == "__main__":
    sys.exit(main())
