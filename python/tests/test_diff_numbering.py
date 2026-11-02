"""Tests for new-file line numbering in diffs sent to the review prompt."""

from __future__ import annotations

from codereview.core.diff_numbering import number_patch

SINGLE_HUNK = (
    "diff --git a/app.py b/app.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -121,3 +122,4 @@ def handler(self):\n"
    "     def handler(self):\n"
    "-        res = old()\n"
    "+        res = res.replace(tzinfo=tz)\n"
    "+        return res\n"
    "     return res\n"
)


def test_context_added_and_deleted_lines_are_numbered() -> None:
    """Context and added lines get a number; deleted lines leave it blank."""
    lines = number_patch(SINGLE_HUNK).splitlines()

    assert lines[5] == "  122 |     def handler(self):"
    assert lines[6] == "-     |         res = old()"
    assert lines[7] == "+ 123 |         res = res.replace(tzinfo=tz)"
    assert lines[8] == "+ 124 |         return res"
    assert lines[9] == "  125 |     return res"


def test_file_and_hunk_headers_are_passed_through() -> None:
    numbered = number_patch(SINGLE_HUNK)

    assert numbered.startswith(SINGLE_HUNK.split("@@", 1)[0])
    assert "@@ -121,3 +122,4 @@ def handler(self)" in numbered


def test_each_hunk_aligns_its_own_numbers() -> None:
    """Width is chosen per hunk, not globally (1-digit vs 4-digit numbers)."""
    patch = (
        "@@ -1,2 +1,2 @@\n"
        " line one\n"
        "-old one\n"
        "+new one\n"
        "@@ -98,2 +999,2 @@\n"
        " line two\n"
        "-old two\n"
        "+new two\n"
    )

    assert number_patch(patch).splitlines() == [
        "@@ -1,2 +1,2 @@",
        "  1 | line one",
        "-   | old one",
        "+ 2 | new one",
        "@@ -98,2 +999,2 @@",
        "   999 | line two",
        "-      | old two",
        "+ 1000 | new two",
    ]


def test_no_newline_marker_is_preserved() -> None:
    patch = (
        "@@ -1,2 +1,2 @@\n"
        " keep\n"
        "-old\n"
        "\\ No newline at end of file\n"
        "+new\n"
        "\\ No newline at end of file\n"
    )

    assert number_patch(patch).splitlines() == [
        "@@ -1,2 +1,2 @@",
        "  1 | keep",
        "-   | old",
        "\\ No newline at end of file",
        "+ 2 | new",
        "\\ No newline at end of file",
    ]


def test_multi_file_patch_keeps_later_file_headers_unnumbered() -> None:
    patch = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
        "diff --git a/b.py b/b.py\n"
        "--- a/b.py\n"
        "+++ b/b.py\n"
        "@@ -5 +5 @@\n"
        "-c\n"
        "+d\n"
    )

    numbered = number_patch(patch)

    assert "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n" in numbered
    assert "-   | a\n+ 1 | b\n" in numbered
    assert "-   | c\n+ 5 | d\n" in numbered


def test_hunk_without_counts_defaults_to_one_line() -> None:
    assert number_patch("@@ -7 +9 @@\n-old\n+new\n") == "@@ -7 +9 @@\n-   | old\n+ 9 | new\n"


def test_patch_without_hunks_is_unchanged() -> None:
    patch = "diff --git a/logo.png b/logo.png\nBinary files a/logo.png and b/logo.png differ\n"

    assert number_patch(patch) == patch
    assert number_patch("") == ""


def test_input_patch_string_is_not_modified() -> None:
    original = SINGLE_HUNK

    number_patch(original)

    assert original == SINGLE_HUNK
    assert "| " not in original
