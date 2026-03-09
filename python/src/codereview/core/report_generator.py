"""Visual Report Generator for CodeReview Agent.

This module provides enhanced visual reporting capabilities including:
- HTML reports with responsive design and charts
- Trend analysis and visualizations
- Code highlighting
"""

from __future__ import annotations

import base64
import json
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

# Chart rendering
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from codereview.models import (
    FileIssue,
    FileReview,
    ReviewResult,
    RiskLevel,
    ReviewConclusion,
)


# Try to use a better font, fallback gracefully
try:
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
    plt.rcParams['axes.unicode_minus'] = False
except Exception:
    pass


class TrendData:
    """Data container for trend analysis."""

    def __init__(self):
        self.dates: list[str] = []
        self.issue_counts: dict[str, int] = defaultdict(int)
        self.confidence_values: list[float] = []
        self.file_counts: dict[str, int] = defaultdict(int)
        self.risk_counts: dict[str, int] = defaultdict(int)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "dates": self.dates,
            "issue_counts": dict(self.issue_counts),
            "confidence_values": self.confidence_values,
            "file_counts": dict(self.file_counts),
            "risk_counts": dict(self.risk_counts),
        }


class ReportGenerator:
    """Generate visual reports for code review results."""

    def __init__(self, project_name: str = "Code Review"):
        """Initialize report generator.

        Args:
            project_name: Name of the project being reviewed
        """
        self.project_name = project_name
        self._chart_buffer: Optional[BytesIO] = None

    def generate_html_report(
        self,
        result: ReviewResult,
        pr_number: Optional[int] = None,
        trend_data: Optional[TrendData] = None,
    ) -> str:
        """Generate a comprehensive HTML report.

        Args:
            result: The review result to visualize
            pr_number: Optional PR number
            trend_data: Optional historical trend data

        Returns:
            HTML string of the report
        """
        # Calculate statistics
        stats = self._calculate_stats(result)

        # Generate charts as base64
        pie_chart = self._generate_pie_chart_base64(result)
        bar_chart = self._generate_bar_chart_base64(result)
        confidence_chart = self._generate_confidence_gauge_base64(result.confidence)

        # Generate trend chart if data provided
        trend_chart = ""
        if trend_data and trend_data.dates:
            trend_chart = self._generate_trend_chart_base64(trend_data)

        # Build HTML
        html = self._build_html(
            result=result,
            stats=stats,
            pr_number=pr_number,
            pie_chart=pie_chart,
            bar_chart=bar_chart,
            confidence_chart=confidence_chart,
            trend_chart=trend_chart,
        )
        return html

    def generate_markdown_report(
        self,
        result: ReviewResult,
        pr_number: Optional[int] = None,
        trend_data: Optional[TrendData] = None,
    ) -> str:
        """Generate an enhanced Markdown report.

        Args:
            result: The review result to document
            pr_number: Optional PR number
            trend_data: Optional historical trend data

        Returns:
            Markdown string of the report
        """
        stats = self._calculate_stats(result)

        lines = [
            f"# 📊 Code Review Report - {self.project_name}",
            "",
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if pr_number:
            lines.append(f"**PR**: #{pr_number}")

        # Summary section
        lines.extend([
            "",
            "## 📋 Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Conclusion | {self._get_conclusion_emoji(result.conclusion)} {result.conclusion.value.replace('_', ' ').title()} |",
            f"| Confidence | {result.confidence:.1f}% |",
            f"| Files Reviewed | {len(result.files_reviewed)} |",
            f"| Total Issues | {stats['total_issues']} |",
            f"| 🔴 High Risk | {stats['high_risk']} |",
            f"| 🟡 Medium Risk | {stats['medium_risk']} |",
            f"| 🟢 Low Risk | {stats['low_risk']} |",
        ])

        # Issue breakdown by type
        issue_types = self._categorize_issues(result)
        if issue_types:
            lines.extend(["", "## 🔍 Issues by Category", ""])
            for category, count in sorted(issue_types.items(), key=lambda x: -x[1]):
                lines.append(f"- **{category}**: {count}")

        # Files section
        lines.extend(["", "## 📁 Files Reviewed", ""])
        lines.append("| File | Risk | Issues | Changes |")
        lines.append("|------|------|--------|---------|")

        for file_review in result.files_reviewed:
            risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                file_review.risk_level.value, "⚪"
            )
            lines.append(
                f"| `{file_review.file_path}` | {risk_emoji} {file_review.risk_level.value} | "
                f"{len(file_review.issues)} | {file_review.changes} |"
            )

        # Detailed issues
        lines.extend(["", "## ⚠️ Detailed Issues", ""])

        for file_review in result.files_reviewed:
            if not file_review.issues:
                continue

            lines.append(f"### 📄 {file_review.file_path}")
            lines.append(f"**Risk Level**: {file_review.risk_level.value.upper()}")
            lines.append("")

            for issue in file_review.issues:
                marker = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    issue.risk_level.value, ""
                )
                lines.append(f"- [{marker} **{issue.risk_level.value.upper()}**] {issue.description}")

                if issue.line_number:
                    lines[-1] += f" (Line {issue.line_number})"

                if issue.suggestion:
                    lines.append(f"  - 💡 Suggestion: {issue.suggestion}")
                lines.append("")

        # Summary text
        lines.extend(["", "## 📝 Summary", "", result.summary])

        # Trend data if available
        if trend_data and trend_data.dates:
            lines.extend(["", "## 📈 Trend Analysis", ""])
            lines.append(f"**Historical Data Points**: {len(trend_data.dates)}")
            lines.append("")
            for i, date in enumerate(trend_data.dates[-5:]):  # Last 5 dates
                issues = list(trend_data.issue_counts.values())[i] if i < len(trend_data.issue_counts) else 0
                lines.append(f"- **{date}**: {issues} issues")

        return "\n".join(lines)

    def generate_trend_chart(
        self,
        data: list[ReviewResult] | list[dict],
        period: str = "week",
    ) -> TrendData:
        """Generate trend data from a list of review results.

        Args:
            data: List of historical review results (ReviewResult or dict)
            period: Aggregation period ('day', 'week', 'month')

        Returns:
            TrendData object with aggregated statistics
        """
        trend = TrendData()

        # Group by time period
        period_data = defaultdict(lambda: {"issues": 0, "confidence": [], "files": 0})

        # Helper function to extract reviewed_at safely
        def get_reviewed_at(item):
            if isinstance(item, dict):
                return item.get('reviewed_at', datetime.now().isoformat())
            return getattr(item, 'reviewed_at', datetime.now())

        # Helper function to get files_reviewed
        def get_files_reviewed(item):
            if isinstance(item, dict):
                return item.get('files_reviewed', [])
            return item.files_reviewed

        # Helper function to get confidence
        def get_confidence(item):
            if isinstance(item, dict):
                return item.get('confidence', 0)
            return item.confidence

        sorted_data = sorted(data, key=get_reviewed_at)

        for result in sorted_data:
            # Use a placeholder time if reviewed_at not available
            review_date = get_reviewed_at(result)
            if isinstance(review_date, str):
                try:
                    review_date = datetime.fromisoformat(review_date.replace('Z', '+00:00'))
                except ValueError:
                    review_date = datetime.now()

            if period == "day":
                key = review_date.strftime("%Y-%m-%d")
            elif period == "week":
                key = review_date.strftime("%Y-W%W")
            else:  # month
                key = review_date.strftime("%Y-%m")

            files_reviewed = get_files_reviewed(result)
            period_data[key]["issues"] += sum(len(fr.get('issues', []) if isinstance(fr, dict) else fr.issues) for fr in files_reviewed)
            period_data[key]["confidence"].append(get_confidence(result))
            period_data[key]["files"] += len(files_reviewed)

            # Track risk levels
            for fr in files_reviewed:
                if isinstance(fr, dict):
                    risk_level = fr.get('risk_level', RiskLevel.LOW)
                    file_path = fr.get('file_path', '')
                else:
                    risk_level = fr.risk_level
                    file_path = fr.file_path

                if isinstance(risk_level, str):
                    risk_level = RiskLevel(risk_level)
                trend.risk_counts[risk_level.value] += 1
                trend.file_counts[file_path] += 1

        # Build trend data
        for key in sorted(period_data.keys()):
            trend.dates.append(key)
            trend.issue_counts[key] = period_data[key]["issues"]
            confidences = period_data[key]["confidence"]
            trend.confidence_values.append(
                sum(confidences) / len(confidences) if confidences else 0
            )

        return trend

    def save_html_report(
        self,
        result: ReviewResult,
        output_path: str | Path,
        pr_number: Optional[int] = None,
        trend_data: Optional[TrendData] = None,
    ) -> Path:
        """Save HTML report to file.

        Args:
            result: The review result
            output_path: Path to save the HTML file
            pr_number: Optional PR number
            trend_data: Optional trend data

        Returns:
            Path to the saved file
        """
        html = self.generate_html_report(result, pr_number, trend_data)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return path

    def save_markdown_report(
        self,
        result: ReviewResult,
        output_path: str | Path,
        pr_number: Optional[int] = None,
        trend_data: Optional[TrendData] = None,
    ) -> Path:
        """Save Markdown report to file.

        Args:
            result: The review result
            output_path: Path to save the Markdown file
            pr_number: Optional PR number
            trend_data: Optional trend data

        Returns:
            Path to the saved file
        """
        md = self.generate_markdown_report(result, pr_number, trend_data)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        return path

    def _calculate_stats(self, result: ReviewResult) -> dict[str, Any]:
        """Calculate statistics from review result."""
        total_issues = sum(len(fr.issues) for fr in result.files_reviewed)

        # Count issues by risk level (more intuitive than counting files)
        high_risk = sum(
            1 for fr in result.files_reviewed
            for issue in fr.issues if issue.risk_level == RiskLevel.HIGH
        )
        medium_risk = sum(
            1 for fr in result.files_reviewed
            for issue in fr.issues if issue.risk_level == RiskLevel.MEDIUM
        )
        low_risk = sum(
            1 for fr in result.files_reviewed
            for issue in fr.issues if issue.risk_level == RiskLevel.LOW
        )

        return {
            "total_issues": total_issues,
            "high_risk": high_risk,
            "medium_risk": medium_risk,
            "low_risk": low_risk,
            "total_files": len(result.files_reviewed),
        }

    def _categorize_issues(self, result: ReviewResult) -> dict[str, int]:
        """Categorize issues by description keywords."""
        categories: dict[str, int] = defaultdict(int)

        keywords = {
            "Security": ["password", "secret", "token", "key", "auth", "credential", "vulnerability"],
            "Performance": ["performance", "slow", "memory", "cache", "optimize", "efficient"],
            "Code Quality": ["code quality", "complex", "duplicate", "refactor", "cleanup"],
            "Error Handling": ["error", "exception", "handling", "null", "undefined"],
            "Best Practices": ["best practice", "convention", "style", "lint", "format"],
            "Documentation": ["comment", "doc", "documentation", "readme"],
        }

        for file_review in result.files_reviewed:
            for issue in file_review.issues:
                desc_lower = issue.description.lower()
                categorized = False

                for category, words in keywords.items():
                    if any(word in desc_lower for word in words):
                        categories[category] += 1
                        categorized = True
                        break

                if not categorized:
                    categories["Other"] += 1

        return categories

    def _get_conclusion_emoji(self, conclusion: ReviewConclusion) -> str:
        """Get emoji for conclusion."""
        return {
            ReviewConclusion.CAN_SUBMIT: "✅",
            ReviewConclusion.NEEDS_REVIEW: "⚠️",
        }.get(conclusion, "❓")

    def _generate_pie_chart_base64(self, result: ReviewResult) -> str:
        """Generate pie chart for issue distribution."""
        stats = self._calculate_stats(result)

        if stats['total_issues'] == 0:
            return ""

        sizes = [stats['high_risk'], stats['medium_risk'], stats['low_risk']]
        labels = ['High Risk', 'Medium Risk', 'Low Risk']
        colors = ['#ff6b6b', '#ffd93d', '#6bcb77']

        # Filter out zero values
        non_zero = [(l, s, c) for l, s, c in zip(labels, sizes, colors) if s > 0]
        if not non_zero:
            return ""

        labels, sizes, colors = zip(*non_zero)

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax.set_title('Issues by Risk Level')

        return self._fig_to_base64(fig)

    def _generate_bar_chart_base64(self, result: ReviewResult) -> str:
        """Generate bar chart for files with issues."""
        file_issues = [
            (fr.file_path, len(fr.issues))
            for fr in result.files_reviewed
            if fr.issues
        ]

        if not file_issues:
            return ""

        # Sort by issue count, take top 10
        file_issues = sorted(file_issues, key=lambda x: -x[1])[:10]

        files = [Path(f[0]).name for f in file_issues]  # Just filename
        counts = [f[1] for f in file_issues]

        # Color by risk level
        file_risks = {fr.file_path: fr.risk_level for fr in result.files_reviewed}
        colors = []
        for f, _ in file_issues:
            risk = file_risks.get(f, RiskLevel.LOW)
            colors.append({
                RiskLevel.HIGH: '#ff6b6b',
                RiskLevel.MEDIUM: '#ffd93d',
                RiskLevel.LOW: '#6bcb77',
            }.get(risk, '#cccccc'))

        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.barh(files, counts, color=colors)
        ax.set_xlabel('Number of Issues')
        ax.set_title('Issues per File')
        ax.invert_yaxis()

        # Add value labels
        for bar, count in zip(bars, counts):
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                   str(count), va='center', fontsize=9)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _generate_confidence_gauge_base64(self, confidence: float) -> str:
        """Generate a gauge chart for confidence score."""
        fig, ax = plt.subplots(figsize=(6, 3))

        # Create a simple horizontal bar gauge
        bar_color = '#6bcb77' if confidence >= 80 else '#ffd93d' if confidence >= 60 else '#ff6b6b'

        ax.barh([0], [100], color='#f0f0f0', height=0.5)
        ax.barh([0], [confidence], color=bar_color, height=0.5)

        ax.set_xlim(0, 100)
        ax.set_ylim(-0.5, 0.5)
        ax.set_yticks([])
        ax.set_xlabel(f'Confidence: {confidence:.0f}%', fontsize=12, fontweight='bold')

        # Add threshold markers
        for threshold, label in [(60, '60%'), (80, '80%')]:
            ax.axvline(x=threshold, color='#999999', linestyle='--', alpha=0.5)
            ax.text(threshold, 0.4, label, ha='center', fontsize=8, color='#666666')

        ax.set_title('Confidence Score', pad=10)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

        return self._fig_to_base64(fig)

    def _generate_trend_chart_base64(self, trend: TrendData) -> str:
        """Generate trend line chart."""
        if not trend.dates:
            return ""

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

        # Issue trend
        issue_values = list(trend.issue_counts.values())
        ax1.plot(trend.dates, issue_values, marker='o', color='#ff6b6b', linewidth=2)
        ax1.fill_between(trend.dates, issue_values, alpha=0.3, color='#ff6b6b')
        ax1.set_ylabel('Total Issues')
        ax1.set_title('Issue Trend Over Time')
        ax1.grid(True, alpha=0.3)

        # Confidence trend
        if trend.confidence_values:
            ax2.plot(trend.dates, trend.confidence_values, marker='s',
                    color='#6bcb77', linewidth=2)
            ax2.fill_between(trend.dates, trend.confidence_values, alpha=0.3,
                           color='#6bcb77')
            ax2.set_ylabel('Confidence %')
            ax2.set_xlabel('Time Period')
            ax2.set_title('Confidence Trend')
            ax2.set_ylim(0, 100)
            ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _fig_to_base64(self, fig) -> str:
        """Convert matplotlib figure to base64 string."""
        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
        return img_base64

    def _build_html(
        self,
        result: ReviewResult,
        stats: dict[str, Any],
        pr_number: Optional[int],
        pie_chart: str,
        bar_chart: str,
        confidence_chart: str,
        trend_chart: str,
    ) -> str:
        """Build complete HTML report."""
        conclusion = result.conclusion.value.replace('_', ' ').title()
        conclusion_emoji = self._get_conclusion_emoji(result.conclusion)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Review Report - {self.project_name}</title>
    <style>
        :root {{
            --primary: #2563eb;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}

        /* Header */
        .header {{
            background: linear-gradient(135deg, var(--primary), #1d4ed8);
            color: white;
            padding: 40px;
            border-radius: 16px;
            margin-bottom: 24px;
        }}

        .header h1 {{
            font-size: 2rem;
            margin-bottom: 8px;
        }}

        .header .meta {{
            opacity: 0.9;
            font-size: 0.9rem;
        }}

        /* Cards */
        .card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}

        .card h2 {{
            font-size: 1.25rem;
            margin-bottom: 16px;
            color: var(--text);
            border-bottom: 2px solid var(--border);
            padding-bottom: 8px;
        }}

        /* Summary Stats */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}

        .stat-card {{
            background: var(--card-bg);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}

        .stat-card .value {{
            font-size: 2rem;
            font-weight: bold;
            color: var(--primary);
        }}

        .stat-card .label {{
            color: var(--text-muted);
            font-size: 0.875rem;
        }}

        .stat-card.high .value {{ color: var(--danger); }}
        .stat-card.medium .value {{ color: var(--warning); }}
        .stat-card.low .value {{ color: var(--success); }}

        /* Conclusion */
        .conclusion {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 1.5rem;
            font-weight: bold;
            padding: 16px;
            background: {self._get_conclusion_bg(result.conclusion)};
            border-radius: 8px;
            margin-bottom: 24px;
        }}

        /* Charts */
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 24px;
        }}

        .chart-container {{
            text-align: center;
        }}

        .chart-container img {{
            max-width: 100%;
            height: auto;
        }}

        /* Files Table */
        .files-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .files-table th, .files-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}

        .files-table th {{
            background: var(--bg);
            font-weight: 600;
        }}

        .files-table tr:hover {{
            background: var(--bg);
        }}

        .risk-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: bold;
            text-transform: uppercase;
        }}

        .risk-high {{ background: #fee2e2; color: #dc2626; }}
        .risk-medium {{ background: #fef3c7; color: #d97706; }}
        .risk-low {{ background: #d1fae5; color: #059669; }}

        /* Issues */
        .issue-item {{
            padding: 16px;
            border-left: 4px solid var(--border);
            margin-bottom: 12px;
            background: var(--bg);
            border-radius: 0 8px 8px 0;
        }}

        .issue-item.high {{ border-color: var(--danger); }}
        .issue-item.medium {{ border-color: var(--warning); }}
        .issue-item.low {{ border-color: var(--success); }}

        .issue-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 8px;
        }}

        .issue-description {{
            font-weight: 500;
        }}

        .issue-suggestion {{
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 8px;
            padding: 8px;
            background: var(--card-bg);
            border-radius: 4px;
        }}

        .code-highlight {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 12px;
            border-radius: 6px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.875rem;
            overflow-x: auto;
            margin-top: 8px;
        }}

        /* Collapsible */
        .collapsible {{
            cursor: pointer;
            padding: 12px;
            background: var(--bg);
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .collapsible:hover {{
            background: var(--border);
        }}

        .collapsible:after {{
            content: '▼';
            font-size: 0.75rem;
            transition: transform 0.3s;
        }}

        .collapsible.active:after {{
            transform: rotate(180deg);
        }}

        .issue-details {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }}

        .issue-details.show {{
            max-height: 500px;
            padding-top: 12px;
        }}

        /* Share Button */
        .share-btn {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: var(--primary);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 24px;
            cursor: pointer;
            font-weight: bold;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
            transition: transform 0.2s;
        }}

        .share-btn:hover {{
            transform: scale(1.05);
        }}

        /* Responsive */
        @media (max-width: 768px) {{
            .header h1 {{ font-size: 1.5rem; }}
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .charts-grid {{ grid-template-columns: 1fr; }}
            .container {{ padding: 12px; }}
        }}

        /* Animations */
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .card {{ animation: fadeIn 0.3s ease-out; }}
        .card:nth-child(2) {{ animation-delay: 0.1s; }}
        .card:nth-child(3) {{ animation-delay: 0.2s; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>📊 Code Review Report</h1>
            <div class="meta">
                <strong>{self.project_name}</strong>
                {" | PR #" + str(pr_number) if pr_number else ""}
                <br>
                Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>

        <!-- Summary Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value">{stats['total_issues']}</div>
                <div class="label">Total Issues</div>
            </div>
            <div class="stat-card high">
                <div class="value">{stats['high_risk']}</div>
                <div class="label">🔴 High Risk</div>
            </div>
            <div class="stat-card medium">
                <div class="value">{stats['medium_risk']}</div>
                <div class="label">🟡 Medium Risk</div>
            </div>
            <div class="stat-card low">
                <div class="value">{stats['low_risk']}</div>
                <div class="label">🟢 Low Risk</div>
            </div>
            <div class="stat-card">
                <div class="value">{stats['total_files']}</div>
                <div class="label">Files Reviewed</div>
            </div>
        </div>

        <!-- Conclusion -->
        <div class="conclusion">
            <span>{conclusion_emoji}</span>
            <span>{conclusion}</span>
            <span style="font-size: 1rem; color: var(--text-muted);">
                (Confidence: {result.confidence:.0f}%)
            </span>
        </div>

        <!-- Charts -->
        <div class="card">
            <h2>📈 Visualizations</h2>
            <div class="charts-grid">
                {self._render_chart_container('Risk Distribution', pie_chart) if pie_chart else ''}
                {self._render_chart_container('Issues per File', bar_chart) if bar_chart else ''}
                {self._render_chart_container('Confidence Score', confidence_chart) if confidence_chart else ''}
            </div>
        </div>

        <!-- Trend Chart -->
        {f'''
        <div class="card">
            <h2>📉 Trend Analysis</h2>
            <div class="chart-container">
                <img src="data:image/png;base64,{trend_chart}" alt="Trend Analysis">
            </div>
        </div>
        ''' if trend_chart else ''}

        <!-- Files Reviewed -->
        <div class="card">
            <h2>📁 Files Reviewed</h2>
            <table class="files-table">
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Risk</th>
                        <th>Issues</th>
                        <th>Changes</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(self._render_file_row(fr) for fr in result.files_reviewed)}
                </tbody>
            </table>
        </div>

        <!-- Detailed Issues -->
        <div class="card">
            <h2>⚠️ Detailed Issues</h2>
            {self._render_issues_list(result)}
        </div>

        <!-- Summary -->
        <div class="card">
            <h2>📝 Summary</h2>
            <p>{result.summary}</p>
        </div>
    </div>

    <!-- Share Button -->
    <button class="share-btn" onclick="copyLink()">
        🔗 Share Report
    </button>

    <script>
        function copyLink() {{
            navigator.clipboard.writeText(window.location.href).then(() => {{
                alert('Link copied to clipboard!');
            }});
        }}

        // Collapsible issues
        document.querySelectorAll('.collapsible').forEach(item => {{
            item.addEventListener('click', () => {{
                item.classList.toggle('active');
                const details = item.nextElementSibling;
                details.classList.toggle('show');
            }});
        }});
    </script>
</body>
</html>"""
        return html

    def _render_chart_container(self, title: str, chart_data: str) -> str:
        """Render a chart container."""
        if not chart_data:
            return ""
        return f"""
        <div class="chart-container">
            <h3>{title}</h3>
            <img src="data:image/png;base64,{chart_data}" alt="{title}">
        </div>
        """

    def _render_file_row(self, file_review: FileReview) -> str:
        """Render a file table row."""
        risk_class = file_review.risk_level.value
        risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_class, "")
        return f"""
        <tr>
            <td><code>{file_review.file_path}</code></td>
            <td><span class="risk-badge risk-{risk_class}">{risk_emoji} {risk_class.upper()}</span></td>
            <td>{len(file_review.issues)}</td>
            <td>{file_review.changes}</td>
        </tr>
        """

    def _render_issues_list(self, result: ReviewResult) -> str:
        """Render the issues list with collapsible sections."""
        all_issues = []
        for file_review in result.files_reviewed:
            for issue in file_review.issues:
                all_issues.append((file_review.file_path, issue))

        if not all_issues:
            return "<p>No issues found. Great job!</p>"

        # Sort by risk level
        risk_order = {"high": 0, "medium": 1, "low": 2}
        all_issues.sort(key=lambda x: risk_order.get(x[1].risk_level.value, 3))

        html_parts = []
        for file_path, issue in all_issues:
            risk_class = issue.risk_level.value
            risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk_class, "")

            html_parts.append(f"""
            <div class="issue-item {risk_class}">
                <div class="issue-header">
                    <span class="issue-description">{risk_emoji} {issue.description}</span>
                    <span class="risk-badge risk-{risk_class}">{risk_class.upper()}</span>
                </div>
                <div style="color: var(--text-muted); font-size: 0.875rem;">
                    📄 {file_path}
                    {" | Line " + str(issue.line_number) if issue.line_number else ""}
                </div>
                {f'<div class="issue-suggestion">💡 {issue.suggestion}</div>' if issue.suggestion else ''}
            </div>
            """)

        return "\n".join(html_parts)

    def _get_conclusion_bg(self, conclusion: ReviewConclusion) -> str:
        """Get background color for conclusion."""
        return {
            ReviewConclusion.CAN_SUBMIT: "#d1fae5",
            ReviewConclusion.NEEDS_REVIEW: "#fef3c7",
        }.get(conclusion, "#f3f4f6")
