"""Tests for auto merger module."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from codereview.core.auto_merger import AutoMerger, MergeResult, create_auto_merger
from codereview.models import (
    AutoMergeConfig,
    AutoMergeConditions,
    FileIssue,
    FileReview,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)


class TestAutoMergerInit:
    """Test AutoMerger initialization."""

    def test_default_config(self):
        """Test AutoMerger with default config."""
        config = AutoMergeConfig()
        merger = AutoMerger(config)
        
        assert merger.is_enabled is False
        assert merger.config.enabled is False

    def test_enabled_config(self):
        """Test AutoMerger with enabled config."""
        config = AutoMergeConfig(enabled=True)
        merger = AutoMerger(config)
        
        assert merger.is_enabled is True


class TestCheckMergeConditions:
    """Test check_merge_conditions method."""

    def create_review_result(
        self,
        confidence: float = 95.0,
        conclusion: ReviewConclusion = ReviewConclusion.CAN_SUBMIT,
        files: list[FileReview] = None,
    ) -> ReviewResult:
        """Helper to create review result."""
        if files is None:
            files = [
                FileReview(
                    file_path="src/main.py",
                    risk_level=RiskLevel.LOW,
                    changes="+10, -5",
                    issues=[],
                )
            ]
        return ReviewResult(
            conclusion=conclusion,
            confidence=confidence,
            files_reviewed=files,
            summary="Test review",
        )

    def test_not_enabled(self):
        """Test when auto merge is not enabled."""
        config = AutoMergeConfig(enabled=False)
        merger = AutoMerger(config)
        
        review_result = self.create_review_result()
        can_merge, reason = merger.check_merge_conditions(review_result)
        
        assert can_merge is False
        assert "not enabled" in reason

    def test_low_confidence(self):
        """Test when confidence is below threshold."""
        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(min_confidence=90.0),
        )
        merger = AutoMerger(config)
        
        review_result = self.create_review_result(confidence=80.0)
        can_merge, reason = merger.check_merge_conditions(review_result)
        
        assert can_merge is False
        assert "Confidence" in reason

    def test_high_risk_file(self):
        """Test when a file has high risk level."""
        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(min_confidence=90.0, max_severity=RiskLevel.LOW),
        )
        merger = AutoMerger(config)
        
        files = [
            FileReview(
                file_path="src/auth.py",
                risk_level=RiskLevel.HIGH,
                changes="+20, -10",
                issues=[],
            )
        ]
        review_result = self.create_review_result(files=files)
        can_merge, reason = merger.check_merge_conditions(review_result)
        
        assert can_merge is False
        assert "risk" in reason.lower()

    def test_medium_risk_below_threshold(self):
        """Test when medium risk is below max severity."""
        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(min_confidence=90.0, max_severity=RiskLevel.MEDIUM),
        )
        merger = AutoMerger(config)
        
        files = [
            FileReview(
                file_path="src/main.py",
                risk_level=RiskLevel.MEDIUM,
                changes="+10, -5",
                issues=[],
            )
        ]
        review_result = self.create_review_result(files=files)
        can_merge, reason = merger.check_merge_conditions(review_result, approval_count=1)
        
        assert can_merge is True

    def test_require_approval_not_met(self):
        """Test when approval is required but not provided."""
        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(min_confidence=90.0, require_approval=True),
        )
        merger = AutoMerger(config)
        
        review_result = self.create_review_result()
        can_merge, reason = merger.check_merge_conditions(review_result, approval_count=0)
        
        assert can_merge is False
        assert "approval" in reason.lower()

    def test_require_approval_met(self):
        """Test when approval requirement is met."""
        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(min_confidence=90.0, require_approval=True),
        )
        merger = AutoMerger(config)
        
        review_result = self.create_review_result()
        can_merge, reason = merger.check_merge_conditions(review_result, approval_count=1)
        
        assert can_merge is True
        assert "met" in reason

    def test_all_conditions_met(self):
        """Test when all conditions are met."""
        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(
                min_confidence=90.0,
                max_severity=RiskLevel.LOW,
                require_approval=True,
            ),
        )
        merger = AutoMerger(config)
        
        review_result = self.create_review_result(
            confidence=95.0,
            conclusion=ReviewConclusion.CAN_SUBMIT,
        )
        can_merge, reason = merger.check_merge_conditions(review_result, approval_count=1)
        
        assert can_merge is True

    def test_wrong_conclusion(self):
        """Test when conclusion is not CAN_SUBMIT."""
        config = AutoMergeConfig(enabled=True)
        merger = AutoMerger(config)
        
        review_result = self.create_review_result(
            conclusion=ReviewConclusion.NEEDS_REVIEW
        )
        can_merge, reason = merger.check_merge_conditions(review_result, approval_count=1)
        
        assert can_merge is False
        assert "conclusion" in reason


class TestFilterByPatterns:
    """Test filter_by_patterns method."""

    def test_no_patterns(self):
        """Test with no file patterns (all files included)."""
        config = AutoMergeConfig(enabled=True, file_patterns=[])
        merger = AutoMerger(config)
        
        files = [
            FileReview(file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]),
            FileReview(file_path="src/utils.py", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[]),
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )
        
        filtered = merger.filter_by_patterns(review_result)
        
        assert len(filtered.files_reviewed) == 2

    def test_filter_by_pattern(self):
        """Test filtering by file patterns."""
        config = AutoMerger(
            AutoMergeConfig(enabled=True, file_patterns=["src/*.py"])
        ).config
        config.file_patterns = ["src/*.py"]
        merger = AutoMerger(config)
        
        files = [
            FileReview(file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]),
            FileReview(file_path="tests/test.py", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[]),
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )
        
        filtered = merger.filter_by_patterns(review_result)
        
        assert len(filtered.files_reviewed) == 1
        assert filtered.files_reviewed[0].file_path == "src/main.py"

    def test_multiple_patterns(self):
        """Test with multiple file patterns."""
        config = AutoMergeConfig(enabled=True, file_patterns=["src/*.py", "*.js"])
        merger = AutoMerger(config)
        
        files = [
            FileReview(file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]),
            FileReview(file_path="app.js", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[]),
            FileReview(file_path="readme.md", risk_level=RiskLevel.LOW, changes="+1, -0", issues=[]),
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )
        
        filtered = merger.filter_by_patterns(review_result)
        
        assert len(filtered.files_reviewed) == 2


class TestAutoMerge:
    """Test auto_merge method."""

    def test_not_enabled_returns_early(self):
        """Test when auto merge is not enabled."""
        import asyncio
        
        config = AutoMergeConfig(enabled=False)
        merger = AutoMerger(config)
        
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=[],
            summary="Test",
        )
        
        result = asyncio.run(merger.auto_merge(
            review_result,
            pr_number=1,
            repo_owner="test",
            repo_name="repo",
        ))
        
        assert result.success is False
        assert "not enabled" in result.message

    def test_dry_run(self):
        """Test dry run mode."""
        import asyncio
        
        config = AutoMergeConfig(enabled=True)
        merger = AutoMerger(config)
        
        files = [FileReview(file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[])]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )
        
        result = asyncio.run(merger.auto_merge(
            review_result,
            pr_number=123,
            repo_owner="test",
            repo_name="repo",
            approval_count=1,
            dry_run=True,
        ))
        
        assert result.success is True
        assert result.dry_run is True
        assert "DRY RUN" in result.message

    def test_no_github_client(self):
        """Test when GitHub client is not configured."""
        import asyncio
        
        config = AutoMergeConfig(enabled=True)
        merger = AutoMerger(config, github_client=None)
        
        files = [FileReview(file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[])]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )
        
        result = asyncio.run(merger.auto_merge(
            review_result,
            pr_number=123,
            repo_owner="test",
            repo_name="repo",
            approval_count=1,
            dry_run=False,
        ))
        
        assert result.success is False
        assert "not configured" in result.message


class TestMergeResult:
    """Test MergeResult class."""

    def test_merge_result_creation(self):
        """Test creating a MergeResult."""
        result = MergeResult(
            success=True,
            message="Success",
            dry_run=False,
            pr_number=42,
        )
        
        assert result.success is True
        assert result.message == "Success"
        assert result.dry_run is False
        assert result.pr_number == 42

    def test_merge_result_repr(self):
        """Test MergeResult string representation."""
        result = MergeResult(success=True, message="Test message")
        
        assert "success=True" in repr(result)
        assert "Test message" in repr(result)


class TestGetMergePreview:
    """Test get_merge_preview method."""

    def test_preview_when_not_enabled(self):
        """Test preview when auto merge is not enabled."""
        config = AutoMergeConfig(enabled=False)
        merger = AutoMerger(config)
        
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=[],
            summary="Test",
        )
        
        preview = merger.get_merge_preview(review_result)
        
        assert preview["enabled"] is False
        assert preview["can_merge"] is False

    def test_preview_when_enabled(self):
        """Test preview when auto merge is enabled."""
        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(
                min_confidence=90.0,
                max_severity=RiskLevel.LOW,
                require_approval=True,
            ),
        )
        merger = AutoMerger(config)
        
        files = [FileReview(file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[])]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )
        
        preview = merger.get_merge_preview(review_result, approval_count=1)
        
        assert preview["enabled"] is True
        assert preview["can_merge"] is True
        assert preview["confidence"] == 95.0
        assert preview["confidence_threshold"] == 90.0


class TestCreateAutoMerger:
    """Test create_auto_merger factory function."""

    def test_create_merger(self):
        """Test creating an auto merger."""
        config = AutoMergeConfig(enabled=True)
        merger = create_auto_merger(config)
        
        assert isinstance(merger, AutoMerger)
        assert merger.is_enabled is True

    def test_create_merger_with_github_client(self):
        """Test creating an auto merger with GitHub client."""
        config = AutoMergeConfig(enabled=True)
        mock_client = MagicMock()
        merger = create_auto_merger(config, github_client=mock_client)
        
        assert merger.github_client is mock_client
