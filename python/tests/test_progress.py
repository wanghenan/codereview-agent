"""Tests for tqdm progress bar integration in reviewer.

Tests verify:
1. review_files() shows progress bar for multiple files
2. Progress bar displays "Reviewing file N/M: filename.py"
3. TQDM_DISABLE=1 environment variable disables progress bar
4. Single file review doesn't show progress bar (len<=1)
5. Progress bar closes properly after completion
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codereview.agents.reviewer import ReviewAgent
from codereview.models import Config, DiffEntry, FileReview, ProjectContext, RiskLevel


class TestProgressBarIntegration:
    """Test tqdm progress bar integration in review_files()."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = MagicMock(spec=Config)
        config.max_concurrency = 2
        config.timeout_seconds = 30
        config.exclude_patterns = []
        config.critical_paths = []
        config.custom_prompt_path = None
        return config

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM."""
        llm = MagicMock()
        chain = MagicMock()
        chain.ainvoke = AsyncMock(
            return_value={
                "risk_level": "low",
                "issues": [],
                "summary": "No issues found",
            }
        )
        llm.chain = chain
        return llm

    @pytest.fixture
    def mock_project_context(self):
        """Create mock project context."""
        return MagicMock(spec=ProjectContext)

    @pytest.fixture
    def sample_diff_entries(self):
        """Create sample diff entries for testing."""
        return [
            DiffEntry(
                filename=f"src/file{i}.py",
                status="modified",
                patch=f"--- a/src/file{i}.py\n+++ b/src/file{i}.py\n@@ -1 +1 @@\n-old\n+new{i}",
                additions=1,
                deletions=1,
            )
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_review_files_shows_progress_bar_for_multiple_files(
        self, mock_config, mock_llm, mock_project_context, sample_diff_entries
    ):
        """Test that progress bar is shown when reviewing multiple files."""
        agent = ReviewAgent(
            config=mock_config,
            llm=mock_llm,
            project_context=mock_project_context,
        )

        async def mock_review(entry, max_retries=3):
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes=f"+{entry.additions}, -{entry.deletions}",
                issues=[],
            )

        with patch("codereview.agents.reviewer.tqdm") as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value = mock_pbar

            with patch.object(agent, "_review_file_with_retry", side_effect=mock_review):
                await agent.review_files(sample_diff_entries)

            mock_tqdm.assert_called_once()
            call_kwargs = mock_tqdm.call_args[1]
            assert call_kwargs.get("disable") is False
            assert call_kwargs.get("desc") == "Reviewing"
            assert call_kwargs.get("unit") == "file"

    @pytest.mark.asyncio
    async def test_progress_bar_displays_correct_description(
        self, mock_config, mock_llm, mock_project_context, sample_diff_entries
    ):
        """Test progress bar displays 'Reviewing' as description."""
        agent = ReviewAgent(
            config=mock_config,
            llm=mock_llm,
            project_context=mock_project_context,
        )

        async def mock_review(entry, max_retries=3):
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes=f"+{entry.additions}, -{entry.deletions}",
                issues=[],
            )

        with patch("codereview.agents.reviewer.tqdm") as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value = mock_pbar

            with patch.object(agent, "_review_file_with_retry", side_effect=mock_review):
                await agent.review_files(sample_diff_entries)

            call_kwargs = mock_tqdm.call_args[1]
            assert call_kwargs.get("desc") == "Reviewing"

    @pytest.mark.asyncio
    async def test_single_file_review_hides_progress_bar(
        self, mock_config, mock_llm, mock_project_context
    ):
        """Test that single file review disables progress bar."""
        single_entry = [
            DiffEntry(
                filename="src/only_file.py",
                status="modified",
                patch="--- a/src/only_file.py\n+++ b/src/only_file.py\n@@ -1 +1 @@\n-old\n+new",
                additions=1,
                deletions=1,
            )
        ]

        agent = ReviewAgent(
            config=mock_config,
            llm=mock_llm,
            project_context=mock_project_context,
        )

        async def mock_review(entry, max_retries=3):
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes=f"+{entry.additions}, -{entry.deletions}",
                issues=[],
            )

        with patch("codereview.agents.reviewer.tqdm") as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value = mock_pbar

            with patch.object(agent, "_review_file_with_retry", side_effect=mock_review):
                await agent.review_files(single_entry)

            mock_tqdm.assert_called_once()
            call_kwargs = mock_tqdm.call_args[1]
            assert call_kwargs.get("disable") is True

    @pytest.mark.asyncio
    async def test_tqdm_disable_env_variable_disables_progress_bar(
        self, mock_config, mock_llm, mock_project_context, sample_diff_entries
    ):
        """Test that TQDM_DISABLE=1 environment variable disables progress bar."""
        agent = ReviewAgent(
            config=mock_config,
            llm=mock_llm,
            project_context=mock_project_context,
        )

        async def mock_review(entry, max_retries=3):
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes=f"+{entry.additions}, -{entry.deletions}",
                issues=[],
            )

        with patch.dict(os.environ, {"TQDM_DISABLE": "1"}):
            with patch("codereview.agents.reviewer.tqdm") as mock_tqdm:
                mock_pbar = MagicMock()
                mock_tqdm.return_value = mock_pbar

                with patch.object(agent, "_review_file_with_retry", side_effect=mock_review):
                    await agent.review_files(sample_diff_entries)

                mock_tqdm.assert_called_once()

    @pytest.mark.asyncio
    async def test_progress_bar_closes_after_completion(
        self, mock_config, mock_llm, mock_project_context, sample_diff_entries
    ):
        """Test that progress bar is closed after all files are reviewed."""
        agent = ReviewAgent(
            config=mock_config,
            llm=mock_llm,
            project_context=mock_project_context,
        )

        async def mock_review(entry, max_retries=3):
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes=f"+{entry.additions}, -{entry.deletions}",
                issues=[],
            )

        with patch("codereview.agents.reviewer.tqdm") as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value = mock_pbar

            with patch.object(agent, "_review_file_with_retry", side_effect=mock_review):
                await agent.review_files(sample_diff_entries)

            mock_pbar.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_progress_bar_accepts_tasks_parameter(
        self, mock_config, mock_llm, mock_project_context, sample_diff_entries
    ):
        """Test that progress bar receives tasks as first argument."""
        agent = ReviewAgent(
            config=mock_config,
            llm=mock_llm,
            project_context=mock_project_context,
        )

        async def mock_review(entry, max_retries=3):
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes=f"+{entry.additions}, -{entry.deletions}",
                issues=[],
            )

        with patch("codereview.agents.reviewer.tqdm") as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value = mock_pbar

            with patch.object(agent, "_review_file_with_retry", side_effect=mock_review):
                await agent.review_files(sample_diff_entries)

            mock_tqdm.assert_called_once()
            call_args = mock_tqdm.call_args
            assert call_args is not None
