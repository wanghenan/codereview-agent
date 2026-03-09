"""Auto Merge PR functionality for CodeReview Agent.

This module provides automatic merging of pull requests based on
code review results and configurable conditions.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any, Optional

from codereview.models import (
    AutoMergeConfig,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)

logger = logging.getLogger(__name__)


class MergeResult:
    """Result of an auto merge operation."""

    def __init__(
        self,
        success: bool,
        message: str,
        dry_run: bool = False,
        pr_number: Optional[int] = None,
    ):
        """Initialize merge result.

        Args:
            success: Whether merge was successful
            message: Result message
            dry_run: Whether this was a dry run
            pr_number: PR number that was merged
        """
        self.success = success
        self.message = message
        self.dry_run = dry_run
        self.pr_number = pr_number

    def __repr__(self) -> str:
        return f"MergeResult(success={self.success}, message='{self.message}', dry_run={self.dry_run})"


class AutoMerger:
    """Manages automatic merging of pull requests based on review results."""

    def __init__(self, config: AutoMergeConfig, github_client: Optional[Any] = None):
        """Initialize auto merger.

        Args:
            config: Auto merge configuration
            github_client: Optional GitHub client for performing merges
        """
        self.config = config
        self.github_client = github_client
        self._severity_order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
        }

    @property
    def is_enabled(self) -> bool:
        """Check if auto merge is enabled."""
        return self.config.enabled

    def check_merge_conditions(self, review_result: ReviewResult, approval_count: int = 0) -> tuple[bool, str]:
        """Check if review results meet merge conditions.

        Args:
            review_result: The code review result
            approval_count: Number of approvals on the PR

        Returns:
            Tuple of (can_merge: bool, reason: str)
        """
        if not self.is_enabled:
            return False, "Auto merge is not enabled"

        conditions = self.config.conditions

        # Check confidence threshold
        if review_result.confidence < conditions.min_confidence:
            return False, f"Confidence {review_result.confidence}% is below threshold {conditions.min_confidence}%"

        # Check risk level
        max_severity_level = self._severity_order.get(conditions.max_severity, 0)
        
        # Check each file's risk level
        for file_review in review_result.files_reviewed:
            file_severity_level = self._severity_order.get(file_review.risk_level, 0)
            if file_severity_level > max_severity_level:
                return False, f"File {file_review.file_path} has {file_review.risk_level.value} risk, exceeds max {conditions.max_severity.value}"

        # Check approval requirement
        if conditions.require_approval and approval_count < 1:
            return False, f"PR requires at least 1 approval, currently has {approval_count}"

        # Check conclusion
        if review_result.conclusion != ReviewConclusion.CAN_SUBMIT:
            return False, f"Review conclusion is {review_result.conclusion.value}, expected can_submit"

        return True, "All merge conditions met"

    def filter_by_patterns(self, review_result: ReviewResult) -> ReviewResult:
        """Filter review results by configured file patterns.

        Args:
            review_result: The code review result

        Returns:
            Filtered review result with only matching files
        """
        if not self.config.file_patterns:
            # No patterns specified, include all files
            return review_result

        filtered_files = []
        for file_review in review_result.files_reviewed:
            for pattern in self.config.file_patterns:
                if fnmatch.fnmatch(file_review.file_path, pattern):
                    filtered_files.append(file_review)
                    break

        # Create new review result with filtered files
        return ReviewResult(
            conclusion=review_result.conclusion,
            confidence=review_result.confidence,
            files_reviewed=filtered_files,
            summary=review_result.summary,
            cache_info=review_result.cache_info,
        )

    async def auto_merge(
        self,
        review_result: ReviewResult,
        pr_number: int,
        repo_owner: str,
        repo_name: str,
        approval_count: int = 0,
        dry_run: bool = False,
    ) -> MergeResult:
        """Attempt to automatically merge a PR.

        Args:
            review_result: The code review result
            pr_number: PR number
            repo_owner: Repository owner
            repo_name: Repository name
            approval_count: Number of approvals on the PR
            dry_run: If True, only simulate the merge without actually merging

        Returns:
            MergeResult indicating success/failure and details
        """
        # Check if auto merge is enabled
        if not self.is_enabled:
            logger.info(f"Auto merge is disabled, skipping PR #{pr_number}")
            return MergeResult(
                success=False,
                message="Auto merge is not enabled",
                pr_number=pr_number,
            )

        # Filter by file patterns if configured
        if self.config.file_patterns:
            review_result = self.filter_by_patterns(review_result)
            logger.info(f"Filtered review result to {len(review_result.files_reviewed)} files matching patterns")

        # Check merge conditions
        can_merge, reason = self.check_merge_conditions(review_result, approval_count)

        if not can_merge:
            logger.info(f"PR #{pr_number} does not meet merge conditions: {reason}")
            return MergeResult(
                success=False,
                message=reason,
                pr_number=pr_number,
            )

        # Log dry run or perform actual merge
        if dry_run:
            logger.info(f"[DRY RUN] Would merge PR #{pr_number} in {repo_owner}/{repo_name}")
            return MergeResult(
                success=True,
                message=f"[DRY RUN] All conditions met, would merge PR #{pr_number}",
                dry_run=True,
                pr_number=pr_number,
            )

        # Perform actual merge
        if self.github_client is None:
            logger.warning(f"No GitHub client configured, cannot merge PR #{pr_number}")
            return MergeResult(
                success=False,
                message="GitHub client not configured",
                pr_number=pr_number,
            )

        try:
            await self._perform_merge(pr_number, repo_owner, repo_name)
            logger.info(f"Successfully merged PR #{pr_number}")
            return MergeResult(
                success=True,
                message=f"Successfully merged PR #{pr_number}",
                pr_number=pr_number,
            )
        except Exception as e:
            logger.error(f"Failed to merge PR #{pr_number}: {e}")
            return MergeResult(
                success=False,
                message=f"Merge failed: {str(e)}",
                pr_number=pr_number,
            )

    async def _perform_merge(self, pr_number: int, repo_owner: str, repo_name: str) -> None:
        """Perform the actual merge via GitHub API.

        Args:
            pr_number: PR number
            repo_owner: Repository owner
            repo_name: Repository name
        """
        if self.github_client is None:
            raise RuntimeError("GitHub client not configured")

        # This would use the GitHub client to perform the merge
        # Example: await self.github_client.pulls.merge(owner, repo, pr_number)
        logger.info(f"Merging PR #{pr_number} in {repo_owner}/{repo_name}")
        # Placeholder for actual implementation
        raise NotImplementedError("GitHub merge implementation requires Octokit integration")

    def get_merge_preview(self, review_result: ReviewResult, approval_count: int = 0) -> dict[str, Any]:
        """Get a preview of merge eligibility without actually merging.

        Args:
            review_result: The code review result
            approval_count: Number of approvals on the PR

        Returns:
            Dictionary with merge eligibility details
        """
        can_merge, reason = self.check_merge_conditions(review_result, approval_count)

        return {
            "enabled": self.is_enabled,
            "can_merge": can_merge,
            "reason": reason,
            "confidence": review_result.confidence,
            "confidence_threshold": self.config.conditions.min_confidence,
            "max_severity": self.config.conditions.max_severity.value,
            "require_approval": self.config.conditions.require_approval,
            "approval_count": approval_count,
            "files_reviewed": len(review_result.files_reviewed),
            "file_patterns": self.config.file_patterns,
            "filtered_files": [
                {
                    "file_path": f.file_path,
                    "risk_level": f.risk_level.value,
                    "issue_count": len(f.issues),
                }
                for f in review_result.files_reviewed
            ],
        }


def create_auto_merger(config: AutoMergeConfig, github_client: Optional[Any] = None) -> AutoMerger:
    """Create an AutoMerger instance.

    Args:
        config: Auto merge configuration
        github_client: Optional GitHub client

    Returns:
        AutoMerger instance
    """
    return AutoMerger(config=config, github_client=github_client)
