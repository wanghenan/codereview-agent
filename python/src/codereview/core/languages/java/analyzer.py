"""Java language analyzer and rules.

This module provides Java-specific code health checks including:
- Resource leak detection (try-with-resources)
- Concurrency safety
- Generic type warnings
- Null pointer safety
- SQL injection prevention
"""

from __future__ import annotations

import re

from .. import (
    BaseLanguageAnalyzer,
    LanguageAnalysisResult,
    LanguageIssue,
    register_analyzer,
)

# Java-specific detection rules
JAVA_RULES = [
    # Resource management
    {
        "id": "JAVA-001",
        "name": "Resource not closed",
        "pattern": r"(?:FileInputStream|FileOutputStream|BufferedReader|BufferedWriter|Connection|Statement|ResultSet|Cursor)\s+\w+\s*=.*(?:new|\.open)",
        "severity": "high",
        "description": "Resource may not be properly closed, causing leaks",
        "suggestion": "Use try-with-resources or explicitly close in finally block",
    },
    {
        "id": "JAVA-002",
        "name": "Database resource leak",
        "pattern": r"(?:Connection|Statement|PreparedStatement|ResultSet)\s+\w+\s*=\s*(?:DriverManager|dataSource\.getConnection)",
        "severity": "high",
        "description": "Database resource should be closed properly",
        "suggestion": "Use try-with-resources for database connections",
    },
    # Concurrency
    {
        "id": "JAVA-003",
        "name": "Thread synchronization missing",
        "pattern": r"(?:public|protected)\s+(?:static\s+)?\w+\s+\w+\s*[;{]",
        "severity": "medium",
        "description": "Shared mutable state may need synchronization",
        "suggestion": "Use synchronized blocks or java.util.concurrent utilities",
    },
    {
        "id": "JAVA-004",
        "name": "Thread.start() without join",
        "pattern": r"\w+\.start\(\);[^}]*$(?!\s*\.join\()",
        "severity": "medium",
        "description": "Thread started but not joined - may cause unexpected behavior",
        "suggestion": "Call join() to wait for thread completion",
    },
    {
        "id": "JAVA-005",
        "name": "Using Date/Time classes instead of modern API",
        "pattern": r"(?:Date|Calendar|TimeZone|SimpleDateFormat)\s*\.",
        "severity": "low",
        "description": "Using legacy Date/Time classes",
        "suggestion": "Use java.time API (LocalDateTime, ZonedDateTime, etc.)",
    },
    # Null safety
    {
        "id": "JAVA-006",
        "name": "Potential NullPointerException",
        "pattern": r"\w+\.\w+\([^)]*\)(?!\s*\.orElse)",
        "severity": "medium",
        "description": "Potential NPE if object is null",
        "suggestion": "Add null checks or use Optional",
    },
    {
        "id": "JAVA-007",
        "name": "Catching NullPointerException",
        "pattern": r"catch\s*\(\s*NullPointerException\s+\w+\s*\)",
        "severity": "high",
        "description": "Catching NPE is a code smell",
        "suggestion": "Fix the root cause of null instead of catching NPE",
    },
    # Generics
    {
        "id": "JAVA-008",
        "name": "Raw type usage",
        "pattern": r"List\s*<[^>]>\s+|Map\s*<[^>]>\s+|Set\s*<[^>]>\s+",
        "severity": "medium",
        "description": "Using raw types instead of parameterized generics",
        "suggestion": "Use proper generic type parameters",
    },
    {
        "id": "JAVA-009",
        "name": "Unchecked cast",
        "pattern": r"\(\s*(?:List|Map|Set|Collection)\s*\)",
        "severity": "medium",
        "description": "Unchecked type cast",
        "suggestion": "Use generics to avoid unchecked casts",
    },
    # SQL Injection
    {
        "id": "JAVA-010",
        "name": "SQL injection risk with Statement",
        "pattern": r"Statement\s+\w+\s*=.*createStatement|executeQuery\s*\(\s*[\"'].*\+",
        "severity": "high",
        "description": "Potential SQL injection vulnerability",
        "suggestion": "Use PreparedStatement with parameterized queries",
    },
    {
        "id": "JAVA-011",
        "name": "String concatenation in SQL",
        "pattern": r"(?:executeQuery|executeUpdate|prepareStatement)\s*\(\s*[\"'][^\"']*\+",
        "severity": "high",
        "description": "String concatenation in SQL query",
        "suggestion": "Use parameterized queries instead",
    },
    # Security
    {
        "id": "JAVA-012",
        "name": "Hardcoded password",
        "pattern": r"(?:password|passwd|pwd|secret)\s*[:=]\s*[\"'][^\"']+[\"']",
        "severity": "high",
        "description": "Hardcoded credentials detected",
        "suggestion": "Use environment variables or a secure vault",
    },
    {
        "id": "JAVA-013",
        "name": "Weak cryptographic algorithm",
        "pattern": r"(?:DES|MD5|SHA1|RC4)\s*\(",
        "severity": "high",
        "description": "Weak cryptographic algorithm detected",
        "suggestion": "Use AES-256 or stronger algorithms",
    },
    # Performance
    {
        "id": "JAVA-014",
        "name": "String concatenation in loop",
        "pattern": r"for\s*\([^)]+\)\s*\{[^}]*[\"'][^\"']*[\"']\s*\+=\s*\w+",
        "severity": "medium",
        "description": "String concatenation in loop is inefficient",
        "suggestion": "Use StringBuilder for string concatenation in loops",
    },
    {
        "id": "JAVA-015",
        "name": "Empty catch block",
        "pattern": r"catch\s*\([^)]+\)\s*\{\s*\}",
        "severity": "medium",
        "description": "Empty catch block silently swallows exceptions",
        "suggestion": "Log the exception or handle it properly",
    },
    # Logging
    {
        "id": "JAVA-016",
        "name": "Sensitive data in logs",
        "pattern": r"log\.(?:info|debug|warn|error)\s*\([^)]*(?:password|token|secret|key)[^)]*\)",
        "severity": "high",
        "description": "Sensitive data may be logged",
        "suggestion": "Avoid logging sensitive information",
    },
    {
        "id": "JAVA-017",
        "name": "System.out usage",
        "pattern": r"System\.(?:out|err)\.(?:print|println)",
        "severity": "low",
        "description": "Using System.out instead of proper logging",
        "suggestion": "Use a logging framework (log4j, slf4j, etc.)",
    },
    # API Design
    {
        "id": "JAVA-018",
        "name": "Returning null instead of empty collection",
        "pattern": r"return\s+null\s*;.*\n.*(?:List|Map|Set|Collection)",
        "severity": "medium",
        "description": "Returning null instead of empty collection",
        "suggestion": "Return empty collections instead of null",
    },
    {
        "id": "JAVA-019",
        "name": "Public mutable field",
        "pattern": r"public\s+(?:static\s+)?(?:final\s+)?\w+\s+\w+\s*[;{]",
        "severity": "medium",
        "description": "Public mutable fields break encapsulation",
        "suggestion": "Use private fields with getters/setters",
    },
    {
        "id": "JAVA-020",
        "name": "Class without serialVersionUID",
        "pattern": r"class\s+\w+\s+implements\s+Serializable\s*\{(?!\s*private\s+static\s+final\s+long\s+serialVersionUID)",
        "severity": "low",
        "description": "Serializable class should declare serialVersionUID",
        "suggestion": "Add private static final long serialVersionUID",
    },
]


@register_analyzer("java")
class JavaAnalyzer(BaseLanguageAnalyzer):
    """Java language code analyzer."""

    def __init__(self, language: str = "java"):
        super().__init__(language)
        self.rules = JAVA_RULES

    def get_rules(self) -> list[dict]:
        """Get Java-specific rules."""
        return self.rules

    def analyze(self, content: str, file_path: str) -> LanguageAnalysisResult:
        """Analyze Java code for common issues.

        Args:
            content: Java source code
            file_path: Path to the file

        Returns:
            Analysis result with issues
        """
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
