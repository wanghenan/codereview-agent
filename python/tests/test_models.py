"""Tests for data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codereview.models import (
    CacheInfo,
    Config,
    ConfigCache,
    ConfigLLM,
    DiffEntry,
    DiffResult,
    FileIssue,
    FileReview,
    LLMProvider,
    MergeMethod,
    OutputConfig,
    ProjectContext,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_level_values(self):
        """Test RiskLevel enum values."""
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.LOW.value == "low"

    def test_risk_level_is_string_enum(self):
        """Test RiskLevel is a string enum."""
        assert isinstance(RiskLevel.HIGH, str)
        assert RiskLevel.HIGH == "high"


class TestReviewConclusion:
    """Tests for ReviewConclusion enum."""

    def test_review_conclusion_values(self):
        """Test ReviewConclusion enum values."""
        assert ReviewConclusion.CAN_SUBMIT.value == "can_submit"
        assert ReviewConclusion.NEEDS_REVIEW.value == "needs_review"

    def test_review_conclusion_is_string_enum(self):
        """Test ReviewConclusion is a string enum."""
        assert isinstance(ReviewConclusion.CAN_SUBMIT, str)


class TestMergeMethod:
    """Tests for MergeMethod enum."""

    def test_merge_method_values(self):
        """Test MergeMethod enum values."""
        assert MergeMethod.SQUASH.value == "squash"
        assert MergeMethod.MERGE.value == "merge"
        assert MergeMethod.REBASE.value == "rebase"

    def test_merge_method_is_string_enum(self):
        """Test MergeMethod is a string enum."""
        assert isinstance(MergeMethod.SQUASH, str)


class TestLLMProvider:
    """Tests for LLMProvider enum."""

    def test_llm_provider_values(self):
        """Test LLMProvider enum values."""
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.ZHIPU.value == "zhipu"
        assert LLMProvider.MINIMAX.value == "minimax"
        assert LLMProvider.QWEN.value == "qwen"
        assert LLMProvider.DEEPSEEK.value == "deepseek"


class TestFileIssue:
    """Tests for FileIssue model."""

    def test_file_issue_required_fields(self):
        """Test FileIssue with required fields only."""
        issue = FileIssue(
            file_path="src/main.py",
            risk_level=RiskLevel.HIGH,
            description="SQL injection vulnerability",
        )

        assert issue.file_path == "src/main.py"
        assert issue.risk_level == RiskLevel.HIGH
        assert issue.description == "SQL injection vulnerability"
        assert issue.line_number is None
        assert issue.suggestion is None

    def test_file_issue_all_fields(self):
        """Test FileIssue with all fields."""
        issue = FileIssue(
            file_path="src/main.py",
            line_number=42,
            risk_level=RiskLevel.MEDIUM,
            description="Unused import",
            suggestion="Remove the unused import",
        )

        assert issue.line_number == 42
        assert issue.suggestion == "Remove the unused import"

    def test_file_issue_serialization(self):
        """Test FileIssue serialization to dict."""
        issue = FileIssue(
            file_path="src/main.py",
            line_number=10,
            risk_level=RiskLevel.LOW,
            description="Style issue",
        )

        data = issue.model_dump()
        assert data["file_path"] == "src/main.py"
        assert data["line_number"] == 10
        assert data["risk_level"] == "low"
        assert data["description"] == "Style issue"


class TestFileReview:
    """Tests for FileReview model."""

    def test_file_review_required_fields(self):
        """Test FileReview with required fields."""
        review = FileReview(
            file_path="src/main.py",
            risk_level=RiskLevel.LOW,
            changes="+10, -5",
        )

        assert review.file_path == "src/main.py"
        assert review.risk_level == RiskLevel.LOW
        assert review.changes == "+10, -5"
        assert review.issues == []

    def test_file_review_with_issues(self):
        """Test FileReview with issues."""
        issues = [
            FileIssue(
                file_path="src/main.py",
                line_number=10,
                risk_level=RiskLevel.HIGH,
                description="Security issue",
            )
        ]
        review = FileReview(
            file_path="src/main.py",
            risk_level=RiskLevel.HIGH,
            changes="+20, -5",
            issues=issues,
        )

        assert len(review.issues) == 1
        assert review.issues[0].description == "Security issue"


class TestReviewResult:
    """Tests for ReviewResult model."""

    def test_review_result_required_fields(self):
        """Test ReviewResult with required fields."""
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=[],
            summary="All good",
        )

        assert result.conclusion == ReviewConclusion.CAN_SUBMIT
        assert result.confidence == 95.0
        assert result.files_reviewed == []
        assert result.cache_info is None

    def test_review_result_with_cache_info(self):
        """Test ReviewResult with cache info."""
        cache_info = CacheInfo(
            used_cache=True,
            cache_timestamp="2024-01-01T00:00:00Z",
            cache_version="1.0.0",
        )
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=90.0,
            files_reviewed=[],
            summary="Test",
            cache_info=cache_info,
        )

        assert result.cache_info is not None
        assert result.cache_info.used_cache is True

    def test_review_result_confidence_range(self):
        """Test ReviewResult confidence validation."""
        # Valid confidence values
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=0.0,
            files_reviewed=[],
            summary="Test",
        )
        assert result.confidence == 0.0

        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=100.0,
            files_reviewed=[],
            summary="Test",
        )
        assert result.confidence == 100.0

        # Invalid - should fail
        with pytest.raises(ValidationError):
            ReviewResult(
                conclusion=ReviewConclusion.CAN_SUBMIT,
                confidence=150.0,  # Above 100
                files_reviewed=[],
                summary="Test",
            )


class TestCacheInfo:
    """Tests for CacheInfo model."""

    def test_cache_info_required_fields(self):
        """Test CacheInfo with required fields."""
        info = CacheInfo(used_cache=False)

        assert info.used_cache is False
        assert info.cache_timestamp is None
        assert info.cache_version is None


class TestConfigLLM:
    """Tests for ConfigLLM model."""

    def test_config_llm_required_fields(self):
        """Test ConfigLLM with required fields."""
        config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="sk-test",
        )

        assert config.provider == LLMProvider.OPENAI
        assert config.api_key == "sk-test"
        assert config.model is None
        assert config.base_url is None
        assert config.temperature == 0.7  # Default

    def test_config_llm_temperature_default(self):
        """Test ConfigLLM temperature default."""
        config = ConfigLLM(provider=LLMProvider.ANTHROPIC, api_key="key")
        assert config.temperature == 0.7

    def test_config_llm_temperature_valid_range(self):
        """Test ConfigLLM accepts valid temperature values."""
        # Valid values
        config = ConfigLLM(provider=LLMProvider.OPENAI, api_key="key", temperature=0.0)
        assert config.temperature == 0.0

        config = ConfigLLM(provider=LLMProvider.OPENAI, api_key="key", temperature=2.0)
        assert config.temperature == 2.0

    def test_config_llm_all_providers(self):
        """Test ConfigLLM with all providers."""
        for provider in LLMProvider:
            config = ConfigLLM(provider=provider, api_key="key")
            assert config.provider == provider


class TestConfigCache:
    """Tests for ConfigCache model."""

    def test_config_cache_defaults(self):
        """Test ConfigCache default values."""
        config = ConfigCache()

        assert config.ttl_days == 7
        assert config.force_refresh is False

    def test_config_cache_ttl_days_valid_range(self):
        """Test ConfigCache ttl_days validation."""
        # Valid boundaries
        config = ConfigCache(ttl_days=1)
        assert config.ttl_days == 1

        config = ConfigCache(ttl_days=30)
        assert config.ttl_days == 30

    def test_config_cache_ttl_days_too_low(self):
        """Test ConfigCache rejects ttl_days < 1."""
        with pytest.raises(ValidationError):
            ConfigCache(ttl_days=0)

    def test_config_cache_ttl_days_too_high(self):
        """Test ConfigCache rejects ttl_days > 30."""
        with pytest.raises(ValidationError):
            ConfigCache(ttl_days=31)


class TestAutoMergeConditions:
    """Tests for AutoMergeConditions model."""

    def test_auto_merge_conditions_defaults(self):
        """Test AutoMergeConditions default values."""
        from codereview.models import AutoMergeConditions

        conditions = AutoMergeConditions()

        assert conditions.min_confidence == 90.0
        assert conditions.max_severity == RiskLevel.LOW
        assert conditions.require_approval is True

    def test_auto_merge_conditions_valid_range(self):
        """Test AutoMergeConditions valid ranges."""
        from codereview.models import AutoMergeConditions

        conditions = AutoMergeConditions(
            min_confidence=0.0,
            max_severity=RiskLevel.HIGH,
            require_approval=False,
        )

        assert conditions.min_confidence == 0.0
        assert conditions.max_severity == RiskLevel.HIGH
        assert conditions.require_approval is False


class TestConfig:
    """Tests for Config model."""

    def test_config_required_fields(self):
        """Test Config with required fields."""
        config = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="key"),
        )

        assert config.llm.provider == LLMProvider.OPENAI
        assert config.critical_paths == []
        assert config.exclude_patterns == []
        assert isinstance(config.cache, ConfigCache)
        assert config.output is not None

    def test_config_defaults(self):
        """Test Config default values."""
        config = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="key"),
        )

        assert config.max_concurrency == 5
        assert config.timeout_seconds == 30.0
        assert config.cache_dir == ".codereview-agent/cache"
        assert config.output.auto_merge.enabled is False

    def test_config_full_loading(self):
        """Test Config full loading with all fields."""
        config = Config(
            llm=ConfigLLM(
                provider=LLMProvider.ANTHROPIC,
                api_key="sk-ant",
                model="claude-sonnet",
                temperature=0.5,
            ),
            critical_paths=["src/", "lib/"],
            exclude_patterns=["*.test.py", "**/node_modules/**"],
            cache=ConfigCache(ttl_days=14, force_refresh=True),
            custom_prompt_path=".custom-prompt.md",
            output=OutputConfig(
                pr_comment=True,
                report_format="json",
            ),
            max_concurrency=10,
            timeout_seconds=60.0,
            cache_dir=".custom-cache",
        )

        assert config.llm.model == "claude-sonnet"
        assert config.llm.temperature == 0.5
        assert config.critical_paths == ["src/", "lib/"]
        assert config.cache.ttl_days == 14
        assert config.cache.force_refresh is True
        assert config.max_concurrency == 10
        assert config.timeout_seconds == 60.0


class TestDiffEntry:
    """Tests for DiffEntry model."""

    def test_diff_entry_required_fields(self):
        """Test DiffEntry with required fields."""
        entry = DiffEntry(filename="src/main.py", status="modified")

        assert entry.filename == "src/main.py"
        assert entry.status == "modified"
        assert entry.additions == 0
        assert entry.deletions == 0
        assert entry.patch is None

    def test_diff_entry_all_fields(self):
        """Test DiffEntry with all fields."""
        entry = DiffEntry(
            filename="src/main.py",
            status="added",
            additions=50,
            deletions=10,
            patch="--- a/src/main.py\n+++ b/src/main.py\n@@ ...",
        )

        assert entry.additions == 50
        assert entry.deletions == 10
        assert entry.patch is not None


class TestDiffResult:
    """Tests for DiffResult model."""

    def test_diff_result_required_fields(self):
        """Test DiffResult with required fields."""
        result = DiffResult(
            pr_number=123,
            base_sha="abc123",
            head_sha="def456",
            files=[],
        )

        assert result.pr_number == 123
        assert result.base_sha == "abc123"
        assert result.head_sha == "def456"
        assert result.files == []

    def test_diff_result_with_files(self):
        """Test DiffResult with file entries."""
        files = [
            DiffEntry(filename="src/a.py", status="added", additions=10),
            DiffEntry(filename="src/b.py", status="modified", additions=5, deletions=2),
        ]
        result = DiffResult(
            pr_number=1,
            base_sha="a",
            head_sha="b",
            files=files,
        )

        assert len(result.files) == 2
        assert result.files[0].filename == "src/a.py"
