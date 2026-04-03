"""Auto Merge PR functionality for CodeReview Agent.

This module provides automatic merging of pull requests based on
code review results and configurable conditions.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import TYPE_CHECKING, Any, Optional

from codereview.models import (
    AutoMergeConditions,
    AutoMergeConfig,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)

if TYPE_CHECKING:
    from codereview.core.github_client import GitHubClient

logger = logging.getLogger(__name__)


class MergeResult:
    """Result of an auto merge operation."""

    def __init__(
        self,
        success: bool,
        message: str,
        dry_run: bool = False,
        pr_number: Optional[int] = None,
        merged: bool = False,
        merge_method: Optional[str] = None,
    ):
        """Initialize merge result.

        Args:
            success: Whether merge operation succeeded
            message: Result message
            dry_run: Whether this was a dry run
            pr_number: PR number that was merged
            merged: Whether the PR was actually merged
            merge_method: The merge method used
        """
        self.success = success
        self.message = message
        self.dry_run = dry_run
        self.pr_number = pr_number
        self.merged = merged
        self.merge_method = merge_method

    def __repr__(self) -> str:
        return (
            f"MergeResult(success={self.success}, "
            f"message='{self.message}', "
            f"dry_run={self.dry_run}, "
            f"merged={self.merged})"
        )


class AutoMerger:
    """Manages automatic merging of pull requests based on review results.

    This class orchestrates the merge decision by:
    1. Checking merge conditions (confidence, severity, approvals)
    2. Optionally filtering by file patterns
    3. Performing the actual merge via GitHub API
    """

    def __init__(
        self,
        config: AutoMergeConfig,
        github_client: Optional[GitHubClient] = None,
        conditions_override: Optional[AutoMergeConditions] = None,
    ):
        """Initialize auto merger.

        Args:
            config: Auto merge configuration
            github_client: Optional GitHub client for performing merges
            conditions_override: Optional override for merge conditions
        """
        self.config = config
        self.github_client = github_client
        # Allow overriding conditions at runtime
        self._conditions = conditions_override or config.conditions
        self._severity_order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
        }

    @property
    def is_enabled(self) -> bool:
        """Check if auto merge is enabled."""
        return self.config.enabled

    @property
    def conditions(self) -> AutoMergeConditions:
        """Get current merge conditions."""
        return self._conditions

    def update_conditions(self, conditions: AutoMergeConditions) -> None:
        """Update merge conditions at runtime.

        Args:
            conditions: New conditions to use
        """
        self._conditions = conditions

    def check_merge_conditions(
        self,
        review_result: ReviewResult,
        approval_count: int = 0,
        check_run_status: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[bool, str]:
        """Check if review results meet merge conditions.

        Args:
            review_result: The code review result
            approval_count: Number of approvals on the PR
            check_run_status: Optional status of CI check runs

        Returns:
            Tuple of (can_merge: bool, reason: str)
        """
        if not self.is_enabled:
            return False, "Auto merge is not enabled"

        conditions = self._conditions

        # Check confidence threshold
        if review_result.confidence < conditions.min_confidence:
            return False, (
                f"Confidence {review_result.confidence:.0f}% is below "
                f"threshold {conditions.min_confidence:.0f}%"
            )

        # Check risk level - find the highest severity file
        max_severity_level = self._severity_order.get(conditions.max_severity, 0)
        highest_file_severity = RiskLevel.LOW

        for file_review in review_result.files_reviewed:
            file_severity_level = self._severity_order.get(file_review.risk_level, 0)
            if file_severity_level > self._severity_order.get(highest_file_severity, 0):
                highest_file_severity = file_review.risk_level

            if file_severity_level > max_severity_level:
                return False, (
                    f"File {file_review.file_path} has "
                    f"{file_review.risk_level.value} risk, "
                    f"exceeds max {conditions.max_severity.value}"
                )

        # Check approval requirement
        if conditions.require_approval and approval_count < 1:
            return False, (
                f"PR requires at least 1 approval (got {approval_count}), "
                f"highest risk: {highest_file_severity.value}"
            )

        # Check CI check runs if provided
        if check_run_status:
            failed_checks = [
                check
                for check in check_run_status
                if check.get("conclusion") in ("failure", "timed_out", "cancelled")
            ]
            if failed_checks:
                failed_names = [c.get("name", "unknown") for c in failed_checks]
                return False, f"CI checks failed: {', '.join(failed_names)}"

        # Check conclusion
        if review_result.conclusion != ReviewConclusion.CAN_SUBMIT:
            # Special case: if confidence is very high and only low-risk issues
            if review_result.confidence >= 95 and highest_file_severity == RiskLevel.LOW:
                logger.info("High confidence + low risk only, proceeding despite needs_review")
            else:
                return False, (
                    f"Review conclusion is {review_result.conclusion.value}, expected can_submit"
                )

        return True, "All merge conditions met"

    def filter_by_patterns(self, review_result: ReviewResult) -> ReviewResult:
        """Filter review results by configured file patterns.

        Only files matching the patterns will be considered for merge.
        If no patterns are configured, all files are included.

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

        if not filtered_files:
            logger.warning("No files matched auto-merge file patterns")

        # Create new review result with filtered files
        return ReviewResult(
            conclusion=review_result.conclusion,
            confidence=review_result.confidence,
            files_reviewed=filtered_files,
            summary=review_result.summary,
            cache_info=review_result.cache_info,
        )

    def should_merge(
        self,
        review_result: ReviewResult,
        approval_count: int = 0,
        check_run_status: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[bool, str]:
        """Determine if a PR should be merged.

        This is a convenience method that combines pattern filtering
        and condition checking.

        Args:
            review_result: The code review result
            approval_count: Number of approvals on the PR
            check_run_status: Optional status of CI check runs

        Returns:
            Tuple of (should_merge: bool, reason: str)
        """
        if not self.is_enabled:
            return False, "Auto merge is not enabled"

        # Filter by patterns first
        filtered_result = self.filter_by_patterns(review_result)

        # If no files remain after filtering, don't merge
        if not filtered_result.files_reviewed:
            return False, "No files matched auto-merge file patterns"

        # Check conditions on filtered result
        return self.check_merge_conditions(
            filtered_result,
            approval_count,
            check_run_status,
        )

    async def merge(
        self,
        review_result: ReviewResult,
        pr_number: int,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        github_token: Optional[str] = None,
        approval_count: int = 0,
        merge_method: str = "squash",
        dry_run: bool = False,
        force: bool = False,
    ) -> MergeResult:
        """Attempt to automatically merge a PR.

        This is the main entry point for auto-merging. It:
        1. Checks if auto-merge is enabled
        2. Gets PR info and approvals from GitHub
        3. Checks merge conditions (unless force=True)
        4. Performs the merge if conditions are met (or if force=True)

        Args:
            review_result: The code review result
            pr_number: PR number
            repo_owner: Repository owner (auto-detected if not provided)
            repo_name: Repository name (auto-detected if not provided)
            github_token: GitHub token (defaults to GITHUB_TOKEN env)
            approval_count: Number of approvals on the PR
            merge_method: Merge method (squash, merge, or rebase)
            dry_run: If True, only simulate the merge without actually merging
            force: If True, skip all condition checks and merge directly

        Returns:
            MergeResult indicating success/failure and details
        """
        from codereview.core.github_client import (
            MergeMethod,
            create_github_client,
        )

        # Check if auto-merge is enabled FIRST
        if not self.is_enabled:
            return MergeResult(
                success=False,
                message="Auto merge is not enabled",
                pr_number=pr_number,
            )

        # Create GitHub client if not provided
        if self.github_client is None:
            try:
                self.github_client = create_github_client(
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    github_token=github_token,
                )
            except ValueError as e:
                return MergeResult(
                    success=False,
                    message=f"Failed to create GitHub client: {e}",
                    pr_number=pr_number,
                )

        # Get PR info for context
        try:
            pr = await self.github_client.get_pull_request(pr_number)
        except Exception as e:
            return MergeResult(
                success=False,
                message=f"Failed to get PR info: {e}",
                pr_number=pr_number,
            )

        # Get CI check runs
        check_runs = []
        try:
            check_runs = await self.github_client.get_check_runs(pr_number, pr.head_sha)
        except Exception as e:
            logger.warning(f"Failed to get check runs: {e}")

        # Filter by file patterns if configured
        filtered_result = self.filter_by_patterns(review_result)

        if not filtered_result.files_reviewed:
            return MergeResult(
                success=False,
                message="No files matched auto-merge file patterns",
                pr_number=pr_number,
            )

        # Check merge conditions (skip if force=True)
        if not force:
            can_merge, reason = self.check_merge_conditions(
                filtered_result,
                approval_count,
                check_runs,
            )

            if not can_merge:
                logger.info(f"PR #{pr_number} does not meet merge conditions: {reason}")
                return MergeResult(
                    success=False,
                    message=reason,
                    pr_number=pr_number,
                )
        else:
            logger.warning(f"PR #{pr_number}: Force merge enabled, skipping condition checks")

        # Dry run mode
        if dry_run:
            logger.info(f"[DRY RUN] Would merge PR #{pr_number} in {pr.url}")
            return MergeResult(
                success=True,
                message=f"[DRY RUN] All conditions met, would merge PR #{pr_number}",
                dry_run=True,
                pr_number=pr_number,
                merged=False,
                merge_method=merge_method,
            )

        # Perform actual merge
        try:
            # Map string to MergeMethod enum
            method_map = {
                "squash": MergeMethod.SQUASH,
                "merge": MergeMethod.MERGE,
                "rebase": MergeMethod.REBASE,
            }
            merge_method_enum = method_map.get(merge_method, MergeMethod.SQUASH)

            # Build commit message from review
            commit_title = f"Auto-merge PR #{pr_number}: {pr.title}"
            commit_message = self._build_merge_commit_message(review_result, filtered_result)

            await self.github_client.merge_pr(
                pr_number=pr_number,
                merge_method=merge_method_enum,
                commit_title=commit_title,
                commit_message=commit_message,
            )

            logger.info(f"Successfully merged PR #{pr_number}")
            return MergeResult(
                success=True,
                message=f"Successfully merged PR #{pr_number}",
                pr_number=pr_number,
                merged=True,
                merge_method=merge_method,
            )

        except Exception as e:
            logger.error(f"Failed to merge PR #{pr_number}: {e}")
            return MergeResult(
                success=False,
                message=f"Merge failed: {str(e)}",
                pr_number=pr_number,
            )

    def _build_merge_commit_message(
        self,
        original_result: ReviewResult,
        filtered_result: ReviewResult,
    ) -> str:
        """Build a commit message for the merge.

        Args:
            original_result: The original review result
            filtered_result: The filtered review result (if patterns were applied)

        Returns:
            Commit message string
        """
        lines = [
            "Auto-merged by CodeReview Agent",
            "",
            f"Confidence: {original_result.confidence:.0f}%",
            f"Files reviewed: {len(original_result.files_reviewed)}",
        ]

        if original_result.files_reviewed != filtered_result.files_reviewed:
            lines.append(
                f"Files for auto-merge: {len(filtered_result.files_reviewed)} "
                f"(filtered by patterns)"
            )

        # Count issues by severity
        high = sum(
            1
            for f in filtered_result.files_reviewed
            for i in f.issues
            if i.risk_level == RiskLevel.HIGH
        )
        medium = sum(
            1
            for f in filtered_result.files_reviewed
            for i in f.issues
            if i.risk_level == RiskLevel.MEDIUM
        )
        low = sum(
            1
            for f in filtered_result.files_reviewed
            for i in f.issues
            if i.risk_level == RiskLevel.LOW
        )

        if high or medium or low:
            lines.append("")
            lines.append("Issues found:")
            if high:
                lines.append(f"  - {high} high risk")
            if medium:
                lines.append(f"  - {medium} medium risk")
            if low:
                lines.append(f"  - {low} low risk")

        return "\n".join(lines)

    async def get_merge_preview(
        self,
        review_result: ReviewResult,
        pr_number: int,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        github_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get a preview of merge eligibility without actually merging.

        This is useful for showing users what would happen before
        they enable auto-merge or for debugging.

        Args:
            review_result: The code review result
            pr_number: PR number
            repo_owner: Repository owner
            repo_name: Repository name
            github_token: GitHub token

        Returns:
            Dictionary with merge eligibility details
        """
        from codereview.core.github_client import create_github_client

        # Create client if needed
        if self.github_client is None:
            try:
                self.github_client = create_github_client(
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    github_token=github_token,
                )
            except ValueError as e:
                return {
                    "enabled": self.is_enabled,
                    "can_merge": False,
                    "reason": f"GitHub client error: {e}",
                    "error": True,
                }

        # Get PR info
        pr_info = {}
        try:
            pr = await self.github_client.get_pull_request(pr_number)
            pr_info = {
                "title": pr.title,
                "author": pr.author,
                "state": pr.state.value,
                "url": pr.url,
            }
        except Exception as e:
            pr_info = {"error": str(e)}

        # Get approvals
        approval_count = 0
        try:
            approvals = await self.github_client.get_pr_approvals(pr_number)
            approval_count = len(approvals)
        except Exception as e:
            logger.warning(f"Failed to get approvals: {e}")

        # Get check runs
        check_runs = []
        try:
            check_runs = await self.github_client.get_check_runs(pr_number)
        except Exception:
            pass

        # Filter by patterns
        filtered_result = self.filter_by_patterns(review_result)

        # Check conditions
        can_merge, reason = self.check_merge_conditions(
            filtered_result,
            approval_count,
            check_runs,
        )

        # Build file summary
        file_summary = []
        for f in filtered_result.files_reviewed:
            file_summary.append(
                {
                    "file_path": f.file_path,
                    "risk_level": f.risk_level.value,
                    "issue_count": len(f.issues),
                    "issues": [
                        {
                            "line": i.line_number,
                            "level": i.risk_level.value,
                            "description": i.description[:80],  # Truncate for preview
                        }
                        for i in f.issues
                    ],
                }
            )

        return {
            "enabled": self.is_enabled,
            "can_merge": can_merge,
            "reason": reason,
            "pr": pr_info,
            "review": {
                "confidence": review_result.confidence,
                "confidence_threshold": self._conditions.min_confidence,
                "conclusion": review_result.conclusion.value,
                "total_files": len(review_result.files_reviewed),
                "filtered_files": len(filtered_result.files_reviewed),
            },
            "merge_requirements": {
                "min_confidence": self._conditions.min_confidence,
                "max_severity": self._conditions.max_severity.value,
                "require_approval": self._conditions.require_approval,
            },
            "current_status": {
                "approval_count": approval_count,
                "check_runs_total": len(check_runs),
                "check_runs_passed": sum(
                    1 for c in check_runs if c.get("conclusion") in ("success", "completed")
                ),
                "check_runs_failed": sum(
                    1
                    for c in check_runs
                    if c.get("conclusion") in ("failure", "timed_out", "cancelled")
                ),
            },
            "file_patterns": self.config.file_patterns,
            "files": file_summary,
        }


def create_auto_merger(
    config: AutoMergeConfig,
    github_client: Optional[GitHubClient] = None,
) -> AutoMerger:
    """Create an AutoMerger instance.

    Args:
        config: Auto merge configuration
        github_client: Optional GitHub client

    Returns:
        AutoMerger instance
    """
    return AutoMerger(config=config, github_client=github_client)
