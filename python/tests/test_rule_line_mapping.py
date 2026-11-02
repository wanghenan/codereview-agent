"""Regression tests for SQL injection rule scope and diff line mapping."""

from pathlib import Path

import pytest
import yaml

from codereview.rules import create_rule_engine

SQLI_RULE_ID = "OWASP-A01-003"
CASES_DIR = Path(__file__).parent / "benchmark" / "cases"


def _sqli_issues(issues: list[dict]) -> list[dict]:
    return [issue for issue in issues if issue["rule_id"] == SQLI_RULE_ID]


class TestSqlInjectionRuleScope:
    """OWASP-A01-003 must match SQL call sites, not prose or identifiers."""

    @pytest.mark.parametrize(
        "line",
        [
            '        Determine whether the provided Task can be executed by the backend.',
            '        """Queue up a task to be executed."""',
            "    # Does the backend support executing Tasks in a given",
            "    def _execute_wrapper(self, func):",
            "    def execute(self, task):",
            "        executed = self._execute(task)",
        ],
    )
    def test_prose_and_identifiers_are_not_flagged(self, line: str) -> None:
        engine = create_rule_engine()

        issues = engine.detect(f"def helper():\n{line}\n    return True\n")

        assert _sqli_issues(issues) == []

    @pytest.mark.parametrize(
        "line",
        [
            'cursor.execute(f"SELECT * FROM t WHERE id = {uid}")',
            'connection.cursor().execute("SELECT 1")',
            'execute("DELETE FROM t WHERE id = 1")',
            'exec("SELECT * FROM t WHERE id = %s" % uid)',
            'query("UPDATE t SET x = 1")',
            'sql = "SELECT * FROM t WHERE id = " + uid',
            'sql = "SELECT * FROM t WHERE id = %s" % uid',
        ],
    )
    def test_real_sql_call_sites_are_flagged(self, line: str) -> None:
        engine = create_rule_engine()

        issues = engine.detect(f"def helper():\n    {line}\n")

        assert len(_sqli_issues(issues)) >= 1

    def test_enqueue_benchmark_case_has_no_sql_injection(self) -> None:
        """The reported false positives were docstrings in this case's diff."""
        case = yaml.safe_load(
            (CASES_DIR / "real-django-enqueue-on-commit-single-db.yaml").read_text()
        )

        issues = create_rule_engine().detect_in_diff(case["diff"])

        assert _sqli_issues(issues) == []


class TestDetectInDiffLineNumbers:
    """detect_in_diff reports new-file line numbers, not added-line offsets."""

    def test_single_hunk_uses_real_file_line(self) -> None:
        diff = """--- a/app.py
+++ b/app.py
@@ -1,3 +1,6 @@
 import sqlite3
+uid = 1
+cursor.execute(f"SELECT * FROM t WHERE id = {uid}")
 
 def f():
"""
        engine = create_rule_engine()

        issues = _sqli_issues(engine.detect_in_diff(diff))

        assert [issue["line_number"] for issue in issues] == [3]
        # detect() keeps its relative, content-only semantics.
        relative = _sqli_issues(engine.detect('uid = 1\ncursor.execute("SELECT 1")\n'))
        assert [issue["line_number"] for issue in relative] == [2]

    def test_multiple_hunks_are_mapped_independently(self) -> None:
        diff = """--- a/app.py
+++ b/app.py
@@ -7,3 +7,4 @@
 ctx7
+cursor.execute("SELECT 1")
 ctx9
 ctx10
@@ -60,3 +61,4 @@
 ctx61
+cursor.execute(f"SELECT * FROM t WHERE id = {uid}")
 ctx63
 ctx64
"""
        issues = _sqli_issues(create_rule_engine().detect_in_diff(diff))

        assert [issue["line_number"] for issue in issues] == [8, 62]

    def test_new_file_hunk_maps_from_line_one(self) -> None:
        diff = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,3 @@
+x = 1
+cursor.execute("SELECT 1")
+y = 2
"""
        issues = _sqli_issues(create_rule_engine().detect_in_diff(diff))

        assert [issue["line_number"] for issue in issues] == [2]
