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


class ConfigCache(BaseModel):
    """Cache configuration."""

    ttl_days: int = Field(default=7, ge=1, le=30)
    force_refresh: bool = False


class OutputConfig(BaseModel):
    """Output configuration."""

    pr_comment: bool = True
    report_path: str = ".codereview-agent/output"
    report_format: str = "markdown"  # markdown, json, both


class Config(BaseModel):
    """CodeReview Agent configuration."""

    llm: ConfigLLM
    critical_paths: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    cache: ConfigCache = Field(default_factory=ConfigCache)
    custom_prompt_path: Optional[str] = None
    output: OutputConfig = Field(default_factory=OutputConfig)


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
