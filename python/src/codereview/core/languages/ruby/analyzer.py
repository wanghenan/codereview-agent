"""Ruby language analyzer and rules.

This module provides Ruby-specific code health checks including:
- Security vulnerabilities
- Rails-specific issues
- Performance patterns
- Best practices
"""

from __future__ import annotations

import re

from .. import (
    BaseLanguageAnalyzer,
    LanguageAnalysisResult,
    LanguageIssue,
    register_analyzer,
)

# Ruby-specific detection rules
RUBY_RULES = [
    # Security
    {
        "id": "RUBY-001",
        "name": "SQL injection risk",
        "pattern": r"(?:find_by_sql|execute|update.*where|delete.*where).*[\"#\{]",
        "severity": "high",
        "description": "Potential SQL injection vulnerability",
        "suggestion": "Use parameterized queries or ActiveRecord methods",
    },
    {
        "id": "RUBY-002",
        "name": "Command injection",
        "pattern": r"(?:system|exec|`|\%x|open).*\#\{",
        "severity": "high",
        "description": "Potential command injection",
        "suggestion": "Sanitize input or use Shellwords.escape",
    },
    {
        "id": "RUBY-003",
        "name": "Eval usage",
        "pattern": r"\b(?:eval|instance_eval|class_eval|module_eval)\s*\(",
        "severity": "high",
        "description": "eval() is dangerous",
        "suggestion": "Avoid eval(), use alternative approaches",
    },
    {
        "id": "RUBY-004",
        "name": "Dangerous YAML load",
        "pattern": r"YAML\.load\s*\(",
        "severity": "high",
        "description": "YAML.load can execute arbitrary code",
        "suggestion": "Use YAML.safe_load for untrusted input",
    },
    {
        "id": "RUBY-005",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|passwd|secret|api_key|apikey)\s*[:=]\s*['\"][^'\"]+['\"]",
        "severity": "high",
        "description": "Hardcoded credentials detected",
        "suggestion": "Use environment variables or credentials",
    },
    {
        "id": "RUBY-006",
        "name": "Weak cryptographic algorithm",
        "pattern": r"(?:Digest::MD5|Digest::SHA1|DES|RC4)",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use bcrypt or modern crypto",
    },
    {
        "id": "RUBY-007",
        "name": "Mass assignment vulnerability",
        "pattern": r"(?:update|create|new)\s*\(\s*params\[",
        "severity": "high",
        "description": "Potential mass assignment vulnerability",
        "suggestion": "Use strong parameters",
    },
    {
        "id": "RUBY-008",
        "name": "Cross-site scripting",
        "pattern": r"(?:raw|html_safe|content_tag)\s*\(",
        "severity": "high",
        "description": "Potential XSS vulnerability",
        "suggestion": "Sanitize before marking as safe",
    },
    # Rails specific
    {
        "id": "RUBY-009",
        "name": "Find without limit",
        "pattern": r"(?:Model|where|all)\.find\(",
        "severity": "medium",
        "description": "Find without limit may load large datasets",
        "suggestion": "Use .limit() or pagination",
    },
    {
        "id": "RUBY-010",
        "name": "N+1 query problem",
        "pattern": r"(?:each|map|collect).*do\s*\|[^|]*\|[^}]*\.find\(|has_many.*do\s*\|",
        "severity": "medium",
        "description": "Potential N+1 query problem",
        "suggestion": "Use includes or eager loading",
    },
    {
        "id": "RUBY-011",
        "name": "Skip CSRF verification",
        "pattern": r"skip_before_action\s*:\s*:verify_authenticity_token",
        "severity": "high",
        "description": "CSRF verification skipped",
        "suggestion": "Ensure CSRF protection is needed",
    },
    {
        "id": "RUBY-012",
        "name": "Bypass validation",
        "pattern": r"save!\s*\(|update!\s*\(",
        "severity": "medium",
        "description": "Using bang method bypasses validation",
        "suggestion": "Handle exceptions or use save with validation",
    },
    # Best practices
    {
        "id": "RUBY-013",
        "name": "Missing else branch",
        "pattern": r"case\s+\w+\s*\n(?!\s*else)",
        "severity": "low",
        "description": "Case statement without else",
        "suggestion": "Add else branch for handling unexpected values",
    },
    {
        "id": "RUBY-014",
        "name": "Global variable",
        "pattern": r"\$[a-zA-Z_]",
        "severity": "medium",
        "description": "Global variable detected",
        "suggestion": "Use class or instance variables",
    },
    {
        "id": "RUBY-015",
        "name": "Ruby1.9 hash syntax",
        "pattern": r":\w+\s*=>",
        "severity": "low",
        "description": "Old hash syntax",
        "suggestion": "Use new hash syntax: key: value",
    },
    {
        "id": "RUBY-016",
        "name": "Debugger left in code",
        "pattern": r"(?:binding\.pry|byebug|debugger|save_and_open_page)",
        "severity": "medium",
        "description": "Debug code left in production",
        "suggestion": "Remove debug statements",
    },
    # Performance
    {
        "id": "RUBY-017",
        "name": "Each vs map",
        "pattern": r"\.each\s*\{[^}]*\push\(",
        "severity": "low",
        "description": "Using each with push instead of map",
        "suggestion": "Use map for transformation",
    },
    {
        "id": "RUBY-018",
        "name": "String concatenation in loop",
        "pattern": r"(?:loop|each|times)\s*\{[^}]*\+=\s*[\"']",
        "severity": "medium",
        "description": "String concatenation in loop",
        "suggestion": "Use Array#join or String#concat",
    },
    {
        "id": "RUBY-019",
        "name": "Dynamic constant",
        "pattern": r"def\s+[A-Z]\w+\s*\(",
        "severity": "medium",
        "description": "Method name starts with uppercase - possible constant",
        "suggestion": "Use lowercase for method names",
    },
    {
        "id": "RUBY-020",
        "name": "Parallel assignment",
        "pattern": r"^\s*\w+\s*,\s*\w+\s*=\s*",
        "severity": "low",
        "description": "Parallel assignment detected",
        "suggestion": "Use separate assignments for clarity",
    },
]


@register_analyzer("ruby")
class RubyAnalyzer(BaseLanguageAnalyzer):
    """Ruby language code analyzer."""

    def __init__(self, language: str = "ruby"):
        super().__init__(language)
        self.rules = RUBY_RULES

    def get_rules(self) -> list[dict]:
        """Get Ruby-specific rules."""
        return self.rules

    def analyze(self, content: str, file_path: str) -> LanguageAnalysisResult:
        """Analyze Ruby code for common issues."""
        issues: list[LanguageIssue] = []

        for rule in self.rules:
            pattern = rule["pattern"]
            matches = self._find_matches(content, pattern)

            for match in matches:
                issues.append(
                    LanguageIssue(
                        rule_id=rule["id"],
                        rule_name=rule["name"],
                        line_number=match["line"],
                        severity=rule["severity"],
                        description=rule["description"],
                        suggestion=rule["suggestion"],
                        language=self.language,
                    )
                )

        health_score = self._calculate_health_score(issues)
        summary = self._generate_summary(issues)

        return LanguageAnalysisResult(
            language=self.language,
            file_path=file_path,
            issues=issues,
            health_score=health_score,
            summary=summary,
        )

    def _find_matches(self, content: str, pattern: str) -> list[dict]:
        """Find pattern matches in content."""
        matches = []
        try:
            regex = re.compile(pattern, re.MULTILINE)
            for line_num, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    matches.append({"line": line_num, "text": line.strip()})
        except re.error:
            pass
        return matches

    def _generate_summary(self, issues: list[LanguageIssue]) -> str:
        """Generate summary of issues."""
        if not issues:
            return "No issues found. Code looks healthy."

        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")

        parts = []
        if high:
            parts.append(f"{high} high severity")
        if medium:
            parts.append(f"{medium} medium severity")
        if low:
            parts.append(f"{low} low severity")

        return f"Found {len(issues)} issue(s): {', '.join(parts)}"
