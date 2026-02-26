"""Output generator for review results."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from codereview.models import ReviewResult, OutputConfig


class OutputGenerator:
    """Generate output for review results."""

    def __init__(self, config: OutputConfig):
        """Initialize output generator.

        Args:
            config: Output configuration
        """
        self.config = config

    async def generate(
        self,
        result: ReviewResult,
        pr_number: int | None = None
    ) -> dict[str, Any]:
        """Generate output in configured formats.

        Args:
            result: Review result
            pr_number: Optional PR number

        Returns:
            Dict with output paths and content
        """
        output = {}

        # Generate markdown
        if self.config.report_format in ("markdown", "both"):
            markdown = self._generate_markdown(result, pr_number)
            output["markdown"] = markdown

            if self.config.report_path:
                await self._save_markdown(markdown, pr_number)

        # Generate JSON
        if self.config.report_format in ("json", "both"):
            json_output = self._generate_json(result)
            output["json"] = json_output

            if self.config.report_path:
                await self._save_json(json_output, pr_number)

        # Generate PR comment
        if self.config.pr_comment:
            output["pr_comment"] = self._generate_pr_comment(result)

        return output

    def _generate_markdown(
        self,
        result: ReviewResult,
        pr_number: int | None = None
    ) -> str:
        """Generate markdown report.

        Args:
            result: Review result
            pr_number: Optional PR number

        Returns:
            Markdown content
        """
        lines = [
            "# CodeReview Agent Report",
            "",
            f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if pr_number:
            lines.append(f"**PR**: #{pr_number}")

        # Conclusion
        emoji = "✅" if result.conclusion.value == "can_submit" else "⚠️"
        lines.extend([
            "",
            f"## Conclusion",
            f"",
            f"**{emoji} {result.conclusion.value.replace('_', ' ').title()}** (Confidence: {result.confidence:.0f}%)",
            "",
        ])

        # Files summary table
        lines.extend([
            "## Changed Files",
            "",
            "| File | Risk | Issues |",
            "|------|------|--------|",
        ])

        for file_review in result.files_reviewed:
            risk_emoji = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢"
            }.get(file_review.risk_level.value, "⚪")

            issue_count = len(file_review.issues)
            lines.append(
                f"| {file_review.file_path} | {risk_emoji} {file_review.risk_level.value} | {issue_count} |"
            )

        # Detailed issues
        lines.extend(["", "## Detailed Issues", ""])

        for file_review in result.files_reviewed:
            if not file_review.issues:
                continue

            lines.extend([
                f"### {file_review.file_path}",
                f"- **Risk**: {file_review.risk_level.value}",
                f"- **Changes**: {file_review.changes}",
                "",
            ])

            for issue in file_review.issues:
                risk_marker = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢"
                }.get(issue.risk_level.value, "")

                lines.append(f"- [{risk_marker} {issue.risk_level.value.upper()}]", end="")

                if issue.line_number:
                    lines.append(f" L{issue.line_number}:", end=" ")

                lines.append(f" {issue.description}")

                if issue.suggestion:
                    lines.append(f"  - Suggestion: {issue.suggestion}")

            lines.append("")

        # Summary
        lines.extend([
            "## Summary",
            "",
            result.summary,
            "",
        ])

        # Cache info
        if result.cache_info:
            lines.extend([
                "---",
                "",
                f"*Cache: {'Used' if result.cache_info.used_cache else 'Fresh analysis'}*",
            ])
            if result.cache_info.cache_timestamp:
                lines.append(f"*{result.cache_info.cache_timestamp}*")

        return "\n".join(lines)

    def _generate_json(self, result: ReviewResult) -> str:
        """Generate JSON report.

        Args:
            result: Review result

        Returns:
            JSON string
        """
        return json.dumps(result.model_dump(), indent=2, ensure_ascii=False)

    def _generate_pr_comment(self, result: ReviewResult) -> str:
        """Generate PR comment.

        Args:
            result: Review result

        Returns:
            PR comment content
        """
        emoji = "✅" if result.conclusion.value == "can_submit" else "⚠️"

        lines = [
            "## CodeReview Agent 🤖",
            "",
            f"**Conclusion**: {emoji} **{result.conclusion.value.replace('_', ' ').title()}** (Confidence: {result.confidence:.0f}%)",
            "",
            "### Summary",
            "",
            "| File | Risk | Issues |",
            "|------|------|--------|",
        ]

        for file_review in result.files_reviewed[:10]:  # Limit to 10 files
            risk_emoji = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢"
            }.get(file_review.risk_level.value, "⚪")

            issue_count = len(file_review.issues)
            lines.append(
                f"| `{file_review.file_path}` | {risk_emoji} {file_review.risk_level.value} | {issue_count} |"
            )

        if len(result.files_reviewed) > 10:
            lines.append(f"| ... | ... | ... |")

        lines.extend([
            "",
            f"*Reviewed {len(result.files_reviewed)} files*",
        ])

        return "\n".join(lines)

    async def _save_markdown(self, content: str, pr_number: int | None = None) -> Path:
        """Save markdown report to file.

        Args:
            content: Markdown content
            pr_number: Optional PR number

        Returns:
            Path to saved file
        """
        report_dir = Path(self.config.report_path)
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        if pr_number:
            filename = f"pr-{pr_number}-{timestamp}.md"
        else:
            filename = f"report-{timestamp}.md"

        filepath = report_dir / filename
        filepath.write_text(content, encoding="utf-8")

        return filepath

    async def _save_json(self, content: str, pr_number: int | None = None) -> Path:
        """Save JSON report to file.

        Args:
            content: JSON content
            pr_number: Optional PR number

        Returns:
            Path to saved file
        """
        report_dir = Path(self.config.report_path)
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        if pr_number:
        if pr_number:
            filename = f"pr-{pr_number}-{timestamp}.json"
        else_number}-{timestamp}.:
            filename = f"report-{timestamp}.json"

        filepath = report_dir / filename
        filepath.write_text(content, encoding="utf-8")

        return filepath
