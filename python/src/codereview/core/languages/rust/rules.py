"""Rust language rules module."""

from typing import Any

RUST_LANGUAGE_RULES: list[dict[str, Any]] = [
    {
        "id": "RUST-RULE-001",
        "name": "Unsafe block",
        "pattern": r"unsafe\s*\{",
        "severity": "medium",
        "description": "Unsafe code block requires safety comments",
        "suggestion": "Document safety invariants",
    },
    {
        "id": "RUST-RULE-002",
        "name": "Unwrap usage",
        "pattern": r"\.unwrap\(\)",
        "severity": "medium",
        "description": "unwrap() can panic",
        "suggestion": "Use ? operator or proper error handling",
    },
    {
        "id": "RUST-RULE-003",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|secret|token)\s*[:=]\s*[\"']",
        "severity": "high",
        "description": "Hardcoded credentials",
        "suggestion": "Use environment variables",
    },
    {
        "id": "RUST-RULE-004",
        "name": "Debug println",
        "pattern": r"println!\s*\(",
        "severity": "low",
        "description": "Debug print found",
        "suggestion": "Use logging crate",
    },
    {
        "id": "RUST-RULE-005",
        "name": "Weak crypto",
        "pattern": r"(?:md5|sha1|des)",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use modern crypto libraries",
    },
    {
        "id": "RUST-RULE-006",
        "name": "Mutable borrow in loop",
        "pattern": r"for\s+[^}]+&mut\s+",
        "severity": "medium",
        "description": "Mutable borrow in loop",
        "suggestion": "Ensure safe borrowing pattern",
    },
]


def get_rust_rules() -> list[dict[str, Any]]:
    """Get Rust language rules."""
    return RUST_LANGUAGE_RULES
