"""Tests for output generation."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from codereview.models import (
    FileReview,
    FileIssue,
    RiskLevel,
    ReviewConclusion,
    ReviewResult,
    OutputConfig,
)
from codereview.output.generator import OutputGenerator


@pytest.fixture
def sample_review_result():
    """Create a sample review result for testing."""
    issues = [
        FileIssue(
            risk_level=RiskLevel.HIGH,
            description="Hardcoded password detected",
            suggestion="Use environment variables",
            file_path="src/auth.py",
            line_number=10,
        ),
        FileIssue(
            risk_level=RiskLevel.MEDIUM,
            description="Console log found",
            suggestion="Remove in production",
            file_path="src/utils.py",
            line_number=25,
        ),
        FileIssue(
            risk_level=RiskLevel.LOW,
            description="TODO comment found",
            suggestion="Complete the task",
            file_path="src/helpers.py",
            line_number=5,
        ),
    ]

    file_reviews = [
        FileReview(
            file_path="src/auth.py",
            risk_level=RiskLevel.HIGH,
            changes="+10, -2",
            issues=[issues[0]],
        ),
        FileReview(
            file_path="src/utils.py",
            risk_level=RiskLevel.LOW,
            changes="+5, -1",
            issues=[issues[1]],
        ),
        FileReview(
            file_path="src/helpers.py",
            risk_level=RiskLevel.LOW,
            changes="+3, -0",
            issues=[issues[2]],
        ),
    ]

    return ReviewResult(
        conclusion=ReviewConclusion.NEEDS_REVIEW,
        confidence=85.0,
        files_reviewed=file_reviews,
        summary="Found 3 issues across 3 files. High risk: hardcoded password.",
    )


@pytest.fixture
def output_config():
    """Create output config for testing."""
    return OutputConfig(
        report_format="markdown",
        report_path="",
        pr_comment=True,
    )


class TestOutputGenerator:
    """Test OutputGenerator class."""

    def test_generator_init(self, output_config):
        """Test output generator initialization."""
        generator = OutputGenerator(output_config)
        assert generator.config == output_config

    def test_generate_markdown(self, sample_review_result, output_config):
        """Test markdown generation."""
        generator = OutputGenerator(output_config)
        markdown = generator._generate_markdown(sample_review_result)

        assert "# CodeReview Agent Report" in markdown
        assert "src/auth.py" in markdown
        assert "src/utils.py" in markdown
        assert "Hardcoded password detected" in markdown
        assert "high" in markdown.lower()

    def test_generate_markdown_with_pr(self, sample_review_result, output_config):
        """Test markdown generation with PR number."""
        generator = OutputGenerator(output_config)
        markdown = generator._generate_markdown(sample_review_result, pr_number=42)

        assert "# CodeReview Agent Report" in markdown
        assert "**PR**: #42" in markdown

    def test_generate_json(self, sample_review_result, output_config):
        """Test JSON generation."""
        generator = OutputGenerator(output_config)
        json_output = generator._generate_json(sample_review_result)

        data = json.loads(json_output)
        assert data["conclusion"] == "needs_review"
        assert data["confidence"] == 85.0
        assert len(data["files_reviewed"]) == 3

    def test_generate_pr_comment(self, sample_review_result, output_config):
        """Test PR comment generation."""
        generator = OutputGenerator(output_config)
        comment = generator._generate_pr_comment(sample_review_result)

        assert "CodeReview Agent" in comment
        assert "src/auth.py" in comment
        assert "needs review" in comment.lower()

    def test_generate_pr_comment_success(self, output_config):
        """Test PR comment with success conclusion."""
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=[],
            summary="No issues found",
        )
        generator = OutputGenerator(output_config)
        comment = generator._generate_pr_comment(result)

        assert "✅" in comment
        assert "can submit" in comment.lower()


class TestOutputGeneratorAsync:
    """Test async output generation."""

    @pytest.mark.asyncio
    async def test_generate_markdown_output(self, sample_review_result):
        """Test generating markdown output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = OutputConfig(
                report_format="markdown",
                report_path=temp_dir,
                pr_comment=True,
            )

            generator = OutputGenerator(config)
            outputs = await generator.generate(sample_review_result, pr_number=123)

            assert "markdown" in outputs
            assert "pr_comment" in outputs

    @pytest.mark.asyncio
    async def test_generate_json_output(self, sample_review_result):
        """Test generating JSON output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = OutputConfig(
                report_format="json",
                report_path=temp_dir,
                pr_comment=False,
            )

            generator = OutputGenerator(config)
            outputs = await generator.generate(sample_review_result)

            assert "json" in outputs

    @pytest.mark.asyncio
    async def test_generate_both_formats(self, sample_review_result):
        """Test generating both markdown and JSON."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = OutputConfig(
                report_format="both",
                report_path=temp_dir,
                pr_comment=True,
            )

            generator = OutputGenerator(config)
            outputs = await generator.generate(sample_review_result, pr_number=1)

            assert "markdown" in outputs
            assert "json" in outputs
            assert "pr_comment" in outputs


class TestMarkdownFormatting:
    """Test markdown output formatting."""

    def test_file_table_formatting(self, output_config):
        """Test file table is properly formatted."""
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=100.0,
            files_reviewed=[
                FileReview(
                    file_path="src/main.py",
                    risk_level=RiskLevel.HIGH,
                    changes="+20, -5",
                    issues=[],
                ),
                FileReview(
                    file_path="lib/helper.ts",
                    risk_level=RiskLevel.LOW,
                    changes="+10, -2",
                    issues=[],
                ),
            ],
            summary="Test",
        )

        generator = OutputGenerator(output_config)
        markdown = generator._generate_markdown(result)

        assert "| File | Risk | Issues |" in markdown
        assert "src/main.py" in markdown
        assert "lib/helper.ts" in markdown

    def test_risk_emoji_mapping(self, output_config):
        """Test risk level emoji mapping."""
        result = ReviewResult(
            conclusion=ReviewConclusion.NEEDS_REVIEW,
            confidence=50.0,
            files_reviewed=[
                FileReview(
                    file_path="high.py",
                    risk_level=RiskLevel.HIGH,
                    changes="+5, -1",
                    issues=[],
                ),
                FileReview(
                    file_path="medium.py",
                    risk_level=RiskLevel.MEDIUM,
                    changes="+3, -0",
                    issues=[],
                ),
                FileReview(
                    file_path="low.py",
                    risk_level=RiskLevel.LOW,
                    changes="+1, -0",
                    issues=[],
                ),
            ],
            summary="Test",
        )

        generator = OutputGenerator(output_config)
        markdown = generator._generate_markdown(result)

        # Check for risk emojis
        assert "🔴" in markdown  # High
        assert "🟡" in markdown  # Medium
        assert "🟢" in markdown  # Low
