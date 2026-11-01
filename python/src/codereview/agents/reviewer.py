"""Code Review Agent using LangGraph.

This agent reviews code changes and provides risk assessment
with confidence scoring.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, TypedDict

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from tqdm import tqdm

from codereview.core.diff_filter import FilterConfig, filter_entries
from codereview.core.finding_filter import FilterRules, filter_findings
from codereview.core.path_matcher import ExcludeMatcher
from codereview.core.symbol_index import Neighbor, SymbolIndex
from codereview.core.tool_runner import ToolRunner
from codereview.models import (
    Config,
    DiffEntry,
    Evidence,
    EvidenceKind,
    FileIssue,
    FileReview,
    FilteredFinding,
    IssueCategory,
    ProjectContext,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)

logger = logging.getLogger(__name__)

#: Directories ignored while looking for the newest Python source.  Kept in
#: sync with ``codereview.core.symbol_index`` so freshness checks see the same
#: tree the index would build from.
_INDEX_IGNORED_DIRS = {
    ".codereview-agent",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}

#: New-file range from a unified-diff hunk header, e.g. ``@@ -1,3 +1,5 @@``.
_HUNK_RANGE_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

# Try to import rule engine
try:
    from codereview.rules import RuleEngine, create_rule_engine  # noqa: F401

    RULES_AVAILABLE = True
except ImportError:
    RULES_AVAILABLE = False
    logger.warning("Rule engine not available, skipping static analysis")


def _extract_balanced_object(text: str) -> Optional[str]:
    """Extract the first balanced ``{...}`` JSON object from ``text``.

    Scans for an opening ``{`` and tracks brace depth to arbitrary nesting,
    ignoring braces inside string literals (handling ``\\"`` escapes). Returns
    the substring of the first object whose braces balance, or ``None``.

    Unlike a fixed-depth regex this handles deeply nested objects correctly,
    e.g. ``{"a":{"b":{"c":1}}}``.

    Args:
        text: Text that may contain a JSON object.

    Returns:
        The balanced object substring, or None.
    """
    start = -1
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    return text[start : i + 1]

    return None


def _raise_os_error(error: OSError) -> None:
    """Surface ``os.walk`` errors so callers can degrade explicitly."""
    raise error


def _newest_python_mtime(root: Path) -> tuple[float, int]:
    """Return the newest Python mtime and the number of files under ``root``.

    Directory traversal errors propagate as ``OSError``; individual files that
    cannot be stat'ed are skipped so one broken symlink does not hide an
    otherwise usable tree.
    """
    newest = 0.0
    count = 0

    for current, dirs, files in os.walk(root, onerror=_raise_os_error):
        dirs[:] = sorted(
            name for name in dirs if name not in _INDEX_IGNORED_DIRS and not name.startswith(".")
        )
        for name in files:
            if not name.endswith(".py"):
                continue
            path = Path(current) / name
            try:
                mtime = path.stat().st_mtime
            except OSError as exc:
                logger.debug("Could not stat Python source %s: %s", path, exc)
                continue
            newest = max(newest, mtime)
            count += 1

    return newest, count


# State for the review orchestrator graph
class OrchestratorState(TypedDict, total=False):
    """State for the review orchestrator graph."""

    config: Config
    diff_entries: list[DiffEntry]
    project_context: ProjectContext | None
    symbol_index: SymbolIndex | None
    file_reviews: list[FileReview]
    conclusion: ReviewConclusion | None
    confidence: float
    summary: str
    review_complete: bool


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

{cross_file_context}

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
            "category": "bug|security|perf|maintainability|style",
            "title": "One-line summary of the finding",
            "description": "Issue description",
            "suggestion": "How to fix",
            "confidence": 0.0,
            "evidence": ["symbol, rule id, or file:line that proves it"],
            "caller": "path:line of the caller, only when the cross-file context shows one"
        }}
    ],
    "summary": "Brief summary of the review"
}}

Guidelines:
- HIGH risk: Security vulnerabilities, hardcoded secrets, auth issues, breaking changes
- MEDIUM risk: Code smells, potential bugs, maintainability issues
- LOW risk: Style issues, minor improvements
- risk_level must be exactly "high", "medium", or "low"
- issues must always be a list (empty [] if no issues)
- Be strict but fair. Focus on real issues, not style preferences.
- category is one of bug / security / perf / maintainability / style
- confidence is a number between 0 and 1 (how sure you are the issue is real)
- evidence lists concrete anchors (symbol names, line numbers, rule ids); an
  issue without any anchor is speculation and should be left out

## Examples

### Example 1 - High Risk (SQL Injection)
Input: A diff adding string concatenation in a SQL query
Output:
{{
    "risk_level": "high",
    "issues": [
        {{
            "line_number": 42,
            "risk_level": "high",
            "description": "SQL injection vulnerability: user input directly concatenated into SQL query",
            "suggestion": "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))"
        }}
    ],
    "summary": "Critical SQL injection vulnerability found in database query"
}}

### Example 2 - Medium Risk (Missing Error Handling)
Input: A diff adding a try block with an empty except
Output:
{{
    "risk_level": "medium",
    "issues": [
        {{
            "line_number": 15,
            "risk_level": "medium",
            "description": "Empty except clause silently swallows all exceptions",
            "suggestion": "Catch specific exceptions and log them: except ValueError as e: logger.error(...)"
        }}
    ],
    "summary": "Poor error handling that may hide runtime issues"
}}

### Example 3 - Low Risk (Naming Convention)
Input: A diff with inconsistent variable naming
Output:
{{
    "risk_level": "low",
    "issues": [],
    "summary": "Clean change with no significant issues found"
}}"""


_CALLER_RE = re.compile(r"^[\w./-]+:\d+$")


def _clean_caller(value: Any) -> Optional[str]:
    """Return ``value`` if it looks like ``path:line``, else ``None``.

    The caller field is a structured claim used for scoring and reporting, so
    a malformed value is dropped rather than stored verbatim.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 200:
        return None
    return candidate if _CALLER_RE.match(candidate) else None


class ReviewAgent:
    """LangGraph-based code review agent."""

    def __init__(
        self,
        config: Config,
        llm: Any,
        project_context: ProjectContext,
        rule_engine: Optional[Any] = None,
        file_cache: Optional[Any] = None,
        tool_runner: Optional[Any] = None,
        project_root: Optional[str | Path] = None,
        symbol_index: Optional[SymbolIndex] = None,
    ):
        """Initialize review agent.

        Args:
            config: Agent configuration
            llm: LangChain LLM instance
            project_context: Pre-analyzed project context
            rule_engine: Optional rule engine for static analysis
            file_cache: Optional file-level review cache
            tool_runner: Optional external tool runner (defaults to ToolRunner)
            project_root: Directory external tools run from (defaults to cwd)
            symbol_index: Optional pre-built symbol index for cross-file context
        """
        self.config = config
        self.llm = llm
        self.project_context = project_context
        self.rule_engine = rule_engine
        self.file_cache = file_cache
        self.tool_runner = tool_runner if tool_runner is not None else ToolRunner()
        self.project_root = Path(project_root) if project_root is not None else Path.cwd()
        self.symbol_index = symbol_index
        self.max_concurrency = config.max_concurrency
        self.timeout_seconds = config.timeout_seconds

        # Pre-compile exclude patterns once (gitignore semantics via pathspec)
        self._exclude_matcher = ExcludeMatcher(config.exclude_patterns)

        # Pre-compute a compact project context summary to reduce token usage
        self._context_summary = self._build_context_summary()

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

        async def review_with_semaphore(entry: DiffEntry) -> tuple[DiffEntry, Optional[FileReview]]:
            async with semaphore:
                result = await self._review_file_with_retry(entry, max_retries=max_retries)
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
            # tqdm wraps the async iterator from as_completed so the bar
            # advances exactly once per completion (no double counting).
            disable = len(tasks) <= 1 or bool(os.getenv("TQDM_DISABLE"))
            with tqdm(
                asyncio.as_completed(tasks),
                total=total,
                desc="Reviewing",
                unit="file",
                disable=disable,
            ) as pbar:
                for coro in pbar:
                    try:
                        entry, review = await coro
                    except Exception as e:
                        # Defensive: _review_file_with_retry already degrades
                        # to a FileReview on failure, but guard against any
                        # exception that escapes it so one bad file cannot
                        # abort the whole batch.
                        logger.error(f"Review task failed unexpectedly: {e}")
                        pbar.update(1)
                        continue

                    pbar.update(1)
                    short = entry.filename[:30] if entry.filename else "unknown"
                    pbar.set_postfix(file=short)

                    if review:
                        results.append(review)

                        # Cache the result
                        if self.file_cache and review.file_path and entry.patch:
                            self.file_cache.save(
                                review.file_path, entry.patch, review.model_dump()
                            )

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

    @staticmethod
    def _to_finding(file_path: str, raw: dict[str, Any]) -> FileIssue:
        """Map one LLM issue dict onto :class:`FileIssue`.

        Unknown/malformed optional fields fall back to defaults rather than
        dropping the whole finding: a review result is more useful with a
        partially populated issue than with nothing.
        """

        def _enum(value: Any, enum_type: Any, default: Any) -> Any:
            try:
                return enum_type(value)
            except (TypeError, ValueError):
                return default

        evidence: list[Evidence] = []
        for item in raw.get("evidence") or []:
            if isinstance(item, str) and item.strip():
                evidence.append(Evidence(kind=EvidenceKind.CONTEXT, detail=item.strip()))
            elif isinstance(item, dict) and item.get("detail"):
                evidence.append(
                    Evidence(
                        kind=_enum(item.get("kind"), EvidenceKind, EvidenceKind.CONTEXT),
                        detail=str(item["detail"]),
                    )
                )

        confidence = raw.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.5

        return FileIssue(
            file_path=file_path,
            line_number=raw.get("line_number"),
            end_line=raw.get("end_line"),
            risk_level=_enum(raw.get("risk_level", "low"), RiskLevel, RiskLevel.LOW),
            description=raw.get("description", ""),
            suggestion=raw.get("suggestion"),
            title=str(raw.get("title") or "")[:200],
            caller=_clean_caller(raw.get("caller")),
            category=_enum(raw.get("category"), IssueCategory, IssueCategory.BUG),
            confidence=max(0.0, min(1.0, float(confidence))),
            evidence=evidence,
            source="llm",
        )

    def _build_context_summary(self) -> str:
        """Build a compact project context summary to reduce token usage.

        Instead of sending the full JSON dump of project_context every time,
        send only the essential fields.

        Returns:
            Compact context string
        """
        ctx = self.project_context
        parts = []

        if ctx.language:
            parts.append(f"Language: {ctx.language}")
        if ctx.tech_stack:
            parts.append(f"Tech stack: {', '.join(ctx.tech_stack[:5])}")
        if ctx.frameworks:
            parts.append(f"Frameworks: {', '.join(ctx.frameworks[:5])}")
        if ctx.code_style:
            parts.append(f"Code style: {ctx.code_style}")

        return "\n".join(parts) if parts else "General project"

    @staticmethod
    def _changed_range(entry: DiffEntry) -> Optional[tuple[int, int]]:
        """Return the inclusive new-file line range touched by ``entry``.

        A unified diff may contain several hunks; the union of their new-file
        ranges is used so one symbol index lookup covers the whole change.
        Entries without a parseable hunk (for example ``patch=None``) have no
        well-defined changed range and yield ``None``.
        """
        if not entry.patch:
            return None

        ranges: list[tuple[int, int]] = []
        for match in _HUNK_RANGE_RE.finditer(entry.patch):
            start = int(match.group(1))
            count = int(match.group(2) or 1)
            end = start + count - 1 if count > 0 else start
            ranges.append((start, end))

        if not ranges:
            return None
        return min(start for start, _ in ranges), max(end for _, end in ranges)

    def _cross_file_context_for(self, entry: DiffEntry) -> str:
        """Render bounded one-hop neighbours for the file under review.

        Returns an empty string whenever cross-file context is disabled, the
        index is absent/empty, the diff has no usable range, or lookup fails.
        Context injection is best-effort and must never abort a review.
        """
        if self.symbol_index is None:
            return ""

        context_config = self.config.context
        if (
            not context_config.neighbors
            or context_config.max_neighbors <= 0
            or context_config.max_chars <= 0
        ):
            return ""

        changed = self._changed_range(entry)
        if changed is None:
            return ""

        try:
            neighbors = self.symbol_index.neighbors(
                entry.filename,
                changed[0],
                changed[1],
                limit=context_config.max_neighbors,
            )
        except Exception as exc:
            logger.warning("Could not collect cross-file context for %s: %s", entry.filename, exc)
            return ""

        return self._format_cross_file_context(
            list(neighbors)[: context_config.max_neighbors],
            context_config.max_chars,
        )

    @staticmethod
    def _format_cross_file_context(neighbors: list[Neighbor], max_chars: int) -> str:
        """Format neighbours compactly, truncating the tail to ``max_chars``."""
        if not neighbors or max_chars <= 0:
            return ""

        def numbered(neighbor: object) -> str:
            """Prefix the excerpt with real line numbers so cited lines are exact."""
            start = getattr(neighbor, "start_line", 1)
            lines = str(getattr(neighbor, "excerpt", "")).splitlines()
            body = "\n".join(f"{start + offset:5d} | {line}" for offset, line in enumerate(lines))
            return (
                f"{getattr(neighbor, 'reason', 'context')} {getattr(neighbor, 'path', '?')}:"
                f"{getattr(neighbor, 'start_line', 0)}-{getattr(neighbor, 'end_line', 0)}\n{body}"
            )

        blocks = [numbered(neighbor) for neighbor in neighbors]
        text = "## Cross-file context\n\n" + "\n\n".join(blocks)
        if len(text) <= max_chars:
            return text

        note = "\n... [truncated]"
        if max_chars <= len(note):
            return text[:max_chars]
        return text[: max_chars - len(note)].rstrip() + note

    def _should_exclude(self, filename: str) -> bool:
        """Check if file should be excluded from review.

        Uses gitignore-style matching (recursive ``**``, ``!`` negation,
        directory anchoring) so documented patterns like ``dist/**`` and
        ``node_modules/**`` behave as users expect.
        """
        return self._exclude_matcher.matches(filename)

    def _tool_issues_for(self, filename: str) -> list[FileIssue]:
        """Run external tools for one changed file and convert their output.

        The runner is invoked only when at least one tool is available for the
        path. Every failure (unavailable runner, spawn error, malformed output)
        is logged and swallowed so external tooling can never abort a review.

        Args:
            filename: Repository-relative path of the file being reviewed.

        Returns:
            Tool findings converted to :class:`FileIssue` objects.
        """
        runner = self.tool_runner
        if runner is None:
            return []

        paths = [filename]

        try:
            list_tools = getattr(runner, "list_tools", None)
            available = list_tools(paths) if callable(list_tools) else None
            if available is not None and not available:
                return []

            # A real ToolRunner reports every unavailable tool as an error
            # entry. Scope it to the available specs so a Python-only change
            # does not gain "eslint is not installed" noise.
            active_runner = runner
            if isinstance(runner, ToolRunner) and available is not None:
                active_runner = ToolRunner(tools=available, timeout=runner.timeout)

            findings = active_runner.run(paths, cwd=self.project_root)
        except Exception as exc:
            logger.warning("External tool analysis failed for %s: %s", filename, exc)
            return []

        issues: list[FileIssue] = []
        for finding in findings or []:
            if not isinstance(finding, dict):
                continue
            try:
                issues.append(self._tool_finding_to_issue(filename, finding))
            except Exception as exc:
                logger.warning("Could not convert tool finding for %s: %s", filename, exc)
        return issues

    @staticmethod
    def _tool_finding_to_issue(fallback_path: str, finding: dict[str, Any]) -> FileIssue:
        """Map one normalised tool finding onto a :class:`FileIssue`."""
        severity = str(finding.get("severity") or "").lower()
        tool = str(finding.get("tool") or "tool")
        rule_id = str(finding.get("rule_id") or "unknown")
        file_path = str(finding.get("file") or fallback_path)

        raw_line = finding.get("line")
        try:
            line_number: Optional[int] = int(raw_line) if raw_line is not None else None
        except (TypeError, ValueError):
            line_number = None
        if line_number is not None and line_number <= 0:
            line_number = None

        if severity == "high":
            category = IssueCategory.BUG
            risk_level = RiskLevel.HIGH
        else:
            category = IssueCategory.MAINTAINABILITY
            risk_level = (
                RiskLevel.MEDIUM
                if severity in ("error", "warning", "medium")
                else RiskLevel.LOW
            )

        return FileIssue(
            file_path=file_path,
            line_number=line_number,
            risk_level=risk_level,
            description=str(finding.get("description") or f"{tool} reported {rule_id}"),
            title=f"{tool}: {rule_id}",
            category=category,
            confidence=0.85,
            source="tool",
            evidence=[Evidence(kind=EvidenceKind.RULE, detail=f"{tool}_{rule_id}")],
        )

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

        # External tools run after the rule engine; they are supplementary and
        # must never break the review when a binary is missing or malformed.
        tool_issues = self._tool_issues_for(entry.filename)

        # Build static results summary for prompt
        static_results = ""
        if static_issues:
            static_results = "Static analysis found the following issues:\n"
            for issue in static_issues:
                static_results += f"- [{issue['severity'].upper()}] {issue['description']} (Line {issue['line_number']})\n"

        cross_file_context = self._cross_file_context_for(entry)
        prompt = self._build_prompt(entry)
        chain = prompt | self.llm | JsonOutputParser()

        try:
            # Run with timeout
            raw_result = await asyncio.wait_for(
                chain.ainvoke(
                    {
                        "project_context": self._context_summary,
                        "critical_paths": "\n".join(self.project_context.critical_paths[:10]),
                        "exclude_patterns": "\n".join(self.config.exclude_patterns[:5]),
                        "static_results": static_results,
                        "cross_file_context": cross_file_context,
                        "filename": entry.filename,
                        "status": entry.status,
                        "additions": entry.additions,
                        "deletions": entry.deletions,
                        "patch": entry.patch or "No diff available",
                    }
                ),
                timeout=self.timeout_seconds,
            )

            # If JsonOutputParser returned None or invalid, try to repair
            result = raw_result if isinstance(raw_result, dict) else self._repair_json_output(raw_result)

            if result is None:
                raise ValueError("Failed to parse LLM output as JSON")

            # Normalize risk_level values
            raw_risk = result.get("risk_level", "low")
            if isinstance(raw_risk, str):
                raw_risk = raw_risk.lower()
            result["risk_level"] = raw_risk if raw_risk in ("high", "medium", "low") else "low"

            # Ensure issues is a list
            if not isinstance(result.get("issues"), list):
                result["issues"] = []

            # Parse result into FileReview
            issues = [
                self._to_finding(entry.filename, issue) for issue in result.get("issues", [])
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
                        title=str(static_issue.get("rule_name") or "rule hit"),
                        category=IssueCategory.SECURITY,
                        confidence=0.9,
                        source="rule",
                        evidence=[
                            Evidence(
                                kind=EvidenceKind.RULE,
                                detail=str(
                                    static_issue.get("rule_id")
                                    or static_issue.get("rule_name")
                                    or "unknown-rule"
                                ),
                            )
                        ],
                    )
                )

            # Add external tool findings (already converted to FileIssue)
            issues.extend(tool_issues)

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

    @staticmethod
    def _repair_json_output(raw: Any) -> Optional[dict]:
        """Try to extract valid JSON from malformed LLM output.

        Handles common cases:
        - LLM wraps JSON in markdown code blocks
        - Extra text before/after the JSON
        - Truncated JSON

        Args:
            raw: Raw LLM output (may be string, dict, or other)

        Returns:
            Parsed dict or None if unrepairable
        """
        if isinstance(raw, dict):
            return raw

        text = str(raw) if raw is not None else ""
        if not text.strip():
            return None

        # Try to find JSON block in text
        import re

        # Match markdown code blocks first: ```json ... ``` or ``` ... ```
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except json.JSONDecodeError:
                pass

        # Extract the outermost balanced JSON object via a brace-counting
        # scan. The previous regex handled only a single nesting level and
        # silently truncated deeply-nested objects; the scan below supports
        # arbitrary depth and respects string literals so braces inside
        # strings don't confuse the counter.
        extracted = _extract_balanced_object(text)
        if extracted is not None:
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass

        return None

    def _build_prompt(self, entry: DiffEntry) -> ChatPromptTemplate:
        """Build prompt for file review.

        If config.custom_prompt_path is set and valid, loads template from file.
        Otherwise falls back to default REVIEW_SYSTEM_PROMPT.

        Template variables supported:
        - {project_context}: Project context from analysis
        - {critical_paths}: List of critical paths
        - {exclude_patterns}: List of exclude patterns
        - {static_results}: Static analysis results
        - {cross_file_context}: Bounded cross-file symbol context (may be empty).
  If the change renames or changes the signature of something that other code
  calls, and the context shows the caller, name that caller using the exact
  `path:line` from the context header (for example "still called at
  src/app/caller.py:42"). Do not speculate about callers the context does not
  show; say "callers not shown" instead. Put that caller in the ``caller``
  field as ``path:line``; leave it out when no caller is shown.
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
        ).partial(cross_file_context="")

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


class ReviewOrchestrator:
    """Orchestrate the complete review process using LangGraph."""

    def __init__(
        self,
        config: Config,
        llm: Any,
        rule_engine: Optional[Any] = None,
        file_cache: Optional[Any] = None,
        tool_runner: Optional[Any] = None,
        project_root: Optional[str | Path] = None,
        symbol_index: Optional[SymbolIndex] = None,
    ):
        """Initialize orchestrator.

        Args:
            config: Agent configuration
            llm: LangChain LLM instance
            rule_engine: Optional rule engine for static analysis
            file_cache: Optional file-level review cache
            tool_runner: Optional external tool runner (defaults to ToolRunner)
            project_root: Directory external tools run from (defaults to cwd)
            symbol_index: Optional pre-built index (skips load/build for this run)
        """
        self.config = config
        self.llm = llm
        self.rule_engine = rule_engine
        self.file_cache = file_cache
        self.tool_runner = tool_runner
        self.project_root = Path(project_root) if project_root is not None else Path.cwd()
        self.symbol_index = symbol_index

    def create_graph(self) -> StateGraph:
        """Create LangGraph for the full review workflow.

        Returns:
            Compiled LangGraph
        """
        workflow = StateGraph(OrchestratorState)

        # Add nodes
        workflow.add_node("prepare_context", self._node_prepare_context)
        workflow.add_node("review_files", self._node_review_files)
        workflow.add_node("calculate_result", self._node_calculate_result)

        # Set entry point
        workflow.set_entry_point("prepare_context")

        # Add edges
        workflow.add_edge("prepare_context", "review_files")
        workflow.add_edge("review_files", "calculate_result")
        workflow.add_edge("calculate_result", END)

        return workflow.compile()

    async def _node_prepare_context(self, state: OrchestratorState) -> dict:
        """Node: Prepare project context if not provided."""
        project_context = state.get("project_context")
        if project_context is None:
            from datetime import datetime

            project_context = ProjectContext(
                tech_stack=["unknown"],
                language="unknown",
                critical_paths=self.config.critical_paths,
                analyzed_at=datetime.now().isoformat(),
            )
        return {"project_context": project_context}

    async def _node_review_files(self, state: OrchestratorState) -> dict:
        """Node: Review all diff files."""
        project_context = state["project_context"]
        diff_entries = state["diff_entries"]

        agent = ReviewAgent(
            self.config,
            self.llm,
            project_context,
            rule_engine=self.rule_engine,
            file_cache=self.file_cache,
            tool_runner=self.tool_runner,
            project_root=self.project_root,
            symbol_index=state.get("symbol_index"),
        )

        file_reviews = await agent.review_files(diff_entries)
        return {"file_reviews": file_reviews}

    async def _node_calculate_result(self, state: OrchestratorState) -> dict:
        """Node: Calculate conclusion, confidence, and summary."""
        file_reviews = state["file_reviews"]
        conclusion, confidence = self._calculate_result(file_reviews)
        summary = self._generate_summary(file_reviews)
        return {
            "conclusion": conclusion,
            "confidence": confidence,
            "summary": summary,
            "review_complete": True,
        }

    async def run_review(
        self, diff_entries: list[DiffEntry], project_context: ProjectContext | None = None
    ) -> ReviewResult:
        """Run complete review process using LangGraph.

        Args:
            diff_entries: List of file diffs
            project_context: Optional pre-analyzed context

        Returns:
            Complete review result
        """
        # Admission filter (S3): drop binaries, generated/lock files,
        # configured excludes, and files over the token budget before any
        # (paid) model work happens. ReviewAgent keeps its own exclude check
        # for callers that use it directly.
        filter_config = FilterConfig(
            extra_skip_patterns=list(self.config.exclude_patterns),
        )
        kept_entries, skipped = filter_entries(diff_entries, filter_config)
        logger.info(
            "Admission filter kept %d file(s), skipped %d",
            len(kept_entries),
            len(skipped),
        )

        symbol_index = self.symbol_index
        if symbol_index is None and kept_entries:
            symbol_index = self._load_or_build_symbol_index()

        graph = self.create_graph()

        initial_state = OrchestratorState(
            config=self.config,
            diff_entries=kept_entries,
            project_context=project_context,
            symbol_index=symbol_index,
            file_reviews=[],
            review_complete=False,
        )

        result_state = await graph.ainvoke(initial_state)

        # Noise filter (S4): every review node has finished, so this is the
        # last point where findings can be dropped before the result is
        # returned and rendered.
        file_reviews, filtered = self._filter_findings(result_state["file_reviews"])

        return ReviewResult(
            conclusion=result_state["conclusion"],
            confidence=result_state["confidence"],
            files_reviewed=file_reviews,
            summary=result_state["summary"],
            skipped=skipped,
            filtered=filtered,
        )

    def _load_or_build_symbol_index(self) -> Optional[SymbolIndex]:
        """Load or build the symbol index once for a review run.

        A persisted index is reused when it is at least as new as the newest
        Python source.  Otherwise it is rebuilt and saved when
        ``context.auto_build`` is enabled.  Every failure path logs a warning
        and returns ``None`` so cross-file context is simply omitted.
        """
        context_config = self.config.context
        if not context_config.neighbors:
            return None

        root = self.project_root
        if not root.is_dir():
            logger.warning("Project root %s is not a readable directory; skipping symbol index", root)
            return None

        try:
            newest_source_mtime, source_files = _newest_python_mtime(root)
        except OSError as exc:
            logger.warning("Could not scan %s for Python sources: %s", root, exc)
            return None

        if source_files == 0:
            logger.debug("No Python sources under %s; skipping symbol index", root)
            return None

        index_path = Path(context_config.index_path)
        if not index_path.is_absolute():
            index_path = root / index_path

        if index_path.is_file():
            try:
                index_is_fresh = index_path.stat().st_mtime >= newest_source_mtime
            except OSError as exc:
                logger.warning("Could not stat symbol index %s: %s", index_path, exc)
                index_is_fresh = False

            if index_is_fresh:
                # A corrupt fresh index must not trigger a rebuild: the caller
                # gets no cross-file context and a visible warning.
                return self._load_symbol_index(index_path)

            if not context_config.auto_build:
                logger.warning(
                    "Symbol index %s is older than the newest Python source and "
                    "context.auto_build is disabled; continuing without cross-file context",
                    index_path,
                )
                return None

        if not context_config.auto_build:
            logger.debug(
                "Symbol index %s is missing and context.auto_build is disabled",
                index_path,
            )
            return None

        try:
            index = SymbolIndex()
            index.build(root)
        except Exception as exc:
            logger.warning("Could not build symbol index under %s: %s", root, exc)
            return None

        try:
            index.save(index_path)
        except Exception as exc:
            logger.warning("Could not save symbol index to %s: %s", index_path, exc)

        return index

    @staticmethod
    def _load_symbol_index(path: Path) -> Optional[SymbolIndex]:
        """Load a persisted index, returning ``None`` when it is unusable."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            logger.warning("Could not load symbol index %s: %s", path, exc)
            return None

        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            logger.warning("Ignoring malformed symbol index %s", path)
            return None

        try:
            index = SymbolIndex()
            index.load(path)
            return index
        except Exception as exc:
            logger.warning("Could not load symbol index %s: %s", path, exc)
            return None

    def _filter_findings(
        self, file_reviews: list[FileReview]
    ) -> tuple[list[FileReview], list[FilteredFinding]]:
        """Apply the configured noise filter to every file review.

        File reviews whose findings all survive are returned unchanged. A
        review with at least one dropped finding is copied with the reduced
        issue list, so cached/shared review objects are never mutated.

        Args:
            file_reviews: Reviews produced by the review nodes.

        Returns:
            ``(kept_reviews, filtered)`` where ``filtered`` records every
            dropped finding and the rule that rejected it.
        """
        filters = self.config.filters
        rules = FilterRules(
            min_confidence=filters.min_confidence,
            drop_low_risk_llm=filters.drop_low_risk_llm,
            drop_categories=tuple(filters.drop_categories),
        )

        updated: list[FileReview] = []
        filtered: list[FilteredFinding] = []

        for review in file_reviews:
            kept, dropped = filter_findings(review.issues, rules)
            if dropped:
                updated.append(review.model_copy(update={"issues": kept}))
                filtered.extend(dropped)
            else:
                updated.append(review)

        if filtered:
            logger.info(
                "Noise filter dropped %d finding(s) from %d file review(s)",
                len(filtered),
                len(file_reviews),
            )

        return updated, filtered

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
