"""Rust language analyzer and rules.

This module provides Rust-specific code health checks including:
- Ownership and borrowing checks
- Lifetime analysis
- Unsafe code usage
- Memory safety patterns
- Error handling
"""

from __future__ import annotations

import re

from .. import (
    BaseLanguageAnalyzer,
    LanguageAnalysisResult,
    LanguageIssue,
    register_analyzer,
)

# Rust-specific detection rules
RUST_RULES = [
    # Ownership and Borrowing
    {
        "id": "RUST-001",
        "name": "Cloned data in loop",
        "pattern": r"for\s+\w+\s+in\s+\w+\.iter\(\)\s*\{[^}]*\.clone\(\)",
        "severity": "medium",
        "description": "Unnecessary cloning in loop",
        "suggestion": "Use references or iterators without cloning",
    },
    {
        "id": "RUST-002",
        "name": "Owned value in function taking reference",
        "pattern": r"fn\s+\w+\([^)]*&\w+[^)]*\)[^}]*\w+\(.*\)",
        "severity": "medium",
        "description": "Passing owned value to function expecting reference",
        "suggestion": "Pass reference (&value) or adjust function signature",
    },
    {
        "id": "RUST-003",
        "name": "Mutable and immutable borrow",
        "pattern": r"let\s+mut\s+\w+\s*=.*\n.*let\s+\w+\s*=.*&\w+",
        "severity": "high",
        "description": "Cannot have mutable and immutable borrows simultaneously",
        "suggestion": "Restructure code to avoid simultaneous borrows",
    },
    # Unsafe code
    {
        "id": "RUST-004",
        "name": "Unsafe block without comment",
        "pattern": r"unsafe\s*\{",
        "severity": "medium",
        "description": "Unsafe block should have safety comments",
        "suggestion": "Add safety documentation explaining why unsafe is needed",
    },
    {
        "id": "RUST-005",
        "name": "Pointer manipulation",
        "pattern": r"(?:\*\w+|\.as_ptr\(\)|\.as_mut_ptr\(\))",
        "severity": "medium",
        "description": "Raw pointer manipulation",
        "suggestion": "Use safe abstractions when possible",
    },
    {
        "id": "RUST-006",
        "name": "Unsafe trait implementation",
        "pattern": "unsafe\\s+impl\\s+",
        "severity": "medium",
        "description": "Unsafe trait implementation",
        "suggestion": "Document safety invariants clearly",
    },
    # Error handling
    {
        "id": "RUST-007",
        "name": "Unwrap on Result",
        "pattern": r"\.unwrap\(\)",
        "severity": "medium",
        "description": "Using unwrap() can panic",
        "suggestion": "Use ? operator or proper error handling",
    },
    {
        "id": "RUST-008",
        "name": "Expect on Result",
        "pattern": r"\.expect\(",
        "severity": "medium",
        "description": "Using expect() can panic with custom message",
        "suggestion": "Use ? or handle errors explicitly",
    },
    {
        "id": "RUST-009",
        "name": "Ignored Result",
        "pattern": r"let\s+_\s*=.*\.(?:ok|err)\(\)",
        "severity": "low",
        "description": "Result value is being ignored",
        "suggestion": "Handle the Result properly",
    },
    # Lifetimes
    {
        "id": "RUST-010",
        "name": "Missing lifetime annotation",
        "pattern": r"fn\s+\w+\([^)]*&[^\s,)]+\s*[^)]*\)[^;{]*->[^;{]*&",
        "severity": "medium",
        "description": "Function returning reference may need lifetime annotation",
        "suggestion": "Add explicit lifetime parameters",
    },
    {
        "id": "RUST-011",
        "name": "Lifetimes in struct",
        "pattern": r"struct\s+\w+\s*\{[^}]*&str",
        "severity": "medium",
        "description": "Struct contains reference, needs lifetime",
        "suggestion": "Add lifetime parameter to struct",
    },
    # Performance
    {
        "id": "RUST-012",
        "name": "String concatenation in loop",
        "pattern": r"for\s*\{[^}]*\+\=.*push_str",
        "severity": "medium",
        "description": "String concatenation in loop is inefficient",
        "suggestion": "Use String::push_str or format! outside loop",
    },
    {
        "id": "RUST-013",
        "name": "Pre-allocation hint",
        "pattern": r"Vec::new\(\)(?!.*with_capacity)",
        "severity": "low",
        "description": "Vec with unknown size may reallocate",
        "suggestion": "Use Vec::with_capacity() if size is known",
    },
    # Concurrency
    {
        "id": "RUST-014",
        "name": "Shared state without synchronization",
        "pattern": r"Arc\s*<\s*Mutex\s*<",
        "severity": "medium",
        "description": "Using Arc<Mutex<T>> for shared state",
        "suggestion": "Ensure proper locking discipline",
    },
    {
        "id": "RUST-015",
        "name": "Thread spawn without join",
        "pattern": r"thread::spawn\([^)]*\);",
        "severity": "medium",
        "description": "Thread spawned but may not be joined",
        "suggestion": "Store handle and call join()",
    },
    # Security
    {
        "id": "RUST-016",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|secret|token|api_key)\s*[:=]\s*[\"'][^\"']+[\"']",
        "severity": "high",
        "description": "Hardcoded credentials detected",
        "suggestion": "Use environment variables or secrets manager",
    },
    {
        "id": "RUST-017",
        "name": "Weak crypto",
        "pattern": r"(?:md5|sha1|des|crypto::(?:md5|sha1))",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use ring or rustls for modern crypto",
    },
    # Logging
    {
        "id": "RUST-018",
        "name": "Debug println",
        "pattern": r"println!\s*\(\s*\"[^\"]*\"",
        "severity": "low",
        "description": "Debug print statement found",
        "suggestion": "Use proper logging crate (log, tracing)",
    },
    # Best practices
    {
        "id": "RUST-019",
        "name": "Unused variable",
        "pattern": r"let\s+\w+\s*[:=][^;]+;",
        "severity": "low",
        "description": "Variable may be unused",
        "suggestion": "Use _ prefix or #[allow(unused)]",
    },
    {
        "id": "RUST-020",
        "name": "Clone for Copy type",
        "pattern": r"\.clone\(\).*(?:i32|u32|i64|u64|f32|f64|bool|char)",
        "severity": "low",
        "description": "Unnecessary clone on Copy type",
        "suggestion": "Copy types don't need cloning",
    },
]


@register_analyzer("rust")
class RustAnalyzer(BaseLanguageAnalyzer):
    """Rust language code analyzer."""

    def __init__(self, language: str = "rust"):
        super().__init__(language)
        self.rules = RUST_RULES

    def get_rules(self) -> list[dict]:
        """Get Rust-specific rules."""
        return self.rules

    def analyze(self, content: str, file_path: str) -> LanguageAnalysisResult:
        """Analyze Rust code for common issues."""
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
