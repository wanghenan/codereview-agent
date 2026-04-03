"""Go language analyzer and rules.

This module provides Go-specific code health checks including:
- Goroutine leak detection
- Deferred function checks
- Error handling patterns
- Race condition detection
"""

from __future__ import annotations

import re

from .. import (
    BaseLanguageAnalyzer,
    LanguageAnalysisResult,
    LanguageIssue,
    register_analyzer,
)

# Go-specific detection rules
GO_RULES = [
    # Goroutine leaks
    {
        "id": "GO-001",
        "name": "Goroutine without proper termination",
        "pattern": r"go\s+func\s*\([^)]*\)\s*\{[^}]*(?:for|select)\s*\{",
        "severity": "high",
        "description": "Goroutine may leak if it runs forever without proper exit condition",
        "suggestion": "Add a quit channel or context to properly terminate the goroutine",
    },
    {
        "id": "GO-002",
        "name": "Missing wait for goroutine",
        "pattern": r"go\s+\w+\([^)]*\)[^;]*\n[^g]*$",
        "severity": "medium",
        "description": "Goroutine started without waiting for completion",
        "suggestion": "Use sync.WaitGroup or channels to wait for goroutine completion",
    },
    # Defer issues
    {
        "id": "GO-003",
        "name": "Deferred function with error check",
        "pattern": r"defer\s+\w+\.Close\(",
        "severity": "low",
        "description": "Consider checking error from deferred Close",
        "suggestion": "Use io.Closer interface or handle close errors properly",
    },
    {
        "id": "GO-004",
        "name": "Defers in loops",
        "pattern": r"for\s*\{[^}]*defer\s+",
        "severity": "high",
        "description": "Defers inside loops can accumulate and cause resource leaks",
        "suggestion": "Move defer outside loops or use explicit cleanup",
    },
    # Error handling
    {
        "id": "GO-005",
        "name": "Ignored error return",
        "pattern": r"_\s*=\s*\w+\([^)]*\)\n(?!\s*if\s+)",
        "severity": "medium",
        "description": "Error return value is being ignored",
        "suggestion": "Handle the error properly or document why it can be ignored",
    },
    {
        "id": "GO-006",
        "name": "Empty error check",
        "pattern": r"if\s+err\s*!=\s*nil\s*\{\s*\}",
        "severity": "medium",
        "description": "Error is checked but not handled",
        "suggestion": "Handle the error or return it up the call stack",
    },
    {
        "id": "GO-007",
        "name": "Printf instead of log",
        "pattern": r"fmt\.Print(?:f|ln)\s*\(",
        "severity": "low",
        "description": "Using fmt.Print instead of structured logging",
        "suggestion": "Use log package for logging, consider log/slog for structured logging",
    },
    # Resource management
    {
        "id": "GO-008",
        "name": "HTTP client without timeout",
        "pattern": r"http\.(?:Client|Get|Post|Do)\s*\([^)]*\)(?!.*(?:Timeout|timeout))",
        "severity": "high",
        "description": "HTTP client without timeout can hang indefinitely",
        "suggestion": "Set a timeout on the HTTP client",
    },
    {
        "id": "GO-009",
        "name": "SQL database connection not closed",
        "pattern": r"db,\s*(?:err|error)\s*:=\s*(?:sql\.Open|driver\.Open)\([^)]*\)",
        "severity": "high",
        "description": "Database connection may not be properly closed",
        "suggestion": "Use defer db.Close() after successful connection",
    },
    # Race conditions
    {
        "id": "GO-010",
        "name": "Shared map without mutex",
        "pattern": r"var\s+\w+\s+map\[",
        "severity": "high",
        "description": "Map access without synchronization can cause race conditions",
        "suggestion": "Use sync.Map or protect with sync.RWMutex",
    },
    # Context usage
    {
        "id": "GO-011",
        "name": "Context not passed to downstream calls",
        "pattern": r"func\s+\w+\s*\([^)]*\)\s*(?:\([^)]*error\))?\s*\{[^}]*(?:http\.|sql\.|grpc\.)(?!\s*ctx",
        "severity": "medium",
        "description": "Function should accept and pass context for cancellation",
        "suggestion": "Add ctx context.Context as first parameter and pass it to downstream calls",
    },
    {
        "id": "GO-012",
        "name": "Context with value not checked",
        "pattern": r"ctx\.Value\([^)]+\)",
        "severity": "low",
        "description": "Using context.Value without type assertion",
        "suggestion": "Use type assertion to safely retrieve values from context",
    },
    # Nil checks
    {
        "id": "GO-013",
        "name": "Pointer dereference without nil check",
        "pattern": r"\*\w+\s*(?:\.|\[)",
        "severity": "medium",
        "description": "Potential nil pointer dereference",
        "suggestion": "Add nil check before dereferencing pointers",
    },
    # Slice issues
    {
        "id": "GO-014",
        "name": "Append to nil slice in loop",
        "pattern": r"for\s*\{[^}]*\w+\s*=\s*append\s*\(\s*\w+\s*,",
        "severity": "medium",
        "description": "Appending to nil slice in loop may cause issues",
        "suggestion": "Initialize slice with make() or proper length",
    },
    # Benchmark issues
    {
        "id": "GO-015",
        "name": "Benchmark function missing B.N",
        "pattern": r"func\s+Benchmark\w+\s*\([^)]*b\s+\*testing\.B\s*\)\s*\{(?!\s*for",
        "severity": "low",
        "description": "Benchmark function should use b.N for iteration",
        "suggestion": "Use 'for i := 0; i < b.N; i++' pattern",
    },
]


@register_analyzer("go")
class GoAnalyzer(BaseLanguageAnalyzer):
    """Go language code analyzer."""

    def __init__(self, language: str = "go"):
        super().__init__(language)
        self.rules = GO_RULES

    def get_rules(self) -> list[dict]:
        """Get Go-specific rules."""
        return self.rules

    def analyze(self, content: str, file_path: str) -> LanguageAnalysisResult:
        """Analyze Go code for common issues.

        Args:
            content: Go source code
            file_path: Path to the file

        Returns:
            Analysis result with issues
        """
        issues: list[LanguageIssue] = []

        # Apply each rule
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

        # Calculate health score
        health_score = self._calculate_health_score(issues)

        # Generate summary
        summary = self._generate_summary(issues)

        return LanguageAnalysisResult(
            language=self.language,
            file_path=file_path,
            issues=issues,
            health_score=health_score,
            summary=summary,
        )

    def _find_matches(self, content: str, pattern: str) -> list[dict]:
        """Find pattern matches in content.

        Args:
            content: Source code
            pattern: Regex pattern

        Returns:
            List of matches with line numbers
        """
        matches = []
        try:
            regex = re.compile(pattern, re.MULTILINE | re.DOTALL)
            for line_num, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    matches.append({"line": line_num, "text": line.strip()})
        except re.error:
            pass
        return matches

    def _generate_summary(self, issues: list[LanguageIssue]) -> str:
        """Generate summary of issues.

        Args:
            issues: List of issues found

        Returns:
            Summary string
        """
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

    def _calculate_health_score(self, issues: list[LanguageIssue]) -> float:
        """Calculate health score based on issues."""
        return super()._calculate_health_score(issues)
