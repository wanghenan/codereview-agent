"""Code Review Agent using LangGraph.

This agent reviews code changes and provides risk assessment
with confidence scoring.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from tqdm import tqdm

from codereview.models import (
    Config,
    DiffEntry,
    FileIssue,
    FileReview,
    ProjectContext,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)

logger = logging.getLogger(__name__)

# Try to import rule engine
try:
    from codereview.rules import RuleEngine, create_rule_engine  # noqa: F401

    RULES_AVAILABLE = True
except ImportError:
    RULES_AVAILABLE = False
    logger.warning("Rule engine not available, skipping static analysis")


# State for the review agent
class ReviewState(dict):
    """State for code review agent."""

    config: Config
    diff_entries: list[DiffEntry]
    project_context: ProjectContext
    results: list[FileReview] = []
    review_complete: bool = False


# System prompt for code review
REVIEW_SYSTEM_PROMPT = """You are an expert code reviewer. Your task is to review code changes
and identify potential issues.

## Project Context
{project_context}

## Critical Paths (High Risk Areas)
{critical_paths}

## Exclude Patterns
{exclude_patterns}

## Static Analysis Results
{static_results}

## Code Diff
File: {filename}
Status: {status}
Changes: +{additions} -{deletions}
Diff:
{patch}

## Your Task
Analyze this code change and provide a risk assessment in JSON format:
{{
    "risk_level": "high|medium|low",
    "issues": [
        {{
            "line_number": 123,
            "risk_level": "high|medium|low",
            "description": "Issue description",
            "suggestion": "How to fix"
        }}
    ],
    "summary": "Brief summary of the review"
}}

Guidelines:
- HIGH risk: Security vulnerabilities, hardcoded secrets, auth issues, breaking changes
- MEDIUM risk: Code smells, potential bugs, maintainability issues
- LOW risk: Style issues, minor improvements

Be strict but fair. Focus on real issues, not style preferences."""


class ReviewAgent:
    """LangGraph-based code review agent."""

    def __init__(
        self,
        config: Config,
        llm: Any,
        project_context: ProjectContext,
        rule_engine: Optional[Any] = None,
        file_cache: Optional[Any] = None,
    ):
        """Initialize review agent.

        Args:
            config: Agent configuration
            llm: LangChain LLM instance
            project_context: Pre-analyzed project context
            rule_engine: Optional rule engine for static analysis
            file_cache: Optional file-level review cache
        """
        self.config = config
        self.llm = llm
        self.project_context = project_context
        self.rule_engine = rule_engine
        self.file_cache = file_cache
        self.max_concurrency = config.max_concurrency
        self.timeout_seconds = config.timeout_seconds

    async def review_files(self, diff_entries: list[DiffEntry]) -> list[FileReview]:
        """Review multiple files with parallel processing.

        Args:
            diff_entries: List of file diffs to review

        Returns:
            List of file review results
        """
        results = []
        semaphore = asyncio.Semaphore(self.max_concurrency)
        max_retries = 3

        # Track progress
        completed = 0
        total = 0

        async def review_with_semaphore(entry: DiffEntry) -> tuple[DiffEntry, Optional[FileReview]]:
            nonlocal completed
            async with semaphore:
                result = await self._review_file_with_retry(entry, max_retries=max_retries)
                completed += 1
                # Log progress
                percent = 100 * completed // total if total > 0 else 0
                short_name = entry.filename.split("/")[-1] if entry.filename else "unknown"
                logger.info(f"📊 Reviewing: {completed}/{total} ({percent}%) - {short_name}")
                return (entry, result)

        # Check for cached results first
        tasks = []
        cached_results = {}

        for entry in diff_entries:
            # Skip excluded patterns
            if self._should_exclude(entry.filename):
                continue

            # Check cache if available
            if self.file_cache and entry.patch:
                cached = self.file_cache.get(entry.filename, entry.patch)
                if cached:
                    logger.info(f"Using cached review for {entry.filename}")
                    cached_results[entry.filename] = FileReview(**cached)
                    continue

            tasks.append(review_with_semaphore(entry))

        total = len(tasks)

        if tasks:
            pbar = tqdm(
                tasks,
                desc="Reviewing",
                unit="file",
                disable=len(tasks) <= 1 or bool(os.getenv("TQDM_DISABLE")),
            )
            # Use as_completed to process results as they come in
            for coro in asyncio.as_completed(pbar):
                entry, review = await coro
                pbar.update(1)
                pbar.set_postfix(file=entry.filename[:30] if entry.filename else "unknown")

                if isinstance(review, Exception):
                    logger.error(f"Review failed for {entry.filename}: {review}")
                    continue
                if review:
                    results.append(review)

                    # Cache the result
                    if self.file_cache and review.file_path and entry.patch:
                        self.file_cache.save(review.file_path, entry.patch, review.model_dump())
            pbar.close()

        # Add cached results
        results.extend(cached_results.values())

        # Log completion
        if total > 0:
            logger.info(f"✅ Review complete: {len(results)}/{total} files reviewed")

        return results

    async def _review_file_with_retry(
        self, entry: DiffEntry, max_retries: int = 3
    ) -> Optional[FileReview]:
        """Review a single file with retry logic.

        Args:
            entry: File diff entry
            max_retries: Maximum number of retry attempts

        Returns:
            File review result or None if all retries failed
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                result = await self._review_file(entry)
                if attempt > 0:
                    logger.info(f"Retry succeeded for {entry.filename} on attempt {attempt + 1}")
                return result
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff: 1, 2, 4 seconds
                    logger.warning(
                        f"Review failed for {entry.filename} (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Review failed for {entry.filename} after {max_retries} attempts: {e}"
                    )

        # All retries failed, return a degraded result
        return FileReview(
            file_path=entry.filename,
            risk_level=RiskLevel.MEDIUM,
            changes=f"+{entry.additions}, -{entry.deletions}",
            issues=[
                FileIssue(
                    file_path=entry.filename,
                    risk_level=RiskLevel.MEDIUM,
                    description=f"Review failed after {max_retries} attempts: {last_error}",
                    suggestion="Consider reviewing this file manually or breaking it into smaller changes",
                )
            ],
        )

    def _should_exclude(self, filename: str) -> bool:
        """Check if file should be excluded from review."""
        import fnmatch

        for pattern in self.config.exclude_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    async def _review_file(self, entry: DiffEntry) -> FileReview:
        """Review a single file with timeout handling.

        Args:
            entry: File diff entry

        Returns:
            File review result
        """
        # Run static analysis first (fast)
        static_issues = []
        if self.rule_engine and entry.patch:
            static_issues = self.rule_engine.detect_in_diff(
                entry.patch, language=self._detect_language(entry.filename)
            )

        # Build static results summary for prompt
        static_results = ""
        if static_issues:
            static_results = "Static analysis found the following issues:\n"
            for issue in static_issues:
                static_results += f"- [{issue['severity'].upper()}] {issue['description']} (Line {issue['line_number']})\n"

        prompt = self._build_prompt(entry)
        chain = prompt | self.llm | JsonOutputParser()

        try:
            # Run with timeout
            result = await asyncio.wait_for(
                chain.ainvoke(
                    {
                        "project_context": json.dumps(self.project_context.model_dump(), indent=2),
                        "critical_paths": "\n".join(self.project_context.critical_paths),
                        "exclude_patterns": "\n".join(self.config.exclude_patterns),
                        "static_results": static_results,
                        "filename": entry.filename,
                        "status": entry.status,
                        "additions": entry.additions,
                        "deletions": entry.deletions,
                        "patch": entry.patch or "No diff available",
                    }
                ),
                timeout=self.timeout_seconds,
            )

            # Parse result into FileReview
            issues = [
                FileIssue(
                    file_path=entry.filename,
                    line_number=issue.get("line_number"),
                    risk_level=RiskLevel(issue.get("risk_level", "low")),
                    description=issue.get("description", ""),
                    suggestion=issue.get("suggestion"),
                )
                for issue in result.get("issues", [])
            ]

            # Add static analysis issues
            for static_issue in static_issues:
                issues.append(
                    FileIssue(
                        file_path=entry.filename,
                        line_number=static_issue.get("line_number"),
                        risk_level=RiskLevel(static_issue.get("severity", "low")),
                        description=f"[Rule: {static_issue.get('rule_name')}] {static_issue.get('description', '')}",
                        suggestion=static_issue.get("suggestion"),
                    )
                )

            # Determine overall risk level
            risk_level = RiskLevel(result.get("risk_level", "low"))

            # Check if file is in critical path
            if self._is_critical_path(entry.filename):
                if risk_level != RiskLevel.HIGH:
                    risk_level = RiskLevel.HIGH

            return FileReview(
                file_path=entry.filename,
                risk_level=risk_level,
                changes=f"+{entry.additions}, -{entry.deletions}",
                issues=issues,
            )

        except asyncio.TimeoutError:
            # Re-raise timeout so retry logic can handle it
            raise
        except Exception:
            # Re-raise other exceptions so retry logic can handle them
            raise

    def _build_prompt(self, entry: DiffEntry) -> ChatPromptTemplate:
        """Build prompt for file review.

        If config.custom_prompt_path is set and valid, loads template from file.
        Otherwise falls back to default REVIEW_SYSTEM_PROMPT.

        Template variables supported:
        - {project_context}: Project context from analysis
        - {critical_paths}: List of critical paths
        - {exclude_patterns}: List of exclude patterns
        - {static_results}: Static analysis results
        - {filename}: Current file being reviewed
        - {status}: File status (added/modified/deleted)
        - {additions}: Number of lines added
        - {deletions}: Number of lines deleted
        - {patch}: The actual diff patch
        """
        prompt_template = REVIEW_SYSTEM_PROMPT

        # Check for custom prompt path
        if self.config.custom_prompt_path:
            custom_path = Path(self.config.custom_prompt_path)
            if custom_path.exists() and custom_path.is_file():
                try:
                    prompt_template = custom_path.read_text(encoding="utf-8")
                    logger.info(f"Using custom prompt from {custom_path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to load custom prompt {custom_path}: {e}, using default"
                    )

        return ChatPromptTemplate.from_messages(
            [("system", prompt_template), ("user", """Review this code change.""")]
        )

    def _is_critical_path(self, filename: str) -> bool:
        """Check if file is in a critical path."""
        for path in self.project_context.critical_paths:
            if filename.startswith(path):
                return True
        return False

    def _detect_language(self, filename: str) -> Optional[str]:
        """Detect programming language from file extension.

        Args:
            filename: File name

        Returns:
            Language identifier or None
        """
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
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
        }
        return language_map.get(ext)

    def create_graph(self) -> StateGraph:
        """Create LangGraph for review workflow.

        Returns:
            Compiled LangGraph
        """
        workflow = StateGraph(ReviewState)

        # Add nodes
        workflow.add_node("review_file", self._node_review_file)
        workflow.add_node("aggregate_results", self._node_aggregate)

        # Set entry point
        workflow.set_entry_point("review_file")

        # Add edges
        workflow.add_edge("review_file", "aggregate_results")
        workflow.add_edge("aggregate_results", END)

        return workflow.compile()

    async def _node_review_file(self, state: ReviewState) -> ReviewState:
        """Node: Review a single file."""
        entry = state["diff_entries"][0]  # Process first entry
        review = await self._review_file(entry)
        state["results"] = [review]
        return state

    async def _node_aggregate(self, state: ReviewState) -> ReviewState:
        """Node: Aggregate results."""
        state["review_complete"] = True
        return state


class ReviewOrchestrator:
    """Orchestrate the complete review process."""

    def __init__(
        self,
        config: Config,
        llm: Any,
        rule_engine: Optional[Any] = None,
        file_cache: Optional[Any] = None,
    ):
        """Initialize orchestrator.

        Args:
            config: Agent configuration
            llm: LangChain LLM instance
            rule_engine: Optional rule engine for static analysis
            file_cache: Optional file-level review cache
        """
        self.config = config
        self.llm = llm
        self.rule_engine = rule_engine
        self.file_cache = file_cache

    async def run_review(
        self, diff_entries: list[DiffEntry], project_context: ProjectContext | None = None
    ) -> ReviewResult:
        """Run complete review process.

        Args:
            diff_entries: List of file diffs
            project_context: Optional pre-analyzed context

        Returns:
            Complete review result
        """
        # Use default context if not provided
        if project_context is None:
            from datetime import datetime

            project_context = ProjectContext(
                tech_stack=["unknown"],
                language="unknown",
                critical_paths=self.config.critical_paths,
                analyzed_at=datetime.now().isoformat(),
            )

        # Create review agent with rule engine and file cache
        agent = ReviewAgent(
            self.config,
            self.llm,
            project_context,
            rule_engine=self.rule_engine,
            file_cache=self.file_cache,
        )

        # Review files
        file_reviews = await agent.review_files(diff_entries)

        # Calculate conclusion and confidence
        conclusion, confidence = self._calculate_result(file_reviews)

        # Generate summary
        summary = self._generate_summary(file_reviews)

        return ReviewResult(
            conclusion=conclusion,
            confidence=confidence,
            files_reviewed=file_reviews,
            summary=summary,
        )

    def _calculate_result(self, file_reviews: list[FileReview]) -> tuple[ReviewConclusion, float]:
        """Calculate review conclusion and confidence.

        Args:
            file_reviews: List of file reviews

        Returns:
            Tuple of (conclusion, confidence)
        """
        high_risk_count = sum(1 for r in file_reviews if r.risk_level == RiskLevel.HIGH)
        medium_risk_count = sum(1 for r in file_reviews if r.risk_level == RiskLevel.MEDIUM)
        low_risk_count = sum(1 for r in file_reviews if r.risk_level == RiskLevel.LOW)

        # Calculate confidence
        base_confidence = 100.0
        confidence = base_confidence - (medium_risk_count * 10) - (low_risk_count * 2)

        # Determine conclusion
        if high_risk_count > 0:
            return ReviewConclusion.NEEDS_REVIEW, 95.0
        elif medium_risk_count <= 2:
            return ReviewConclusion.CAN_SUBMIT, max(confidence, 50.0)
        else:
            return ReviewConclusion.NEEDS_REVIEW, max(confidence, 50.0)

    def _generate_summary(self, file_reviews: list[FileReview]) -> str:
        """Generate summary text."""
        if not file_reviews:
            return "No files to review."

        summary_parts = []
        for review in file_reviews:
            issue_count = len(review.issues)
            summary_parts.append(
                f"- {review.file_path}: {review.risk_level.value} ({issue_count} issues)"
            )

        return "\n".join(summary_parts)
