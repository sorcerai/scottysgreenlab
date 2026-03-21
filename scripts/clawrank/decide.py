#!/usr/bin/env python3
"""ClawRank Decision Engine for Scotty's Green Lab.

Reads the world state snapshot and decides what content action to take next:
- If unprocessed briefs exist: return a write action pointing to the first brief
- If no briefs: find the pillar with lowest article coverage and return a research action

Usage (standalone):
  python3 scripts/clawrank/decide.py

Callable as a library:
  from scripts.clawrank.decide import decide
  result = decide(world_state, briefs_dir)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def decide(world_state: dict, briefs_dir: Path) -> dict:
    """Decide what content to write next.

    Args:
        world_state: Snapshot dict produced by collect_brain_state() or cmd_world_state().
                     Must contain "articles_by_pillar" (dict[str, int]) and "total_articles" (int).
        briefs_dir:  Path to directory containing brief JSON files.

    Returns:
        A dict with keys:
          - action: "write" | "research"
          - target: brief file path (str) for write, or pillar name for research
          - reason: human-readable explanation
    """
    briefs_dir = Path(briefs_dir)

    # Check for unprocessed briefs first
    if briefs_dir.exists():
        brief_files = sorted(briefs_dir.glob("*.json"))
        unprocessed = []
        for bf in brief_files:
            try:
                brief = json.loads(bf.read_text(encoding="utf-8"))
                if brief.get("status") != "published":
                    unprocessed.append(bf)
            except (json.JSONDecodeError, OSError):
                # Treat unparseable briefs as unprocessed
                unprocessed.append(bf)

        if unprocessed:
            return {
                "action": "write",
                "target": str(unprocessed[0]),
                "reason": "unprocessed brief available",
            }

    # No unprocessed briefs — find lowest-coverage pillar
    articles_by_pillar: dict[str, int] = world_state.get("articles_by_pillar", {})

    if not articles_by_pillar:
        return {
            "action": "research",
            "target": "general",
            "reason": "no pillar data available, defaulting to general research",
        }

    lowest_pillar = min(articles_by_pillar, key=lambda p: articles_by_pillar[p])
    lowest_count = articles_by_pillar[lowest_pillar]

    return {
        "action": "research",
        "target": lowest_pillar,
        "reason": f"lowest coverage pillar ({lowest_count} articles)",
    }


if __name__ == "__main__":
    import os
    import sys

    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

    _ARTIFACTS_DIR = _PROJECT_ROOT / "artifacts" / "clawrank"
    _BRIEFS_DIR = _PROJECT_ROOT / "data" / "content-pipeline" / "briefs"

    # Load most recent world state
    snapshots = sorted(_ARTIFACTS_DIR.glob("world-state-*.json"), reverse=True) if _ARTIFACTS_DIR.exists() else []
    if not snapshots:
        print("No world state found. Run: python3 scripts/clawrank/run.py --world-state")
        sys.exit(1)

    _world_state = json.loads(snapshots[0].read_text())
    print(f"Using snapshot: {snapshots[0].name}")

    _result = decide(_world_state, _BRIEFS_DIR)
    print(f"\nDecision:")
    print(f"  action : {_result['action']}")
    print(f"  target : {_result['target']}")
    print(f"  reason : {_result['reason']}")
