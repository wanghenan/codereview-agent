"""Tests for auto merger module."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from codereview.core.auto_merger import AutoMerger, MergeResult, create_auto_merger
from codereview.models import (
    AutoMergeConfig,
    AutoMergeConditions,
    FileIssue,
    FileReview,
    MergeMethod,
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

    def test_wrong_conclusion_with_high_confidence_low_risk(self):
        """Test when conclusion is NEEDS_REVIEW but confidence is high and risk is low."""
        config = AutoMergeConfig(enabled=True)
        merger = AutoMerger(config)

        # With 95%+ confidence and only low-risk issues, we allow proceeding
        files = [
            FileReview(
                file_path="src/main.py",
                risk_level=RiskLevel.LOW,
                changes="+10, -5",
                issues=[],
            )
        ]
        review_result = self.create_review_result(
            conclusion=ReviewConclusion.NEEDS_REVIEW,
            confidence=95.0,
            files=files,
        )
        can_merge, reason = merger.check_merge_conditions(review_result, approval_count=1)

        # High confidence + low risk only = allow merge despite NEEDS_REVIEW
        assert can_merge is True


class TestFilterByPatterns:
    """Test filter_by_patterns method."""

    def test_no_patterns(self):
        """Test with no file patterns (all files included)."""
        config = AutoMergeConfig(enabled=True, file_patterns=[])
        merger = AutoMerger(config)

        files = [
            FileReview(
                file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]
            ),
            FileReview(
                file_path="src/utils.py", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[]
            ),
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
        config = AutoMergeConfig(enabled=True, file_patterns=["src/*.py"])
        merger = AutoMerger(config)

        files = [
            FileReview(
                file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]
            ),
            FileReview(
                file_path="tests/test.py", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[]
            ),
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
            FileReview(
                file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]
            ),
            FileReview(file_path="app.js", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[]),
            FileReview(
                file_path="readme.md", risk_level=RiskLevel.LOW, changes="+1, -0", issues=[]
            ),
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )

        filtered = merger.filter_by_patterns(review_result)

        assert len(filtered.files_reviewed) == 2


class TestMerge:
    """Test merge method."""

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

        # When not enabled, should return early without trying to access GitHub
        result = asyncio.run(
            merger.merge(
                review_result,
                pr_number=1,
                repo_owner="test",
                repo_name="repo",
            )
        )

        assert result.success is False
        assert "not enabled" in result.message

    def test_dry_run_with_mocked_github(self):
        """Test dry run mode with mocked GitHub client."""
        import asyncio
        from codereview.core.github_client import GitHubClient, PullRequest, MergeState

        config = AutoMergeConfig(enabled=True)
        # Create a mock GitHub client
        mock_client = MagicMock(spec=GitHubClient)
        mock_pr = PullRequest(
            number=123,
            title="Test PR",
            state=MergeState.OPEN,
            head_sha="abc123",
            base_sha="def456",
            base_branch="main",
            head_branch="feature",
            additions=10,
            deletions=5,
            changed_files=1,
            author="testuser",
            url="https://github.com/test/repo/pull/123",
        )
        mock_client.get_pull_request = AsyncMock(return_value=mock_pr)
        mock_client.get_pr_approvals = AsyncMock(return_value=[])
        mock_client.get_check_runs = AsyncMock(return_value=[])

        merger = AutoMerger(config, github_client=mock_client)

        files = [
            FileReview(
                file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]
            )
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )

        result = asyncio.run(
            merger.merge(
                review_result,
                pr_number=123,
                approval_count=1,
                dry_run=True,
            )
        )

        assert result.success is True
        assert result.dry_run is True
        assert "DRY RUN" in result.message

    def test_conditions_not_met(self):
        """Test when merge conditions are not met."""
        import asyncio
        from codereview.core.github_client import GitHubClient, PullRequest, MergeState

        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(min_confidence=90.0),
        )
        mock_client = MagicMock(spec=GitHubClient)
        mock_pr = PullRequest(
            number=123,
            title="Test PR",
            state=MergeState.OPEN,
            head_sha="abc123",
            base_sha="def456",
            base_branch="main",
            head_branch="feature",
            additions=10,
            deletions=5,
            changed_files=1,
            author="testuser",
            url="https://github.com/test/repo/pull/123",
        )
        mock_client.get_pull_request = AsyncMock(return_value=mock_pr)
        mock_client.get_pr_approvals = AsyncMock(return_value=[])
        mock_client.get_check_runs = AsyncMock(return_value=[])

        merger = AutoMerger(config, github_client=mock_client)

        # Confidence below threshold
        files = [
            FileReview(
                file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]
            )
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=80.0,  # Below 90% threshold
            files_reviewed=files,
            summary="Test",
        )

        result = asyncio.run(
            merger.merge(
                review_result,
                pr_number=123,
                approval_count=1,
                dry_run=False,
            )
        )

        assert result.success is False
        assert "Confidence" in result.message


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


class TestShouldMerge:
    """Test should_merge convenience method."""

    def test_should_merge_when_enabled_and_conditions_met(self):
        """Test should_merge when conditions are met."""
        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(
                min_confidence=90.0,
                require_approval=True,
            ),
        )
        merger = AutoMerger(config)

        files = [
            FileReview(
                file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]
            )
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=files,
            summary="Test",
        )

        can_merge, reason = merger.should_merge(review_result, approval_count=1)

        assert can_merge is True
        assert "met" in reason.lower()

    def test_should_merge_when_disabled(self):
        """Test should_merge when disabled."""
        config = AutoMergeConfig(enabled=False)
        merger = AutoMerger(config)

        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=[],
            summary="Test",
        )

        can_merge, reason = merger.should_merge(review_result)

        assert can_merge is False
        assert "not enabled" in reason


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


class TestMergeMethodSelection:
    """Tests for merge method selection."""

    def test_merge_method_squash(self):
        """Test squash merge method selection."""
        config = AutoMergeConfig(
            enabled=True,
            merge_method=MergeMethod.SQUASH,
        )
        merger = AutoMerger(config)

        assert merger.config.merge_method == MergeMethod.SQUASH

    def test_merge_method_merge(self):
        """Test merge commit method selection."""
        config = AutoMergeConfig(
            enabled=True,
            merge_method=MergeMethod.MERGE,
        )
        merger = AutoMerger(config)

        assert merger.config.merge_method == MergeMethod.MERGE

    def test_merge_method_rebase(self):
        """Test rebase merge method selection."""
        config = AutoMergeConfig(
            enabled=True,
            merge_method=MergeMethod.REBASE,
        )
        merger = AutoMerger(config)

        assert merger.config.merge_method == MergeMethod.REBASE

    def test_merge_uses_configured_method(self):
        """Test that merge uses the configured method."""
        import asyncio
        from codereview.core.github_client import GitHubClient, PullRequest, MergeState

        config = AutoMergeConfig(
            enabled=True,
            merge_method=MergeMethod.REBASE,
            conditions=AutoMergeConditions(
                min_confidence=0.0,
                require_approval=False,
            ),
        )
        mock_client = MagicMock(spec=GitHubClient)
        mock_pr = PullRequest(
            number=123,
            title="Test PR",
            state=MergeState.OPEN,
            head_sha="abc123",
            base_sha="def456",
            base_branch="main",
            head_branch="feature",
            additions=10,
            deletions=5,
            changed_files=1,
            author="testuser",
            url="https://github.com/test/repo/pull/123",
        )
        mock_client.get_pull_request = AsyncMock(return_value=mock_pr)
        mock_client.get_pr_approvals = AsyncMock(return_value=[])
        mock_client.get_check_runs = AsyncMock(return_value=[])

        merger = AutoMerger(config, github_client=mock_client)

        files = [
            FileReview(
                file_path="src/main.py", risk_level=RiskLevel.LOW, changes="+10, -5", issues=[]
            )
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=100.0,
            files_reviewed=files,
            summary="Test",
        )

        result = asyncio.run(
            merger.merge(
                review_result,
                pr_number=123,
                merge_method="rebase",
                dry_run=True,
            )
        )

        assert result.success is True
        assert result.merge_method == "rebase"


class TestDryRunMode:
    """Tests for dry-run mode."""

    def test_dry_run_returns_without_merging(self):
        """Test that dry_run mode doesn't actually merge."""
        import asyncio
        from codereview.core.github_client import GitHubClient, PullRequest, MergeState

        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(require_approval=False),
        )
        mock_client = MagicMock(spec=GitHubClient)
        mock_pr = PullRequest(
            number=456,
            title="Dry run test",
            state=MergeState.OPEN,
            head_sha="abc",
            base_sha="def",
            base_branch="main",
            head_branch="feature",
            additions=5,
            deletions=2,
            changed_files=1,
            author="testuser",
            url="https://github.com/test/repo/pull/456",
        )
        mock_client.get_pull_request = AsyncMock(return_value=mock_pr)
        mock_client.get_pr_approvals = AsyncMock(return_value=[])
        mock_client.get_check_runs = AsyncMock(return_value=[])

        merger = AutoMerger(config, github_client=mock_client)

        files = [
            FileReview(file_path="test.py", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[])
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=100.0,
            files_reviewed=files,
            summary="Test",
        )

        result = asyncio.run(
            merger.merge(
                review_result,
                pr_number=456,
                dry_run=True,
            )
        )

        assert result.dry_run is True
        assert result.merged is False
        assert "DRY RUN" in result.message
        # Ensure merge was never called
        mock_client.merge_pr.assert_not_called()

    def test_dry_run_with_conditions_not_met(self):
        """Test dry run when conditions are not met."""
        import asyncio
        from codereview.core.github_client import GitHubClient, PullRequest, MergeState

        config = AutoMergeConfig(
            enabled=True,
            conditions=AutoMergeConditions(min_confidence=90.0),
        )
        mock_client = MagicMock(spec=GitHubClient)
        mock_pr = PullRequest(
            number=789,
            title="Low confidence",
            state=MergeState.OPEN,
            head_sha="abc",
            base_sha="def",
            base_branch="main",
            head_branch="feature",
            additions=5,
            deletions=2,
            changed_files=1,
            author="testuser",
            url="https://github.com/test/repo/pull/789",
        )
        mock_client.get_pull_request = AsyncMock(return_value=mock_pr)
        mock_client.get_pr_approvals = AsyncMock(return_value=[])
        mock_client.get_check_runs = AsyncMock(return_value=[])

        merger = AutoMerger(config, github_client=mock_client)

        files = [
            FileReview(file_path="test.py", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[])
        ]
        review_result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=50.0,  # Below threshold
            files_reviewed=files,
            summary="Test",
        )

        result = asyncio.run(
            merger.merge(
                review_result,
                pr_number=789,
                dry_run=True,
            )
        )

        assert result.success is False
        assert "Confidence" in result.message
