"""Code Review Agent using LangGraph.

This agent reviews code changes and provides risk assessment
with confidence scoring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END

from codereview.models import (
    Config,
    DiffEntry,
    FileIssue,
    FileReview,
    ProjectContext,
    RiskLevel,
    ReviewConclusion,
    ReviewResult,
)


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

    def __init__(self, config: Config, llm: Any, project_context: ProjectContext):
        """Initialize review agent.

        Args:
            config: Agent configuration
            llm: LangChain LLM instance
            project_context: Pre-analyzed project context
        """
        self.config = config
        self.llm = llm
        self.project_context = project_context

    async def review_files(self, diff_entries: list[DiffEntry]) -> list[FileReview]:
        """Review multiple files.

        Args:
            diff_entries: List of file diffs to review

        Returns:
            List of file review results
        """
        results = []

        for entry in diff_entries:
            # Skip excluded patterns
            if self._should_exclude(entry.filename):
                continue

            review = await self._review_file(entry)
            results.append(review)

        return results

    def _should_exclude(self, filename: str) -> bool:
        """Check if file should be excluded from review."""
        import fnmatch

        for pattern in self.config.exclude_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    async def _review_file(self, entry: DiffEntry) -> FileReview:
        """Review a single file.

        Args:
            entry: File diff entry

        Returns:
            File review result
        """
        prompt = self._build_prompt(entry)
        chain = prompt | self.llm | JsonOutputParser()

        try:
            result = await chain.ainvoke(
                {
                    "project_context": json.dumps(self.project_context.model_dump(), indent=2),
                    "critical_paths": "\n".join(self.project_context.critical_paths),
                    "exclude_patterns": "\n".join(self.config.exclude_patterns),
                    "filename": entry.filename,
                    "status": entry.status,
                    "additions": entry.additions,
                    "deletions": entry.deletions,
                    "patch": entry.patch or "No diff available",
                }
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

        except Exception as e:
            # Return a basic review on error
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes=f"+{entry.additions}, -{entry.deletions}",
                issues=[],
            )

    def _build_prompt(self, entry: DiffEntry) -> ChatPromptTemplate:
        """Build prompt for file review."""
        return ChatPromptTemplate.from_messages(
            [("system", REVIEW_SYSTEM_PROMPT), ("user", """Review this code change.""")]
        )

    def _is_critical_path(self, filename: str) -> bool:
        """Check if file is in a critical path."""
        for path in self.project_context.critical_paths:
            if filename.startswith(path):
                return True
        return False

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

    def __init__(self, config: Config, llm: Any):
        """Initialize orchestrator.

        Args:
            config: Agent configuration
            llm: LangChain LLM instance
        """
        self.config = config
        self.llm = llm

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

        # Create review agent
        agent = ReviewAgent(self.config, self.llm, project_context)

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
