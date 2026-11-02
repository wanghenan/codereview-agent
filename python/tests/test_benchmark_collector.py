"""Tests for the real-PR collector's slicing and fallback rules."""

from __future__ import annotations

from tests.benchmark import collect_real_prs as collector


def test_normalize_hunk_recounts_truncated_body() -> None:
    hunk = "@@ -108,11 +111,123 @@\n a\n b\n c\n"

    normalized = collector.normalize_hunk(hunk)

    assert normalized.splitlines()[0] == "@@ -108,3 +111,3 @@"
    assert collector.hunk_is_truncated(hunk)
    assert not collector.hunk_is_truncated(normalized)


def test_line_at_position_skips_diff_preamble_and_deletions() -> None:
    block = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,3 @@\n a\n+X\n b\n"

    assert collector.line_at_position(block, 5) == 1
    assert collector.line_at_position(block, 6) == 2
    assert collector.line_at_position(block, 7) == 3
    assert collector.line_at_position(block, 1) is None


def test_diff_covers_only_the_new_side() -> None:
    block = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,3 @@\n a\n+X\n b\n"

    assert collector.diff_covers_line(block, 1)
    assert collector.diff_covers_line(block, 3)
    assert not collector.diff_covers_line(block, 4)


def test_patch_block_builds_applicable_headers() -> None:
    patch = "@@ -1,2 +1,3 @@\n a\n+X\n b"

    added = collector.patch_block("x.py", {"status": "added", "patch": patch})
    modified = collector.patch_block("x.py", {"status": "modified", "patch": patch})

    assert added.startswith("diff --git a/x.py b/x.py\nnew file mode 100644\n--- /dev/null\n")
    assert modified.startswith("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n")
    assert collector.patch_block("x.py", {"status": "renamed", "patch": patch}) == ""


def test_comment_target_uses_commit_parent_when_commit_touches_file(monkeypatch) -> None:
    commit = {
        "parents": [{"sha": "parent"}],
        "files": [
            {
                "filename": "x.py",
                "status": "modified",
                "patch": "@@ -1,2 +1,3 @@\n a\n+X\n b",
            }
        ],
    }
    monkeypatch.setattr(collector, "commit_detail", lambda repo, sha: commit)
    comment = {
        "path": "x.py",
        "original_commit_id": "sha",
        "original_line": 2,
        "diff_hunk": "@@ -1,2 +1,3 @@\n a\n+X\n b\n",
    }

    block, base, line = collector.comment_target("o/r", {"base": {"sha": "base"}}, comment)

    assert base == "parent"
    assert line == 2
    assert "diff --git a/x.py b/x.py" in block


def test_comment_target_prefers_hunk_when_commit_changes_other_lines(monkeypatch) -> None:
    """A comment on line 2 must use the hunk that covers line 2, not a commit hunk elsewhere."""
    commit = {
        "parents": [{"sha": "parent"}],
        "files": [
            {
                "filename": "x.py",
                "status": "modified",
                "patch": "@@ -40,2 +40,3 @@\n c\n+Y\n d",
            }
        ],
    }
    monkeypatch.setattr(collector, "commit_detail", lambda repo, sha: commit)
    comment = {
        "path": "x.py",
        "original_commit_id": "sha",
        "original_line": 2,
        "original_position": 6,
        "diff_hunk": "@@ -1,2 +1,3 @@\n a\n+X\n b\n",
    }

    block, base, line = collector.comment_target("o/r", {"base": {"sha": "base"}}, comment)

    assert base == "base"
    assert line == 2
    assert "+X" in block


def test_comment_target_falls_back_when_commit_does_not_touch_file(monkeypatch) -> None:
    commit = {"parents": [{"sha": "parent"}], "files": [{"filename": "other.py"}]}
    monkeypatch.setattr(collector, "commit_detail", lambda repo, sha: commit)
    comment = {
        "path": "x.py",
        "original_commit_id": "sha",
        "original_line": 2,
        "diff_hunk": "@@ -1,2 +1,3 @@\n a\n+X\n b\n",
    }

    block, base, line = collector.comment_target("o/r", {"base": {"sha": "base"}}, comment)

    assert base == "base"
    assert line == 2


def test_comment_target_returns_none_without_any_cover(monkeypatch) -> None:
    monkeypatch.setattr(
        collector,
        "commit_detail",
        lambda repo, sha: (_ for _ in ()).throw(RuntimeError("gone")),
    )
    comment = {
        "path": "x.py",
        "original_commit_id": "sha",
        "original_line": 20,
        "diff_hunk": "@@ -1,2 +1,3 @@\n a\n+X\n b\n",
    }

    assert collector.comment_target("o/r", {"base": {"sha": "base"}}, comment) is None
