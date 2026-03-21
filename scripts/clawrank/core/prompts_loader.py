"""Prompt management for the ClawRank pipeline (Nautix edition).

Loads prompts from YAML (prompts.nautix.yaml) with optional user overrides.
Supports reusable blocks that get injected into stage prompts.

Usage::

    from scripts.clawrank.prompts_loader import PromptManager

    pm = PromptManager()                           # defaults only
    pm = PromptManager("custom_prompts.yaml")      # with overrides

    sp = pm.for_stage("niche_init", topic="business funding", seed_keywords="...")
    resp = llm.complete(system_prompt=sp.system, user_prompt=sp.user, stage=1)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default prompts YAML location (relative to this file)
_DEFAULT_PROMPTS_PATH = Path(__file__).parent.parent / "prompts.scotty.yaml"


def _render(template: str, variables: dict[str, str]) -> str:
    """Replace ``{var_name}`` placeholders with *variables* values.

    Only bare ``{word_chars}`` tokens are substituted -- JSON schema
    examples like ``{{key: value}}`` are left untouched because
    doubled braces are escaped by YAML.
    """

    def _replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(variables[key]) if key in variables else match.group(0)

    return re.sub(r"\{(\w+)\}", _replacer, template)


@dataclass(frozen=True)
class RenderedPrompt:
    """Fully rendered prompt ready for LLM."""
    system: str
    user: str
    json_mode: bool = False
    max_tokens: int | None = None


class PromptManager:
    """Central registry for ClawRank pipeline prompts."""

    def __init__(self, overrides_path: str | Path | None = None) -> None:
        self._stages: dict[str, dict[str, Any]] = {}
        self._blocks: dict[str, str] = {}
        self._content_type_templates: dict[str, str] = {}

        # Load defaults
        self._load_yaml(_DEFAULT_PROMPTS_PATH)

        # Apply user overrides
        if overrides_path:
            self._load_yaml(Path(overrides_path), is_override=True)

    def _load_yaml(self, path: Path, is_override: bool = False) -> None:
        if not path.exists():
            if is_override:
                logger.warning("Prompts file not found: %s -- using defaults", path)
            else:
                logger.error("Default prompts file not found: %s", path)
            return

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            logger.warning("Bad prompts YAML %s: %s", path, exc)
            return

        # Blocks
        for block_name, block_text in (data.get("blocks") or {}).items():
            if isinstance(block_text, str):
                self._blocks[block_name] = block_text

        # Stages
        for stage_name, stage_data in (data.get("stages") or {}).items():
            if isinstance(stage_data, dict):
                if stage_name in self._stages and is_override:
                    self._stages[stage_name].update(stage_data)
                else:
                    self._stages[stage_name] = dict(stage_data)

        # Content type templates
        for tpl_name, tpl_text in (data.get("content_type_templates") or {}).items():
            if isinstance(tpl_text, str):
                self._content_type_templates[tpl_name] = tpl_text

        action = "overrides from" if is_override else "defaults from"
        logger.info("Loaded prompt %s %s", action, path)

    # -- primary API ------------------------------------------------------

    def for_stage(
        self,
        stage: str,
        *,
        evolution_overlay: str = "",
        **kwargs: Any,
    ) -> RenderedPrompt:
        """Return a fully rendered prompt for *stage* with variables filled."""
        entry = self._stages[stage]
        kw = {k: str(v) for k, v in kwargs.items()}

        # Inject block references into kwargs
        for block_name, block_text in self._blocks.items():
            kw.setdefault(block_name, _render(block_text, kw))

        # Inject content type template if applicable
        ct = kw.get("content_type", "")
        if ct and ct in self._content_type_templates:
            kw.setdefault("content_type_template", self._content_type_templates[ct])

        user_text = _render(entry["user"], kw)
        if evolution_overlay:
            user_text = f"{user_text}\n\n{evolution_overlay}"

        return RenderedPrompt(
            system=_render(entry["system"], kw),
            user=user_text,
            json_mode=entry.get("json_mode", False),
            max_tokens=entry.get("max_tokens"),
        )

    def system(self, stage: str) -> str:
        return self._stages[stage]["system"]

    def user(self, stage: str, **kwargs: Any) -> str:
        kw = {k: str(v) for k, v in kwargs.items()}
        for block_name, block_text in self._blocks.items():
            kw.setdefault(block_name, _render(block_text, kw))
        return _render(self._stages[stage]["user"], kw)

    def max_tokens(self, stage: str) -> int | None:
        return self._stages[stage].get("max_tokens")

    def block(self, name: str, **kwargs: Any) -> str:
        return _render(
            self._blocks[name],
            {k: str(v) for k, v in kwargs.items()},
        )

    def content_type_template(self, content_type: str, **kwargs: Any) -> str:
        tpl = self._content_type_templates.get(content_type, "")
        return _render(tpl, {k: str(v) for k, v in kwargs.items()})

    def stage_names(self) -> list[str]:
        return list(self._stages.keys())

    def has_stage(self, stage: str) -> bool:
        return stage in self._stages
