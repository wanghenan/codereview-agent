"""Inline PR review comment construction and machine-readable findings output.

S2 keeps the PR page as the primary surface: only findings that carry a line
anchor become inline comments, and the highest-signal ones are selected first
so a noisy review does not flood the diff. Everything else is folded into the
review summary body. ``findings_payload`` is the same data as plain dicts for
``findings.json``, ready to hand to a coding agent.
"""

from __future__ import annotations

from typing import Any

from codereview.models import FileIssue, ReviewResult, RiskLevel

MAX_INLINE_COMMENTS = 25
MAX_SUMMARY_FINDINGS = 20

_SEVERITY_ORDER = {
    RiskLevel.HIGH: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.LOW: 2,
}


class InlineCommentBuilder:
    """Build inline review comments plus a summary from a :class:`ReviewResult`.

    Findings with ``line_number`` are candidates for inline comments; findings
    without a line anchor are only ever summarised, because GitHub cannot place
    them on the diff.
    """

    def build(self, review_result: ReviewResult) -> dict[str, Any]:
        """Build the review payload.

        Args:
            review_result: Complete review result to render.

        Returns:
            A dict with ``comments`` (``[{"path", "line", "body"}]``) and
            ``summary`` (the review body with folded findings).
        """
        anchored: list[FileIssue] = []
        folded: list[FileIssue] = []

        for file_review in review_result.files_reviewed:
            for issue in file_review.issues:
                if issue.line_number is not None:
                    anchored.append(issue)
                else:
                    folded.append(issue)

        anchored.sort(key=self._sort_key)
        selected = anchored[:MAX_INLINE_COMMENTS]
        folded.extend(anchored[MAX_INLINE_COMMENTS:])
        folded.sort(key=self._sort_key)

        comments = [
            {
                "path": issue.file_path,
                "line": issue.line_number,
                "body": self._render_body(issue),
            }
            for issue in selected
        ]

        return {
            "comments": comments,
            "summary": self._render_summary(review_result.summary, folded),
        }

    def findings_payload(self, review_result: ReviewResult) -> list[dict[str, Any]]:
        """Return every finding as a JSON-serialisable dict for ``findings.json``.

        Args:
            review_result: Complete review result to flatten.

        Returns:
            One ``model_dump`` per issue, in review order (files then issues).
        """
        return [
            issue.model_dump(mode="json")
            for file_review in review_result.files_reviewed
            for issue in file_review.issues
        ]

    def _sort_key(self, issue: FileIssue) -> tuple[int, float, str, int]:
        """Order by severity, then confidence, then path/line for stability."""
        return (
            _SEVERITY_ORDER[issue.risk_level],
            -issue.confidence,
            issue.file_path,
            issue.line_number if issue.line_number is not None else 0,
        )

    def _render_body(self, issue: FileIssue) -> str:
        """Render one finding as the markdown body of an inline comment."""
        lines: list[str] = []
        heading = issue.title.strip() or self._first_line(issue.description)
        if heading:
            lines.extend([f"**{heading}**", ""])

        description = issue.description.strip()
        if description and description != heading:
            lines.extend([description, ""])

        if issue.evidence:
            lines.append("**Evidence**")
            lines.extend(
                f"- {evidence.kind.value}: {evidence.detail}" for evidence in issue.evidence
            )
            lines.append("")

        if issue.suggested_patch:
            lines.extend(["```diff", issue.suggested_patch.rstrip(), "```"])

        return "\n".join(lines).strip()

    def _render_summary(self, base_summary: str, folded: list[FileIssue]) -> str:
        """Append folded findings to the review summary.

        The folded list is capped at :data:`MAX_SUMMARY_FINDINGS` lines; the
        remainder is reported as a single ``+N more`` line so the summary stays
        readable on a large review.
        """
        parts: list[str] = []
        base = base_summary.strip()
        if base:
            parts.append(base)

        if not folded:
            return "\n".join(parts)

        if parts:
            parts.append("")
        parts.append("**Findings not shown inline**")
        for issue in folded[:MAX_SUMMARY_FINDINGS]:
            parts.append(self._summary_line(issue))

        remaining = len(folded) - MAX_SUMMARY_FINDINGS
        if remaining > 0:
            parts.append(f"+{remaining} more")

        return "\n".join(parts)

    def _summary_line(self, issue: FileIssue) -> str:
        """Render one folded finding as a single summary line."""
        location = issue.file_path
        if issue.line_number is not None:
            location = f"{location}:{issue.line_number}"

        label = issue.title.strip() or self._first_line(issue.description)
        severity = issue.risk_level.value.upper()
        if label:
            return f"- [{severity}] {location} — {label}"
        return f"- [{severity}] {location}"

    @staticmethod
    def _first_line(text: str) -> str:
        """Return the first non-empty line of ``text``, trimmed."""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""


__all__ = ["MAX_INLINE_COMMENTS", "MAX_SUMMARY_FINDINGS", "InlineCommentBuilder"]
