"""Tests for the S4 noise filter and its orchestration wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codereview.agents.reviewer import ReviewAgent, ReviewOrchestrator
from codereview.core.config import ConfigLoader
from codereview.core.finding_filter import (
    REASON_CATEGORY,
    REASON_LOW_CONFIDENCE,
    REASON_LOW_RISK_LLM,
    FilterRules,
    filter_findings,
)
from codereview.models import (
    Config,
    ConfigFilters,
    ConfigLLM,
    DiffEntry,
    FileIssue,
    FileReview,
    IssueCategory,
    LLMProvider,
    ReviewResult,
    RiskLevel,
)


def _issue(
    *,
    source: str = "llm",
    confidence: float = 0.9,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    category: IssueCategory = IssueCategory.BUG,
    description: str = "finding",
) -> FileIssue:
    """Build a FileIssue without repeating the model boilerplate."""
    return FileIssue(
        file_path="src/app.py",
        line_number=1,
        risk_level=risk_level,
        description=description,
        confidence=confidence,
        category=category,
        source=source,
    )


def _config(**filter_kwargs) -> Config:
    """Build a Config with optional non-default filter settings."""
    return Config(
        llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
        filters=ConfigFilters(**filter_kwargs),
    )


class TestFilterRules:
    """Each rule on its own, including the disabled defaults."""

    def test_defaults_keep_everything(self) -> None:
        issues = [
            _issue(confidence=0.0, risk_level=RiskLevel.LOW, category=IssueCategory.STYLE),
            _issue(source="rule", confidence=0.0, risk_level=RiskLevel.LOW),
            _issue(source="tool", confidence=0.0, risk_level=RiskLevel.LOW),
        ]

        kept, filtered = filter_findings(issues, FilterRules())

        assert kept == issues
        assert filtered == []

    def test_min_confidence_drops_only_below_threshold(self) -> None:
        below = _issue(confidence=0.49, description="below")
        at_threshold = _issue(confidence=0.5, description="at threshold")
        above = _issue(confidence=0.8, description="above")

        kept, filtered = filter_findings(
            [below, at_threshold, above], FilterRules(min_confidence=0.5)
        )

        assert kept == [at_threshold, above]
        assert len(filtered) == 1
        assert filtered[0].reason == REASON_LOW_CONFIDENCE
        assert filtered[0].issue is below

    def test_min_confidence_zero_is_disabled(self) -> None:
        issue = _issue(confidence=0.0)

        kept, filtered = filter_findings([issue], FilterRules(min_confidence=0.0))

        assert kept == [issue]
        assert filtered == []

    def test_drop_low_risk_llm_only_drops_low_risk(self) -> None:
        low = _issue(risk_level=RiskLevel.LOW, description="low")
        medium = _issue(risk_level=RiskLevel.MEDIUM, description="medium")
        high = _issue(risk_level=RiskLevel.HIGH, description="high")

        kept, filtered = filter_findings(
            [low, medium, high], FilterRules(drop_low_risk_llm=True)
        )

        assert kept == [medium, high]
        assert [item.reason for item in filtered] == [REASON_LOW_RISK_LLM]
        assert filtered[0].issue is low

    def test_rule_and_tool_findings_are_immune_to_confidence_and_low_risk(self) -> None:
        rule_low = _issue(
            source="rule", confidence=0.0, risk_level=RiskLevel.LOW, description="rule"
        )
        tool_low = _issue(
            source="tool", confidence=0.0, risk_level=RiskLevel.LOW, description="tool"
        )
        llm_low = _issue(
            source="llm", confidence=0.0, risk_level=RiskLevel.LOW, description="llm"
        )

        kept, filtered = filter_findings(
            [rule_low, tool_low, llm_low],
            FilterRules(min_confidence=0.9, drop_low_risk_llm=True),
        )

        assert kept == [rule_low, tool_low]
        assert filtered[0].issue is llm_low
        # Field order decides the recorded reason: confidence wins over risk.
        assert filtered[0].reason == REASON_LOW_CONFIDENCE

    def test_drop_categories_applies_to_every_source(self) -> None:
        issues = [
            _issue(source="llm", category=IssueCategory.STYLE, description="llm-style"),
            _issue(source="rule", category=IssueCategory.STYLE, description="rule-style"),
            _issue(source="tool", category=IssueCategory.STYLE, description="tool-style"),
            _issue(source="llm", category=IssueCategory.BUG, description="bug"),
        ]

        kept, filtered = filter_findings(
            issues, FilterRules(drop_categories=("style",))
        )

        assert [issue.description for issue in kept] == ["bug"]
        assert [item.issue.description for item in filtered] == [
            "llm-style",
            "rule-style",
            "tool-style",
        ]
        assert [item.reason for item in filtered] == [REASON_CATEGORY] * 3

    def test_category_rule_accepts_enum_values(self) -> None:
        issue = _issue(category=IssueCategory.STYLE)

        _kept, filtered = filter_findings(
            [issue], FilterRules(drop_categories=(IssueCategory.STYLE.value,))
        )

        assert filtered[0].reason == REASON_CATEGORY

    def test_first_failed_rule_wins(self) -> None:
        issue = _issue(
            confidence=0.1,
            risk_level=RiskLevel.LOW,
            category=IssueCategory.STYLE,
        )

        _kept, filtered = filter_findings(
            [issue],
            FilterRules(
                min_confidence=0.5,
                drop_low_risk_llm=True,
                drop_categories=("style",),
            ),
        )

        assert filtered[0].reason == REASON_LOW_CONFIDENCE


class TestConfigDefaults:
    """The config defaults must preserve today's output exactly."""

    def test_default_config_filter_block(self) -> None:
        config = Config(llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"))

        assert config.filters.min_confidence == 0.5
        assert config.filters.drop_low_risk_llm is False
        assert config.filters.drop_categories == []

    def test_default_config_keeps_confident_findings(self) -> None:
        config = Config(llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"))
        issues = [
            _issue(confidence=0.6, risk_level=RiskLevel.LOW, category=IssueCategory.STYLE),
            _issue(source="rule", confidence=0.0, risk_level=RiskLevel.LOW),
        ]

        kept, filtered = filter_findings(
            issues,
            FilterRules(
                min_confidence=config.filters.min_confidence,
                drop_low_risk_llm=config.filters.drop_low_risk_llm,
                drop_categories=tuple(config.filters.drop_categories),
            ),
        )

        assert kept == issues
        assert filtered == []

    def test_loader_normalises_camel_case_filter_keys(self, tmp_path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
llm:
  provider: openai
  apiKey: test-key
filters:
  minConfidence: 0.7
  dropLowRiskLlm: true
  dropCategories:
    - style
""",
            encoding="utf-8",
        )

        config = ConfigLoader.load(config_path)

        assert config.filters.min_confidence == pytest.approx(0.7)
        assert config.filters.drop_low_risk_llm is True
        assert config.filters.drop_categories == ["style"]


def _entry(filename: str = "src/main.py") -> DiffEntry:
    """Build a single reviewable DiffEntry."""
    return DiffEntry(
        filename=filename,
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1 +1 @@\n-old\n+new",
    )


def _stub_review_files(monkeypatch: pytest.MonkeyPatch, issues: list[FileIssue]) -> None:
    """Make ReviewAgent.review_files return one review containing ``issues``."""

    async def fake_review_files(self, diff_entries):  # noqa: ANN001
        return [
            FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.MEDIUM,
                changes="+1, -1",
                issues=list(issues),
            )
            for entry in diff_entries
        ]

    monkeypatch.setattr(ReviewAgent, "review_files", fake_review_files)


async def test_orchestrator_drops_findings_and_records_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_review filters every file review before returning the result."""
    config = _config(
        min_confidence=0.5,
        drop_low_risk_llm=True,
        drop_categories=["style"],
    )
    low_confidence = _issue(confidence=0.2, description="low-confidence")
    low_risk = _issue(confidence=0.9, risk_level=RiskLevel.LOW, description="low-risk")
    style_rule = _issue(
        source="rule",
        confidence=0.9,
        risk_level=RiskLevel.HIGH,
        category=IssueCategory.STYLE,
        description="style-rule",
    )
    kept_issue = _issue(confidence=0.9, risk_level=RiskLevel.MEDIUM, description="keep")

    _stub_review_files(
        monkeypatch, [low_confidence, low_risk, style_rule, kept_issue]
    )

    result = await ReviewOrchestrator(config, MagicMock()).run_review([_entry()])

    assert isinstance(result, ReviewResult)
    assert result.files_reviewed[0].issues == [kept_issue]
    assert [item.reason for item in result.filtered] == [
        REASON_LOW_CONFIDENCE,
        REASON_LOW_RISK_LLM,
        REASON_CATEGORY,
    ]
    assert [item.issue.description for item in result.filtered] == [
        "low-confidence",
        "low-risk",
        "style-rule",
    ]


async def test_orchestrator_with_default_config_keeps_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default filters are a no-op on the orchestration path too."""
    config = _config()
    issues = [
        _issue(confidence=0.6, risk_level=RiskLevel.LOW, category=IssueCategory.STYLE),
        _issue(source="rule", confidence=0.0, risk_level=RiskLevel.LOW),
    ]

    _stub_review_files(monkeypatch, issues)

    result = await ReviewOrchestrator(config, MagicMock()).run_review([_entry()])

    assert result.files_reviewed[0].issues == issues
    assert result.filtered == []
