"""Rules scan code only: comments and docstrings must not produce findings."""

from pathlib import Path

import pytest
import yaml

from codereview.rules import create_rule_engine
from codereview.rules.code_only import strip_comments_and_docstrings

CASES_DIR = Path(__file__).parent / "benchmark" / "cases"
DJANGO_CASE = CASES_DIR / "real-django-migrate-install-error-swallowed.yaml"


def _rule_issues(content: str, rule_id: str, language: str = "python") -> list[dict]:
    """Return findings for one rule."""
    return [
        issue
        for issue in create_rule_engine().detect(content, language=language)
        if issue["rule_id"] == rule_id
    ]


class TestStripCommentsAndDocstrings:
    """Unit tests for the code-only preprocessing helper."""

    def test_comment_is_blanked_without_moving_lines(self) -> None:
        content = "# The MD5 digest is weak.\nx = 1\n"

        stripped = strip_comments_and_docstrings(content, language="python")

        assert stripped == " " * len("# The MD5 digest is weak.") + "\nx = 1\n"
        assert stripped.count("\n") == content.count("\n")
        assert len(stripped) == len(content)

    def test_docstring_is_blanked(self) -> None:
        content = 'def f():\n    """Return the hex MD5 digest."""\n    return 1\n'

        stripped = strip_comments_and_docstrings(content, language="python")

        assert "MD5" not in stripped
        assert stripped.splitlines()[2] == "    return 1"

    def test_inline_string_literals_are_kept(self) -> None:
        content = 'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")\n'

        assert strip_comments_and_docstrings(content, language="python") == content

    def test_assigned_multiline_string_is_kept(self) -> None:
        content = 'SQL = """\nSELECT * FROM t\n"""\n'

        assert strip_comments_and_docstrings(content, language="python") == content

    def test_file_path_infers_python(self) -> None:
        content = "# md5\nx = 1\n"

        stripped = strip_comments_and_docstrings(content, file_path="app.py")

        assert "md5" not in stripped
        assert stripped.endswith("\nx = 1\n")

    def test_unparsable_python_is_returned_unchanged(self) -> None:
        content = "def broken(:\n    # md5 is weak\n"

        assert strip_comments_and_docstrings(content, language="python") == content

    def test_empty_content(self) -> None:
        assert strip_comments_and_docstrings("", language="python") == ""

    def test_javascript_line_and_block_comments_are_blanked(self) -> None:
        content = "// md5 is weak\n/* sha1 and rc4 are weak */\nmd5(value)\n"

        stripped = strip_comments_and_docstrings(content, language="javascript")

        assert "md5 is weak" not in stripped
        assert "sha1 and rc4" not in stripped
        assert stripped.splitlines()[2] == "md5(value)"
        assert len(stripped) == len(content)

    def test_javascript_strings_are_not_treated_as_comments(self) -> None:
        content = 'const url = "http://example.com"; // md5\nmd5(value)\n'

        stripped = strip_comments_and_docstrings(content, language="javascript")

        assert stripped.splitlines()[0].rstrip() == 'const url = "http://example.com";'
        assert stripped.splitlines()[1] == "md5(value)"


class TestCommentsAndDocstringsDoNotMatch:
    """Every audit-table prose example must stop producing a finding."""

    @pytest.mark.parametrize(
        "rule_id, content",
        [
            (
                "OWASP-A02-001",
                "# The MD5 digest is not safe.\nx = 1\n",
            ),
            (
                "OWASP-A02-001",
                '"""Normalise md5 and sha1 digests."""\nx = 1\n',
            ),
            (
                "OWASP-A03-001",
                "# Call the exec() helper for this task.\nx = 1\n",
            ),
            (
                "OWASP-A08-001",
                "# Never eval() untrusted input.\nx = 1\n",
            ),
            (
                "OWASP-A08-001",
                '"""\nNever eval() untrusted input.\n"""\nx = 1\n',
            ),
            (
                "OWASP-A10-001",
                "# fetch(url) without validation.\nx = 1\n",
            ),
            (
                "OWASP-A10-001",
                '"""Helper to fetch(url) remote pages."""\nx = 1\n',
            ),
            (
                "OWASP-A03-003",
                "# frontend uses {{ template }} syntax\nx = 1\n",
            ),
            (
                "OWASP-A05-003",
                "# verify=False disables TLS checks\nx = 1\n",
            ),
            (
                "OWASP-A09-002",
                "# log(password) only in debug builds\nx = 1\n",
            ),
            (
                "OWASP-A01-001",
                '# password = "hunter2"\nx = 1\n',
            ),
            (
                "OWASP-A01-001",
                '"""Example: password = "hunter2" belongs in a vault."""\nx = 1\n',
            ),
            (
                "OWASP-A10-002",
                '# url = request.args["next"]\nx = 1\n',
            ),
            (
                "OWASP-A02-003",
                "# random.random() is not cryptographically secure\nx = 1\n",
            ),
            (
                "OWASP-A05-001",
                "# DEBUG = True for local runs\nx = 1\n",
            ),
        ],
    )
    def test_prose_is_not_flagged(self, rule_id: str, content: str) -> None:
        assert _rule_issues(content, rule_id) == []


class TestRealCodeStillMatches:
    """Sanitising must not hide defects that live in actual code."""

    @pytest.mark.parametrize(
        "rule_id, snippet",
        [
            ("OWASP-A01-003", 'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")'),
            ("OWASP-A02-001", "hashlib.md5(data)"),
            ("OWASP-A05-003", "requests.get(url, verify=False)"),
            ("OWASP-A08-001", "eval(user_input)"),
            ("PY-002", "eval(user_input)"),
            ("OWASP-A10-001", "fetch(url)"),
        ],
    )
    def test_code_snippet_is_still_flagged(self, rule_id: str, snippet: str) -> None:
        content = f"def handler(uid, data, url, user_input):\n    {snippet}\n"

        assert _rule_issues(content, rule_id) != []


class TestLineNumbers:
    """Blanked prose keeps the original line numbering."""

    def test_defect_after_prose_keeps_original_line_number(self) -> None:
        content = (
            "# The MD5 digest is weak.\n"  # line 1
            '"""Module docstring.\n'  # line 2
            "\n"  # line 3
            "Mentions eval() and fetch(url) in prose.\n"  # line 4
            '"""\n'  # line 5
            "\n"  # line 6
            "import hashlib\n"  # line 7
            "\n"  # line 8
            "\n"  # line 9
            "def load(path):\n"  # line 10
            "    return hashlib.md5(open(path).read())\n"  # line 11
        )

        md5_issues = _rule_issues(content, "OWASP-A02-001")

        assert [issue["line_number"] for issue in md5_issues] == [11]
        assert _rule_issues(content, "OWASP-A08-001") == []
        assert _rule_issues(content, "OWASP-A10-001") == []

    def test_detect_in_diff_maps_line_numbers_after_stripping(self) -> None:
        diff = (
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,4 +1,7 @@\n"
            " ctx1\n"
            "+# The MD5 digest is weak.\n"
            '+"""Docstring mentioning eval() and fetch(url)."""\n'
            " uid = 1\n"
            '+cursor.execute(f"SELECT * FROM t WHERE id = {uid}")\n'
            " ctx5\n"
            " ctx6\n"
        )
        issues = create_rule_engine().detect_in_diff(diff, language="python")
        sqli = [issue for issue in issues if issue["rule_id"] == "OWASP-A01-003"]

        assert [issue["line_number"] for issue in sqli] == [5]
        assert [issue for issue in issues if issue["rule_id"] == "OWASP-A02-001"] == []


class TestSyntaxErrorDegrades:
    """A partial or non-Python payload must not break detection."""

    def test_detect_does_not_raise_on_unparsable_python(self) -> None:
        content = "def broken(:\n    # The MD5 digest is weak.\n"

        issues = create_rule_engine().detect(content, language="python")

        assert isinstance(issues, list)

    def test_detect_in_diff_does_not_raise_on_unparsable_python(self) -> None:
        diff = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 ctx1
+cursor.execute(+
 ctx3
"""
        issues = create_rule_engine().detect_in_diff(diff, language="python")

        assert isinstance(issues, list)


class TestDjangoMigrateBenchmarkCase:
    """End-to-end check on a real diff with comments and docstrings."""

    def test_only_code_lines_produce_findings(self) -> None:
        case = yaml.safe_load(DJANGO_CASE.read_text())
        diff = case["diff"]
        engine = create_rule_engine()
        added_lines, line_numbers = engine._added_lines_from_diff(diff)
        raw = "\n".join(added_lines)
        sanitized = strip_comments_and_docstrings(raw, language="python")

        # The case does contain prose, and the helper keeps offsets stable.
        assert sanitized != raw
        assert len(sanitized) == len(raw)
        assert sanitized.count("\n") == raw.count("\n")

        issues = engine.detect_in_diff(diff, language="python")
        sanitized_lines = sanitized.split("\n")

        assert issues
        for issue in issues:
            position = line_numbers.index(issue["line_number"])
            assert issue["matched_text"] in sanitized_lines[position]

        # The real SQL injection findings are still reported at their lines.
        sql_lines = [
            issue["line_number"] for issue in issues if issue["rule_id"] == "OWASP-A01-003"
        ]
        assert sql_lines == [190, 214, 237]
