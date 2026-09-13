"""Error classification and semantic exit codes for AI agent consumers."""

from __future__ import annotations

import json
import sys

# AI Agent-friendly exit codes
EXIT_SUCCESS = 0
EXIT_ISSUES_FOUND = 1
EXIT_CONFIG_ERROR = 2
EXIT_LLM_ERROR = 3
EXIT_NETWORK_ERROR = 4
EXIT_UNKNOWN_ERROR = 5
SCHEMA_VERSION = "1.1"


def _classify_error(error: Exception) -> str:
    """Classify an error into a semantic category for AI agent consumers."""
    msg = str(error).lower()
    if any(kw in msg for kw in ("config", "validation", "api_key", "apikey")):
        return "config_error"
    if any(kw in msg for kw in ("rate", "timeout", "llm", "model", "token")):
        return "llm_error"
    if any(kw in msg for kw in ("connect", "network", "github", "dns", "refuse")):
        return "network_error"
    return "unknown_error"


def _exit_code_for_error(error: Exception) -> int:
    """Return semantic exit code based on error type."""
    msg = str(error).lower()
    if any(kw in msg for kw in ("config", "validation", "api_key", "apikey")):
        return EXIT_CONFIG_ERROR
    if any(kw in msg for kw in ("rate", "timeout", "llm", "model", "token")):
        return EXIT_LLM_ERROR
    if any(kw in msg for kw in ("connect", "network", "github", "dns", "refuse")):
        return EXIT_NETWORK_ERROR
    return EXIT_UNKNOWN_ERROR


def _json_error(error: Exception, json_output: bool = False) -> int:
    """Handle errors with structured JSON output for AI agent mode."""
    exit_code = _exit_code_for_error(error)
    error_type = _classify_error(error)
    if json_output:
        error_payload = json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "success": False,
                "error": {
                    "type": error_type,
                    "message": str(error),
                    "exit_code": exit_code,
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        print(error_payload, file=sys.stderr)
    else:
        print(f"Error: {error}", file=sys.stderr)
    return exit_code
