"""Data models for CodeReview Agent."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


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


class IssueCategory(str, Enum):
    """Category of a review finding, used for filtering and reporting."""

    BUG = "bug"
    SECURITY = "security"
    PERF = "perf"
    MAINTAINABILITY = "maintainability"
    STYLE = "style"


class EvidenceKind(str, Enum):
    """Where a finding's evidence comes from."""

    RULE = "rule"
    SYMBOL = "symbol"
    CONTEXT = "context"
    DIFF = "diff"


class Evidence(BaseModel):
    """One concrete anchor backing a finding.

    A finding without evidence is a claim; the anchors are what make it
    reviewable and what allow later stages to dedupe or hand it to an agent.
    """

    kind: EvidenceKind
    detail: str = Field(min_length=1, description="Rule id, symbol, or file:line reference")


class FileIssue(BaseModel):
    """An issue found in a file during review.

    Also serves as the ``Finding`` model: ``title``/``category``/``confidence``/
    ``evidence``/``suggested_patch``/``source`` are the S1 additions. They all
    default, so existing producers and cached payloads keep validating.
    """

    file_path: str
    line_number: Optional[int] = None
    risk_level: RiskLevel
    description: str
    suggestion: Optional[str] = None

    # --- S1 fields (all optional for backwards compatibility) --------------
    title: str = ""
    end_line: Optional[int] = None
    category: IssueCategory = IssueCategory.BUG
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_patch: Optional[str] = None
    source: Literal["rule", "tool", "llm"] = "llm"
    #: ``path:line`` of the caller that the change breaks, when the model was
    #: shown one in the cross-file context. Structured so the claim is
    #: checkable instead of being buried in prose.
    caller: Optional[str] = None

    @model_validator(mode="after")
    def _check_line_range(self) -> FileIssue:
        """Reject a range whose end precedes its start."""
        if self.end_line is not None and self.line_number is not None:
            if self.end_line < self.line_number:
                raise ValueError("end_line must not be before line_number")
        return self

    def dedupe_key(self) -> tuple[str, int, str]:
        """Return the key used to suppress duplicate findings across runs.

        Line numbers are bucketed by 10 so small shifts do not create repeats.
        """
        bucket = (self.line_number or 0) // 10
        label = (self.title or self.description).strip().lower()[:80]
        return (self.file_path, bucket, label)


# The plan (docs/CODE_REVIEW_UPGRADE_PLAN.md) calls this model ``Finding``.
Finding = FileIssue


class FilteredFinding(BaseModel):
    """A finding removed by the noise filter, with the rule that dropped it.

    Keeping the dropped finding (rather than only a count) lets callers audit
    why a finding disappeared and, later, compute per-rule false-positive
    rates without re-running the review.
    """

    reason: Literal["low-confidence", "low-risk-llm", "category"]
    issue: FileIssue


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


class SkipRecord(BaseModel):
    """A diff entry removed by the admission filter before review.

    Kept intentionally minimal so it can be serialized into ``findings.json``
    and summarized in one line on the PR without another schema change.
    """

    filename: str
    reason: str
    detail: str = ""


class ReviewResult(BaseModel):
    """Complete review result."""

    conclusion: ReviewConclusion
    confidence: float = Field(ge=0, le=100, description="Confidence percentage")
    files_reviewed: list[FileReview]
    summary: str
    cache_info: Optional[CacheInfo] = None
    skipped: list[SkipRecord] = Field(
        default_factory=list,
        description="Diff entries filtered out before review (S3 admission layer)",
    )
    filtered: list[FilteredFinding] = Field(
        default_factory=list,
        description="Findings removed by the noise filter after review (S4)",
    )


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


class ConfigFilters(BaseModel):
    """Noise-filter configuration for findings.

    ``min_confidence`` defaults to 0.5: the S0 baseline showed that dropping
    LLM findings below 0.5 removes one of six noise cases without losing any
    true positive. The other two rules stay off by default.
    """

    min_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Drop LLM findings below this confidence (0 disables)",
    )
    drop_low_risk_llm: bool = Field(
        default=False,
        description="Drop low-risk findings produced by the LLM",
    )
    drop_categories: list[str] = Field(
        default_factory=list,
        description="Drop findings in these categories, regardless of source",
    )


class ConfigContext(BaseModel):
    """Cross-file symbol context configuration (S5).

    The defaults enable one-hop neighbour injection, but the feature is
    deliberately best-effort: a missing index with ``auto_build`` off simply
    leaves the prompt unchanged.
    """

    neighbors: bool = Field(
        default=True,
        description="Inject one-hop symbol neighbours into review prompts",
    )
    max_neighbors: int = Field(
        default=3,
        ge=0,
        description="Maximum related symbols included per reviewed file",
    )
    max_chars: int = Field(
        default=2400,
        ge=0,
        description="Maximum size of the cross-file context section",
    )
    index_path: str = Field(
        default=".codereview-agent/index.json",
        description="Repository-relative path of the persisted symbol index",
    )
    auto_build: bool = Field(
        default=True,
        description="Build and save the index when it is missing or stale",
    )


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
    filters: ConfigFilters = Field(default_factory=ConfigFilters)
    context: ConfigContext = Field(default_factory=ConfigContext)
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
