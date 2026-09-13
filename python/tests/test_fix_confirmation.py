"""Behavior tests for fix confirmation timing (S2) and --min-risk filtering (S3).

S2: The confirmation prompt must gate *whether fixes are applied*, not appear
    after files were already written. ``run_fix`` accepts a ``confirm``
    callback; when it returns False no file may be modified.
S3: ``--min-risk high`` must exclude medium/low issues from fixing. The filter
    compares risk levels by severity order, not by ad-hoc string membership.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codereview.core.fixer import FixResult, FixSuggestion, FixType
from codereview.models import (
    Config,
    ConfigLLM,
    FileIssue,
    FileReview,
    LLMProvider,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _make_config() -> Config:
    return Config(llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"))


def _make_review_result(file_path: str, risk_levels: list[RiskLevel]) -> ReviewResult:
    """One file, one issue per given risk level."""
    issues = [
        FileIssue(
            file_path=file_path,
            line_number=i + 1,
            risk_level=level,
            description=f"{level.value} issue",
            suggestion="fix it",
        )
        for i, level in enumerate(risk_levels)
    ]
    worst = max(risk_levels, key=lambda r: _RISK_ORDER[r.value])
    return ReviewResult(
        conclusion=ReviewConclusion.NEEDS_REVIEW,
        confidence=50.0,
        files_reviewed=[
            FileReview(file_path=file_path, risk_level=worst, changes="+3, -0", issues=issues)
        ],
        summary="test review",
    )


def _make_fix_suggestion(file_path: str, line: int = 1) -> FixSuggestion:
    return FixSuggestion(
        issue=FileIssue(
            file_path=file_path,
            line_number=line,
            risk_level=RiskLevel.HIGH,
            description="high issue",
            suggestion="fix it",
        ),
        original_code="x = 1",
        fixed_code="x = 2",
        fix_type=FixType.BUG_FIX,
        risk_level=RiskLevel.HIGH,
        confidence=90.0,
        explanation="test fix",
    )


def _patch_common(review_result: ReviewResult, generate_fix_return=None):
    """Patch config/LLM/orchestrator/fixer around run_fix."""
    config = _make_config()
    orchestrator_cls = MagicMock()
    orchestrator_cls.return_value.run_review = AsyncMock(return_value=review_result)
    fixer_cls = MagicMock()
    fixer_cls.return_value.generate_fix = AsyncMock(return_value=generate_fix_return)
    fixer_cls.return_value.apply_fix = AsyncMock(
        return_value=FixResult(success=True, fixed_code="x = 2\n")
    )
    return (
        patch("codereview.cli.ConfigLoader.load", return_value=config),
        patch("codereview.cli.LLMFactory.create", return_value=MagicMock()),
        patch("codereview.cli.ReviewOrchestrator", orchestrator_cls),
        patch("codereview.core.fixer.CodeFixer", fixer_cls),
    )


def _diff_input(file_path: str) -> str:
    return json.dumps(
        {
            "files": [
                {
                    "filename": file_path,
                    "status": "modified",
                    "additions": 1,
                    "deletions": 0,
                    "patch": "@@ -1 +1 @@\n-x = 1\n+x = 2",
                }
            ]
        }
    )


class TestFixConfirmationTiming:
    """S2: confirmation must happen before any file is written."""

    async def test_confirmation_rejected_leaves_file_untouched(self, tmp_path: Path):
        from codereview.cli import run_fix

        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        review_result = _make_review_result(str(target), [RiskLevel.HIGH])
        patches = _patch_common(review_result, generate_fix_return=_make_fix_suggestion(str(target)))

        with patches[0], patches[1], patches[2], patches[3]:
            result = await run_fix(
                diff_input=_diff_input(str(target)),
                apply=True,
                dry_run=False,
                confirm=lambda fixes_count, files_count: False,
            )

        assert result["success"] is True
        assert result.get("cancelled") is True
        assert result["applied"] == 0
        assert result["applied_files"] == []
        assert target.read_text(encoding="utf-8") == "x = 1\n"

    async def test_confirmation_accepted_applies_fixes(self, tmp_path: Path):
        from codereview.cli import run_fix

        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        review_result = _make_review_result(str(target), [RiskLevel.HIGH])
        patches = _patch_common(review_result, generate_fix_return=_make_fix_suggestion(str(target)))

        with patches[0], patches[1], patches[2], patches[3]:
            result = await run_fix(
                diff_input=_diff_input(str(target)),
                apply=True,
                dry_run=False,
                confirm=lambda fixes_count, files_count: True,
            )

        assert result["success"] is True
        assert result.get("cancelled") is not True
        assert result["applied"] == 1
        assert target.read_text(encoding="utf-8") == "x = 2\n"

    async def test_no_confirm_callback_applies_without_prompting(self, tmp_path: Path):
        """CI/--yes path: no callback means apply directly (backwards compatible)."""
        from codereview.cli import run_fix

        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        review_result = _make_review_result(str(target), [RiskLevel.HIGH])
        patches = _patch_common(review_result, generate_fix_return=_make_fix_suggestion(str(target)))

        with patches[0], patches[1], patches[2], patches[3]:
            result = await run_fix(
                diff_input=_diff_input(str(target)),
                apply=True,
                dry_run=False,
            )

        assert result["applied"] == 1
        assert target.read_text(encoding="utf-8") == "x = 2\n"


class TestMinRiskFilter:
    """S3: --min-risk filters issues by severity order."""

    @pytest.mark.parametrize(
        ("min_risk", "expected_count"),
        [
            ("high", 1),  # only high
            ("medium", 2),  # high + medium
            ("low", 3),  # high + medium + low
        ],
    )
    async def test_min_risk_filters_by_severity_order(
        self, tmp_path: Path, min_risk: str, expected_count: int
    ):
        from codereview.cli import run_fix

        target = tmp_path / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        review_result = _make_review_result(
            str(target), [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]
        )
        # generate_fix returns None -> run_fix reports issues_count without applying
        patches = _patch_common(review_result, generate_fix_return=None)

        with patches[0], patches[1], patches[2], patches[3]:
            result = await run_fix(
                diff_input=_diff_input(str(target)),
                apply=False,
                dry_run=True,
                min_risk=min_risk,
            )

        assert result["success"] is True
        assert result["issues_count"] == expected_count
