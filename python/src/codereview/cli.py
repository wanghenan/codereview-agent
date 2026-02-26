"""Command-line interface for CodeReview Agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from codereview.agents import ProjectAnalyzer, ReviewOrchestrator
from codereview.core import CacheManager, ConfigLoader, LLMFactory
from codereview.models import DiffEntry, ReviewResult
from codereview.output import OutputGenerator


async def run_review(
    config_path: str | Path | None = None,
    diff_input: str | None = None,
    pr_number: int | None = None,
    force_refresh: bool = False,
    output_only: bool = False,
) -> dict:
    """Run the code review process.

    Args:
        config_path: Path to config file
        diff_input: JSON string with diff entries or path to file
        pr_number: PR number
        force_refresh: Force cache refresh
        output_only: Only output, don't save files

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
    cache_manager = CacheManager(cache_ttl_days=config.cache.ttl_days)

    # Get or analyze project context
    project_context = None

    if not config.cache.force_refresh:
        project_context = cache_manager.load()

    if project_context is None:
        # Analyze project
        analyzer = ProjectAnalyzer(config, llm)
        project_context = await analyzer.analyze(Path.cwd())
        cache_manager.save(project_context)

    # Parse diff input
    diff_entries = _parse_diff(diff_input)

    # Run review
    orchestrator = ReviewOrchestrator(config, llm)
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

    generator = OutputGenerator(output_config)
    outputs = await generator.generate(result, pr_number)

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
            pass

    if not diff_input:
        return []

    # Try to load as JSON
    try:
        data = json.loads(diff_input)
        if isinstance(data, list):
            return [DiffEntry(**entry) for entry in data]
        elif isinstance(data, dict) and "files" in data:
            return [DiffEntry(**entry) for entry in data["files"]]
    except json.JSONDecodeError:
        pass

    # If it's a path, try to read file
    path = Path(diff_input)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return [DiffEntry(**entry) for entry in data.get("files", data)]
        except Exception:
            pass

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
