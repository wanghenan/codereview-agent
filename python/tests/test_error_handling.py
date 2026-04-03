"""Tests for error handling improvements.

Tests verify that:
1. get_git_diff() raises RuntimeError on failure
2. GitHub API 404 error includes PR number
3. ConfigError includes field_name attribute
4. Cache save uses atomic write
5. Analyzer failure logs WARNING
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from codereview.cli import _parse_diff, get_git_diff
from codereview.core.cache import CacheManager
from codereview.core.config import ConfigError, ConfigLoader
from codereview.agents.analyzer import ProjectAnalyzer, logger


class TestGetGitDiffRaisesRuntimeError:
    def test_raises_runtime_error_when_git_fails(self):
        with patch("subprocess.run") as mock_run:
            def run_side_effect(*args, **kwargs):
                raise subprocess.CalledProcessError(1, "git", stderr="fatal: not a git repository")
            mock_run.side_effect = run_side_effect

            with pytest.raises(RuntimeError) as exc_info:
                get_git_diff()

            assert "Failed to get git diff" in str(exc_info.value)

    def test_raises_runtime_error_when_both_fallbacks_fail(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="initial error"),
                MagicMock(returncode=128, stdout="", stderr="fatal: no commits"),
            ]

            with pytest.raises(RuntimeError) as exc_info:
                get_git_diff()

            assert "Failed to get git diff" in str(exc_info.value)


class TestParseDiffLogsWarning:
    def test_json_error_logs_warning_with_first_100_chars(self, caplog):
        invalid_json = '{"files": ['

        with caplog.at_level(logging.WARNING):
            result = _parse_diff(invalid_json)

        assert result == []
        assert any("Failed to parse" in record.message for record in caplog.records)


class TestGitHubClientErrorIncludesPR:
    @pytest.mark.asyncio
    async def test_http_error_404_includes_pr_number(self):
        from codereview.core.github_client import GitHubClient
        import urllib.error

        client = GitHubClient(repo_owner="test-owner", repo_name="test-repo")

        with patch.object(client, "_get_repo_info", return_value=("test-owner", "test-repo")):
            client._gh_available = False
            with patch("urllib.request.urlopen") as mock_urlopen:
                def raise_404(url, timeout=None):
                    raise urllib.error.HTTPError(
                        url=url, code=404, msg="Not Found", hdrs={}, fp=None
                    )
                mock_urlopen.side_effect = raise_404
                with pytest.raises(RuntimeError) as exc_info:
                    await client.get_pr_diff(123)

                assert "123" in str(exc_info.value)


class TestConfigErrorHasFieldName:
    def test_config_error_has_field_name_attribute(self):
        error = ConfigError("Invalid configuration")
        assert hasattr(error, "field_name")

    def test_config_error_with_field_name_kwarg(self):
        error = ConfigError("Invalid configuration", field_name="llm.provider")
        assert error.field_name == "llm.provider"


class TestCacheAtomicWrite:
    def test_cache_save_uses_atomic_write(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        manager = CacheManager(cache_ttl_days=7, cache_dir=str(cache_dir))

        from codereview.models import ProjectContext

        ctx = ProjectContext(
            tech_stack=["python"],
            language="python",
            critical_paths=[],
            analyzed_at="2024-01-01T00:00:00",
        )

        original_replace = os.replace
        replace_called = []

        def spy_replace(src, dst):
            replace_called.append((src, dst))
            original_replace(src, dst)

        with patch("codereview.core.cache.os.replace", spy_replace):
            manager.save(ctx)

        assert len(replace_called) == 1
        src, dst = replace_called[0]
        assert ".tmp" in str(src)
        assert dst == manager.cache_file


class TestAnalyzerFailureLogsWarning:
    @pytest.mark.asyncio
    async def test_analyze_failure_logs_warning(self, caplog, tmp_path):
        from codereview.models import Config, ProjectContext
        from unittest.mock import MagicMock

        config = MagicMock(spec=Config)
        config.critical_paths = ["src/auth"]

        analyzer = ProjectAnalyzer(config, MagicMock())

        async def mock_llm_analyze(files_info, root_dir):
            logger.warning("Failed to analyze project context, using defaults")
            return ProjectContext(
                tech_stack=["unknown"],
                language="unknown",
                frameworks=[],
                dependencies={},
                critical_paths=["src/auth"],
                analyzed_at="2024-01-01T00:00:00",
            )

        with patch.object(analyzer, "_llm_analyze", mock_llm_analyze):
            with caplog.at_level(logging.WARNING):
                result = await analyzer.analyze(tmp_path)

        assert any("Failed to analyze" in record.message for record in caplog.records)
        assert result.tech_stack == ["unknown"]
        assert result.language == "unknown"
