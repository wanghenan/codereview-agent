"""Tests for the ExcludeMatcher (gitignore-style path exclusion)."""

from __future__ import annotations

from codereview.core.path_matcher import ExcludeMatcher


class TestExcludeMatcher:
    """Unit tests for gitignore-style pattern matching."""

    def test_empty_patterns_match_nothing(self) -> None:
        """No patterns -> nothing excluded."""
        matcher = ExcludeMatcher([])
        assert matcher.matches("src/main.py") is False
        assert matcher.matches("anything.go") is False

    def test_none_patterns_match_nothing(self) -> None:
        """None patterns -> nothing excluded."""
        matcher = ExcludeMatcher(None)
        assert matcher.matches("src/main.py") is False

    def test_simple_glob_pattern(self) -> None:
        """Basic glob patterns match as documented (glob semantics)."""
        matcher = ExcludeMatcher(["*.test.py"])
        assert matcher.matches("foo.test.py") is True
        assert matcher.matches("src/utils.test.py") is True
        assert matcher.matches("src/main.py") is False

    def test_recursive_directory_pattern(self) -> None:
        """``node_modules/**`` excludes everything under the directory."""
        matcher = ExcludeMatcher(["node_modules/**"])
        assert matcher.matches("node_modules/react/index.js") is True
        assert matcher.matches("src/node_modules/utils.js") is False
        assert matcher.matches("src/app.py") is False

    def test_anchored_directory_pattern(self) -> None:
        """Leading slash anchors pattern to the repo root."""
        matcher = ExcludeMatcher(["/build/**"])
        assert matcher.matches("build/output.js") is True
        assert matcher.matches("src/build/local.js") is False

    def test_negation_pattern(self) -> None:
        """``!`` re-includes a path that an earlier pattern excluded."""
        matcher = ExcludeMatcher(["*.md", "!IMPORTANT.md"])
        assert matcher.matches("README.md") is True
        # Negation re-includes; IMPORTANT.md should NOT be excluded.
        assert matcher.matches("IMPORTANT.md") is False

    def test_directory_pattern_without_double_star(self) -> None:
        """``dist/`` (trailing slash) excludes the whole directory tree."""
        matcher = ExcludeMatcher(["dist/"])
        assert matcher.matches("dist/bundle.js") is True
        assert matcher.matches("dist/sub/deep.js") is True

    def test_distinct_from_prefix(self) -> None:
        """``dist/**`` must not match ``distrib/**`` (directory-aware)."""
        matcher = ExcludeMatcher(["dist/**"])
        assert matcher.matches("dist/a.js") is True
        assert matcher.matches("distrib/a.js") is False

    def test_existing_reviewer_assertions_hold(self) -> None:
        """Patterns used by test_reviewer.py must keep matching."""
        matcher = ExcludeMatcher(["*.test.py", "**/node_modules/**"])
        assert matcher.matches("foo.test.py") is True
        assert matcher.matches("src/node_modules/utils.js") is True
        assert matcher.matches("src/main.py") is False
        assert matcher.matches("src/utils.py") is False
