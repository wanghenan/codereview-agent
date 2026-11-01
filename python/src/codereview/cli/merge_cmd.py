"""Merge command: auto-merge reviewed PRs when conditions are met."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from codereview.agents import ReviewOrchestrator
from codereview.cli.errors import SCHEMA_VERSION, _json_error
from codereview.core import ConfigLoader, LLMFactory
from codereview.models import DiffEntry

logger = logging.getLogger(__name__)


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
