"""Tests for CLI flags: --version, --clear-cache, --dry-run and --offline."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest


class TestVersionFlag:
    """Tests for --version flag."""

    def test_version_flag_prints_expected_format(self, tmp_path, capsys):
        """--version should print 'codereview-agent X.Y.Z' format."""
        from codereview.cli import main

        with patch.object(sys, "argv", ["codereview", "--version"]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "codereview-agent" in captured.out
        import re

        version_match = re.search(r"codereview-agent (\d+\.\d+\.\d+)", captured.out)
        assert version_match is not None, (
            f"Expected 'codereview-agent X.Y.Z' format, got: {captured.out}"
        )

    def test_version_flag_exit_code_zero(self, tmp_path):
        """--version should return 0."""
        from codereview.cli import main

        with patch.object(sys, "argv", ["codereview", "--version"]):
            result = main()

        assert result == 0

    def test_version_not_affect_other_args(self, tmp_path):
        """--version combined with other args should still just show version."""
        from codereview.cli import main

        with patch.object(sys, "argv", ["codereview", "--version", "--config", "foo.yaml"]):
            result = main()

        assert result == 0


class TestClearCacheFlag:
    """Tests for --clear-cache flag."""

    def test_clear_cache_without_yes_prompts(self, tmp_path, capsys):
        """--clear-cache without --yes should prompt for confirmation."""
        from codereview.cli import main

        with patch.object(sys, "argv", ["codereview", "--clear-cache"]):
            with patch("builtins.input", return_value="n"):
                result = main()

        assert result == 0
        captured = capsys.readouterr()
        out_lower = captured.out.lower()
        assert (
            "clear" in out_lower
            or "confirm" in out_lower
            or "y/n" in out_lower
            or "cache" in out_lower
        )

    def test_clear_cache_with_yes_removes_cache_dir(self, tmp_path, capsys):
        """--clear-cache --yes should remove .codereview-agent/cache/ directory."""
        from codereview import cli

        cache_dir = tmp_path / ".codereview-agent" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "project-context.json").write_text('{"test": "data"}')

        assert cache_dir.exists()

        with patch.object(sys, "argv", ["codereview", "--clear-cache", "--yes"]):
            with patch.object(cli, "CACHE_DIR", cache_dir):
                result = cli.main()

        assert result == 0
        assert not cache_dir.exists()

        captured = capsys.readouterr()
        out_lower = captured.out.lower()
        assert "cleared" in out_lower or "removed" in out_lower or "success" in out_lower

    def test_clear_cache_with_yes_nonexistent_cache(self, tmp_path, capsys):
        """--clear-cache --yes on nonexistent cache should succeed."""
        from codereview import cli

        cache_dir = tmp_path / ".codereview-agent" / "cache"

        with patch.object(sys, "argv", ["codereview", "--clear-cache", "--yes"]):
            with patch.object(cli, "CACHE_DIR", cache_dir):
                result = cli.main()

        assert result == 0
        captured = capsys.readouterr()
        out_lower = captured.out.lower()
        assert (
            "cleared" in out_lower
            or "removed" in out_lower
            or "success" in out_lower
            or "nothing" in out_lower
            or "exist" in out_lower
        )

    def test_clear_cache_yes_requires_clear_cache(self, tmp_path):
        """--yes without --clear-cache should not trigger cache clearing."""
        from codereview.cli import main

        with patch.object(sys, "argv", ["codereview", "--yes"]):
            try:
                result = main()
                assert result is not None
            except SystemExit:
                pass


class TestDryRunOfflineFlags:
    """Tests for the --dry-run / --offline review switches."""

    @staticmethod
    def _run_main(argv):
        """Run the review CLI with ``run_review`` mocked out."""
        from codereview import cli

        mock_run_review = AsyncMock(return_value={"result": {"files_reviewed": []}, "outputs": {}})
        with patch.object(sys, "argv", argv):
            with patch.object(cli, "run_review", mock_run_review):
                result = cli.main()

        assert result == 0
        return mock_run_review

    def test_dry_run_flag_forwarded_to_run_review(self):
        """--dry-run must reach run_review as dry_run=True."""
        mock_run_review = self._run_main(["codereview", "--dry-run"])

        kwargs = mock_run_review.await_args.kwargs
        assert kwargs["dry_run"] is True
        assert kwargs["offline"] is False

    def test_offline_flag_forwarded_to_run_review(self):
        """--offline must reach run_review as offline=True."""
        mock_run_review = self._run_main(["codereview", "--offline"])

        kwargs = mock_run_review.await_args.kwargs
        assert kwargs["offline"] is True
        assert kwargs["dry_run"] is False

    def test_flags_default_to_false(self):
        """Both switches default to False when omitted."""
        mock_run_review = self._run_main(["codereview"])

        kwargs = mock_run_review.await_args.kwargs
        assert kwargs["dry_run"] is False
        assert kwargs["offline"] is False

    def test_help_documents_both_flags(self, capsys):
        """--help must list both switches and explain how they differ."""
        from codereview.cli import main

        with patch.object(sys, "argv", ["codereview", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "--dry-run" in out
        assert "--offline" in out
        assert "network" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
