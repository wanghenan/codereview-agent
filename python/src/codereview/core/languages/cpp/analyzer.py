"""C++ language analyzer and rules.

This module provides C++-specific code health checks including:
- Memory management (raw pointers, new/delete)
- Smart pointer usage
- RAII compliance
- Resource acquisition patterns
- Thread safety
"""

from __future__ import annotations

import re

from .. import (
    BaseLanguageAnalyzer,
    LanguageAnalysisResult,
    LanguageIssue,
    register_analyzer,
)

# C++-specific detection rules
CPP_RULES = [
    # Memory management
    {
        "id": "CPP-001",
        "name": "Raw new/delete usage",
        "pattern": r"\bnew\s+\w+[^;]*;[^}]*\bdelete\s+",
        "severity": "high",
        "description": "Raw new/delete detected - use smart pointers",
        "suggestion": "Use std::unique_ptr or std::shared_ptr",
    },
    {
        "id": "CPP-002",
        "name": "Memory leak risk",
        "pattern": r"\bnew\s+\w+[^;]*\n(?!\s*delete)",
        "severity": "high",
        "description": "Memory allocated but may not be deleted",
        "suggestion": "Use smart pointers or RAII",
    },
    {
        "id": "CPP-003",
        "name": "Raw pointer without delete",
        "pattern": r"(?:int|float|double|char|void)\s*\*\s*\w+\s*=\s*new",
        "severity": "high",
        "description": "Raw pointer allocation",
        "suggestion": "Use std::unique_ptr<T>",
    },
    {
        "id": "CPP-004",
        "name": "Delete on pointer not from new",
        "pattern": r"delete\s+\w+[^;]*;(?:(?!\s*new\s+).)*",
        "severity": "high",
        "description": "delete on pointer not from new - undefined behavior",
        "suggestion": "Only delete pointers from new",
    },
    # Smart pointers
    {
        "id": "CPP-005",
        "name": "Missing smart pointer",
        "pattern": r"(?:class|struct)\s+\w+\s*\{[^}]*(?:std::|using).*pointer[^}]*\}",
        "severity": "medium",
        "description": "Consider using smart pointers for class members",
        "suggestion": "Use std::unique_ptr or std::shared_ptr",
    },
    {
        "id": "CPP-006",
        "name": "shared_ptr from this",
        "pattern": r"shared_from_this",
        "severity": "medium",
        "description": "Enable shared_from_this on class",
        "suggestion": "Inherit from std::enable_shared_from_this<T>",
    },
    # RAII
    {
        "id": "CPP-007",
        "name": "Non-RAII resource",
        "pattern": r"(?:FILE|fopen|fclose|malloc|free)\s*\(",
        "severity": "medium",
        "description": "Non-RAII resource handling",
        "suggestion": "Use RAII wrappers or smart pointers",
    },
    {
        "id": "CPP-008",
        "name": "Virtual destructor missing",
        "pattern": r"class\s+\w+\s*:.*public\s+\w+\s*\{(?!\s*virtual\s+~)",
        "severity": "high",
        "description": "Base class without virtual destructor",
        "suggestion": "Add virtual destructor to base classes",
    },
    # Thread safety
    {
        "id": "CPP-009",
        "name": "Global mutable state",
        "pattern": r"(?:static|global)\s+\w+\s+\w+\s*[;{](?!\s*const)",
        "severity": "medium",
        "description": "Global mutable state",
        "suggestion": "Consider thread safety for global state",
    },
    {
        "id": "CPP-010",
        "name": "Thread without join",
        "pattern": r"std::thread\s+\w+\s*\([^)]*\)\s*;",
        "severity": "medium",
        "description": "Thread created but may not be joined",
        "suggestion": "Store thread handle and call join() or detach()",
    },
    {
        "id": "CPP-011",
        "name": "Race condition risk",
        "pattern": r"std::mutex\s+\w+\s*;",
        "severity": "medium",
        "description": "Mutex declared but may not be locking properly",
        "suggestion": "Use std::lock_guard or std::unique_lock",
    },
    # Security
    {
        "id": "CPP-012",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|secret|token|key)\s*[:=]\s*[\"'][^\"']+[\"']",
        "severity": "high",
        "description": "Hardcoded credentials detected",
        "suggestion": "Use environment variables or secure storage",
    },
    {
        "id": "CPP-013",
        "name": "Buffer overflow risk",
        "pattern": r"(?:strcpy|strcat|sprintf|gets)\s*\(",
        "severity": "high",
        "description": "Unsafe string functions",
        "suggestion": "Use strncpy, strncat, snprintf, or std::string",
    },
    {
        "id": "CPP-014",
        "name": "Format string vulnerability",
        "pattern": r"printf\s*\(\s*\w+\s*[,)]",
        "severity": "high",
        "description": "Potential format string vulnerability",
        "suggestion": 'Use printf("%s", str) instead of printf(str)',
    },
    {
        "id": "CPP-015",
        "name": "Weak crypto",
        "pattern": r"(?:DES|MD5|SHA1|RC4)\s*\(",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use OpenSSL or libsodium",
    },
    # Performance
    {
        "id": "CPP-016",
        "name": "Copy in loop",
        "pattern": r"for\s*\([^)]+\)\s*\{[^}]*\w+\s+\w+\s*=\s*\w+",
        "severity": "medium",
        "description": "Potential unnecessary copy in loop",
        "suggestion": "Use references or move semantics",
    },
    {
        "id": "CPP-017",
        "name": "Pass by value",
        "pattern": r"(?:void|int|std::\w+)\s+\w+\([^)]*\b\w+\s+\w+\)",
        "severity": "low",
        "description": "Consider passing by const reference",
        "suggestion": "Use const reference for large types",
    },
    # Best practices
    {
        "id": "CPP-018",
        "name": "Using namespace in header",
        "pattern": r"#pragma\s+once.*using\s+namespace\s+std",
        "severity": "medium",
        "description": "using namespace in header pollutes namespace",
        "suggestion": "Use explicit std:: prefix in headers",
    },
    {
        "id": "CPP-019",
        "name": "Empty catch block",
        "pattern": r"catch\s*\(\s*\.\.\.\s*\)\s*\{\s*\}",
        "severity": "medium",
        "description": "Empty catch block",
        "suggestion": "Log exception or handle properly",
    },
    {
        "id": "CPP-020",
        "name": "Magic numbers",
        "pattern": r"(?<![\w\.])[0-9]{2,}(?!\.[0-9])",
        "severity": "low",
        "description": "Magic number detected",
        "suggestion": "Use named constants",
    },
]


@register_analyzer("cpp")
class CppAnalyzer(BaseLanguageAnalyzer):
    """C++ language code analyzer."""

    def __init__(self, language: str = "cpp"):
        super().__init__(language)
        self.rules = CPP_RULES

    def get_rules(self) -> list[dict]:
        """Get C++-specific rules."""
        return self.rules

    def analyze(self, content: str, file_path: str) -> LanguageAnalysisResult:
        """Analyze C++ code for common issues."""
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
