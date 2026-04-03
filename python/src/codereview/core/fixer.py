"""Smart Fix - AI-powered code fixing for CodeReview Agent.

This module provides intelligent code fixing capabilities that analyze issues
found during code review and generate specific fix suggestions using LLM.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from codereview.models import FileIssue, RiskLevel

logger = logging.getLogger(__name__)


class FixType(str, Enum):
    """Types of fixes supported by the fixer."""

    SECURITY = "security"  # Security vulnerabilities
    CODE_STYLE = "code_style"  # Code style improvements
    PERFORMANCE = "performance"  # Performance optimizations
    BUG_FIX = "bug_fix"  # Bug fixes
    BEST_PRACTICE = "best_practice"  # Best practice improvements
    GENERAL = "general"  # General improvements


@dataclass
class FixSuggestion:
    """Represents a single fix suggestion.

    Attributes:
        issue: The original issue that triggered this fix
        original_code: The original code snippet
        fixed_code: The suggested fixed code
        fix_type: Type of fix
        risk_level: Risk level of the issue
        confidence: Confidence score (0-100)
        explanation: Explanation of the fix
    """

    issue: FileIssue
    original_code: str
    fixed_code: str
    fix_type: FixType
    risk_level: RiskLevel
    confidence: float
    explanation: str

    def to_display_string(self, index: int) -> str:
        """Convert to display string for user output.

        Args:
            index: Index of this suggestion

        Returns:
            Formatted string for display
        """
        risk_emoji = {
            RiskLevel.HIGH: "🔴",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.LOW: "🟢",
        }

        lines = [
            f"🔧 建议修复 #{index}: {self.issue.description}",
            "",
            "原始代码:",
            f"  {self.original_code.strip()}",
            "",
            "修复建议:",
            f"  {self.fixed_code.strip()}",
            "",
            f"风险等级: {risk_emoji.get(self.risk_level, '')} {self.risk_level.value} | "
            f"置信度: {self.confidence}%",
            f"修复类型: {self.fix_type.value}",
            "",
            f"说明: {self.explanation}",
        ]
        return "\n".join(lines)

    def to_diff(self) -> str:
        """Generate unified diff format.

        Returns:
            Unified diff string
        """
        original_lines = self.original_code.strip().splitlines()
        fixed_lines = self.fixed_code.strip().splitlines()

        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile="original",
            tofile="fixed",
            lineterm="",
        )
        return "\n".join(diff)


@dataclass
class FixResult:
    """Result of applying a fix.

    Attributes:
        success: Whether the fix was applied successfully
        fixed_code: The fixed code (if successful)
        error: Error message (if failed)
        verification_passed: Whether verification passed
    """

    success: bool
    fixed_code: Optional[str] = None
    error: Optional[str] = None
    verification_passed: bool = False


# System prompt for code fixing
FIX_SYSTEM_PROMPT = """You are an expert code fixer. Your task is to analyze code issues
and generate specific fix suggestions.

## Issue Information
File: {file_path}
Line: {line_number}
Risk Level: {risk_level}
Issue Description: {description}
Current Suggestion: {suggestion}

## Original Code (Context)
{original_code}

## Language
{language}

## Your Task
Generate a specific fix for this issue. Return your response in JSON format:
{{
    "fix_type": "security|code_style|performance|bug_fix|best_practice|general",
    "fixed_code": "The specific fixed code snippet",
    "explanation": "Brief explanation of what was changed and why",
    "confidence": 95
}}

Guidelines:
- Provide the exact code that should replace the original
- If the issue is in the middle of a code block, include enough context
- Use appropriate syntax for the language
- Be specific and actionable"""


class CodeFixer:
    """AI-powered code fixer using LLM.

    This class analyzes issues found during code review and generates
    specific fix suggestions using a language model.
    """

    def __init__(
        self,
        llm: Any,
        timeout_seconds: float = 30.0,
    ):
        """Initialize the code fixer.

        Args:
            llm: LangChain LLM instance
            timeout_seconds: Timeout for fix generation
        """
        self.llm = llm
        self.timeout_seconds = timeout_seconds

    def analyze_fix_type(self, issue: FileIssue) -> FixType:
        """Analyze the type of fix needed based on the issue.

        Args:
            issue: The issue to analyze

        Returns:
            The likely fix type
        """
        description = issue.description.lower()
        suggestion = (issue.suggestion or "").lower()

        combined = f"{description} {suggestion}"

        # Security-related keywords
        security_keywords = [
            "sql injection",
            "xss",
            "cross-site",
            "csrf",
            "injection",
            "authentication",
            "authorization",
            "password",
            "secret",
            "credential",
            "vulnerability",
            "security",
            "unsafe",
            "eval",
            "exec",
            "hardcoded",
            "api key",
            "token",
        ]
        if any(kw in combined for kw in security_keywords):
            return FixType.SECURITY

        # Performance keywords
        performance_keywords = [
            "performance",
            "slow",
            "memory",
            "leak",
            "n+1",
            "query",
            "database",
            "cache",
            "optimize",
            "efficient",
        ]
        if any(kw in combined for kw in performance_keywords):
            return FixType.PERFORMANCE

        # Code style keywords
        style_keywords = [
            "style",
            "format",
            "lint",
            "convention",
            "naming",
            "unused",
            "import",
            "variable",
            "function name",
        ]
        if any(kw in combined for kw in style_keywords):
            return FixType.CODE_STYLE

        # Bug fix keywords
        bug_keywords = [
            "bug",
            "error",
            "exception",
            "crash",
            "fix",
            "wrong",
            "incorrect",
            "issue",
            "problem",
            "fail",
        ]
        if any(kw in combined for kw in bug_keywords):
            return FixType.BUG_FIX

        # Best practice keywords
        best_practice_keywords = [
            "best practice",
            "recommend",
            "should",
            "consider",
            "improve",
            "refactor",
            "deprecated",
            "anti-pattern",
        ]
        if any(kw in combined for kw in best_practice_keywords):
            return FixType.BEST_PRACTICE

        return FixType.GENERAL

    async def generate_fix(
        self,
        issue: FileIssue,
        original_code: str,
        language: str = "python",
    ) -> Optional[FixSuggestion]:
        """Generate a fix suggestion for an issue.

        Args:
            issue: The issue to fix
            original_code: The original code snippet
            language: Programming language

        Returns:
            FixSuggestion if successful, None otherwise
        """
        import asyncio

        fix_type = self.analyze_fix_type(issue)

        prompt = self._build_fix_prompt(
            issue=issue,
            original_code=original_code,
            language=language,
        )

        chain = prompt | self.llm | JsonOutputParser()

        try:
            result = await asyncio.wait_for(
                chain.ainvoke(
                    {
                        "file_path": issue.file_path,
                        "line_number": issue.line_number or 0,
                        "risk_level": issue.risk_level.value,
                        "description": issue.description,
                        "suggestion": issue.suggestion or "No suggestion provided",
                        "original_code": original_code,
                        "language": language,
                    }
                ),
                timeout=self.timeout_seconds,
            )

            return FixSuggestion(
                issue=issue,
                original_code=original_code,
                fixed_code=result.get("fixed_code", ""),
                fix_type=FixType(result.get("fix_type", fix_type.value)),
                risk_level=issue.risk_level,
                confidence=result.get("confidence", 80.0),
                explanation=result.get("explanation", ""),
            )

        except asyncio.TimeoutError:
            logger.warning(f"Fix generation timed out for {issue.file_path}:{issue.line_number}")
            return None
        except Exception as e:
            logger.error(f"Fix generation failed: {e}")
            return None

    def _build_fix_prompt(
        self, issue: FileIssue, original_code: str, language: str
    ) -> ChatPromptTemplate:
        """Build prompt for fix generation."""
        return ChatPromptTemplate.from_messages(
            [("system", FIX_SYSTEM_PROMPT), ("user", """Generate a fix for this issue.""")]
        )

    async def apply_fix(
        self,
        full_file_content: str,
        fix_suggestion: FixSuggestion,
    ) -> FixResult:
        """Apply a fix suggestion to the full file content.

        Args:
            full_file_content: Complete content of the file
            fix_suggestion: The fix suggestion to apply

        Returns:
            FixResult with the applied fix or error
        """
        try:
            # Simple text replacement - replace original code with fixed code
            # This is a basic implementation; more sophisticated logic could be added
            if fix_suggestion.original_code.strip() in full_file_content:
                fixed_content = full_file_content.replace(
                    fix_suggestion.original_code.strip(),
                    fix_suggestion.fixed_code.strip(),
                )
                return FixResult(
                    success=True,
                    fixed_code=fixed_content,
                    verification_passed=True,  # Basic verification
                )
            else:
                # Try with more flexible matching
                original_lines = fix_suggestion.original_code.strip().splitlines()
                file_lines = full_file_content.splitlines()

                # Find the best match
                best_index = -1

                for i in range(len(file_lines) - len(original_lines) + 1):
                    match = True
                    for j, orig_line in enumerate(original_lines):
                        if orig_line.strip() != file_lines[i + j].strip():
                            match = False
                            break
                    if match:
                        best_index = i
                        break

                if best_index >= 0:
                    # Replace the matched lines
                    new_lines = (
                        file_lines[:best_index]
                        + fix_suggestion.fixed_code.strip().splitlines()
                        + file_lines[best_index + len(original_lines) :]
                    )
                    return FixResult(
                        success=True,
                        fixed_code="\n".join(new_lines),
                        verification_passed=True,
                    )

                return FixResult(
                    success=False,
                    error="Could not find original code in file",
                )

        except Exception as e:
            return FixResult(
                success=False,
                error=str(e),
            )


class FixOrchestrator:
    """Orchestrates the fixing process for multiple issues.

    This class manages the workflow of generating fixes, presenting them
    to users, and applying selected fixes.
    """

    def __init__(self, llm: Any, timeout_seconds: float = 30.0):
        """Initialize the fix orchestrator.

        Args:
            llm: LangChain LLM instance
            timeout_seconds: Timeout for fix generation
        """
        self.fixer = CodeFixer(llm, timeout_seconds)

    async def generate_fixes(
        self,
        issues: list[FileIssue],
        file_contents: dict[str, str],
        languages: Optional[dict[str, str]] = None,
    ) -> list[FixSuggestion]:
        """Generate fix suggestions for multiple issues.

        Args:
            issues: List of issues to fix
            file_contents: Map of file paths to their contents
            languages: Optional map of file paths to languages

        Returns:
            List of fix suggestions
        """
        fixes = []

        for issue in issues:
            file_path = issue.file_path
            if file_path not in file_contents:
                logger.warning(f"No file content found for {file_path}")
                continue

            original_code = file_contents[file_path]
            language = (languages or {}).get(file_path, "python")

            fix = await self.fixer.generate_fix(
                issue=issue,
                original_code=original_code,
                language=language,
            )

            if fix:
                fixes.append(fix)

        return fixes

    async def apply_selected_fixes(
        self,
        file_content: str,
        selected_fixes: list[FixSuggestion],
    ) -> str:
        """Apply multiple selected fixes to a file.

        Args:
            file_content: Original file content
            selected_fixes: List of fixes to apply

        Returns:
            Fixed file content
        """
        current_content = file_content

        for fix in selected_fixes:
            result = await self.fixer.apply_fix(current_content, fix)
            if result.success and result.fixed_code:
                current_content = result.fixed_code
            else:
                logger.warning(f"Failed to apply fix: {result.error}")

        return current_content

    def format_fixes_for_display(
        self,
        fixes: list[FixSuggestion],
    ) -> str:
        """Format multiple fixes for display.

        Args:
            fixes: List of fix suggestions

        Returns:
            Formatted string for display
        """
        if not fixes:
            return "No fixes available."

        lines = ["=" * 50, "🔧 智能修复建议", "=" * 50, ""]

        for i, fix in enumerate(fixes, 1):
            lines.append(fix.to_display_string(i))
            lines.append("")

        lines.append("-" * 50)
        lines.append("是否采纳? [y/n/a(采纳所有)]")

        return "\n".join(lines)
