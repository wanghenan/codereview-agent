"""PHP language analyzer and rules.

This module provides PHP-specific code health checks including:
- Security vulnerabilities
- SQL injection prevention
- XSS prevention
- Authentication issues
- Best practices
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import (
    BaseLanguageAnalyzer,
    LanguageAnalysisResult,
    LanguageIssue,
    register_analyzer,
)


# PHP-specific detection rules
PHP_RULES = [
    # Security
    {
        "id": "PHP-001",
        "name": "SQL injection risk",
        "pattern": r"(?:mysql_query|mysqli_query|pg_query|SELECT|INSERT|UPDATE|DELETE).*\$_",
        "severity": "high",
        "description": "Potential SQL injection vulnerability",
        "suggestion": "Use prepared statements",
    },
    {
        "id": "PHP-002",
        "name": "XSS vulnerability",
        "pattern": r"echo\s+.*\$_|print\s+.*\$_|print_r\s*\(\s*\$_",
        "severity": "high",
        "description": "Potential XSS vulnerability",
        "suggestion": "Use htmlspecialchars() or escape output",
    },
    {
        "id": "PHP-003",
        "name": "eval() usage",
        "pattern": r"\beval\s*\(",
        "severity": "high",
        "description": "eval() is dangerous",
        "suggestion": "Avoid eval(), use alternative approaches",
    },
    {
        "id": "PHP-004",
        "name": "File inclusion vulnerability",
        "pattern": r"(?:include|require|include_once|require_once)\s*\(\s*\$_",
        "severity": "high",
        "description": "Dynamic file inclusion",
        "suggestion": "Validate and whitelist included files",
    },
    {
        "id": "PHP-005",
        "name": "Command injection",
        "pattern": r"(?:exec|system|passthru|shell_exec|`)\s*\(\s*\$_",
        "severity": "high",
        "description": "Potential command injection",
        "suggestion": "Sanitize input or use escapeshellarg()",
    },
    {
        "id": "PHP-006",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|passwd|pwd|secret|api_key)\s*=\s*[\"'][^\"']+[\"']",
        "severity": "high",
        "description": "Hardcoded credentials detected",
        "suggestion": "Use environment variables",
    },
    {
        "id": "PHP-007",
        "name": "Weak cryptographic algorithm",
        "pattern": r"(?:md5|sha1|des|crypt)\s*\(",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use password_hash() or openssl",
    },
    {
        "id": "PHP-008",
        "name": "Unserialize vulnerability",
        "pattern": r"unserialize\s*\(\s*\$_",
        "severity": "high",
        "description": "unserialize() with user input is dangerous",
        "suggestion": "Use JSON instead",
    },
    # Error handling
    {
        "id": "PHP-009",
        "name": "Error reporting in production",
        "pattern": r"error_reporting\s*\(\s*E_ALL\s*\)|ini_set\s*\(\s*['\"]display_errors",
        "severity": "medium",
        "description": "Error reporting enabled",
        "suggestion": "Disable display_errors in production",
    },
    {
        "id": "PHP-010",
        "name": "Empty catch block",
        "pattern": r"catch\s*\([^)]+\)\s*\{\s*\}",
        "severity": "medium",
        "description": "Empty catch block",
        "suggestion": "Log or handle the exception",
    },
    # Session security
    {
        "id": "PHP-011",
        "name": "Session without secure flags",
        "pattern": r"session_start\s*\(\s*\)",
        "severity": "medium",
        "description": "Session without secure configuration",
        "suggestion": "Set session.cookie_secure and httponly",
    },
    {
        "id": "PHP-012",
        "name": "CSRF protection missing",
        "pattern": r"(?:form|Form)\s*:[^:]*method\s*=\s*[\"']post[\"']",
        "severity": "medium",
        "description": "Consider adding CSRF protection",
        "suggestion": "Use CSRF tokens",
    },
    # Best practices
    {
        "id": "PHP-013",
        "name": "PHP short tag",
        "pattern": r"<\?[^p]",
        "severity": "medium",
        "description": "PHP short tag may be disabled",
        "suggestion": "Use <?php",
    },
    {
        "id": "PHP-014",
        "name": "Mixed content in arrays",
        "pattern": r"array\s*\([^)]*\[\]|<?\?php",
        "severity": "low",
        "description": "Mixed content in array",
        "suggestion": "Use consistent array syntax",
    },
    {
        "id": "PHP-015",
        "name": "Debug mode enabled",
        "pattern": r"(?:DEBUG|debug)\s*[:=]\s*(?:true|TRUE|1)|defined\s*\(\s*[\"']DEBUG[\"']",
        "severity": "medium",
        "description": "Debug mode enabled",
        "suggestion": "Disable debug in production",
    },
    # Performance
    {
        "id": "PHP-016",
        "name": "Include vs require",
        "pattern": r"include\s+",
        "severity": "low",
        "description": "include may fail silently",
        "suggestion": "Use require for required files",
    },
    {
        "id": "PHP-017",
        "name": "Gzip not enabled",
        "pattern": r"(?:ob_start|ob_gzhandler)",
        "severity": "low",
        "description": "Consider enabling output buffering",
        "suggestion": "Use output buffering for compression",
    },
    # Type safety
    {
        "id": "PHP-018",
        "name": "Loose comparison",
        "pattern": r"==\s*(?!==|!=)",
        "severity": "medium",
        "description": "Loose comparison used",
        "suggestion": "Use === for strict comparison",
    },
    {
        "id": "PHP-019",
        "name": "Variable variables",
        "pattern": r"\$\$\w+",
        "severity": "medium",
        "description": "Variable variables can be insecure",
        "suggestion": "Use arrays instead",
    },
    {
        "id": "PHP-020",
        "name": "Missing type hints",
        "pattern": r"function\s+\w+\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{",
        "severity": "low",
        "description": "Function without return type hint",
        "suggestion": "Add return type hints for PHP 7+",
    },
]


@register_analyzer("php")
class PhpAnalyzer(BaseLanguageAnalyzer):
    """PHP language code analyzer."""

    def __init__(self, language: str = "php"):
        super().__init__(language)
        self.rules = PHP_RULES

    def get_rules(self) -> list[dict]:
        """Get PHP-specific rules."""
        return self.rules

    def analyze(self, content: str, file_path: str) -> LanguageAnalysisResult:
        """Analyze PHP code for common issues."""
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
