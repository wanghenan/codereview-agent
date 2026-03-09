"""C# language rules module."""

from typing import Any

CSHARP_LANGUAGE_RULES: list[dict[str, Any]] = [
    {
        "id": "CSHARP-RULE-001",
        "name": "SQL injection",
        "pattern": r"(?:SqlCommand|executeQuery).*\+",
        "severity": "high",
        "description": "SQL injection vulnerability",
        "suggestion": "Use parameterized queries",
    },
    {
        "id": "CSHARP-RULE-002",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|secret|key)\s*[:=]\s*[\"']",
        "severity": "high",
        "description": "Hardcoded credentials",
        "suggestion": "Use config/secrets",
    },
    {
        "id": "CSHARP-RULE-003",
        "name": "Weak crypto",
        "pattern": r"(?:DESCrypto|MD5|SHA1)",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use AES-256",
    },
    {
        "id": "CSHARP-RULE-004",
        "name": "Resource leak",
        "pattern": r"(?:Stream|Reader|Writer)\s+\w+\s*=.*new",
        "severity": "high",
        "description": "Resource may not be disposed",
        "suggestion": "Use using statement",
    },
    {
        "id": "CSHARP-RULE-005",
        "name": "Blocking async",
        "pattern": r"\.Result|\.Wait\(\)",
        "severity": "high",
        "description": "Blocking on async can deadlock",
        "suggestion": "Use await",
    },
    {
        "id": "CSHARP-RULE-006",
        "name": "Empty catch",
        "pattern": r"catch\s*\([^)]+\)\s*\{\s*\}",
        "severity": "medium",
        "description": "Empty catch block",
        "suggestion": "Handle exception",
    },
    {
        "id": "CSHARP-RULE-007",
        "name": "XSS vuln",
        "pattern": r"\.InnerHtml\s*=",
        "severity": "high",
        "description": "XSS vulnerability",
        "suggestion": "Use InnerText",
    },
    {
        "id": "CSHARP-RULE-008",
        "name": "Catching NRE",
        "pattern": r"catch\s*\(\s*NullReferenceException",
        "severity": "high",
        "description": "Catching NullReferenceException",
        "suggestion": "Fix root cause",
    },
]


def get_csharp_rules() -> list[dict[str, Any]]:
    """Get C# language rules."""
    return CSHARP_LANGUAGE_RULES
