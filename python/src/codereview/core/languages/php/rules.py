"""PHP language rules module."""

from typing import Any

PHP_LANGUAGE_RULES: list[dict[str, Any]] = [
    {
        "id": "PHP-RULE-001",
        "name": "SQL injection",
        "pattern": r"(?:mysql_query|mysqli_query|SELECT|INSERT).*\$_",
        "severity": "high",
        "description": "SQL injection vulnerability",
        "suggestion": "Use prepared statements",
    },
    {
        "id": "PHP-RULE-002",
        "name": "XSS vuln",
        "pattern": r"echo\s+.*\$_|print\s+.*\$_",
        "severity": "high",
        "description": "XSS vulnerability",
        "suggestion": "Use htmlspecialchars()",
    },
    {
        "id": "PHP-RULE-003",
        "name": "eval() usage",
        "pattern": r"\beval\s*\(",
        "severity": "high",
        "description": "eval() is dangerous",
        "suggestion": "Avoid eval()",
    },
    {
        "id": "PHP-RULE-004",
        "name": "Command injection",
        "pattern": r"(?:exec|system|shell_exec|`)\s*\(\s*\$_",
        "severity": "high",
        "description": "Command injection risk",
        "suggestion": "Sanitize input",
    },
    {
        "id": "PHP-RULE-005",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|secret|key)\s*=\s*[\"']",
        "severity": "high",
        "description": "Hardcoded credentials",
        "suggestion": "Use env vars",
    },
    {
        "id": "PHP-RULE-006",
        "name": "Weak crypto",
        "pattern": r"(?:md5|sha1|des|crypt)\s*\(",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use password_hash()",
    },
    {
        "id": "PHP-RULE-007",
        "name": "Error reporting",
        "pattern": r"error_reporting\s*\(\s*E_ALL",
        "severity": "medium",
        "description": "Error reporting enabled",
        "suggestion": "Disable in production",
    },
    {
        "id": "PHP-RULE-008",
        "name": "Empty catch",
        "pattern": r"catch\s*\([^)]+\)\s*\{\s*\}",
        "severity": "medium",
        "description": "Empty catch block",
        "suggestion": "Handle exception",
    },
]


def get_php_rules() -> list[dict[str, Any]]:
    """Get PHP language rules."""
    return PHP_LANGUAGE_RULES
