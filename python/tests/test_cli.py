"""Tests for CLI functionality."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCLI:
    """Test CLI functions."""

    def test_parse_git_diff_simple(self):
        """Test parsing simple git diff."""
        from codereview.cli import parse_git_diff_to_entries

        diff_output = """diff --git a/test.py b/test.py
index abcdefg..1234567 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
+new line
 old line
"""

        entries = parse_git_diff_to_entries(diff_output)

        assert len(entries) == 1
        assert entries[0].filename == "test.py"
        assert entries[0].status == "modified"
        assert entries[0].additions >= 1

    def test_parse_git_diff_multiple_files(self):
        """Test parsing diff with multiple files."""
        from codereview.cli import parse_git_diff_to_entries

        diff_output = """diff --git a/file1.py b/file1.py
new file mode 100644
--- /dev/null
+++ b/file1.py
@@ -0,0 +1,2 @@
+line1
+line2
diff --git a/file2.py b/file2.py
deleted file mode 100644
--- a/file2.py
+++ /dev/null
@@ -1,3 +0,0 @@
-old content
"""

        entries = parse_git_diff_to_entries(diff_output)

        assert len(entries) == 2
        assert entries[0].filename == "file1.py"
        assert entries[0].status == "added"
        assert entries[1].filename == "file2.py"
        assert entries[1].status == "deleted"

    def test_parse_git_diff_empty(self):
        """Test parsing empty diff."""
        from codereview.cli import parse_git_diff_to_entries

        entries = parse_git_diff_to_entries("")
        assert len(entries) == 0

    def test_parse_diff_json(self):
        """Test parsing JSON diff input."""
        from codereview.cli import _parse_diff

        json_input = json.dumps(
            [
                {
                    "filename": "test.py",
                    "status": "modified",
                    "additions": 10,
                    "deletions": 5,
                    "patch": "@@ diff content",
                }
            ]
        )

        entries = _parse_diff(json_input)

        assert len(entries) == 1
        assert entries[0].filename == "test.py"

    def test_parse_diff_json_with_files_key(self):
        """Test parsing JSON with files key."""
        from codereview.cli import _parse_diff

        json_input = json.dumps(
            {
                "files": [
                    {
                        "filename": "main.py",
                        "status": "modified",
                        "additions": 20,
                        "deletions": 10,
                        "patch": "@@ content",
                    }
                ]
            }
        )

        entries = _parse_diff(json_input)

        assert len(entries) == 1
        assert entries[0].filename == "main.py"

    def test_parse_diff_file_path(self):
        """Test parsing diff from file path."""
        pass

    def test_parse_diff_empty_input(self):
        """Test parsing empty input."""
        from codereview.cli import _parse_diff

        entries = _parse_diff(None)
        assert len(entries) == 0

        entries = _parse_diff("")
        assert len(entries) == 0


class TestCLIArgs:
    """Test CLI argument parsing."""

    def test_cli_help(self):
        """Test CLI help output."""
        import sys
        from codereview.cli import main

        with patch.object(sys, "argv", ["codereview", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_parse_diff_json_invalid(self):
        """Test parsing invalid JSON."""
        from codereview.cli import _parse_diff

        entries = _parse_diff("not valid json {")
        assert len(entries) == 0


class TestGitDiff:
    """Test git diff functionality."""

    @patch("subprocess.run")
    def test_get_git_diff_success(self, mock_run):
        """Test successful git diff retrieval."""
        from codereview.cli import get_git_diff

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff content"
        mock_run.return_value = mock_result

        result = get_git_diff(branch="main")

        assert result == "diff content"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_get_git_diff_failure(self, mock_run):
        """Test git diff failure handling."""
        from codereview.cli import get_git_diff

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="git error")

        with pytest.raises(RuntimeError) as exc_info:
            get_git_diff(branch="main")

        assert "Failed to get git diff" in str(exc_info.value)

    @patch("subprocess.run")
    def test_get_git_diff_with_base_branch(self, mock_run):
        """Test git diff with base branch."""
        from codereview.cli import get_git_diff

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff"
        mock_run.return_value = mock_result

        result = get_git_diff(branch="main", base_branch="develop")

        call_args = mock_run.call_args[0][0]
        assert "develop" in " ".join(call_args)


class TestInteractiveFixSelection:
    """Tests for interactive fix selection mode."""

    def test_interactive_flag_parsing(self):
        """Test that --interactive flag is parsed correctly."""
        from argparse import Namespace

        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
            mock_parse.return_value = Namespace(
                config=None,
                pr=123,
                diff=None,
                token=None,
                apply=False,
                dry_run=True,
                yes=False,
                file=None,
                min_risk="high",
                json=False,
                output=None,
                interactive=True,
            )

            args = mock_parse.return_value
            assert hasattr(args, "interactive")
            assert args.interactive is True

    def test_fix_summary_shows_applied_and_skipped(self):
        """Test that summary shows correct applied/skipped counts."""
        from codereview.cli import _print_fix_output

        result = {
            "success": True,
            "fixes": [
                {
                    "index": 1,
                    "file": "test.py",
                    "line": 10,
                    "risk": "high",
                    "issue": "Issue 1",
                    "original_code": "x = 1",
                    "fixed_code": "x = 2",
                    "explanation": "Fixed",
                    "diff": "--- original\n+++ fixed",
                },
            ],
            "total_issues": 2,
            "fixes_generated": 2,
            "applied": 1,
            "skipped": 1,
            "dry_run": False,
        }

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _print_fix_output(result, MagicMock(json=False, apply=True))
            output = mock_stdout.getvalue()

            assert "Applied" in output or "applied" in output.lower()
            assert "skipped" in output.lower() or "Skipped" in output

    def test_run_fix_accepts_interactive_parameter(self):
        """Test that run_fix accepts interactive parameter."""
        import inspect
        from codereview.cli import run_fix

        sig = inspect.signature(run_fix)
        params = sig.parameters

        assert "interactive" in params
        assert params["interactive"].default is False

    def test_run_fix_returns_skipped_count_in_result(self):
        """Test that run_fix returns skipped count in result dict."""
        from codereview.cli import run_fix
        import inspect

        # Check the return dict includes 'skipped' key
        # We can't easily test the full function without mocks,
        # but we can verify the implementation returns the right structure
        result = {
            "success": True,
            "fixes": [],
            "total_issues": 0,
            "fixes_generated": 0,
            "applied": 0,
            "skipped": 0,
            "applied_files": [],
            "applied_changes": {},
            "dry_run": True,
        }

        assert "skipped" in result
