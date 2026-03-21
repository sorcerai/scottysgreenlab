"""ClawRank config loading and validation for Scotty's Green Lab.

Loads config.scotty.yaml (or any YAML config) and validates required fields.
Adapted from the upstream ClawRank config module with ACP/ACPX/CLI support,
extended with brain DB connection and GPU model endpoint configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = (
    "project.name",
    "niche.topic",
    "runtime.timezone",
    "knowledge_base.root",
)
KB_SUBDIRS = (
    "keywords",
    "competitors",
    "research",
    "content",
    "analytics",
    "lessons",
)
PROJECT_MODES = {"auto", "semi-auto", "manual"}
KB_BACKENDS = {"markdown", "obsidian"}
TARGET_FRAMEWORKS = {"nextjs", "astro", "wordpress", "hugo", "static", "headless", "custom"}
LLM_PROVIDERS = {"openai-compatible", "acp", "acpx", "cli"}


def _get_by_path(data: dict[str, Any], dotted_key: str) -> Any:
    cur: Any = data
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    mode: str = "auto"


@dataclass(frozen=True)
class NicheConfig:
    """Core niche definition."""
    topic: str
    domains: tuple[str, ...] = ()
    seed_keywords: tuple[str, ...] = ()
    target_audiences: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    locale: str = "en-US"
    geo_targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeConfig:
    timezone: str
    max_parallel_tasks: int = 4
    approval_timeout_hours: int = 24
    retry_limit: int = 2


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    backend: str
    root: str
    obsidian_vault: str = ""


@dataclass(frozen=True)
class LlmConfig:
    """LLM configuration -- supports OpenAI-compatible, ACP, ACPX, and CLI backends."""
    provider: str                        # openai-compatible, acp, acpx, cli
    base_url: str = ""
    api_key_env: str = ""
    api_key: str = ""
    primary_model: str = ""
    fallback_models: tuple[str, ...] = ()
    embed_url: str = ""
    embed_model: str = ""
    notes: str = ""
    # ACPX-specific
    acpx_backend: str = "claude"         # claude, codex, gemini
    acpx_session_prefix: str = "clawrank"
    # Per-stage backend routing
    default_backend: str = "gemini"
    heavy_backend: str = "claude"


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


@dataclass(frozen=True)
class SecurityConfig:
    hitl_required_stages: tuple[int, ...] = (5, 9, 16)
    allow_publish_without_approval: bool = False
    redact_sensitive_logs: bool = True


@dataclass(frozen=True)
class KeywordConfig:
    max_keywords_per_seed: int = 200
    paa_depth: int = 3
    serp_similarity_threshold: float = 0.6
    semantic_cluster_min_size: int = 3
    min_search_volume: int = 10
    max_difficulty: float = 0.8
    competitor_count: int = 10
    enable_academic_mining: bool = True
    enable_forum_mining: bool = True
    enable_job_mining: bool = False


@dataclass(frozen=True)
class ContentConfig:
    enabled_types: tuple[str, ...] = ()
    pillar_word_count: int = 4000
    comparison_word_count: int = 2500
    how_to_word_count: int = 2000
    glossary_word_count: int = 800
    statistics_word_count: int = 2000
    listicle_word_count: int = 2500
    min_eeat_score: float = 0.7
    min_originality_score: float = 0.6
    max_ai_slop_score: float = 0.3
    enable_data_visualization: bool = True
    enable_expert_quotes: bool = True
    enable_contrarian_takes: bool = True
    citation_density_target: int = 3
    batch_size: int = 10


@dataclass(frozen=True)
class PublishConfig:
    target_framework: str = "nextjs"
    output_dir: str = "content/blog/"
    mdx_enabled: bool = True
    frontmatter_schema: str = "nautix"
    auto_deploy: bool = False
    sitemap_enabled: bool = True
    robots_txt_enabled: bool = True
    og_image_generation: bool = False


@dataclass(frozen=True)
class MonitorConfig:
    enable_rank_tracking: bool = True
    rank_check_interval_hours: int = 24
    enable_competitor_monitoring: bool = True
    competitor_diff_interval_days: int = 7
    content_decay_threshold_days: int = 90
    enable_gsc_integration: bool = False
    gsc_credentials_env: str = ""


@dataclass(frozen=True)
class ContentAgentConfig:
    writer_temperature: float = 0.7
    fact_check_enabled: bool = True
    contrarian_enabled: bool = True
    quality_scorer_enabled: bool = True
    review_max_rounds: int = 2


@dataclass(frozen=True)
class PromptsConfig:
    custom_file: str = ""


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CRConfig:
    """ClawRank configuration -- top-level dataclass."""
    project: ProjectConfig
    niche: NicheConfig
    runtime: RuntimeConfig
    knowledge_base: KnowledgeBaseConfig
    llm: LlmConfig
    brain: BrainConfig = field(default_factory=BrainConfig)
    gpu_models: GpuModelsConfig = field(default_factory=GpuModelsConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    keywords: KeywordConfig = field(default_factory=KeywordConfig)
    content: ContentConfig = field(default_factory=ContentConfig)
    publish: PublishConfig = field(default_factory=PublishConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    content_agent: ContentAgentConfig = field(default_factory=ContentAgentConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        project_root: Path | None = None,
        check_paths: bool = True,
    ) -> CRConfig:
        result = validate_config(
            data, project_root=project_root, check_paths=check_paths
        )
        if not result.ok:
            raise ValueError("; ".join(result.errors))

        project = data["project"]
        niche = data["niche"]
        runtime = data["runtime"]
        kb = data["knowledge_base"]
        llm = data["llm"]
        brain = data.get("brain") or {}
        gpu_models = data.get("gpu_models") or {}
        security = data.get("security") or {}
        keywords = data.get("keywords") or {}
        content = data.get("content") or {}
        publish = data.get("publish") or {}
        monitor = data.get("monitor") or {}
        content_agent = data.get("content_agent") or {}
        prompts = data.get("prompts") or {}

        return cls(
            project=ProjectConfig(
                name=project["name"],
                mode=project.get("mode", "auto"),
            ),
            niche=_parse_niche_config(niche),
            runtime=RuntimeConfig(
                timezone=runtime["timezone"],
                max_parallel_tasks=int(runtime.get("max_parallel_tasks", 4)),
                approval_timeout_hours=int(runtime.get("approval_timeout_hours", 24)),
                retry_limit=int(runtime.get("retry_limit", 2)),
            ),
            knowledge_base=KnowledgeBaseConfig(
                backend=kb.get("backend", "markdown"),
                root=kb["root"],
                obsidian_vault=kb.get("obsidian_vault", ""),
            ),
            llm=_parse_llm_config(llm),
            brain=_parse_brain_config(brain),
            gpu_models=_parse_gpu_models_config(gpu_models),
            security=SecurityConfig(
                hitl_required_stages=tuple(
                    int(s) for s in security.get("hitl_required_stages", (5, 9, 16))
                ),
                allow_publish_without_approval=bool(
                    security.get("allow_publish_without_approval", False)
                ),
                redact_sensitive_logs=bool(security.get("redact_sensitive_logs", True)),
            ),
            keywords=_parse_keyword_config(keywords),
            content=_parse_content_config(content),
            publish=_parse_publish_config(publish),
            monitor=_parse_monitor_config(monitor),
            content_agent=_parse_content_agent_config(content_agent),
            prompts=PromptsConfig(custom_file=prompts.get("custom_file", "")),
        )

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        project_root: str | Path | None = None,
        check_paths: bool = True,
    ) -> CRConfig:
        config_path = Path(path).expanduser().resolve()
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        resolved_root = (
            Path(project_root).expanduser().resolve()
            if project_root
            else config_path.parent
        )
        return cls.from_dict(data, project_root=resolved_root, check_paths=check_paths)


def validate_config(
    data: dict[str, Any],
    *,
    project_root: Path | None = None,
    check_paths: bool = True,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    llm_provider = _get_by_path(data, "llm.provider")
    for key in REQUIRED_FIELDS:
        value = _get_by_path(data, key)
        if _is_blank(value):
            errors.append(f"Missing required field: {key}")

    # ACPX and CLI providers do not require base_url or api_key
    if llm_provider not in ("acp", "acpx", "cli"):
        for llm_key in ("llm.base_url", "llm.api_key_env"):
            value = _get_by_path(data, llm_key)
            if _is_blank(value):
                errors.append(f"Missing required field: {llm_key}")

    project_mode = _get_by_path(data, "project.mode")
    if not _is_blank(project_mode) and project_mode not in PROJECT_MODES:
        errors.append(f"Invalid project.mode: {project_mode}")

    kb_backend = _get_by_path(data, "knowledge_base.backend")
    if not _is_blank(kb_backend) and kb_backend not in KB_BACKENDS:
        errors.append(f"Invalid knowledge_base.backend: {kb_backend}")

    target_fw = _get_by_path(data, "publish.target_framework")
    if not _is_blank(target_fw) and target_fw not in TARGET_FRAMEWORKS:
        warnings.append(f"Unknown publish.target_framework: {target_fw} (custom assumed)")

    hitl = _get_by_path(data, "security.hitl_required_stages")
    if hitl is not None:
        if not isinstance(hitl, list):
            errors.append("security.hitl_required_stages must be a list")
        else:
            for stage in hitl:
                if not isinstance(stage, int) or not 1 <= stage <= 23:
                    errors.append(f"Invalid hitl_required_stages entry: {stage}")

    kb_root_raw = _get_by_path(data, "knowledge_base.root")
    if check_paths and not _is_blank(kb_root_raw) and project_root is not None:
        kb_root = project_root / str(kb_root_raw)
        if not kb_root.exists():
            warnings.append(f"KB root does not exist (will be created): {kb_root}")

    return ValidationResult(
        ok=not errors, errors=tuple(errors), warnings=tuple(warnings)
    )


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_niche_config(data: dict[str, Any]) -> NicheConfig:
    return NicheConfig(
        topic=data["topic"],
        domains=tuple(data.get("domains") or ()),
        seed_keywords=tuple(data.get("seed_keywords") or ()),
        target_audiences=tuple(data.get("target_audiences") or ()),
        entities=tuple(data.get("entities") or ()),
        locale=data.get("locale", "en-US"),
        geo_targets=tuple(data.get("geo_targets") or ()),
    )


def _parse_llm_config(data: dict[str, Any]) -> LlmConfig:
    return LlmConfig(
        provider=data.get("provider", "acpx"),
        base_url=data.get("base_url", ""),
        api_key_env=data.get("api_key_env", ""),
        api_key=data.get("api_key", ""),
        primary_model=data.get("primary_model", ""),
        fallback_models=tuple(data.get("fallback_models") or ()),
        embed_url=data.get("embed_url", ""),
        embed_model=data.get("embed_model", ""),
        notes=data.get("notes", ""),
        acpx_backend=data.get("acpx_backend", "claude"),
        acpx_session_prefix=data.get("acpx_session_prefix", "clawrank"),
        default_backend=data.get("default_backend", "gemini"),
        heavy_backend=data.get("heavy_backend", "claude"),
    )


def _parse_brain_config(data: dict[str, Any]) -> BrainConfig:
    if not data:
        return BrainConfig()
    return BrainConfig(
        connection_env=data.get("connection_env", "BRAIN_DB_URL"),
        database_id=data.get("database_id", ""),
    )


def _parse_gpu_models_config(data: dict[str, Any]) -> GpuModelsConfig:
    if not data:
        return GpuModelsConfig()
    return GpuModelsConfig(
        intent_classifier=data.get("intent_classifier", ""),
        query_fanout=data.get("query_fanout", ""),
        sentiment=data.get("sentiment", ""),
        reranker=data.get("reranker", ""),
        embedder=data.get("embedder", "local://e5-base-v2"),
    )


def _parse_keyword_config(data: dict[str, Any]) -> KeywordConfig:
    if not data:
        return KeywordConfig()
    return KeywordConfig(
        max_keywords_per_seed=int(data.get("max_keywords_per_seed", 200)),
        paa_depth=int(data.get("paa_depth", 3)),
        serp_similarity_threshold=float(data.get("serp_similarity_threshold", 0.6)),
        semantic_cluster_min_size=int(data.get("semantic_cluster_min_size", 3)),
        min_search_volume=int(data.get("min_search_volume", 10)),
        max_difficulty=float(data.get("max_difficulty", 0.8)),
        competitor_count=int(data.get("competitor_count", 10)),
        enable_academic_mining=bool(data.get("enable_academic_mining", True)),
        enable_forum_mining=bool(data.get("enable_forum_mining", True)),
        enable_job_mining=bool(data.get("enable_job_mining", False)),
    )


def _parse_content_config(data: dict[str, Any]) -> ContentConfig:
    if not data:
        return ContentConfig()
    return ContentConfig(
        enabled_types=tuple(data.get("enabled_types") or ()),
        pillar_word_count=int(data.get("pillar_word_count", 4000)),
        comparison_word_count=int(data.get("comparison_word_count", 2500)),
        how_to_word_count=int(data.get("how_to_word_count", 2000)),
        glossary_word_count=int(data.get("glossary_word_count", 800)),
        statistics_word_count=int(data.get("statistics_word_count", 2000)),
        listicle_word_count=int(data.get("listicle_word_count", 2500)),
        min_eeat_score=float(data.get("min_eeat_score", 0.7)),
        min_originality_score=float(data.get("min_originality_score", 0.6)),
        max_ai_slop_score=float(data.get("max_ai_slop_score", 0.3)),
        enable_data_visualization=bool(data.get("enable_data_visualization", True)),
        enable_expert_quotes=bool(data.get("enable_expert_quotes", True)),
        enable_contrarian_takes=bool(data.get("enable_contrarian_takes", True)),
        citation_density_target=int(data.get("citation_density_target", 3)),
        batch_size=int(data.get("batch_size", 10)),
    )


def _parse_publish_config(data: dict[str, Any]) -> PublishConfig:
    if not data:
        return PublishConfig()
    return PublishConfig(
        target_framework=data.get("target_framework", "nextjs"),
        output_dir=data.get("output_dir", "content/blog/"),
        mdx_enabled=bool(data.get("mdx_enabled", True)),
        frontmatter_schema=data.get("frontmatter_schema", "nautix"),
        auto_deploy=bool(data.get("auto_deploy", False)),
        sitemap_enabled=bool(data.get("sitemap_enabled", True)),
        robots_txt_enabled=bool(data.get("robots_txt_enabled", True)),
        og_image_generation=bool(data.get("og_image_generation", False)),
    )


def _parse_monitor_config(data: dict[str, Any]) -> MonitorConfig:
    if not data:
        return MonitorConfig()
    return MonitorConfig(
        enable_rank_tracking=bool(data.get("enable_rank_tracking", True)),
        rank_check_interval_hours=int(data.get("rank_check_interval_hours", 24)),
        enable_competitor_monitoring=bool(data.get("enable_competitor_monitoring", True)),
        competitor_diff_interval_days=int(data.get("competitor_diff_interval_days", 7)),
        content_decay_threshold_days=int(data.get("content_decay_threshold_days", 90)),
        enable_gsc_integration=bool(data.get("enable_gsc_integration", False)),
        gsc_credentials_env=data.get("gsc_credentials_env", ""),
    )


def _parse_content_agent_config(data: dict[str, Any]) -> ContentAgentConfig:
    if not data:
        return ContentAgentConfig()
    return ContentAgentConfig(
        writer_temperature=float(data.get("writer_temperature", 0.7)),
        fact_check_enabled=bool(data.get("fact_check_enabled", True)),
        contrarian_enabled=bool(data.get("contrarian_enabled", True)),
        quality_scorer_enabled=bool(data.get("quality_scorer_enabled", True)),
        review_max_rounds=int(data.get("review_max_rounds", 2)),
    )


def load_config(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
    check_paths: bool = True,
) -> CRConfig:
    return CRConfig.load(path, project_root=project_root, check_paths=check_paths)
