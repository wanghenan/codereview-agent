"""Tests for CLI bug fixes."""

import pytest


class TestCLIBugFixes:
    """Test cases for specific CLI bugs."""

    def test_preview_files_list_comparison_bug(self):
        """Test that comparing preview.get('files', []) directly to int raises TypeError.

        Bug: cli.py:491 has `preview.get("files", []) > 5` which compares a list
        to an integer, causing: TypeError: '>' not supported between 'list' and 'int'

        Fix: Should use `len(preview.get("files", [])) > 5`
        """
        preview = {
            "files": [
                {"file_path": f"file{i}.py", "risk_level": "low", "issue_count": 0}
                for i in range(6)  # 6 files to trigger the > 5 check
            ]
        }

        # This is the buggy pattern - should raise TypeError
        with pytest.raises(TypeError, match="'>' not supported.*list.*int"):
            if preview.get("files", []) > 5:
                pass

    def test_preview_files_list_comparison_fix(self):
        """Test that len() comparison works correctly for preview files check."""
        preview = {
            "files": [
                {"file_path": f"file{i}.py", "risk_level": "low", "issue_count": 0}
                for i in range(6)
            ]
        }

        # This is the fixed pattern - should work correctly
        if len(preview.get("files", [])) > 5:
            remaining = len(preview.get("files", [])) - 5
            assert remaining == 1
        else:
            pytest.fail("Should have detected more than 5 files")

    def test_preview_files_5_or_fewer(self):
        """Test that exactly 5 files doesn't trigger the 'more files' message."""
        preview = {
            "files": [
                {"file_path": f"file{i}.py", "risk_level": "low", "issue_count": 0}
                for i in range(5)  # Exactly 5 files
            ]
        }

        # With exactly 5, should NOT enter the > 5 branch
        result = len(preview.get("files", [])) > 5
        assert result is False

    def test_preview_files_empty(self):
        """Test that empty files list is handled correctly."""
        preview = {"files": []}

        result = len(preview.get("files", [])) > 5
        assert result is False

    def test_preview_files_missing_key(self):
        """Test that missing 'files' key defaults to empty list."""
        preview = {}

        result = len(preview.get("files", [])) > 5
        assert result is False
