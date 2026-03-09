"""Tests for the Visual Report Generator."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codereview.core.report_generator import ReportGenerator, TrendData
from codereview.models import (
    FileIssue,
    FileReview,
    RiskLevel,
    ReviewConclusion,
    ReviewResult,
)


@pytest.fixture
def sample_review_result():
    """Create a sample review result for testing."""
    issues = [
        FileIssue(
            file_path="src/auth.py",
            line_number=10,
            risk_level=RiskLevel.HIGH,
            description="Hardcoded password detected",
            suggestion="Use environment variables for sensitive data",
        ),
        FileIssue(
            file_path="src/auth.py",
            line_number=25,
            risk_level=RiskLevel.MEDIUM,
            description="Missing error handling",
            suggestion="Add try-catch block",
        ),
        FileIssue(
            file_path="src/utils.py",
            line_number=50,
            risk_level=RiskLevel.LOW,
            description="Console log found",
            suggestion="Remove debug logs in production",
        ),
        FileIssue(
            file_path="src/main.py",
            line_number=100,
            risk_level=RiskLevel.HIGH,
            description="SQL injection vulnerability",
            suggestion="Use parameterized queries",
        ),
    ]

    file_reviews = [
        FileReview(
            file_path="src/auth.py",
            risk_level=RiskLevel.HIGH,
            changes="+45, -12",
            issues=[issues[0], issues[1]],
        ),
        FileReview(
            file_path="src/utils.py",
            risk_level=RiskLevel.LOW,
            changes="+10, -3",
            issues=[issues[2]],
        ),
        FileReview(
            file_path="src/main.py",
            risk_level=RiskLevel.HIGH,
            changes="+100, -20",
            issues=[issues[3]],
        ),
        FileReview(
            file_path="src/helpers.py",
            risk_level=RiskLevel.LOW,
            changes="+5, -0",
            issues=[],
        ),
    ]

    return ReviewResult(
        conclusion=ReviewConclusion.NEEDS_REVIEW,
        confidence=72.5,
        files_reviewed=file_reviews,
        summary="Found 4 issues across 4 files. High risk issues require immediate attention.",
    )


@pytest.fixture
def clean_review_result():
    """Create a review result with no issues."""
    return ReviewResult(
        conclusion=ReviewConclusion.CAN_SUBMIT,
        confidence=95.0,
        files_reviewed=[
            FileReview(
                file_path="src/main.py",
                risk_level=RiskLevel.LOW,
                changes="+10, -2",
                issues=[],
            ),
        ],
        summary="Code looks good, no significant issues found.",
    )


class TestReportGeneratorInit:
    """Test ReportGenerator initialization."""

    def test_default_init(self):
        """Test initialization with defaults."""
        generator = ReportGenerator()
        assert generator.project_name == "Code Review"

    def test_custom_project_name(self):
        """Test initialization with custom project name."""
        generator = ReportGenerator(project_name="MyProject")
        assert generator.project_name == "MyProject"


class TestHTMLReportGeneration:
    """Test HTML report generation."""

    def test_generate_html_report_basic(self, sample_review_result):
        """Test basic HTML report generation."""
        generator = ReportGenerator(project_name="TestProject")
        html = generator.generate_html_report(sample_review_result)

        assert "<!DOCTYPE html>" in html
        assert "TestProject" in html
        assert "Code Review Report" in html

    def test_html_contains_stats(self, sample_review_result):
        """Test that HTML contains statistics."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        # Check for total issues
        assert "4" in html  # Total issues
        assert "2" in html  # High risk (2 files with high risk)
        assert "1" in html  # Medium risk
        assert "1" in html  # Low risk

    def test_html_contains_conclusion(self, sample_review_result):
        """Test that HTML contains conclusion."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        assert "Needs Review" in html or "needs_review" in html.lower()
        assert "72.5" in html or "73" in html  # Confidence

    def test_html_with_pr_number(self, sample_review_result):
        """Test HTML generation with PR number."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result, pr_number=42)

        assert "#42" in html or "PR #42" in html

    def test_html_contains_charts(self, sample_review_result):
        """Test that HTML contains chart placeholders."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        assert "Visualizations" in html or "chart" in html.lower()
        assert "base64" in html  # Charts are embedded as base64

    def test_html_responsive_design(self, sample_review_result):
        """Test that HTML has responsive design."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        assert "@media" in html
        assert "max-width" in html

    def test_html_files_table(self, sample_review_result):
        """Test that HTML contains files table."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        assert "src/auth.py" in html
        assert "src/utils.py" in html
        assert "src/main.py" in html

    def test_html_detailed_issues(self, sample_review_result):
        """Test that HTML contains detailed issues."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        assert "Hardcoded password" in html
        assert "SQL injection" in html

    def test_html_clean_result(self, clean_review_result):
        """Test HTML generation with no issues."""
        generator = ReportGenerator()
        html = generator.generate_html_report(clean_review_result)

        assert "Can Submit" in html or "can_submit" in html.lower()
        assert "no significant issues" in html.lower() or "great job" in html.lower()


class TestMarkdownReportGeneration:
    """Test Markdown report generation."""

    def test_generate_markdown_basic(self, sample_review_result):
        """Test basic Markdown report generation."""
        generator = ReportGenerator(project_name="TestProject")
        md = generator.generate_markdown_report(sample_review_result)

        assert "# 📊 Code Review Report" in md
        assert "TestProject" in md

    def test_markdown_summary_table(self, sample_review_result):
        """Test Markdown summary table."""
        generator = ReportGenerator()
        md = generator.generate_markdown_report(sample_review_result)

        assert "| Metric | Value |" in md
        assert "Conclusion" in md
        assert "Confidence" in md

    def test_markdown_files_section(self, sample_review_result):
        """Test Markdown files section."""
        generator = ReportGenerator()
        md = generator.generate_markdown_report(sample_review_result)

        assert "## 📁 Files Reviewed" in md
        assert "| File | Risk | Issues |" in md

    def test_markdown_detailed_issues(self, sample_review_result):
        """Test Markdown detailed issues section."""
        generator = ReportGenerator()
        md = generator.generate_markdown_report(sample_review_result)

        assert "## ⚠️ Detailed Issues" in md
        assert "Hardcoded password" in md

    def test_markdown_with_pr(self, sample_review_result):
        """Test Markdown with PR number."""
        generator = ReportGenerator()
        md = generator.generate_markdown_report(sample_review_result, pr_number=123)

        assert "#123" in md or "PR #123" in md

    def test_markdown_risk_emoji(self, sample_review_result):
        """Test Markdown uses correct risk emojis."""
        generator = ReportGenerator()
        md = generator.generate_markdown_report(sample_review_result)

        assert "🔴" in md  # High risk
        assert "🟡" in md  # Medium risk
        assert "🟢" in md  # Low risk


class TestTrendAnalysis:
    """Test trend analysis functionality."""

    def test_generate_trend_chart_empty(self):
        """Test trend chart with empty data."""
        generator = ReportGenerator()
        trend = generator.generate_trend_chart([])

        assert len(trend.dates) == 0
        assert len(trend.issue_counts) == 0

    def test_generate_trend_chart_single(self):
        """Test trend chart with single result."""
        generator = ReportGenerator()

        # Create result using model_dump to preserve all fields and add reviewed_at
        base_dict = {
            "conclusion": ReviewConclusion.CAN_SUBMIT,
            "confidence": 85.0,
            "files_reviewed": [
                {
                    "file_path": "src/file1.py",
                    "risk_level": RiskLevel.LOW,
                    "changes": "+10, -5",
                    "issues": []
                }
            ],
            "summary": "Test",
            "reviewed_at": datetime.now().isoformat()
        }

        trend = generator.generate_trend_chart([base_dict])

        assert len(trend.dates) >= 1

    def test_generate_trend_chart_multiple(self):
        """Test trend chart with multiple results."""
        generator = ReportGenerator()

        # Create historical data as dictionaries
        results = []
        for i in range(5):
            result_dict = {
                "conclusion": ReviewConclusion.CAN_SUBMIT if i > 2 else ReviewConclusion.NEEDS_REVIEW,
                "confidence": 60.0 + i * 5,
                "files_reviewed": [
                    {
                        "file_path": f"src/file{i}.py",
                        "risk_level": RiskLevel.LOW,
                        "changes": "+10, -5",
                        "issues": []
                    }
                ],
                "summary": "Test",
                "reviewed_at": (datetime.now() - timedelta(days=i)).isoformat()
            }
            results.append(result_dict)

        trend = generator.generate_trend_chart(results)

        # Note: With week period, dates within same week may be grouped together
        assert len(trend.dates) >= 1
        assert len(trend.confidence_values) >= 1

    def test_trend_data_to_dict(self):
        """Test TrendData serialization."""
        trend = TrendData()
        trend.dates = ["2024-01", "2024-02"]
        trend.issue_counts = {"2024-01": 10, "2024-02": 5}
        trend.confidence_values = [80.0, 85.0]

        data = trend.to_dict()

        assert data["dates"] == ["2024-01", "2024-02"]
        assert data["issue_counts"] == {"2024-01": 10, "2024-02": 5}
        assert data["confidence_values"] == [80.0, 85.0]

    def test_generate_trend_by_week(self):
        """Test trend by week period."""
        generator = ReportGenerator()

        results = []
        for i in range(10):
            result_dict = {
                "conclusion": ReviewConclusion.CAN_SUBMIT,
                "confidence": 90.0,
                "files_reviewed": [
                    {
                        "file_path": f"src/file{i}.py",
                        "risk_level": RiskLevel.LOW,
                        "changes": "+5, -2",
                        "issues": []
                    }
                ],
                "summary": "Test",
                "reviewed_at": (datetime.now() - timedelta(days=i * 3)).isoformat()
            }
            results.append(result_dict)

        trend = generator.generate_trend_chart(results, period="week")
        assert len(trend.dates) > 0


class TestFileSaving:
    """Test file saving functionality."""

    def test_save_html_report(self, sample_review_result):
        """Test saving HTML report to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = ReportGenerator()
            output_path = Path(temp_dir) / "report.html"

            result_path = generator.save_html_report(
                sample_review_result,
                output_path,
                pr_number=1
            )

            assert result_path.exists()
            content = result_path.read_text()
            assert "<!DOCTYPE html>" in content

    def test_save_markdown_report(self, sample_review_result):
        """Test saving Markdown report to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = ReportGenerator()
            output_path = Path(temp_dir) / "report.md"

            result_path = generator.save_markdown_report(
                sample_review_result,
                output_path,
                pr_number=1
            )

            assert result_path.exists()
            content = result_path.read_text()
            assert "# 📊 Code Review Report" in content

    def test_save_creates_parent_dirs(self, sample_review_result):
        """Test that save creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = ReportGenerator()
            output_path = Path(temp_dir) / "subdir" / "report.html"

            result_path = generator.save_html_report(sample_review_result, output_path)

            assert result_path.exists()
            assert result_path.parent.exists()


class TestStatistics:
    """Test statistics calculation."""

    def test_calculate_stats(self, sample_review_result):
        """Test statistics calculation."""
        generator = ReportGenerator()
        stats = generator._calculate_stats(sample_review_result)

        assert stats["total_issues"] == 4
        assert stats["high_risk"] == 2  # 2 files with high risk
        assert stats["medium_risk"] == 1
        assert stats["low_risk"] == 1
        assert stats["total_files"] == 4

    def test_categorize_issues(self, sample_review_result):
        """Test issue categorization."""
        generator = ReportGenerator()
        categories = generator._categorize_issues(sample_review_result)

        assert "Security" in categories  # password, SQL injection
        assert categories["Security"] >= 2

    def test_categorize_performance_issues(self):
        """Test categorization of performance issues."""
        result = ReviewResult(
            conclusion=ReviewConclusion.NEEDS_REVIEW,
            confidence=50.0,
            files_reviewed=[
                FileReview(
                    file_path="slow.py",
                    risk_level=RiskLevel.MEDIUM,
                    changes="+100, -0",
                    issues=[
                        FileIssue(
                            file_path="slow.py",
                            risk_level=RiskLevel.MEDIUM,
                            description="This query is slow and needs optimization",
                        )
                    ],
                )
            ],
            summary="Performance issue",
        )

        generator = ReportGenerator()
        categories = generator._categorize_issues(result)

        assert "Performance" in categories


class TestCharts:
    """Test chart generation."""

    def test_pie_chart_generation(self, sample_review_result):
        """Test pie chart generation."""
        generator = ReportGenerator()
        chart = generator._generate_pie_chart_base64(sample_review_result)

        assert chart  # Should return non-empty base64 string
        assert "iVBOR" in chart  # PNG header

    def test_bar_chart_generation(self, sample_review_result):
        """Test bar chart generation."""
        generator = ReportGenerator()
        chart = generator._generate_bar_chart_base64(sample_review_result)

        assert chart
        assert "iVBOR" in chart

    def test_confidence_gauge(self, sample_review_result):
        """Test confidence gauge generation."""
        generator = ReportGenerator()
        chart = generator._generate_confidence_gauge_base64(72.5)

        assert chart
        assert "iVBOR" in chart

    def test_empty_pie_chart(self, clean_review_result):
        """Test pie chart with no issues."""
        generator = ReportGenerator()
        chart = generator._generate_pie_chart_base64(clean_review_result)

        # Should return empty string for no issues
        assert chart == ""

    def test_trend_chart_with_data(self):
        """Test trend chart generation."""
        generator = ReportGenerator()

        results = []
        for i in range(3):
            result_dict = {
                "conclusion": ReviewConclusion.CAN_SUBMIT,
                "confidence": 80.0 + i * 5,
                "files_reviewed": [],
                "summary": "Test",
                "reviewed_at": (datetime.now() - timedelta(days=i)).isoformat()
            }
            results.append(result_dict)

        trend = generator.generate_trend_chart(results)
        chart = generator._generate_trend_chart_base64(trend)

        assert chart
        assert "iVBOR" in chart


class TestHTMLFormatting:
    """Test HTML formatting details."""

    def test_html_has_share_button(self, sample_review_result):
        """Test that HTML has share button."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        assert "Share Report" in html or "share" in html.lower()

    def test_html_has_collapsible_issues(self, sample_review_result):
        """Test that HTML has collapsible issue sections."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        assert "collapsible" in html.lower() or "details" in html.lower()

    def test_html_code_highlighting(self, sample_review_result):
        """Test HTML code highlighting classes."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        assert "code" in html.lower() or "pre" in html.lower()

    def test_conclusion_colors(self, sample_review_result):
        """Test conclusion styling."""
        generator = ReportGenerator()
        html = generator.generate_html_report(sample_review_result)

        # Should have different colors for different conclusions
        assert "#d1fae5" in html or "#fef3c7" in html  # Background colors


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_result_with_no_files(self):
        """Test handling of result with no files."""
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=100.0,
            files_reviewed=[],
            summary="No files to review.",
        )

        generator = ReportGenerator()
        html = generator.generate_html_report(result)

        assert "Can Submit" in html or "can_submit" in html.lower()

    def test_result_with_no_issues(self, clean_review_result):
        """Test handling of result with no issues."""
        generator = ReportGenerator()

        html = generator.generate_html_report(clean_review_result)
        md = generator.generate_markdown_report(clean_review_result)

        assert "Can Submit" in html
        assert "no significant issues" in md.lower() or "can submit" in md.lower()

    def test_extreme_confidence_values(self):
        """Test confidence at boundaries."""
        for confidence in [0.0, 50.0, 100.0]:
            result = ReviewResult(
                conclusion=ReviewConclusion.CAN_SUBMIT,
                confidence=confidence,
                files_reviewed=[],
                summary="Test",
            )

            generator = ReportGenerator()
            html = generator.generate_html_report(result)

            assert str(int(confidence)) in html

    def test_all_risk_levels(self):
        """Test handling all risk levels."""
        result = ReviewResult(
            conclusion=ReviewConclusion.NEEDS_REVIEW,
            confidence=50.0,
            files_reviewed=[
                FileReview(
                    file_path="high.py",
                    risk_level=RiskLevel.HIGH,
                    changes="+5, -1",
                    issues=[FileIssue(
                        file_path="high.py",
                        risk_level=RiskLevel.HIGH,
                        description="High risk issue",
                    )],
                ),
                FileReview(
                    file_path="medium.py",
                    risk_level=RiskLevel.MEDIUM,
                    changes="+3, -0",
                    issues=[FileIssue(
                        file_path="medium.py",
                        risk_level=RiskLevel.MEDIUM,
                        description="Medium risk issue",
                    )],
                ),
                FileReview(
                    file_path="low.py",
                    risk_level=RiskLevel.LOW,
                    changes="+1, -0",
                    issues=[FileIssue(
                        file_path="low.py",
                        risk_level=RiskLevel.LOW,
                        description="Low risk issue",
                    )],
                ),
            ],
            summary="Test",
        )

        generator = ReportGenerator()
        html = generator.generate_html_report(result)

        assert "🔴" in html
        assert "🟡" in html
        assert "🟢" in html


class TestIntegration:
    """Integration tests."""

    def test_full_workflow(self, sample_review_result):
        """Test complete report generation workflow."""
        generator = ReportGenerator(project_name="IntegrationTest")

        # Generate historical data
        historical_results = []
        for i in range(3):
            result_dict = {
                "conclusion": ReviewConclusion.CAN_SUBMIT,
                "confidence": 80.0 + i * 5,
                "files_reviewed": [],
                "summary": "Historical test",
                "reviewed_at": (datetime.now() - timedelta(days=i)).isoformat()
            }
            historical_results.append(result_dict)

        trend = generator.generate_trend_chart(historical_results)

        # Generate reports
        html = generator.generate_html_report(sample_review_result, pr_number=42, trend_data=trend)
        md = generator.generate_markdown_report(sample_review_result, pr_number=42, trend_data=trend)

        assert "<!DOCTYPE html>" in html
        assert "# 📊 Code Review Report" in md
        assert "#42" in md
        assert "IntegrationTest" in html
        assert "Trend" in html or "trend" in html.lower()
