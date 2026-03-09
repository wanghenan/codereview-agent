"""Command-line interface for CodeReview Agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path

from codereview.agents import ProjectAnalyzer, ReviewOrchestrator
from codereview.core import CacheManager, ConfigLoader, LLMFactory
from codereview.models import DiffEntry, ReviewResult
from codereview.output import OutputGenerator

# Try to import rule engine
try:
    from codereview.rules import create_rule_engine
    RULES_AVAILABLE = True
except ImportError:
    RULES_AVAILABLE = False
    logging.warning("Rule engine not available")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


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
            cwd=Path.cwd()
        )
        
        if result.returncode != 0:
            # Fallback: try comparing with HEAD
            result = subprocess.run(
                ["git", "diff", "HEAD", "--", "."],
                capture_output=True,
                text=True,
                cwd=Path.cwd()
            )
        
        return result.stdout
    except Exception as e:
        logger.error(f"Failed to get git diff: {e}")
        return ""


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
                entries.append(DiffEntry(
                    filename=current_file,
                    status=current_status,
                    additions=additions,
                    deletions=deletions,
                    patch="\n".join(patch_lines)
                ))
            
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
                new_start = int(match.group(1))
                new_count = int(match.group(2) or 1)
                old_start = int(match.group(3))
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
        entries.append(DiffEntry(
            filename=current_file,
            status=current_status,
            additions=additions,
            deletions=deletions,
            patch="\n".join(patch_lines)
        ))
    
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

    Returns:
        Dict with review results
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
        cache_ttl_days=config.cache.ttl_days,
        enable_file_cache=not disable_cache
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
            logger.info(f"Loaded {len(rule_engine.rules)} detection rules")
        except Exception as e:
            logger.warning(f"Failed to load rules: {e}")

    # Get file cache
    file_cache = cache_manager.file_cache if not disable_cache else None

    # Run review
    orchestrator = ReviewOrchestrator(
        config, llm, 
        rule_engine=rule_engine,
        file_cache=file_cache
    )
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

    return {"result": result.model_dump(), "outputs": outputs}


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
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse as inline JSON: {e}")

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
        logger.warning(f"Diff input is not valid JSON and file does not exist: {diff_input[:100]}...")

    return []


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
        "--output", "-o", type=str, 
        help="Output path for report (overrides config)"
    )
    
    parser.add_argument(
        "--branch", "-b", type=str, 
        help="Git branch to compare against (e.g., main, develop)"
    )
    
    parser.add_argument(
        "--base-branch", type=str,
        help="Base branch for comparison (overrides --branch)"
    )
    
    parser.add_argument(
        "--rules-dir", type=str,
        help="Custom rules directory (default: built-in rules)"
    )
    
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Disable file-level review caching"
    )

    args = parser.parse_args()

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
            )
        )

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            # Print PR comment if available
            if "pr_comment" in result.get("outputs", {}):
                print(result["outputs"]["pr_comment"])

            # Print report path if saved
            if "markdown" in result.get("outputs", {}):
                print(f"\n📄 Full report generated.")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
