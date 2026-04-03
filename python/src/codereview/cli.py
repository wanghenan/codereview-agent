"""Command-line interface for CodeReview Agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from codereview.agents import ProjectAnalyzer, ReviewOrchestrator
from codereview.core import CacheManager, ConfigLoader, LLMFactory
from codereview.models import DiffEntry
from codereview.output import OutputGenerator

# Try to import rule engine
try:
    from codereview.rules import create_rule_engine, get_all_rules

    RULES_AVAILABLE = True
except ImportError:
    RULES_AVAILABLE = False
    logging.warning("Rule engine not available")

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".codereview-agent/cache")

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
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            import re

            content = pyproject_path.read_text(encoding="utf-8")
            match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            if match:
                return match.group(1)
    except Exception:
        pass

    return "0.0.0"


def get_git_diff(branch: str = "main", base_branch: str = None) -> str:
    """Get git diff for current branch vs target branch.

    Args:
        branch: Target branch to compare against (default: main)
        base_branch: Optional base branch (overrides branch if provided)

    Returns:
        Git diff output
    """
    try:
        # Determine the comparison base
        compare_branch = base_branch or branch

        # Try to get diff against the specified branch
        result = subprocess.run(
            ["git", "diff", f"{compare_branch}...", "--", "."],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        if result.returncode != 0:
            # Fallback: try comparing with HEAD
            result = subprocess.run(
                ["git", "diff", "HEAD", "--", "."], capture_output=True, text=True, cwd=Path.cwd()
            )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to get git diff: {result.stderr}")

        return result.stdout
    except Exception as e:
        logger.error(f"Failed to get git diff: {e}")
        raise RuntimeError(f"Failed to get git diff: {e}") from e


def parse_git_diff_to_entries(diff_output: str) -> list[DiffEntry]:
    """Parse git diff output into DiffEntry list.

    Args:
        diff_output: Raw git diff output

    Returns:
        List of DiffEntry objects
    """
    import re

    entries = []
    current_file = None
    current_status = "modified"
    additions = 0
    deletions = 0
    patch_lines = []

    for line in diff_output.split("\n"):
        # Detect new file
        if line.startswith("diff --git"):
            # Save previous file
            if current_file:
                entries.append(
                    DiffEntry(
                        filename=current_file,
                        status=current_status,
                        additions=additions,
                        deletions=deletions,
                        patch="\n".join(patch_lines),
                    )
                )

            # Extract filename
            match = re.match(r"diff --git a/(.*) b/(.*)", line)
            if match:
                current_file = match.group(2)
            current_status = "modified"
            additions = 0
            deletions = 0
            patch_lines = [line]

        elif line.startswith("new file"):
            current_status = "added"
            patch_lines.append(line)

        elif line.startswith("deleted file"):
            current_status = "deleted"
            patch_lines.append(line)

        elif line.startswith("index "):
            patch_lines.append(line)

        elif line.startswith("@@"):
            # Extract stats from hunk header
            match = re.search(r"@@\+.*(\d+)(?:,(\d+))? -(\d+)(?:,(\d+))? @@", line)
            if match:
                new_count = int(match.group(2) or 1)
                old_count = int(match.group(4) or 1)
                additions += new_count
                deletions += old_count
            patch_lines.append(line)

        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
            patch_lines.append(line)

        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
            patch_lines.append(line)

        elif line.startswith(" "):
            patch_lines.append(line)

    # Save last file
    if current_file:
        entries.append(
            DiffEntry(
                filename=current_file,
                status=current_status,
                additions=additions,
                deletions=deletions,
                patch="\n".join(patch_lines),
            )
        )

    return entries


async def run_review(
    config_path: str | Path | None = None,
    diff_input: str | None = None,
    pr_number: int | None = None,
    force_refresh: bool = False,
    output_only: bool = False,
    output_path: str | None = None,
    git_branch: str | None = None,
    rules_dir: str | None = None,
    disable_cache: bool = False,
    auto_merge: bool = False,
    github_token: str | None = None,
    merge_dry_run: bool = True,
    disabled_rules: Optional[list[str]] = None,
) -> dict:
    """Run the code review process.

    Args:
        config_path: Path to config file
        diff_input: JSON string with diff entries or path to file
        pr_number: PR number
        force_refresh: Force cache refresh
        output_only: Only output, don't save files
        output_path: Custom output path for report
        git_branch: Git branch to compare against
        rules_dir: Custom rules directory
        disable_cache: Disable file-level review cache
        auto_merge: Automatically merge PR if conditions are met
        github_token: GitHub token (overrides config)
        merge_dry_run: Dry run for auto-merge (default: True)

    Returns:
        Dict with review results and optionally merge result
    """
    # Load config
    config = ConfigLoader.load(config_path)

    # Override cache settings
    if force_refresh:
        config.cache.force_refresh = True

    # Create LLM
    llm = LLMFactory.create(config.llm)

    # Initialize cache manager
    cache_manager = CacheManager(
        cache_ttl_days=config.cache.ttl_days, enable_file_cache=not disable_cache
    )

    # Get or analyze project context
    project_context = None

    if not config.cache.force_refresh:
        project_context = cache_manager.load()

    if project_context is None:
        # Analyze project
        analyzer = ProjectAnalyzer(config, llm)
        project_context = await analyzer.analyze(Path.cwd())
        cache_manager.save(project_context)

    # Parse diff input or get from git
    diff_entries = _parse_diff(diff_input)

    # If no diff provided, try to get from git
    if not diff_entries and git_branch:
        logger.info(f"Getting diff from git branch: {git_branch}")
        git_diff = get_git_diff(branch=git_branch)
        if git_diff:
            diff_entries = parse_git_diff_to_entries(git_diff)
            logger.info(f"Found {len(diff_entries)} files changed")

    # Initialize rule engine if available
    rule_engine = None
    if RULES_AVAILABLE:
        try:
            rules_path = Path(rules_dir) if rules_dir else None
            rule_engine = create_rule_engine(rules_dir=rules_path)

            # Disable specified rules
            if disabled_rules:
                disabled = rule_engine.disable_rules(disabled_rules)
                logger.info(f"Disabled {len(disabled)} rule(s): {disabled}")

            logger.info(f"Loaded {len(rule_engine.rules)} detection rules")
        except Exception as e:
            logger.warning(f"Failed to load rules: {e}")

    # Get file cache
    file_cache = cache_manager.file_cache if not disable_cache else None

    # Run review
    orchestrator = ReviewOrchestrator(config, llm, rule_engine=rule_engine, file_cache=file_cache)
    result = await orchestrator.run_review(diff_entries, project_context)

    # Add cache info
    cache_info = cache_manager.get_cache_info()
    result.cache_info = type(
        "CacheInfo",
        (),
        {
            "used_cache": project_context is not None and not config.cache.force_refresh,
            "cache_timestamp": cache_info.get("modified_at"),
            "cache_version": cache_info.get("version"),
        },
    )()

    # Generate output
    output_config = config.output
    if output_only:
        # Don't save files
        output_config.report_path = ""

    # Override output path if specified
    if output_path:
        output_config.report_path = output_path

    generator = OutputGenerator(output_config)
    outputs = await generator.generate(result, pr_number)

    # Print cache stats
    if file_cache:
        stats = file_cache.get_stats()
        logger.info(f"File cache stats: {stats}")

    # Auto-merge if requested
    merge_output = None
    if auto_merge and pr_number:
        from codereview.core.auto_merger import create_auto_merger
        from codereview.core.github_client import create_github_client

        try:
            github_client = create_github_client(github_token=github_token)
            merger = create_auto_merger(config.output.auto_merge, github_client)

            # Get approvals
            approvals = await github_client.get_pr_approvals(pr_number)
            approval_count = len(approvals)

            if merge_dry_run:
                # Get merge preview
                preview = await merger.get_merge_preview(
                    review_result=result,
                    pr_number=pr_number,
                    github_token=github_token,
                )
                merge_output = {
                    "dry_run": True,
                    "preview": preview,
                }
            else:
                # Perform merge
                merge_result = await merger.merge(
                    review_result=result,
                    pr_number=pr_number,
                    approval_count=approval_count,
                    github_token=github_token,
                    dry_run=False,
                )
                merge_output = {
                    "dry_run": False,
                    "success": merge_result.success,
                    "message": merge_result.message,
                    "merged": merge_result.merged,
                    "merge_method": merge_result.merge_method,
                }
        except Exception as e:
            logger.error(f"Auto-merge failed: {e}")
            merge_output = {
                "error": str(e),
                "success": False,
            }

    result_dict = {"result": result.model_dump(), "outputs": outputs}
    if merge_output:
        result_dict["merge"] = merge_output

    return result_dict


def _parse_diff(diff_input: str | None) -> list[DiffEntry]:
    """Parse diff input.

    Args:
        diff_input: JSON string or None

    Returns:
        List of diff entries
    """
    if not diff_input:
        # Read from stdin
        try:
            diff_input = sys.stdin.read()
        except Exception:
            logger.warning("Failed to read from stdin")

    if not diff_input:
        logger.warning("No diff input provided")
        return []

    # Try to load as JSON
    try:
        data = json.loads(diff_input)
        if isinstance(data, list):
            return [DiffEntry(**entry) for entry in data]
        elif isinstance(data, dict) and "files" in data:
            return [DiffEntry(**entry) for entry in data["files"]]
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse diff JSON: {diff_input[:100]}...")

    # If it's a path, try to read file
    path = Path(diff_input)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return [DiffEntry(**entry) for entry in data.get("files", data)]
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON file {path}: {e}")
        except Exception as e:
            logger.error(f"Error reading diff file {path}: {e}")
    else:
        logger.warning(
            f"Diff input is not valid JSON and file does not exist: {diff_input[:100]}..."
        )

    return []


def _print_rules(json_output: bool = False) -> None:
    """Print all available detection rules.

    Args:
        json_output: If True, output as JSON array. Otherwise, output as table.
    """
    if not RULES_AVAILABLE:
        print("Rule engine not available", file=sys.stderr)
        return

    rules = get_all_rules()

    if json_output:
        rules_data = [
            {
                "id": r.id,
                "name": r.name,
                "severity": r.severity,
                "description": r.description,
                "language": r.language,
            }
            for r in rules
        ]
        print(json.dumps(rules_data, indent=2))
    else:
        print(f"\n{'=' * 80}")
        print(f"  CodeReview Agent - Available Detection Rules ({len(rules)} rules)")
        print(f"{'=' * 80}\n")

        print(f"{'ID':<20} {'Name':<35} {'Severity':<10} {'Language'}")
        print("-" * 80)

        for rule in rules:
            lang = rule.language or "all"
            print(f"{rule.id:<20} {rule.name:<35} {rule.severity:<10} {lang}")

        print(f"\n{'=' * 80}")
        print(f"Total: {len(rules)} rules")
        print(f"{'=' * 80}\n")


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

    # Auto-merge arguments
    parser.add_argument(
        "--auto-merge",
        action="store_true",
        help="Automatically merge PR if conditions are met (requires --pr)",
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
                merge_dry_run=True,  # Always dry-run for now, --apply-auto-merge for non-dry
                disabled_rules=disabled_rules,
            )
        )

        # Add schema_version for AI agent compatibility
        result["schema_version"] = SCHEMA_VERSION

        # Add fix_available to each issue in review results
        if "result" in result and "files_reviewed" in result["result"]:
            for file_review in result["result"]["files_reviewed"]:
                if "issues" in file_review:
                    for issue in file_review["issues"]:
                        suggestion = issue.get("suggestion")
                        issue["fix_available"] = (
                            suggestion is not None and len(str(suggestion).strip()) > 0
                        )

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

        return 0

    except Exception as e:
        return _json_error(e, json_output=args.json)


async def run_fix(
    config_path: str | Path | None = None,
    pr_number: int | None = None,
    github_token: str | None = None,
    diff_input: str | None = None,
    apply: bool = False,
    dry_run: bool = False,
    file_filter: str | None = None,
    min_risk: str = "high",
    json: bool = False,
    output_path: str | None = None,
    interactive: bool = False,
) -> dict:
    """Generate and optionally apply fixes for code issues.

    Args:
        config_path: Path to config file
        pr_number: PR number (if reading from GitHub)
        github_token: GitHub token (overrides config)
        diff_input: JSON diff data or path to diff file
        apply: Actually apply fixes to files
        dry_run: Only preview, don't apply (default True unless apply=True)
        file_filter: Only fix issues in files matching this pattern
        min_risk: Minimum risk level to fix (high, medium, low)
        json: Output as JSON
        output_path: Optional path to save fix preview

    Returns:
        Dict with fix results
    """
    from codereview.core.fixer import CodeFixer
    from codereview.core.github_client import create_github_client

    # Load config
    config = ConfigLoader.load(config_path)

    # Determine files to process
    diff_entries = []
    file_contents = {}

    if pr_number:
        # Get diff from GitHub
        github_client = create_github_client(github_token=github_token)
        try:
            diff_files = await github_client.get_pr_diff(pr_number)
            diff_entries = [
                DiffEntry(
                    filename=f.filename,
                    status=f.status,
                    additions=f.additions,
                    deletions=f.deletions,
                    patch=f.patch,
                )
                for f in diff_files
            ]
            logger.info(f"Fetched {len(diff_entries)} files from PR #{pr_number}")
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch PR #{pr_number}: {e}",
            }
    elif diff_input:
        diff_entries = _parse_diff(diff_input)
        if not diff_entries:
            return {
                "success": False,
                "error": "No diff entries found in input",
            }
    else:
        return {
            "success": False,
            "error": "Either --pr or --diff must be provided",
            "hint": "Use --pr <number> for GitHub PR or --diff <json/file> for local diff",
        }

    # Filter files if specified
    if file_filter:
        import fnmatch

        diff_entries = [e for e in diff_entries if fnmatch.fnmatch(e.filename, file_filter)]
        if not diff_entries:
            return {
                "success": False,
                "error": f"No files match pattern: {file_filter}",
            }

    # Run review to get issues
    llm = LLMFactory.create(config.llm)
    orchestrator = ReviewOrchestrator(config, llm)

    # Get project context (use minimal context for fix)
    from datetime import datetime

    from codereview.models import ProjectContext

    project_context = ProjectContext(
        tech_stack=["unknown"],
        language="unknown",
        critical_paths=config.critical_paths,
        analyzed_at=datetime.now().isoformat(),
    )

    result = await orchestrator.run_review(diff_entries, project_context)

    # Collect issues
    all_issues = []
    for file_review in result.files_reviewed:
        for issue in file_review.issues:
            # Filter by risk level
            if issue.risk_level.value in [min_risk, "high", "medium"]:
                if issue.risk_level.value in ("high", "medium") or min_risk == "low":
                    all_issues.append((file_review.filename, issue))

    if not all_issues:
        return {
            "success": True,
            "message": "No issues found matching the criteria",
            "fixes": [],
            "applied": False,
        }

    # Read file contents for all affected files
    affected_files = list(set(f for f, _ in all_issues))
    for filepath in affected_files:
        content = _read_file_content(filepath)
        if content:
            file_contents[filepath] = content

    # Detect languages
    languages = {}
    for filepath in affected_files:
        languages[filepath] = _detect_language(filepath)

    # Generate fixes
    fixer = CodeFixer(llm, timeout_seconds=30.0)
    fixes = []

    for filepath, issue in all_issues:
        if filepath not in file_contents:
            logger.warning(f"Could not read file: {filepath}")
            continue

        original_code = file_contents[filepath]
        language = languages.get(filepath, "python")

        fix = await fixer.generate_fix(
            issue=issue,
            original_code=original_code,
            language=language,
        )

        if fix:
            fixes.append(fix)

    if not fixes:
        return {
            "success": True,
            "message": "Could not generate any fixes",
            "issues_count": len(all_issues),
            "fixes_generated": 0,
            "applied": False,
        }

    # Format fixes for display
    fixes_output = []
    for i, fix in enumerate(fixes, 1):
        fix_info = {
            "index": i,
            "file": fix.issue.file_path,
            "line": fix.issue.line_number,
            "risk": fix.risk_level.value,
            "issue": fix.issue.description,
            "original_code": fix.original_code,
            "fixed_code": fix.fixed_code,
            "explanation": fix.explanation,
            "diff": fix.to_diff(),
        }
        fixes_output.append(fix_info)

    # Apply fixes if requested
    applied_count = 0
    skipped_count = 0
    applied_files = []
    selected_fixes = []  # Track fixes user selected to apply

    if apply and not dry_run:
        # Sort fixes by file and line number (apply from bottom to top to preserve line numbers)
        fixes_by_file = {}
        for fix in fixes:
            if fix.issue.file_path not in fixes_by_file:
                fixes_by_file[fix.issue.file_path] = []
            fixes_by_file[fix.issue.file_path].append(fix)

        # Track changes for summary
        applied_changes = {}  # filepath -> {"original": str, "fixed": str, "count": int}
        apply_all_remaining = False

        for filepath, file_fixes in fixes_by_file.items():
            if filepath not in file_contents:
                continue

            current_content = file_contents[filepath]
            original_content = current_content  # Keep for diff

            # Sort by line number descending (fix bottom-up)
            file_fixes.sort(key=lambda f: f.issue.line_number or 0, reverse=True)

            for fix in file_fixes:
                if interactive and not apply_all_remaining:
                    # Interactive mode: show fix details and prompt
                    _print_interactive_fix_prompt(fix, filepath)

                    while True:
                        response = input("Apply this fix? [y/n/a]: ").strip().lower()
                        if response in ("y", "yes"):
                            # Apply this fix
                            result = await fixer.apply_fix(current_content, fix)
                            if result.success and result.fixed_code:
                                current_content = result.fixed_code
                                applied_count += 1
                                selected_fixes.append(fix)
                            else:
                                logger.warning(
                                    f"Failed to apply fix for {filepath}: {result.error}"
                                )
                            break
                        elif response in ("n", "no"):
                            # Skip this fix
                            skipped_count += 1
                            break
                        elif response in ("a", "all"):
                            # Apply all remaining without prompting
                            apply_all_remaining = True
                            result = await fixer.apply_fix(current_content, fix)
                            if result.success and result.fixed_code:
                                current_content = result.fixed_code
                                applied_count += 1
                                selected_fixes.append(fix)
                            else:
                                logger.warning(
                                    f"Failed to apply fix for {filepath}: {result.error}"
                                )
                            break
                        else:
                            print("Invalid response. Please enter 'y', 'n', or 'a'.")
                else:
                    # Non-interactive mode: apply all fixes
                    result = await fixer.apply_fix(current_content, fix)
                    if result.success and result.fixed_code:
                        current_content = result.fixed_code
                        applied_count += 1
                        selected_fixes.append(fix)
                    else:
                        logger.warning(f"Failed to apply fix for {filepath}: {result.error}")

            # Write fixed content if any fixes were applied
            if selected_fixes and current_content != original_content:
                try:
                    Path(filepath).write_text(current_content, encoding="utf-8")
                    applied_files.append(filepath)
                    applied_changes[filepath] = {
                        "original": original_content,
                        "fixed": current_content,
                        "count": len(file_fixes),
                    }
                    logger.info(f"Applied {len(file_fixes)} fixes to {filepath}")
                except Exception as e:
                    logger.error(f"Failed to write {filepath}: {e}")

    return {
        "success": True,
        "fixes": fixes_output,
        "total_issues": len(all_issues),
        "fixes_generated": len(fixes),
        "applied": applied_count if apply and not dry_run else 0,
        "skipped": skipped_count if interactive else 0,
        "applied_files": applied_files if apply and not dry_run else [],
        "applied_changes": applied_changes if apply and not dry_run else {},
        "dry_run": dry_run or not apply,
    }


def _print_interactive_fix_prompt(fix, filepath: str) -> None:
    """Print details of a single fix for interactive mode."""
    print(f"\n{'=' * 60}")
    print(f"📄 File: {filepath}")
    print(f"📍 Line: {fix.issue.line_number}")
    print(f"🔴 Risk: {fix.risk_level.value.upper()}")
    print(f"{'=' * 60}")
    print(f"\nIssue: {fix.issue.description}")
    if fix.issue.suggestion:
        print(f"\nSuggestion: {fix.issue.suggestion}")

    # Show diff
    original_lines = fix.original_code.strip().splitlines()
    fixed_lines = fix.fixed_code.strip().splitlines()

    print("\n--- Original Code")
    for line in original_lines[:5]:
        print(f"   -  {line}")
    if len(original_lines) > 5:
        print(f"   -  ... ({len(original_lines) - 5} more lines)")

    print("\n+++ Fixed Code")
    for line in fixed_lines[:5]:
        print(f"   +  {line}")
    if len(fixed_lines) > 5:
        print(f"   +  ... ({len(fixed_lines) - 5} more lines)")

    print(f"\n💡 {fix.explanation}")


def _read_file_content(filepath: str) -> str | None:
    """Read file content with multiple encoding attempts."""
    path = Path(filepath)
    if not path.exists():
        return None

    # Try UTF-8 first
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        pass

    # Try other common encodings
    for encoding in ["utf-8-sig", "gbk", "gb2312", "latin-1"]:
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue

    return None


def _detect_language(filename: str) -> str:
    """Detect programming language from file extension."""
    ext = Path(filename).suffix.lower()
    language_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "javascript",
        ".jsx": "javascript",
        ".tsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".cs": "csharp",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".vue": "vue",
        ".svelte": "svelte",
    }
    return language_map.get(ext, "python")


def main_fix():
    """Main entry point for fix CLI."""
    parser = argparse.ArgumentParser(
        description="CodeReview Agent Fix - Generate and apply fixes for code issues"
    )

    parser.add_argument("--config", "-c", type=str, help="Path to config file")
    parser.add_argument("--pr", "-p", type=int, help="PR number (fetch diff from GitHub)")
    parser.add_argument("--diff", "-d", type=str, help="JSON diff data or path to diff file")
    parser.add_argument("--token", "-t", type=str, help="GitHub token (or set GITHUB_TOKEN)")
    parser.add_argument(
        "--apply", action="store_true", help="Apply fixes to files (default: dry-run)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview fixes without applying")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt (for CI/non-TTY)"
    )
    parser.add_argument("--file", "-f", type=str, help="Only fix issues in files matching pattern")
    parser.add_argument(
        "--min-risk",
        choices=["high", "medium", "low"],
        default="high",
        help="Minimum risk level to fix (default: high)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", "-o", type=str, help="Save fix preview to file")
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode: prompt for each fix (y/n/a)",
    )

    args = parser.parse_args()

    # Determine dry_run mode
    dry_run = args.dry_run or not args.apply

    try:
        result = asyncio.run(
            run_fix(
                config_path=args.config,
                pr_number=args.pr,
                github_token=args.token,
                diff_input=args.diff,
                apply=args.apply,
                dry_run=dry_run,
                file_filter=args.file,
                min_risk=args.min_risk,
                json=args.json,
                output_path=args.output,
                interactive=args.interactive,
            )
        )

        # Confirmation prompt for apply mode
        if args.apply and not args.yes and not args.json:
            # Check if running in TTY
            import sys

            if sys.stdout.isatty():
                fixes_count = result.get("fixes_generated", 0)
                files_count = len(set(f.get("file") for f in result.get("fixes", [])))
                print(f"\n{'=' * 60}")
                response = (
                    input(
                        f"⚠️  Confirm applying {fixes_count} fixes to {files_count} file(s)? [y/N]: "
                    )
                    .strip()
                    .lower()
                )
                if response not in ("y", "yes"):
                    print("❌ Cancelled. No files were modified.")
                    return 1
                print("✅ Applying fixes...")
            # Non-TTY: proceed without confirmation

        result["schema_version"] = SCHEMA_VERSION

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _print_fix_output(result, args)

        # Save to file if specified
        if args.output and not args.json:
            output_content = _format_fix_output_text(result)
            Path(args.output).write_text(output_content, encoding="utf-8")
            print(f"\n📄 Fix preview saved to: {args.output}")

        return 0 if result.get("success") else 1

    except Exception as e:
        return _json_error(e, json_output=args.json)


def _print_fix_output(result: dict, args) -> None:
    """Print fix output in human-readable format."""
    if not result.get("success"):
        print(f"❌ {result.get('error', 'Unknown error')}")
        if result.get("hint"):
            print(f"💡 {result.get('hint')}")
        return

    fixes = result.get("fixes", [])
    dry_run = result.get("dry_run", True)

    # Header
    mode = "🔍 DRY RUN" if dry_run else "✅ APPLYING"
    print(f"\n{'=' * 60}")
    print(f"  CodeReview Agent Fix {mode}")
    print(f"{'=' * 60}")

    # Summary by risk level
    high_count = sum(1 for f in fixes if f["risk"] == "high")
    medium_count = sum(1 for f in fixes if f["risk"] == "medium")
    low_count = sum(1 for f in fixes if f["risk"] == "low")

    print("\n📊 Risk Summary:")
    if high_count > 0:
        print(f"   🔴 High: {high_count}")
    if medium_count > 0:
        print(f"   🟡 Medium: {medium_count}")
    if low_count > 0:
        print(f"   🟢 Low: {low_count}")
    print(f"   Total: {len(fixes)} fixes")

    # Applied info
    if result.get("applied", 0) > 0:
        print(f"\n   ✅ Applied: {result.get('applied', 0)} fixes")
        if result.get("skipped", 0) > 0:
            print(f"   ⏭️  Skipped: {result.get('skipped', 0)} fixes")

        # Changes summary
        applied_changes = result.get("applied_changes", {})
        if applied_changes:
            total_additions = 0
            total_deletions = 0

            print(f"\n{'=' * 60}")
            print("  📊 Changes Summary")
            print(f"{'=' * 60}")
            print(f"   📁 {len(applied_changes)} files modified")

            for filepath, change in applied_changes.items():
                orig_lines = change["original"].splitlines()
                fixed_lines = change["fixed"].splitlines()
                additions = len(fixed_lines) - len(orig_lines)
                total_additions += max(0, additions)
                total_deletions += max(0, -additions)

                print(
                    f"\n   📄 {filepath} ({change['count']} fix{'es' if change['count'] > 1 else ''}):"
                )

                # Show first few changes as diff
                orig_set = set(change["original"].splitlines())
                fixed_set = set(change["fixed"].splitlines())

                # Find removed and added lines
                removed = [ln for ln in orig_set - fixed_set if ln.strip()][:2]
                added = [ln for ln in fixed_set - orig_set if ln.strip()][:2]

                for line in removed[:2]:
                    print(f"      - {line[:60]}")
                for line in added[:2]:
                    print(f"      + {line[:60]}")

            print(f"\n   📈 Total: +{total_additions} lines, -{total_deletions} lines")

    elif dry_run:
        print("\n   💡 Run with --apply to apply these fixes")

    if not fixes:
        print("\n✨ No issues to fix!")
        return

    # Group fixes by file
    fixes_by_file = {}
    for fix_info in fixes:
        filepath = fix_info["file"]
        if filepath not in fixes_by_file:
            fixes_by_file[filepath] = []
        fixes_by_file[filepath].append(fix_info)

    # File-level preview
    print(f"\n{'=' * 60}")
    print(f"  📄 Files Summary ({len(fixes_by_file)} files)")
    print(f"{'=' * 60}")
    for filepath, file_fixes in fixes_by_file.items():
        print(f"\n  📄 {filepath} ({len(file_fixes)} fix{'es' if len(file_fixes) > 1 else ''})")
        for fix in file_fixes:
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fix["risk"], "⚪")
            print(f"     {emoji} #{fix['index']}:{fix['line']} - {fix['issue'][:50]}...")

    # Detailed diff preview
    print(f"\n{'=' * 60}")
    print("  🔍 Diff Preview")
    print(f"{'=' * 60}")

    for fix_info in fixes:
        print(
            f"\n🔧 #{fix_info['index']} | {fix_info['file']}:{fix_info['line']} | {fix_info['risk'].upper()}"
        )
        print(f"   Issue: {fix_info['issue'][:80]}")

        # Git-style diff
        original_lines = fix_info["original_code"].strip().splitlines()
        fixed_lines = fix_info["fixed_code"].strip().splitlines()

        print("\n   --- Original")
        for line in original_lines[:5]:
            print(f"   -  {line}")
        if len(original_lines) > 5:
            print(f"   -  ... ({len(original_lines) - 5} more lines)")

        print('"   +++ Fixed')
        for line in fixed_lines[:5]:
            print(f"   +  {line}")
        if len(fixed_lines) > 5:
            print(f"   +  ... ({len(fixed_lines) - 5} more lines)")

        print(f"\n   💡 {fix_info['explanation'][:80]}")

    # Confirmation prompt for apply mode
    if not dry_run:
        print(f"\n{'=' * 60}")
        print("✅ All fixes have been applied successfully!")
        print(f"{'=' * 60}")


def _format_fix_output_text(result: dict) -> str:
    """Format fix output as text for file export."""
    lines = ["# CodeReview Agent Fix Preview", ""]

    fixes = result.get("fixes", [])
    dry_run = result.get("dry_run", True)

    # Risk summary
    high_count = sum(1 for f in fixes if f["risk"] == "high")
    medium_count = sum(1 for f in fixes if f["risk"] == "medium")
    low_count = sum(1 for f in fixes if f["risk"] == "low")

    lines.append("## Summary")
    lines.append(f"- Mode: {'🔍 DRY RUN' if dry_run else '✅ APPLIED'}")
    lines.append(f"- Total fixes: {len(fixes)}")
    lines.append(f"- 🔴 High: {high_count} | 🟡 Medium: {medium_count} | 🟢 Low: {low_count}")

    if result.get("applied", 0) > 0:
        lines.append(f"- Applied: {result.get('applied', 0)}")

    if fixes:
        # Group by file
        fixes_by_file = {}
        for fix_info in fixes:
            filepath = fix_info["file"]
            if filepath not in fixes_by_file:
                fixes_by_file[filepath] = []
            fixes_by_file[filepath].append(fix_info)

        lines.append("")
        lines.append(f"## Files Summary ({len(fixes_by_file)} files)")
        for filepath, file_fixes in fixes_by_file.items():
            lines.append(f"- **{filepath}** ({len(file_fixes)} fixes)")
            for fix in file_fixes:
                emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fix["risk"], "⚪")
                lines.append(f"  {emoji} #{fix['index']}:{fix['line']} - {fix['issue'][:60]}")

        lines.append("")
        lines.append("## Detailed Fixes")
        for fix_info in fixes:
            lines.append("")
            lines.append(
                f"### #{fix_info['index']} | {fix_info['file']}:{fix_info['line']} | {fix_info['risk'].upper()}"
            )
            lines.append(f"**Issue**: {fix_info['issue']}")
            lines.append("")
            lines.append("```diff")
            lines.append("--- Original")
            for line in fix_info["original_code"].strip().splitlines():
                lines.append(f"- {line}")
            lines.append("+++ Fixed")
            for line in fix_info["fixed_code"].strip().splitlines():
                lines.append(f"+ {line}")
            lines.append("```")
            lines.append(f"**Explanation**: {fix_info['explanation']}")

    return "\n".join(lines)


async def run_merge(
    config_path: str | Path | None = None,
    pr_number: int | None = None,
    github_token: str | None = None,
    dry_run: bool = False,
    output_path: str | None = None,
    json: bool = False,
    force: bool = False,
) -> dict:
    """Run auto-merge for a PR.

    Args:
        config_path: Path to config file
        pr_number: PR number
        github_token: GitHub token (overrides config)
        dry_run: Only check, don't actually merge
        output_path: Optional path to save merge preview
        json: Output as JSON
        force: Skip condition checks and force merge

    Returns:
        Dict with merge result
    """
    from codereview.core.auto_merger import create_auto_merger
    from codereview.core.github_client import create_github_client

    # Load config
    config = ConfigLoader.load(config_path)

    # Check if auto-merge is enabled
    if not config.output.auto_merge.enabled:
        return {
            "success": False,
            "error": "Auto merge is not enabled in config",
            "hint": "Set autoMerge.enabled: true in config",
        }

    if not pr_number:
        return {
            "success": False,
            "error": "PR number is required",
            "hint": "Use --pr <number>",
        }

    # Create GitHub client
    github_client = create_github_client(github_token=github_token)

    # Get PR diff and run review
    try:
        # Get PR info first
        pr = await github_client.get_pull_request(pr_number)
        logger.info(f"Processing PR #{pr_number}: {pr.title}")

        # Get approvals
        approvals = await github_client.get_pr_approvals(pr_number)
        approval_count = len(approvals)

        # Get diff
        diff_files = await github_client.get_pr_diff(pr_number)

        # Convert to DiffEntry
        diff_entries = [
            DiffEntry(
                filename=f.filename,
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
                patch=f.patch,
            )
            for f in diff_files
        ]

        # Run review
        llm = LLMFactory.create(config.llm)
        orchestrator = ReviewOrchestrator(config, llm)
        result = await orchestrator.run_review(diff_entries, None)

        # Create auto-merger
        merger = create_auto_merger(config.output.auto_merge, github_client)

        # Get merge preview
        preview = await merger.get_merge_preview(
            review_result=result,
            pr_number=pr_number,
        )

        if dry_run:
            return {
                "success": preview["can_merge"],
                "preview": preview,
                "dry_run": True,
            }

        # Attempt merge
        merge_result = await merger.merge(
            review_result=result,
            pr_number=pr_number,
            approval_count=approval_count,
            dry_run=False,
            force=force,
        )

        return {
            "success": merge_result.success,
            "message": merge_result.message,
            "merged": merge_result.merged,
            "merge_method": merge_result.merge_method,
            "preview": preview,
        }

    except Exception as e:
        logger.error(f"Auto-merge failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def main_merge():
    """Main entry point for auto-merge CLI."""
    parser = argparse.ArgumentParser(
        description="CodeReview Agent Auto-Merge - Automatically merge PRs based on review results"
    )

    parser.add_argument("--config", "-c", type=str, help="Path to config file")
    parser.add_argument("--pr", "-p", type=int, required=True, help="PR number")
    parser.add_argument("--token", "-t", type=str, help="GitHub token (or set GITHUB_TOKEN)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't merge")
    parser.add_argument(
        "--force", action="store_true", help="Force merge even if conditions are not met"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", "-o", type=str, help="Save preview to file")

    args = parser.parse_args()

    try:
        result = asyncio.run(
            run_merge(
                config_path=args.config,
                pr_number=args.pr,
                github_token=args.token,
                dry_run=args.dry_run,
                output_path=args.output,
                json=args.json,
                force=args.force,
            )
        )

        result["schema_version"] = SCHEMA_VERSION

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result.get("dry_run"):
                print("🔍 Dry Run Mode")
                preview = result.get("preview", {})
                print(f"\n{'=' * 50}")
                print(f"PR #{args.pr}: {preview.get('pr', {}).get('title', 'Unknown')}")
                print(f"{'=' * 50}")

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

            elif result.get("success"):
                force_note = " (forced)" if args.force else ""
                print(f"✅ {result.get('message')}{force_note}")
                if result.get("merged"):
                    print(f"   Merge method: {result.get('merge_method', 'squash')}")
            else:
                print(f"❌ {result.get('error')}")
                if result.get("hint"):
                    print(f"💡 {result.get('hint')}")

        return 0 if result.get("success") else 1

    except Exception as e:
        return _json_error(e, json_output=args.json)


if __name__ == "__main__":
    import sys

    # Check if running as fix or merge subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "fix":
        sys.argv.pop(1)
        sys.exit(main_fix())
    if len(sys.argv) > 1 and sys.argv[1] == "merge":
        sys.argv.pop(1)
        sys.exit(main_merge())
    sys.exit(main())
