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
        """Initialize output generator."""
        self.config = config

    async def generate(self, result: ReviewResult, pr_number: int | None = None) -> dict[str, Any]:
        """Generate output in configured formats."""
        output = {}

        if self.config.report_format in ("markdown", "both"):
            markdown = self._generate_markdown(result, pr_number)
            output["markdown"] = markdown
            if self.config.report_path:
                await self._save_markdown(markdown, pr_number)

        if self.config.report_format in ("json", "both"):
            json_output = self._generate_json(result)
            output["json"] = json_output
            if self.config.report_path:
                await self._save_json(json_output, pr_number)

        if self.config.pr_comment:
            output["pr_comment"] = self._generate_pr_comment(result)

        return output

    def _generate_markdown(self, result: ReviewResult, pr_number: int | None = None) -> str:
        """Generate markdown report."""
        lines = [
            "# CodeReview Agent Report",
            "",
            f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if pr_number:
            lines.append(f"**PR**: #{pr_number}")

        emoji = "✅" if result.conclusion.value == "can_submit" else "⚠️"
        lines.extend(
            [
                "",
                f"## Conclusion",
                f"",
                f"**{emoji} {result.conclusion.value.replace('_', ' ').title()}** (Confidence: {result.confidence:.0f}%)",
                "",
            ]
        )

        lines.extend(
            ["## Changed Files", "", "| File | Risk | Issues |", "|------|------|--------|"]
        )

        for file_review in result.files_reviewed:
            risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                file_review.risk_level.value, "⚪"
            )
            lines.append(
                f"| {file_review.file_path} | {risk_emoji} {file_review.risk_level.value} | {len(file_review.issues)} |"
            )

        lines.extend(["", "## Detailed Issues", ""])

        for file_review in result.files_reviewed:
            if not file_review.issues:
                continue
            lines.extend(
                [f"### {file_review.file_path}", f"- **Risk**: {file_review.risk_level.value}", ""]
            )
            for issue in file_review.issues:
                marker = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(issue.risk_level.value, "")
                lines.append(f"- [{marker} {issue.risk_level.value.upper()}] {issue.description}")

        lines.extend(["", "## Summary", "", result.summary])
        return "\n".join(lines)

    def _generate_json(self, result: ReviewResult) -> str:
        """Generate JSON report."""
        return json.dumps(result.model_dump(), indent=2, ensure_ascii=False)

    def _generate_pr_comment(self, result: ReviewResult) -> str:
        """Generate PR comment."""
        emoji = "✅" if result.conclusion.value == "can_submit" else "⚠️"
        lines = [
            "## CodeReview Agent 🤖",
            "",
            f"**Conclusion**: {emoji} **{result.conclusion.value.replace('_', ' ').title()}** (Confidence: {result.confidence:.0f}%)",
            "",
            "| File | Risk | Issues |",
            "|------|------|--------|",
        ]

        for file_review in result.files_reviewed[:10]:
            risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                file_review.risk_level.value, "⚪"
            )
            lines.append(
                f"| `{file_review.file_path}` | {risk_emoji} {file_review.risk_level.value} | {len(file_review.issues)} |"
            )

        return "\n".join(lines)

    async def _save_markdown(self, content: str, pr_number: int | None = None) -> Path:
        """Save markdown report."""
        report_dir = Path(self.config.report_path)
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"pr-{pr_number}-{timestamp}.md" if pr_number else f"report-{timestamp}.md"
        filepath = report_dir / filename
        filepath.write_text(content, encoding="utf-8")
        return filepath

    async def _save_json(self, content: str, pr_number: int | None = None) -> Path:
        """Save JSON report."""
        report_dir = Path(self.config.report_path)
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"pr-{pr_number}-{timestamp}.json" if pr_number else f"report-{timestamp}.json"
        filepath = report_dir / filename
        filepath.write_text(content, encoding="utf-8")
        return filepath
