"""Review command: orchestrate the full code review process."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

from codereview.agents import ProjectAnalyzer, ReviewOrchestrator
from codereview.cli.diff_parser import _parse_diff, get_git_diff, parse_git_diff_to_entries
from codereview.core import CacheManager, ConfigLoader, LLMFactory
from codereview.core.dedupe import MEMORY_PATH, AlreadyReportedIndex, TeamMemory, apply_dedupe
from codereview.core.github_client import create_github_client
from codereview.models import CacheInfo
from codereview.output import InlineCommentBuilder, OutputGenerator

# Try to import rule engine
try:
    from codereview.rules import create_rule_engine, get_all_rules

    RULES_AVAILABLE = True
except ImportError:
    RULES_AVAILABLE = False
    logging.warning("Rule engine not available")

logger = logging.getLogger(__name__)


def _compute_rules_hash(rule_engine: object) -> str:
    """Compute a short, stable hash of the active rule set.

    Folded into the file-review cache key so that editing/updating the OWASP
    rules (or disabling rules) invalidates stale cached reviews.

    Args:
        rule_engine: A RuleEngine instance (or None).

    Returns:
        An 8-char hex hash, or ``"no-rules"`` when there is no rule engine.
    """
    import hashlib

    rules = getattr(rule_engine, "rules", None)
    if not rules:
        return "no-rules"

    # Sort for stability across rule insertion order; only identity-relevant
    # fields matter for cache validity.
    payload = sorted(
        (getattr(r, "id", ""), getattr(r, "pattern", ""), getattr(r, "severity", ""))
        for r in rules
    )
    raw = repr(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:8]


def _compute_cache_namespace(config: object, rule_engine: object) -> str:
    """Build the cache namespace from the active model and rule hash.

    Args:
        config: Agent Config (its ``llm`` field determines the model).
        rule_engine: RuleEngine instance (or None).

    Returns:
        ``"<model>:<rules-hash>"``.
    """
    llm_cfg = getattr(config, "llm", None)
    model = getattr(llm_cfg, "model", None) or LLMFactory.DEFAULT_MODELS.get(
        getattr(llm_cfg, "provider", None), "unknown"
    )
    return f"{model}:{_compute_rules_hash(rule_engine)}"

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
    dry_run: bool = False,
    offline: bool = False,
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
        disabled_rules: Rule ids to disable
        dry_run: Build inline review payload but do not post it
        offline: Alias for dry-run inline behaviour; never touch the network

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

    # Initialize rule engine if available (needed before cache namespace,
    # since the rules hash is folded into the file-review cache key)
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

    # Initialize cache manager. The namespace folds in the active model and
    # rule-set hash so changing either invalidates stale file-review caches.
    cache_namespace = _compute_cache_namespace(config, rule_engine)
    cache_manager = CacheManager(
        cache_ttl_days=config.cache.ttl_days,
        enable_file_cache=not disable_cache,
        cache_namespace=cache_namespace,
    )

    # Reclaim disk space by pruning expired/corrupt file-review cache entries.
    # Cheap (glob + header read) and bounds cache growth across runs.
    if cache_manager.file_cache is not None:
        removed = cache_manager.file_cache.cleanup_expired()
        if removed:
            logger.debug(f"Pruned {removed} expired cache file(s)")

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

    # Get file cache
    file_cache = cache_manager.file_cache if not disable_cache else None

    # Run review
    orchestrator = ReviewOrchestrator(config, llm, rule_engine=rule_engine, file_cache=file_cache)
    result = await orchestrator.run_review(diff_entries, project_context)

    # Add cache info
    cache_info = cache_manager.get_cache_info()
    result.cache_info = CacheInfo(
        used_cache=project_context is not None and not config.cache.force_refresh,
        cache_timestamp=cache_info.get("modified_at"),
        cache_version=cache_info.get("version"),
    )

    # Generate output
    output_config = config.output
    if output_only:
        # Don't save files
        output_config.report_path = ""

    # Override output path if specified
    if output_path:
        output_config.report_path = output_path

    # S6: suppress what the PR already reports and down-weight what a human
    # dismissed. Both are best-effort: a failed GitHub read leaves the review
    # exactly as it would have been without this step.
    github_client = None
    dedupe_report = None
    if pr_number is not None and config.output.pr_comment:
        if not (dry_run or offline):
            try:
                github_client = create_github_client(github_token=github_token)
            except Exception as e:
                logger.warning(
                    "Could not create GitHub client; skipping inline review for PR #%s: %s",
                    pr_number,
                    e,
                )
        dedupe_report = await _dedupe_against_pr(
            result,
            pr_number,
            client=github_client,
            memory_path=Path.cwd() / MEMORY_PATH,
            touch_network=not (dry_run or offline),
        )

    generator = OutputGenerator(output_config)
    outputs = await generator.generate(result, pr_number)

    # Inline review output (S2): always expose the machine-readable findings
    # payload, and post the line-anchored comments as a single review when a PR
    # is known and PR commenting is enabled.
    inline_builder = InlineCommentBuilder()
    outputs["findings"] = inline_builder.findings_payload(result)
    if dedupe_report is not None:
        outputs["dedupe"] = {
            "already_reported": dedupe_report.already_reported,
            "downweighted": dedupe_report.downweighted,
        }

    if pr_number is not None and config.output.pr_comment:
        notes = dedupe_report.notes() if dedupe_report is not None else None
        inline_payload = inline_builder.build(result, notes=notes)
        if dry_run or offline:
            logger.info("Skipping inline review post for PR #%s (dry-run/offline)", pr_number)
        elif not inline_payload["comments"] and dedupe_report and dedupe_report.already_reported:
            # Every finding this run produced is already on the PR. Posting an
            # empty review would repeat the summary for no new information.
            logger.info(
                "All %d finding(s) were already reported on PR #%s; nothing to post",
                dedupe_report.already_reported,
                pr_number,
            )
        elif github_client is None:
            logger.warning("No GitHub client; skipping inline review for PR #%s", pr_number)
        else:
            try:
                posted = await github_client.create_review(
                    pr_number,
                    inline_payload["comments"],
                    body=inline_payload["summary"],
                )
                if not posted:
                    logger.warning("GitHub rejected inline review for PR #%s", pr_number)
            except Exception as e:
                logger.warning("Failed to post inline review for PR #%s: %s", pr_number, e)

    # Print cache stats
    if file_cache:
        stats = file_cache.get_stats()
        logger.info(f"File cache stats: {stats}")

    # Auto-merge if requested
    merge_output = None
    if auto_merge and pr_number:
        from codereview.core.auto_merger import create_auto_merger

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
async def _dedupe_against_pr(
    result,
    pr_number: int,
    *,
    client,
    memory_path: Path,
    touch_network: bool,
):
    """Drop already-reported findings and apply team memory to one result.

    Args:
        result: Review result to prune in place.
        pr_number: PR whose existing comments are the dedupe baseline.
        client: GitHub client, or ``None`` when one could not be created.
        memory_path: Where the dismissal memory lives for this repository.
        touch_network: False for dry-run/offline, which must not call GitHub.

    Returns:
        A :class:`codereview.core.dedupe.DedupeReport`.
    """
    comments = []
    if client is not None and touch_network:
        try:
            comments = await client.list_review_comments(pr_number)
        except Exception as e:  # noqa: BLE001 - dedupe must never fail a review
            logger.warning("Could not read existing PR comments for dedupe: %s", e)

    memory = TeamMemory.load(memory_path)
    learned = memory.learn_from_comments(comments)
    if learned:
        memory.save()
        logger.info("Team memory learned %d dismissal(s) from PR #%s reactions", learned, pr_number)

    return apply_dedupe(result, AlreadyReportedIndex.from_comments(comments), memory)


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
