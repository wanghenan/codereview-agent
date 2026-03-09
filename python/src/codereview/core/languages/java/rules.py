"""Java language rules module."""

from typing import Any

JAVA_LANGUAGE_RULES: list[dict[str, Any]] = [
    {
        "id": "JAVA-RULE-001",
        "name": "Resource leak",
        "pattern": r"(?:FileInputStream|Connection|Statement)\s+\w+\s*=",
        "severity": "high",
        "description": "Resource may not be closed properly",
        "suggestion": "Use try-with-resources",
    },
    {
        "id": "JAVA-RULE-002",
        "name": "SQL injection with Statement",
        "pattern": r"Statement\s+.*createStatement|executeQuery.*\+",
        "severity": "high",
        "description": "Potential SQL injection vulnerability",
        "suggestion": "Use PreparedStatement",
    },
    {
        "id": "JAVA-RULE-003",
        "name": "Hardcoded password",
        "pattern": r"password\s*[:=]\s*[\"'][^\"']+[\"']",
        "severity": "high",
        "description": "Hardcoded password detected",
        "suggestion": "Use environment variables",
    },
    {
        "id": "JAVA-RULE-004",
        "name": "Weak crypto",
        "pattern": r"(?:DES|MD5|SHA1)\s*\(",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use AES-256 or stronger",
    },
    {
        "id": "JAVA-RULE-005",
        "name": "Empty catch block",
        "pattern": r"catch\s*\([^)]+\)\s*\{\s*\}",
        "severity": "medium",
        "description": "Empty catch block",
        "suggestion": "Log or handle properly",
    },
    {
        "id": "JAVA-RULE-006",
        "name": "System.out usage",
        "pattern": r"System\.out\.(?:print|println)",
        "severity": "low",
        "description": "Using System.out instead of logging",
        "suggestion": "Use logging framework",
    },
    {
        "id": "JAVA-RULE-007",
        "name": "Catching NPE",
        "pattern": r"catch\s*\(\s*NullPointerException",
        "severity": "high",
        "description": "Catching NullPointerException",
        "suggestion": "Fix root cause of null",
    },
    {
        "id": "JAVA-RULE-008",
        "name": "Raw type usage",
        "pattern": r"(?:List|Map|Set)<>",
        "severity": "medium",
        "description": "Using raw types",
        "suggestion": "Use generic type parameters",
    },
]


def get_java_rules() -> list[dict[str, Any]]:
    """Get Java language rules."""
    return JAVA_LANGUAGE_RULES
