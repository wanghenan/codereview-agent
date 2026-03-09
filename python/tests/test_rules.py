"""Tests for rule engine."""

import pytest
from codereview.rules import DetectionRule, RuleEngine, create_rule_engine


class TestDetectionRule:
    """Test DetectionRule dataclass."""

    def test_rule_creation(self):
        """Test creating a detection rule."""
        rule = DetectionRule(
            id="test001",
            name="Test Rule",
            pattern=r"password\s*=\s*['\"][^'\"]+['\"]",
            severity="high",
            description="Hardcoded password detected",
            suggestion="Use environment variables",
        )
        assert rule.id == "test001"
        assert rule.name == "Test Rule"
        assert rule.severity == "high"
        assert rule._compiled_pattern is not None

    def test_rule_match(self):
        """Test rule matching."""
        rule = DetectionRule(
            id="test002",
            name="API Key Detection",
            pattern=r"api[_-]?key\s*=\s*['\"]",
            severity="high",
            description="API key detected",
            suggestion="Use env vars",
        )

        content = 'api_key = "sk-1234567890abcdefghij"'
        matches = rule.match(content)

        assert len(matches) >= 1

    def test_rule_no_match(self):
        """Test rule with no matches."""
        rule = DetectionRule(
            id="test003",
            name="Token Detection",
            pattern=r"token\s*=\s*['\"][A-Za-z0-9]+['\"]",
            severity="medium",
            description="Token detected",
            suggestion="Use env vars",
        )

        content = "var api_url = 'https://api.example.com'"
        matches = rule.match(content)

        assert len(matches) == 0

    def test_rule_invalid_regex(self):
        """Test rule with invalid regex pattern."""
        rule = DetectionRule(
            id="test004",
            name="Invalid Rule",
            pattern=r"[invalid",
            severity="low",
            description="Test invalid",
            suggestion="None",
        )
        # Invalid regex should result in None compiled pattern
        assert rule._compiled_pattern is None

    def test_rule_match_with_line_numbers(self):
        """Test rule match returns correct line numbers."""
        rule = DetectionRule(
            id="test005",
            name="Console Log",
            pattern=r"console\.log\(",
            severity="low",
            description="Console log found",
            suggestion="Remove in production",
        )

        content = """function test() {
    console.log("debug1");
    console.log("debug2");
}"""
        matches = rule.match(content)

        assert len(matches) == 2
        assert matches[0]["line_number"] == 2
        assert matches[1]["line_number"] == 3


class TestRuleEngine:
    """Test RuleEngine class."""

    def test_create_rule_engine(self):
        """Test creating a rule engine."""
        engine = create_rule_engine()
        assert engine is not None
        assert isinstance(engine.rules, list)

    def test_detect_in_content(self):
        """Test detection in content."""
        engine = create_rule_engine()

        # Test with Python content containing common issues
        content = """
import os
password = "hardcoded_password"
api_key = "sk-1234567890abcdef"
"""
        issues = engine.detect(content, language="python")

        # Should find at least some issues (depends on loaded rules)
        assert isinstance(issues, list)

    def test_detect_with_language_filter(self):
        """Test detection with language filter."""
        engine = create_rule_engine()

        python_content = "password = 'hardcoded'"
        issues = engine.detect(python_content, language="python")

        assert isinstance(issues, list)

    def test_detect_in_diff(self):
        """Test detection in diff content."""
        engine = create_rule_engine()

        diff_content = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
+password = "hardcoded"
 def hello():
     pass
"""
        issues = engine.detect_in_diff(diff_content)

        assert isinstance(issues, list)

    def test_get_rules_by_severity(self):
        """Test filtering rules by severity."""
        engine = create_rule_engine()
        high_rules = engine.get_rules_by_severity("high")

        assert isinstance(high_rules, list)

    def test_get_rule_by_id(self):
        """Test getting a specific rule by ID."""
        engine = create_rule_engine()

        # Get first rule if exists
        if engine.rules:
            first_rule = engine.rules[0]
            found_rule = engine.get_rule_by_id(first_rule.id)
            assert found_rule is not None
            assert found_rule.id == first_rule.id

        # Non-existent rule
        assert engine.get_rule_by_id("non_existent_rule_12345") is None

    def test_custom_rules(self):
        """Test loading custom rules."""
        custom_rules = [
            {
                "id": "custom001",
                "name": "Custom Rule",
                "pattern": r"TODO:.*",
                "severity": "low",
                "description": "TODO comment found",
                "suggestion": "Complete the task",
            }
        ]

        engine = create_rule_engine(custom_rules=custom_rules)

        # Should have custom rule
        custom_rule = engine.get_rule_by_id("custom001")
        assert custom_rule is not None
        assert custom_rule.name == "Custom Rule"
