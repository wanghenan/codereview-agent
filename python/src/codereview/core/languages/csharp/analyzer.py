"""C# language analyzer and rules.

This module provides C#-specific code health checks including:
- Security vulnerabilities
- Async/await patterns
- IDisposable patterns
- Null handling
- Performance patterns
"""

from __future__ import annotations

import re

from .. import (
    BaseLanguageAnalyzer,
    LanguageAnalysisResult,
    LanguageIssue,
    register_analyzer,
)

# C#-specific detection rules
CSHARP_RULES = [
    # Security
    {
        "id": "CSHARP-001",
        "name": "SQL injection risk",
        "pattern": r"(?:SqlCommand|SqlDataAdapter|OleDbCommand).*\+.*(?:Request|Query|param)",
        "severity": "high",
        "description": "Potential SQL injection vulnerability",
        "suggestion": "Use parameterized queries or Entity Framework",
    },
    {
        "id": "CSHARP-002",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|passwd|secret|api_key|connectionString)\s*[:=]\s*[\"'][^\"']+[\"']",
        "severity": "high",
        "description": "Hardcoded credentials detected",
        "suggestion": "Use configuration or secrets management",
    },
    {
        "id": "CSHARP-003",
        "name": "Weak cryptographic algorithm",
        "pattern": r"(?:DESCryptoServiceProvider|MD5CryptoServiceProvider|SHA1CryptoServiceProvider)",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use AES-256 or SHA256+",
    },
    {
        "id": "CSHARP-004",
        "name": "XSS vulnerability",
        "pattern": r"(?:InnerHtml|HtmlRaw|innerHTML)\s*=",
        "severity": "high",
        "description": "Potential XSS vulnerability",
        "suggestion": "Use InnerText or encode input",
    },
    {
        "id": "CSHARP-005",
        "name": "Path traversal",
        "pattern": r"(?:File|OpenRead|OpenWrite).*Request\.",
        "severity": "high",
        "description": "Potential path traversal",
        "suggestion": "Validate and sanitize file paths",
    },
    # Resource management
    {
        "id": "CSHARP-006",
        "name": "Resource not disposed",
        "pattern": r"(?:Stream|Reader|Writer|Connection|Command)\s+\w+\s*=\s*new",
        "severity": "high",
        "description": "Resource may not be properly disposed",
        "suggestion": "Use using statement",
    },
    {
        "id": "CSHARP-007",
        "name": "Missing IDisposable",
        "pattern": r"class\s+\w+\s*:\s*(?!IDisposable)",
        "severity": "medium",
        "description": "Class with unmanaged resources should implement IDisposable",
        "suggestion": "Implement IDisposable pattern",
    },
    {
        "id": "CSHARP-008",
        "name": "Empty catch block",
        "pattern": r"catch\s*\([^)]+\)\s*\{\s*\}",
        "severity": "medium",
        "description": "Empty catch block",
        "suggestion": "Log or handle exception properly",
    },
    # Async/await
    {
        "id": "CSHARP-009",
        "name": "Async without await",
        "pattern": r"async\s+task\w*\s+",
        "severity": "medium",
        "description": "Async method without await",
        "suggestion": "Use Task.Run or remove async",
    },
    {
        "id": "CSHARP-010",
        "name": "Blocking on async",
        "pattern": r"\.Result\s*;|\.Wait\(\)\s*;|\.GetAwaiter\(\)\.GetResult\(\)",
        "severity": "high",
        "description": "Blocking on async code can cause deadlocks",
        "suggestion": "Use await instead",
    },
    # Null handling
    {
        "id": "CSHARP-011",
        "name": "Null check missing",
        "pattern": r"\w+\.\w+\([^)]*\)(?!\s*\.HasValue)",
        "severity": "medium",
        "description": "Potential NullReferenceException",
        "suggestion": "Add null check or use null-conditional operator",
    },
    {
        "id": "CSHARP-012",
        "name": "Catching NullReferenceException",
        "pattern": r"catch\s*\(\s*NullReferenceException",
        "severity": "high",
        "description": "Catching NullReferenceException",
        "suggestion": "Fix the root cause of null",
    },
    # Performance
    {
        "id": "CSHARP-013",
        "name": "String concatenation in loop",
        "pattern": r"for\s*\{[^}]*\+=\s*[\"']",
        "severity": "medium",
        "description": "String concatenation in loop",
        "suggestion": "Use StringBuilder",
    },
    {
        "id": "CSHARP-014",
        "name": "LINQ multiple enumeration",
        "pattern": r"\.ToList\(\).*\.ToList\(\)|\.Count\(\).*\.Count\(\)",
        "severity": "medium",
        "description": "Multiple enumeration of IEnumerable",
        "suggestion": "Store result in variable",
    },
    {
        "id": "CSHARP-015",
        "name": "Missing optimization attributes",
        "pattern": r"\[MethodImpl\(MethodImplOptions\.NoInlining\)\]",
        "severity": "low",
        "description": "Consider optimization attributes",
        "suggestion": "Use AggressiveInlining for small methods",
    },
    # Best practices
    {
        "id": "CSHARP-016",
        "name": "Obsolete API",
        "pattern": r"\[Obsolete\(",
        "severity": "low",
        "description": "Using obsolete API",
        "suggestion": "Use modern alternatives",
    },
    {
        "id": "CSHARP-017",
        "name": "Debug code in release",
        "pattern": r"#if\s+DEBUG.*Console\.Write|#if\s+DEBUG.*Debug\.Write",
        "severity": "low",
        "description": "Debug code left in code",
        "suggestion": "Use conditional logging",
    },
    {
        "id": "CSHARP-018",
        "name": "Magic numbers",
        "pattern": r"(?<![\w\.])[0-9]{2,}(?!\.[0-9])",
        "severity": "low",
        "description": "Magic number detected",
        "suggestion": "Use named constants",
    },
    {
        "id": "CSHARP-019",
        "name": "Public fields",
        "pattern": r"public\s+(?:static\s+)?(?!\w+\s+).*(?<!)\s+\w+\s*[;{]",
        "severity": "medium",
        "description": "Public fields break encapsulation",
        "suggestion": "Use properties",
    },
    {
        "id": "CSHARP-020",
        "name": "Sealed class",
        "pattern": r"sealed\s+class",
        "severity": "low",
        "description": "Sealed class prevents inheritance",
        "suggestion": "Consider if sealing is appropriate",
    },
]


@register_analyzer("csharp")
class CSharpAnalyzer(BaseLanguageAnalyzer):
    """C# language code analyzer."""

    def __init__(self, language: str = "csharp"):
        super().__init__(language)
        self.rules = CSHARP_RULES

    def get_rules(self) -> list[dict]:
        """Get C#-specific rules."""
        return self.rules

    def analyze(self, content: str, file_path: str) -> LanguageAnalysisResult:
        """Analyze C# code for common issues."""
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
