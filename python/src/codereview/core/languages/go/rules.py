"""Go language rules module.

This module exports Go-specific detection rules for the rule engine.
"""

from typing import Any

# Go-specific rules for the rule engine
GO_LANGUAGE_RULES: list[dict[str, Any]] = [
    {
        "id": "GO-RULE-001",
        "name": "Goroutine leak risk",
        "pattern": r"go\s+func\s*\([^)]*\)\s*\{[^}]{100,}",
        "severity": "high",
        "description": "Long-running goroutine without exit condition may cause leaks",
        "suggestion": "Add context cancellation or quit channel",
    },
    {
        "id": "GO-RULE-002",
        "name": "Deferred Close without error check",
        "pattern": r"defer\s+\w+\.Close\(",
        "severity": "low",
        "description": "Consider checking error from deferred Close",
        "suggestion": "Use named return or ioutil.TempFile pattern",
    },
    {
        "id": "GO-RULE-003",
        "name": "Ignored error",
        "pattern": r"_\s*=\s*\w+\([^)]*\)(?:\s*\n\s*){0,1}(?!\s*if)",
        "severity": "medium",
        "description": "Error return value is being ignored",
        "suggestion": "Handle the error properly",
    },
    {
        "id": "GO-RULE-004",
        "name": "Empty error handler",
        "pattern": r"if\s+err\s*!=\s*nil\s*\{\s*\}",
        "severity": "medium",
        "description": "Error is checked but not handled",
        "suggestion": "Log the error or return it",
    },
    {
        "id": "GO-RULE-005",
        "name": "HTTP client without timeout",
        "pattern": r"http\.(?:Client|Get|Post|Do)\s*\([^)]*\)(?!.*(?:Timeout|timeout))",
        "severity": "high",
        "description": "HTTP client without timeout can hang",
        "suggestion": "Set Client.Timeout or Request.WithContext",
    },
    {
        "id": "GO-RULE-006",
        "name": "SQL connection not closed",
        "pattern": r"(?:db|conn),?\s*(?:err)?:=.*sql\.(?:Open|Connect)",
        "severity": "high",
        "description": "Database connection should be closed",
        "suggestion": "Use defer db.Close()",
    },
    {
        "id": "GO-RULE-007",
        "name": "Shared map access",
        "pattern": r"(?:map\[\w+\]\w+|var\s+\w+\s+map)",
        "severity": "high",
        "description": "Map accessed without mutex - race condition risk",
        "suggestion": "Use sync.Map or sync.RWMutex",
    },
    {
        "id": "GO-RULE-008",
        "name": "Missing context parameter",
        "pattern": r"func\s+\w+\s*\([^)]*\)\s*(?:\([^)]*error\))?\s*\{[^}]{50,}(?:http|sql|grpc)\.",
        "severity": "medium",
        "description": "Consider passing context.Context",
        "suggestion": "Add ctx context.Context as first parameter",
    },
    {
        "id": "GO-RULE-009",
        "name": "Printf for logging",
        "pattern": r"fmt\.Print(?:f|ln)\s*\(",
        "severity": "low",
        "description": "Using fmt.Print instead of log package",
        "suggestion": "Use log or log/slog package",
    },
    {
        "id": "GO-RULE-010",
        "name": "Defer in loop",
        "pattern": r"for\s*\{[^}]{1,50}defer\s+",
        "severity": "high",
        "description": "Defer in loop can cause resource leaks",
        "suggestion": "Move defer outside loop or use explicit cleanup",
    },
]


def get_go_rules() -> list[dict[str, Any]]:
    """Get Go language rules."""
    return GO_LANGUAGE_RULES
