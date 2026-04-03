"""Data models for CodeReview Agent."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk level for code changes."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ZHIPU = "zhipu"
    MINIMAX = "minimax"
    QWEN = "qwen"
    DEEPSEEK = "deepseek"


class MergeMethod(str, Enum):
    """GitHub merge method."""

    SQUASH = "squash"
    MERGE = "merge"
    REBASE = "rebase"


class FileIssue(BaseModel):
    """An issue found in a file during review."""

    file_path: str
    line_number: Optional[int] = None
    risk_level: RiskLevel
    description: str
    suggestion: Optional[str] = None


class FileReview(BaseModel):
    """Review result for a single file."""

    file_path: str
    risk_level: RiskLevel
    changes: str = Field(description="Summary of changes (e.g., '+45, -12')")
    issues: list[FileIssue] = Field(default_factory=list)


class ReviewConclusion(str, Enum):
    """Conclusion of the code review."""

    CAN_SUBMIT = "can_submit"
    NEEDS_REVIEW = "needs_review"


class ReviewResult(BaseModel):
    """Complete review result."""

    conclusion: ReviewConclusion
    confidence: float = Field(ge=0, le=100, description="Confidence percentage")
    files_reviewed: list[FileReview]
    summary: str
    cache_info: Optional[CacheInfo] = None


class CacheInfo(BaseModel):
    """Information about the cache used for this review."""

    used_cache: bool
    cache_timestamp: Optional[str] = None
    cache_version: Optional[str] = None


class ProjectContext(BaseModel):
    """Project context captured during analysis."""

    tech_stack: list[str] = Field(default_factory=list)
    language: Optional[str] = None
    frameworks: list[str] = Field(default_factory=list)
    dependencies: dict[str, str] = Field(default_factory=dict)
    critical_paths: list[str] = Field(default_factory=list)
    code_style: Optional[str] = None
    directory_structure: Optional[str] = None
    linter_config: Optional[dict] = None
    version: str = Field(default="1.0.0")
    analyzed_at: str


class ConfigLLM(BaseModel):
    """LLM configuration."""

    provider: LLMProvider
    api_key: str
    model: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    fallback_providers: list[LLMProvider] = Field(default_factory=list)


class ConfigCache(BaseModel):
    """Cache configuration."""

    ttl_days: int = Field(default=7, ge=1, le=30)
    force_refresh: bool = False


class AutoMergeConditions(BaseModel):
    """Conditions for auto merge."""

    min_confidence: float = Field(
        default=90.0, ge=0, le=100, description="Minimum confidence percentage"
    )
    max_severity: RiskLevel = Field(default=RiskLevel.LOW, description="Maximum allowed risk level")
    require_approval: bool = Field(default=True, description="Require at least one approval")


class AutoMergeConfig(BaseModel):
    """Auto merge configuration."""

    enabled: bool = Field(default=False, description="Enable auto merge")
    file_patterns: list[str] = Field(
        default_factory=list, description="File patterns to include for auto merge"
    )
    merge_method: MergeMethod = Field(
        default=MergeMethod.SQUASH, description="Merge method (squash, merge, or rebase)"
    )
    conditions: AutoMergeConditions = Field(default_factory=AutoMergeConditions)


class OutputConfig(BaseModel):
    """Output configuration."""

    pr_comment: bool = True
    report_path: str = ".codereview-agent/output"
    report_format: str = "markdown"  # markdown, json, both
    auto_merge: AutoMergeConfig = Field(default_factory=AutoMergeConfig)
    merge_method: MergeMethod = Field(
        default=MergeMethod.SQUASH, description="Default merge method for auto-merge"
    )


class Config(BaseModel):
    """CodeReview Agent configuration."""

    llm: ConfigLLM
    critical_paths: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    cache: ConfigCache = Field(default_factory=ConfigCache)
    custom_prompt_path: Optional[str] = None
    output: OutputConfig = Field(default_factory=OutputConfig)
    max_concurrency: int = Field(default=5, ge=1, le=50)
    timeout_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    cache_dir: str = ".codereview-agent/cache"
    default_models: Optional[dict[str, str]] = None


class DiffEntry(BaseModel):
    """A file diff entry."""

    filename: str
    status: str = Field(description="added, modified, deleted, renamed")
    additions: int = 0
    deletions: int = 0
    patch: Optional[str] = None


class DiffResult(BaseModel):
    """Result of getting diff from GitHub."""

    pr_number: int
    base_sha: str
    head_sha: str
    files: list[DiffEntry]
