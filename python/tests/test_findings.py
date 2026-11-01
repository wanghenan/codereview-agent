"""Tests for the S1 finding model (evidence anchors, confidence, dedupe)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codereview.agents.reviewer import ReviewAgent
from codereview.models import (
    Evidence,
    EvidenceKind,
    FileIssue,
    IssueCategory,
    RiskLevel,
)


def _issue(**overrides):
    base = {
        "file_path": "src/app.py",
        "line_number": 42,
        "risk_level": RiskLevel.HIGH,
        "description": "boom",
    }
    base.update(overrides)
    return FileIssue(**base)


class TestFindingDefaults:
    """New fields must default so old payloads and callers keep working."""

    def test_legacy_construction_still_validates(self):
        issue = _issue()
        assert issue.source == "llm"
        assert issue.category is IssueCategory.BUG
        assert issue.confidence == 0.5
        assert issue.evidence == []
        assert issue.title == ""
        assert issue.suggested_patch is None

    def test_evidence_serialises(self):
        issue = _issue(evidence=[Evidence(kind=EvidenceKind.RULE, detail="OWASP-001")])
        data = issue.model_dump()
        assert data["evidence"][0]["kind"] == "rule"
        assert data["evidence"][0]["detail"] == "OWASP-001"

    def test_end_line_before_start_rejected(self):
        with pytest.raises(ValidationError):
            _issue(line_number=40, end_line=39)

    def test_end_line_equal_start_allowed(self):
        assert _issue(line_number=40, end_line=40).end_line == 40

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            _issue(confidence=1.5)


class TestDedupeKey:
    """Duplicates within the same line bucket and label collapse."""

    def test_same_bucket_and_title_collide(self):
        a = _issue(line_number=41, title="Unclosed file handle")
        b = _issue(line_number=48, title="unclosed FILE handle")
        assert a.dedupe_key() == b.dedupe_key()

    def test_different_bucket_differs(self):
        a = _issue(line_number=41, title="t")
        b = _issue(line_number=61, title="t")
        assert a.dedupe_key() != b.dedupe_key()

    def test_falls_back_to_description(self):
        a = _issue(description="Same problem", title="")
        b = _issue(description="same problem", title="")
        assert a.dedupe_key() == b.dedupe_key()


class TestToFinding:
    """LLM output is normalised, not trusted."""

    def test_parses_rich_issue(self):
        finding = ReviewAgent._to_finding(
            "src/app.py",
            {
                "line_number": 12,
                "end_line": 14,
                "risk_level": "high",
                "category": "security",
                "title": "SQL injection",
                "description": "user input concatenated into query",
                "suggestion": "use parameters",
                "confidence": 0.87,
                "evidence": [{"kind": "symbol", "detail": "build_query()"}, "src/app.py:12"],
            },
        )
        assert finding.category is IssueCategory.SECURITY
        assert finding.confidence == pytest.approx(0.87)
        assert finding.source == "llm"
        assert finding.end_line == 14
        assert [e.kind for e in finding.evidence] == [
            EvidenceKind.SYMBOL,
            EvidenceKind.CONTEXT,
        ]

    def test_bad_values_fall_back(self):
        finding = ReviewAgent._to_finding(
            "src/app.py",
            {
                "risk_level": "catastrophic",
                "category": "vibes",
                "confidence": "very sure",
                "evidence": [None, "", {"detail": ""}],
            },
        )
        assert finding.risk_level is RiskLevel.LOW
        assert finding.category is IssueCategory.BUG
        assert finding.confidence == 0.5
        assert finding.evidence == []

    def test_confidence_is_clamped(self):
        finding = ReviewAgent._to_finding(
            "src/app.py", {"risk_level": "low", "description": "x", "confidence": 3}
        )
        assert finding.confidence == 1.0

    def test_title_truncated(self):
        finding = ReviewAgent._to_finding(
            "src/app.py", {"risk_level": "low", "description": "x", "title": "t" * 500}
        )
        assert len(finding.title) == 200
