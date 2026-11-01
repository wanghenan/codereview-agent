"""Command-line interface for CodeReview Agent.

The CLI is split into focused modules; this package level keeps the
dispatcher (``cli``), the review entry point (``main``), shared constants,
and backwards-compatible re-exports so ``from codereview.cli import X``
and ``patch("codereview.cli.X")`` keep working.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

# Re-exported so tests and AI agents can patch/import them from codereview.cli
from codereview.agents import ProjectAnalyzer, ReviewOrchestrator
from codereview.cli.console import _print_fix_output
from codereview.cli.diff_parser import _parse_diff, get_git_diff, parse_git_diff_to_entries
from codereview.cli.errors import (
    EXIT_CONFIG_ERROR,
    EXIT_ISSUES_FOUND,
    EXIT_LLM_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_SUCCESS,
    EXIT_UNKNOWN_ERROR,
    SCHEMA_VERSION,
    _classify_error,
    _exit_code_for_error,
    _json_error,
)
from codereview.cli.fix_cmd import main_fix, run_fix
from codereview.cli.merge_cmd import main_merge, run_merge
from codereview.cli.review_cmd import (
    _compute_cache_namespace,
    _compute_rules_hash,
    _print_rules,
    run_review,
)
from codereview.core import CacheManager, ConfigLoader, LLMFactory
from codereview.output import OutputGenerator

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".codereview-agent/cache")

__all__ = [
    "CACHE_DIR",
    "EXIT_CONFIG_ERROR",
    "EXIT_ISSUES_FOUND",
    "EXIT_LLM_ERROR",
    "EXIT_NETWORK_ERROR",
    "EXIT_SUCCESS",
    "EXIT_UNKNOWN_ERROR",
    "SCHEMA_VERSION",
    "CacheManager",
    "ConfigLoader",
    "LLMFactory",
    "OutputGenerator",
    "ProjectAnalyzer",
    "ReviewOrchestrator",
    "_classify_error",
    "_compute_cache_namespace",
    "_compute_rules_hash",
    "_exit_code_for_error",
    "_json_error",
    "_parse_diff",
    "_print_fix_output",
    "cli",
    "get_git_diff",
    "get_version",
    "main",
    "main_fix",
    "main_merge",
    "parse_git_diff_to_entries",
    "run_fix",
    "run_merge",
    "run_review",
]


def get_version() -> str:
    """Get the version of codereview-agent.

    Returns:
        Version string (X.Y.Z) or "0.0.0" if not found.
    """
    # Try importlib.metadata first (Python 3.8+)
    try:
        from importlib.metadata import version

        return version("codereview-agent")
    except Exception:
        pass

    # Fallback: read from pyproject.toml
    try:
        pyproject_path = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            import re

            content = pyproject_path.read_text(encoding="utf-8")
            match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            if match:
                return match.group(1)
    except Exception:
        pass

    return "0.0.0"
def cli() -> int:
    """Top-level CLI dispatcher using argparse subparsers.

    Routes ``codereview`` (review), ``codereview fix`` and ``codereview merge``
    to the corresponding handlers. The subcommand token is popped from
    ``sys.argv`` before delegating, so each handler's own ``parse_args()``
    sees only its own arguments.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="codereview",
        description="CodeReview Agent - AI-powered code review",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="{fix,merge}",
    )
    subparsers.add_parser("fix", help="Auto-fix code review issues")
    subparsers.add_parser("merge", help="Auto-merge a reviewed PR")
    # No subparser for the default review command; any other token (or none)
    # falls through to main().

    # Only parse the first token to decide routing; do NOT consume the rest,
    # because the delegated handler re-parses sys.argv itself.
    argv = sys.argv[1:]
    command = argv[0] if argv else None

    if command in ("fix", "merge"):
        # Pop the subcommand token so the handler sees its own arg list.
        sys.argv.pop(1)
        return main_fix() if command == "fix" else main_merge()

    # Default: review command (no subcommand token). ``main`` handles unknown
    # args / --help / --version via its own parser.
    return main()


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(description="CodeReview Agent - AI-powered code review")

    parser.add_argument("--config", "-c", type=str, help="Path to config file")

    parser.add_argument("--diff", "-d", type=str, help="JSON diff data or path to diff file")

    parser.add_argument("--pr", "-p", type=int, help="PR number")

    parser.add_argument("--refresh", "-r", action="store_true", help="Force cache refresh")

    parser.add_argument(
        "--output-only", action="store_true", help="Output to stdout only, don't save files"
    )

    parser.add_argument("--json", action="store_true", help="Output as JSON")

    # New arguments for enhanced CLI experience
    parser.add_argument(
        "--output", "-o", type=str, help="Output path for report (overrides config)"
    )

    parser.add_argument(
        "--branch", "-b", type=str, help="Git branch to compare against (e.g., main, develop)"
    )

    parser.add_argument(
        "--base-branch", type=str, help="Base branch for comparison (overrides --branch)"
    )

    parser.add_argument(
        "--rules-dir", type=str, help="Custom rules directory (default: built-in rules)"
    )

    parser.add_argument("--no-cache", action="store_true", help="Disable file-level review caching")

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Build the inline review payload but do not post it to GitHub "
            "(findings are still reported locally)"
        ),
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Never post anything and never create a GitHub client: equivalent "
            "to --dry-run for the inline review payload, with no GitHub network access"
        ),
    )

    # Auto-merge arguments
    parser.add_argument(
        "--auto-merge",
        action="store_true",
        help="Automatically merge PR if conditions are met (requires --pr)",
    )

    parser.add_argument(
        "--apply-auto-merge",
        action="store_true",
        help="Actually merge when --auto-merge conditions are met (default: dry-run preview)",
    )

    parser.add_argument(
        "--token", "-t", type=str, help="GitHub token (or set GITHUB_TOKEN env var)"
    )

    # Version flag
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version number and exit",
    )

    # Clear cache flag
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the cache directory (.codereview-agent/cache/)",
    )

    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt for --clear-cache",
    )

    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List all available detection rules and exit",
    )

    parser.add_argument(
        "--disable-rule",
        action="append",
        default=[],
        help="Rule ID to disable (can be specified multiple times or comma-separated)",
    )

    # Logging control arguments
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Enable quiet mode - only show ERROR messages",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (overrides --verbose and --quiet)",
    )

    args = parser.parse_args()

    # Configure logging based on flags
    # Priority: quiet > verbose > log_level > default
    if args.quiet:
        log_level = logging.ERROR
    elif args.verbose:
        log_level = logging.DEBUG
    elif args.log_level:
        log_level = getattr(logging, args.log_level.upper())
    else:
        log_level = logging.INFO

    # In --json mode, route logs to stderr to keep stdout clean
    if args.json:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stderr,
        )
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    # Handle --version first (short-circuit)
    if args.version:
        version = get_version()
        print(f"codereview-agent {version}")
        return 0

    # Handle --list-rules (short-circuit)
    if args.list_rules:
        _print_rules(args.json)
        return 0

    # Handle --clear-cache
    if args.clear_cache:
        cache_dir = CACHE_DIR
        if cache_dir.exists():
            if args.yes or not sys.stdout.isatty():
                shutil.rmtree(cache_dir)
                print(f"Cache directory {cache_dir} has been cleared.")
                return 0
            else:
                response = input(f"Clear cache directory {cache_dir}? [y/N]: ").strip().lower()
                if response in ("y", "yes"):
                    shutil.rmtree(cache_dir)
                    print(f"Cache directory {cache_dir} has been cleared.")
                    return 0
                else:
                    print("Cache clear cancelled.")
                    return 0
        else:
            print(f"Cache directory {cache_dir} does not exist (nothing to clear).")
            return 0

    # Flatten --disable-rule arguments (can be comma-separated)
    disabled_rules = []
    for rule_arg in args.disable_rule:
        if "," in rule_arg:
            disabled_rules.extend(rule_arg.split(","))
        else:
            disabled_rules.append(rule_arg)

    # Run async
    try:
        result = asyncio.run(
            run_review(
                config_path=args.config,
                diff_input=args.diff,
                pr_number=args.pr,
                force_refresh=args.refresh,
                output_only=args.output_only,
                output_path=args.output,
                git_branch=args.base_branch or args.branch,
                rules_dir=args.rules_dir,
                disable_cache=args.no_cache,
                auto_merge=args.auto_merge,
                github_token=args.token,
                merge_dry_run=not args.apply_auto_merge,
                disabled_rules=disabled_rules,
                dry_run=args.dry_run,
                offline=args.offline,
            )
        )

        # Add schema_version for AI agent compatibility
        result["schema_version"] = SCHEMA_VERSION

        # Add fix_available to each issue in review results
        has_high_risk = False
        if "result" in result and "files_reviewed" in result["result"]:
            for file_review in result["result"]["files_reviewed"]:
                if "issues" in file_review:
                    for issue in file_review["issues"]:
                        suggestion = issue.get("suggestion")
                        issue["fix_available"] = (
                            suggestion is not None and len(str(suggestion).strip()) > 0
                        )
                        if issue.get("risk_level") == "high":
                            has_high_risk = True

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            # Print PR comment if available
            if "pr_comment" in result.get("outputs", {}):
                print(result["outputs"]["pr_comment"])

            # Print report path if saved
            if "markdown" in result.get("outputs", {}):
                print("\n📄 Full report generated.")

            # Print merge info if auto-merge was requested
            if args.auto_merge and "merge" in result:
                merge_result = result["merge"]
                print(f"\n{'=' * 50}")
                print("  Auto-Merge Preview")
                print(f"{'=' * 50}")

                if "error" in merge_result:
                    print(f"❌ {merge_result['error']}")
                elif merge_result.get("dry_run"):
                    preview = merge_result.get("preview", {})
                    can_merge = preview.get("can_merge", False)
                    emoji = "✅" if can_merge else "❌"
                    print(f"\n{emoji} Can Merge: {can_merge}")
                    print(f"Reason: {preview.get('reason', 'Unknown')}")
                    print(
                        f"\n📊 Review Confidence: {preview.get('review', {}).get('confidence', 0):.0f}%"
                    )
                    print(
                        f"   Required: {preview.get('merge_requirements', {}).get('min_confidence', 0):.0f}%"
                    )
                    print(
                        f"\n👥 Approvals: {preview.get('current_status', {}).get('approval_count', 0)}"
                    )
                    print(f"\n📁 Files ({preview.get('review', {}).get('filtered_files', 0)}):")
                    for f in preview.get("files", [])[:5]:
                        risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                            f.get("risk_level", ""), "⚪"
                        )
                        print(f"  {risk_emoji} {f['file_path']} ({f.get('issue_count', 0)} issues)")
                    if len(preview.get("files", [])) > 5:
                        print(f"  ... and {len(preview.get('files', [])) - 5} more files")
                else:
                    if merge_result.get("success"):
                        print(f"✅ {merge_result.get('message')}")
                        if merge_result.get("merged"):
                            print(f"   Merge method: {merge_result.get('merge_method', 'squash')}")
                    else:
                        print(f"❌ {merge_result.get('message', 'Merge failed')}")

        # Detect if all files had LLM failures (graceful degradation produced
        # only error descriptions rather than real review results)
        if "result" in result and "files_reviewed" in result["result"]:
            files = result["result"]["files_reviewed"]
            if files:
                all_llm_failed = all(
                    any(
                        "review failed" in str(issue.get("description", "")).lower()
                        or "error code" in str(issue.get("description", "")).lower()
                        for issue in fr.get("issues", [])
                    )
                    for fr in files
                )
                if all_llm_failed:
                    if args.json:
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                    return EXIT_LLM_ERROR

        # Return semantic exit code for AI agent consumers
        if has_high_risk:
            return EXIT_ISSUES_FOUND

        return EXIT_SUCCESS

    except Exception as e:
        return _json_error(e, json_output=args.json)
