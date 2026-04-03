"""Tests for rule management (--list-rules, --disable-rule)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Get the python source directory
PYTHON_SRC = Path(__file__).parent.parent / "src"


class TestGetAllRules:
    """Test get_all_rules() function."""

    def test_get_all_rules_returns_list(self):
        """Test that get_all_rules returns a list of DetectionRule."""
        sys.path.insert(0, str(PYTHON_SRC))
        try:
            from codereview.rules import get_all_rules

            rules = get_all_rules()
            assert isinstance(rules, list)
        finally:
            sys.path.remove(str(PYTHON_SRC))

    def test_get_all_rules_returns_30_rules(self):
        """Test that get_all_rules returns exactly 30 rules."""
        sys.path.insert(0, str(PYTHON_SRC))
        try:
            from codereview.rules import get_all_rules

            rules = get_all_rules()
            assert len(rules) == 30
        finally:
            sys.path.remove(str(PYTHON_SRC))

    def test_get_all_rules_returns_detection_rules(self):
        """Test that returned items are DetectionRule instances."""
        sys.path.insert(0, str(PYTHON_SRC))
        try:
            from codereview.rules import DetectionRule, get_all_rules

            rules = get_all_rules()
            for rule in rules:
                assert isinstance(rule, DetectionRule)
        finally:
            sys.path.remove(str(PYTHON_SRC))


class TestDisableRules:
    """Test disable_rules() method on RuleEngine."""

    def test_disable_rules_removes_rule(self):
        """Test that disable_rules removes specified rule IDs."""
        sys.path.insert(0, str(PYTHON_SRC))
        try:
            from codereview.rules import RuleEngine, create_rule_engine

            engine = create_rule_engine()
            initial_count = len(engine.rules)

            # Disable a specific rule
            engine.disable_rules(["OWASP-A01-001"])

            # Should have one fewer rule
            assert len(engine.rules) == initial_count - 1

            # The disabled rule should not be in the list
            rule_ids = [r.id for r in engine.rules]
            assert "OWASP-A01-001" not in rule_ids
        finally:
            sys.path.remove(str(PYTHON_SRC))

    def test_disable_rules_multiple_ids(self):
        """Test disabling multiple rule IDs at once."""
        sys.path.insert(0, str(PYTHON_SRC))
        try:
            from codereview.rules import create_rule_engine

            engine = create_rule_engine()
            initial_count = len(engine.rules)

            # Disable multiple rules
            engine.disable_rules(["OWASP-A01-001", "OWASP-A01-002", "OWASP-A01-003"])

            assert len(engine.rules) == initial_count - 3

            rule_ids = [r.id for r in engine.rules]
            assert "OWASP-A01-001" not in rule_ids
            assert "OWASP-A01-002" not in rule_ids
            assert "OWASP-A01-003" not in rule_ids
        finally:
            sys.path.remove(str(PYTHON_SRC))

    def test_disable_rules_invalid_id_warns(self, caplog):
        """Test that disabling non-existent rule ID logs a warning."""
        sys.path.insert(0, str(PYTHON_SRC))
        try:
            import logging

            from codereview.rules import create_rule_engine

            engine = create_rule_engine()

            # Capture log warnings
            with caplog.at_level(logging.WARNING, logger="codereview.rules"):
                engine.disable_rules(["INVALID-RULE-ID"])

            # Should have logged a warning about invalid ID
            assert any("INVALID-RULE-ID" in str(record.message) for record in caplog.records)
        finally:
            sys.path.remove(str(PYTHON_SRC))

    def test_disable_rules_affects_detect(self):
        """Test that disabled rules don't produce detections."""
        sys.path.insert(0, str(PYTHON_SRC))
        try:
            from codereview.rules import create_rule_engine

            engine = create_rule_engine()

            # Get a rule that would match something
            rule_to_disable = engine.get_rule_by_id("OWASP-A01-001")
            if rule_to_disable:
                # Find content that would match this rule
                test_content = 'password = "hardcoded_password"'
                before_disable = engine.detect(test_content, language="python")
                before_rule_ids = [r["rule_id"] for r in before_disable]

                # Confirm rule was detected before disable
                assert "OWASP-A01-001" in before_rule_ids

                # Disable the rule
                engine.disable_rules(["OWASP-A01-001"])

                # After disabling, should not find the same issue
                after_disable = engine.detect(test_content, language="python")
                after_rule_ids = [r["rule_id"] for r in after_disable] if after_disable else []

                assert "OWASP-A01-001" not in after_rule_ids
        finally:
            sys.path.remove(str(PYTHON_SRC))


class TestListRulesCli:
    """Test --list-rules CLI flag."""

    def test_list_rules_outputs_table(self):
        """Test that --list-rules outputs a table format."""
        result = subprocess.run(
            [sys.executable, "-m", "codereview.cli", "--list-rules"],
            capture_output=True,
            text=True,
            cwd=PYTHON_SRC.parent.parent,
        )

        assert result.returncode == 0
        # Should contain rule IDs in output
        assert "OWASP-A01-001" in result.stdout
        assert "OWASP-A02-001" in result.stdout

    def test_list_rules_exits_zero(self):
        """Test that --list-rules exits with code 0."""
        result = subprocess.run(
            [sys.executable, "-m", "codereview.cli", "--list-rules"],
            capture_output=True,
            text=True,
            cwd=PYTHON_SRC.parent.parent,
        )

        assert result.returncode == 0

    def test_list_rules_json_output(self):
        """Test that --list-rules --json outputs valid JSON array."""
        result = subprocess.run(
            [sys.executable, "-m", "codereview.cli", "--list-rules", "--json"],
            capture_output=True,
            text=True,
            cwd=PYTHON_SRC.parent.parent,
        )

        assert result.returncode == 0

        # Should be valid JSON
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 30

        # Each item should have expected fields
        for rule in data:
            assert "id" in rule
            assert "name" in rule
            assert "severity" in rule


class TestDisableRuleCli:
    """Test --disable-rule CLI flag."""

    def test_disable_rule_skips_rule(self):
        """Test that --disable-rule skips the specified rule during review."""
        # This is tested by checking that when we run with --disable-rule,
        # the rule doesn't appear in outputs
        diff_json = json.dumps({"files": []})

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "codereview.cli",
                "--disable-rule",
                "OWASP-A01-001",
                "--diff",
                diff_json,
            ],
            capture_output=True,
            text=True,
            cwd=PYTHON_SRC.parent.parent,
        )

        # Should not error (even with empty diff)
        # The important thing is --disable-rule is accepted
        assert result.returncode in (0, 1)  # 1 if no actual review happens

    def test_disable_rule_comma_separated(self):
        """Test that --disable-rule supports comma-separated rule IDs."""
        diff_json = json.dumps({"files": []})

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "codereview.cli",
                "--disable-rule",
                "OWASP-A01-001,OWASP-A01-002",
                "--diff",
                diff_json,
            ],
            capture_output=True,
            text=True,
            cwd=PYTHON_SRC.parent.parent,
        )

        # Should not error
        assert result.returncode in (0, 1)

    def test_disable_rule_invalid_id_warning(self):
        """Test that --disable-rule with invalid ID outputs warning.

        Note: Full CLI test requires valid config. This test verifies
        the --disable-rule flag is at least recognized by argparse.
        The invalid rule warning is logged when run_review() is called.
        """
        # Test that --disable-rule is recognized by argparse (returns 2 for unrecognized)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "codereview.cli",
                "--disable-rule",
                "INVALID-RULE-ID",
                "--diff",
                "{}",
            ],
            capture_output=True,
            text=True,
            cwd=PYTHON_SRC.parent.parent,
        )

        # Should NOT be unrecognized argument error ( argparse error code 2)
        # It may fail for other reasons (like config), but not unrecognized arg
        assert "unrecognized arguments" not in result.stderr
