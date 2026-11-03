"""Fix command: generate and apply fixes for reviewed issues."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from codereview.agents import ReviewOrchestrator
from codereview.cli.console import (
    _format_fix_output_text,
    _print_fix_output,
    _print_interactive_fix_prompt,
)
from codereview.cli.diff_parser import _parse_diff
from codereview.cli.errors import SCHEMA_VERSION, _json_error
from codereview.core import ConfigLoader, LLMFactory
from codereview.models import DiffEntry

logger = logging.getLogger(__name__)


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
    interactive: bool = False,
    confirm: Callable[[int, int], bool] | None = None,
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
        interactive: Prompt for each fix individually (y/n/a)
        confirm: Optional callback ``(fixes_count, files_count) -> bool`` invoked
            after fixes are generated but *before* any file is written. When it
            returns False, no file is modified and the result has
            ``cancelled: True``. None means apply without asking (CI/--yes).

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

    # Collect issues at or above the minimum risk level (severity-ordered)
    risk_order = {"low": 0, "medium": 1, "high": 2}
    min_level = risk_order[min_risk]
    all_issues = []
    for file_review in result.files_reviewed:
        for issue in file_review.issues:
            if risk_order[issue.risk_level.value] >= min_level:
                all_issues.append((file_review.file_path, issue))

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

    # Confirmation gate: ask *before* writing anything to disk
    if apply and not dry_run and confirm is not None:
        files_count = len({fix.issue.file_path for fix in fixes})
        if not confirm(len(fixes), files_count):
            return {
                "success": True,
                "fixes": fixes_output,
                "total_issues": len(all_issues),
                "fixes_generated": len(fixes),
                "applied": 0,
                "skipped": 0,
                "applied_files": [],
                "applied_changes": {},
                "dry_run": True,
                "cancelled": True,
            }

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

    # Confirmation gate for apply mode: asked after fixes are generated but
    # before any file is written. CI/non-TTY/--yes skip the prompt.
    confirm_callback = None
    if args.apply and not args.yes and not args.json and sys.stdout.isatty():

        def confirm_callback(fixes_count: int, files_count: int) -> bool:
            print(f"\n{'=' * 60}")
            response = (
                input(f"⚠️  Confirm applying {fixes_count} fixes to {files_count} file(s)? [y/N]: ")
                .strip()
                .lower()
            )
            if response not in ("y", "yes"):
                print("❌ Cancelled. No files were modified.")
                return False
            print("✅ Applying fixes...")
            return True

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
                interactive=args.interactive,
                confirm=confirm_callback,
            )
        )

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

        return 0 if result.get("success") and not result.get("cancelled") else 1

    except Exception as e:
        return _json_error(e, json_output=args.json)

