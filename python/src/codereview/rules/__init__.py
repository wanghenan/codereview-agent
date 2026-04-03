"""Risk detection rule engine."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DetectionRule:
    """A single detection rule."""

    id: str
    name: str
    pattern: str
    severity: str  # high, medium, low
    description: str
    suggestion: str
    language: Optional[str] = None  # Language-specific, None for all

    def __post_init__(self):
        """Compile regex pattern."""
        try:
            self._compiled_pattern = re.compile(self.pattern, re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            logger.warning(f"Invalid regex pattern for rule {self.id}: {e}")
            self._compiled_pattern = None

    def match(self, content: str) -> list[dict]:
        """Match pattern against content.

        Args:
            content: Code content to scan

        Returns:
            List of matches with line numbers
        """
        if not self._compiled_pattern:
            return []

        matches = []
        for line_num, line in enumerate(content.split("\n"), 1):
            for match in self._compiled_pattern.finditer(line):
                matches.append(
                    {
                        "rule_id": self.id,
                        "rule_name": self.name,
                        "line_number": line_num,
                        "matched_text": match.group(0),
                        "severity": self.severity,
                        "description": self.description,
                        "suggestion": self.suggestion,
                    }
                )

        return matches


class RuleEngine:
    """Risk detection rule engine."""

    DEFAULT_RULES_DIR = Path(__file__).parent

    def __init__(self, rules_dir: Optional[Path] = None, custom_rules: Optional[list] = None):
        """Initialize rule engine.

        Args:
            rules_dir: Directory containing rule files
            custom_rules: Optional list of custom rules to add
        """
        self.rules_dir = rules_dir or self.DEFAULT_RULES_DIR
        self.rules: list[DetectionRule] = []
        self._load_rules()

        if custom_rules:
            self._load_custom_rules(custom_rules)

    def _load_rules(self) -> None:
        """Load all rule files from rules directory."""
        if not self.rules_dir.exists():
            logger.warning(f"Rules directory not found: {self.rules_dir}")
            return

        # Load YAML rules
        for rule_file in self.rules_dir.glob("*.yaml"):
            self._load_yaml_rules(rule_file)

        for rule_file in self.rules_dir.glob("*.json"):
            self._load_json_rules(rule_file)

        logger.info(f"Loaded {len(self.rules)} detection rules")

    def _load_yaml_rules(self, rule_file: Path) -> None:
        """Load rules from YAML file."""
        try:
            with open(rule_file) as f:
                data = yaml.safe_load(f)

            # Load main rules
            for rule_data in data.get("rules", []):
                self.rules.append(DetectionRule(**rule_data))

            # Load language-specific rules
            for lang, lang_rules in data.get("language_rules", {}).items():
                for rule_data in lang_rules:
                    rule_data["language"] = lang
                    self.rules.append(DetectionRule(**rule_data))

            logger.debug(f"Loaded rules from {rule_file.name}")
        except Exception as e:
            logger.error(f"Error loading rules from {rule_file}: {e}")

    def _load_json_rules(self, rule_file: Path) -> None:
        """Load rules from JSON file."""
        try:
            with open(rule_file) as f:
                data = json.load(f)

            # Load main rules
            for rule_data in data.get("rules", []):
                self.rules.append(DetectionRule(**rule_data))

            # Load language-specific rules
            for lang, lang_rules in data.get("language_rules", {}).items():
                for rule_data in lang_rules:
                    rule_data["language"] = lang
                    self.rules.append(DetectionRule(**rule_data))

            logger.debug(f"Loaded rules from {rule_file.name}")
        except Exception as e:
            logger.error(f"Error loading rules from {rule_file}: {e}")

    def _load_custom_rules(self, custom_rules: list) -> None:
        """Load custom rules provided at runtime."""
        for rule_data in custom_rules:
            try:
                self.rules.append(DetectionRule(**rule_data))
            except Exception as e:
                logger.error(f"Error loading custom rule: {e}")

    def detect(
        self, content: str, language: Optional[str] = None, file_path: Optional[str] = None
    ) -> list[dict]:
        """Detect risks in code content.

        Args:
            content: Code content to scan
            language: Programming language (optional, for language-specific rules)
            file_path: File path (optional, for context)

        Returns:
            List of detected issues
        """
        issues = []

        for rule in self.rules:
            # Filter by language if specified
            if rule.language and language and rule.language.lower() != language.lower():
                continue

            matches = rule.match(content)
            issues.extend(matches)

        return issues

    def detect_in_diff(self, diff_content: str, language: Optional[str] = None) -> list[dict]:
        """Detect risks in diff content.

        Args:
            diff_content: Diff/patch content
            language: Programming language

        Returns:
            List of detected issues in diff
        """
        issues = []

        # Extract added lines from diff
        added_lines = []
        for line in diff_content.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])  # Remove +

        added_content = "\n".join(added_lines)

        # Run detection on added content
        issues = self.detect(added_content, language)

        return issues

    def get_rules_by_severity(self, severity: str) -> list[DetectionRule]:
        """Get rules by severity level.

        Args:
            severity: Severity level (high, medium, low)

        Returns:
            List of rules matching the severity
        """
        return [r for r in self.rules if r.severity == severity]

    def get_rule_by_id(self, rule_id: str) -> Optional[DetectionRule]:
        """Get a specific rule by ID.

        Args:
            rule_id: Rule ID

        Returns:
            Rule if found, None otherwise
        """
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None

    def disable_rules(self, ids: list[str]) -> list[str]:
        """Disable rules by their IDs.

        Args:
            ids: List of rule IDs to disable

        Returns:
            List of actually disabled rule IDs (excludes invalid IDs)
        """
        disabled = []
        invalid_ids = []

        for rule_id in ids:
            for i, rule in enumerate(self.rules):
                if rule.id == rule_id:
                    self.rules.pop(i)
                    disabled.append(rule_id)
                    break
            else:
                invalid_ids.append(rule_id)

        for invalid_id in invalid_ids:
            logger.warning(f"Rule not found or already disabled: {invalid_id}")

        if disabled:
            logger.info(f"Disabled {len(disabled)} rule(s): {disabled}")

        return disabled


def create_rule_engine(
    rules_dir: Optional[Path] = None, custom_rules: Optional[list] = None
) -> RuleEngine:
    """Create a rule engine instance.

    Args:
        rules_dir: Custom rules directory
        custom_rules: Custom rules to add

    Returns:
        Configured RuleEngine instance
    """
    return RuleEngine(rules_dir=rules_dir, custom_rules=custom_rules)


def get_all_rules() -> list[DetectionRule]:
    """Get all loaded detection rules.

    Returns:
        List of all DetectionRule instances
    """
    engine = RuleEngine()
    return engine.rules


def disable_rules(ids: list[str]) -> list[str]:
    """Disable rules by their IDs.

    Args:
        ids: List of rule IDs to disable

    Returns:
        List of actually disabled rule IDs (excludes invalid IDs)
    """
    engine = RuleEngine()
    return engine.disable_rules(ids)
