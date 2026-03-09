"""C++ language rules module."""

from typing import Any

CPP_LANGUAGE_RULES: list[dict[str, Any]] = [
    {
        "id": "CPP-RULE-001",
        "name": "Raw new/delete",
        "pattern": r"\bnew\s+\w+[^;]*;[^}]*\bdelete\s+",
        "severity": "high",
        "description": "Raw new/delete detected",
        "suggestion": "Use smart pointers",
    },
    {
        "id": "CPP-RULE-002",
        "name": "Virtual destructor missing",
        "pattern": r"class\s+\w+\s*:.*public\s+\w+\s*\{(?!\s*virtual\s+~)",
        "severity": "high",
        "description": "Base class needs virtual destructor",
        "suggestion": "Add virtual destructor",
    },
    {
        "id": "CPP-RULE-003",
        "name": "Buffer overflow",
        "pattern": r"(?:strcpy|strcat|sprintf|gets)\s*\(",
        "severity": "high",
        "description": "Unsafe string functions",
        "suggestion": "Use safe alternatives",
    },
    {
        "id": "CPP-RULE-004",
        "name": "Hardcoded credentials",
        "pattern": r"(?:password|secret|token)\s*[:=]\s*[\"']",
        "severity": "high",
        "description": "Hardcoded credentials",
        "suggestion": "Use environment variables",
    },
    {
        "id": "CPP-RULE-005",
        "name": "Thread not joined",
        "pattern": r"std::thread\s+\w+\s*\([^)]*\)",
        "severity": "medium",
        "description": "Thread may not be joined",
        "suggestion": "Call join() or detach()",
    },
    {
        "id": "CPP-RULE-006",
        "name": "Format string vuln",
        "pattern": r"printf\s*\(\s*\w+\s*[,)]",
        "severity": "high",
        "description": "Format string vulnerability",
        "suggestion": "Use printf(\"%s\", str)",
    },
    {
        "id": "CPP-RULE-007",
        "name": "Weak crypto",
        "pattern": r"(?:DES|MD5|SHA1)",
        "severity": "high",
        "description": "Weak cryptographic algorithm",
        "suggestion": "Use modern crypto",
    },
    {
        "id": "CPP-RULE-008",
        "name": "Empty catch",
        "pattern": r"catch\s*\(\s*\.\.\.\s*\)\s*\{\s*\}",
        "severity": "medium",
        "description": "Empty catch block",
        "suggestion": "Handle exception properly",
    },
]


def get_cpp_rules() -> list[dict[str, Any]]:
    """Get C++ language rules."""
    return CPP_LANGUAGE_RULES
