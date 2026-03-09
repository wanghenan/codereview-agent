"""Ruby language rules module."""

from typing import Any

RUBY_LANGUAGE_RULES: list[dict[str, Any]] = [
    {
        "id": "RUBY-RULE-001",
        "name": "SQL injection",
        "pattern": r"(?:find_by_sql|execute).*[\"#\{]",
        "severity": "high",
        "description": "SQL injection vulnerability",
        "suggestion": "Use parameterized queries",
    },
    {
        "id": "RUBY-RULE-002",
        "name": "Command injection",
        "pattern": r"(?:system|exec|`).*\#\{",
        "severity": "high",
        "description": "Command injection risk",
        "suggestion": "Sanitize input",
    },
    {
        "id": "RUBY-RULE-003",
        "name": "eval() usage",
        "pattern": r"\b(?:eval|instance_eval)\s*\(",
        "severity": "high",
        "description": "eval() is dangerous",
        "suggestion": "Avoid eval()",
    },
    {
        "id": "RUBY-RULE-004",
        "name": "YAML load",
        "pattern": r"YAML\.load\s*\(",
        "severity": "high",
        "description": "YAML.load can execute code",
        "suggestion": "Use YAML.safe_load",
    },
    {
        "id": "RUBY-RULE-005",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|secret|key)\s*[:=]\s*['\"]",
        "severity": "high",
        "description": "Hardcoded credentials",
        "suggestion": "Use env vars",
    },
    {
        "id": "RUBY-RULE-006",
        "name": "Weak crypto",
        "pattern": r"(?:MD5|SHA1|DES)",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use bcrypt",
    },
    {
        "id": "RUBY-RULE-007",
        "name": "XSS vuln",
        "pattern": r"(?:raw|html_safe)\s*\(",
        "severity": "high",
        "description": "XSS vulnerability",
        "suggestion": "Sanitize input",
    },
    {
        "id": "RUBY-RULE-008",
        "name": "N+1 query",
        "pattern": r"\.each.*\.find\(",
        "severity": "medium",
        "description": "Potential N+1 query",
        "suggestion": "Use includes",
    },
]


def get_ruby_rules() -> list[dict[str, Any]]:
    """Get Ruby language rules."""
    return RUBY_LANGUAGE_RULES
