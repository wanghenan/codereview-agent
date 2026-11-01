"""Tests for S2 inline review output and the create_review request."""

from __future__ import annotations

import json
import urllib.request
from unittest.mock import MagicMock

import pytest

from codereview.core.github_client import GitHubClient
from codereview.models import (
    Evidence,
    EvidenceKind,
    FileIssue,
    FileReview,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)
from codereview.output.inline import (
    MAX_INLINE_COMMENTS,
    MAX_SUMMARY_FINDINGS,
    InlineCommentBuilder,
)


def _issue(**overrides) -> FileIssue:
    """Create a finding with sensible defaults."""
    base = {
        "file_path": "src/app.py",
        "line_number": 10,
        "risk_level": RiskLevel.HIGH,
        "description": "Something is wrong",
        "title": "Broken thing",
    }
    base.update(overrides)
    return FileIssue(**base)


def _result(*issues: FileIssue, summary: str = "Base review summary") -> ReviewResult:
    """Wrap findings in a single-file review result."""
    return ReviewResult(
        conclusion=ReviewConclusion.NEEDS_REVIEW,
        confidence=80.0,
        files_reviewed=[
            FileReview(
                file_path="src/app.py",
                risk_level=RiskLevel.HIGH,
                changes="+10, -2",
                issues=list(issues),
            )
        ],
        summary=summary,
    )


class TestBuildPayload:
    """Payload shape and anchoring rules."""

    def test_returns_comments_and_summary(self):
        payload = InlineCommentBuilder().build(_result(_issue()))

        assert set(payload) == {"comments", "summary"}
        assert len(payload["comments"]) == 1
        comment = payload["comments"][0]
        assert set(comment) == {"path", "line", "body"}
        assert comment["path"] == "src/app.py"
        assert comment["line"] == 10
        assert isinstance(comment["body"], str)

    def test_only_line_anchored_issues_become_comments(self):
        anchored = _issue(file_path="src/anchored.py", line_number=12)
        unanchored = _issue(file_path="src/unanchored.py", line_number=None)

        payload = InlineCommentBuilder().build(_result(anchored, unanchored))

        assert [c["path"] for c in payload["comments"]] == ["src/anchored.py"]
        assert "src/unanchored.py" in payload["summary"]

    def test_no_findings_returns_base_summary(self):
        payload = InlineCommentBuilder().build(
            ReviewResult(
                conclusion=ReviewConclusion.CAN_SUBMIT,
                confidence=95.0,
                files_reviewed=[],
                summary="Nothing to report",
            )
        )

        assert payload["comments"] == []
        assert payload["summary"] == "Nothing to report"


class TestCapAndOrdering:
    """The inline list is capped and ordered by signal, then location."""

    def test_cap_at_max_inline_comments(self):
        issues = [
            _issue(file_path=f"src/f{i:02d}.py", line_number=i + 1) for i in range(30)
        ]

        payload = InlineCommentBuilder().build(_result(*issues))

        assert len(payload["comments"]) == MAX_INLINE_COMMENTS
        assert MAX_INLINE_COMMENTS == 25

    def test_orders_by_severity_then_confidence_then_location(self):
        issues = [
            _issue(file_path="b.py", line_number=2, risk_level=RiskLevel.HIGH, confidence=0.4),
            _issue(file_path="b.py", line_number=5, risk_level=RiskLevel.HIGH, confidence=0.9),
            _issue(file_path="a.py", line_number=7, risk_level=RiskLevel.HIGH, confidence=0.9),
            _issue(file_path="m.py", line_number=1, risk_level=RiskLevel.MEDIUM, confidence=1.0),
            _issue(file_path="l.py", line_number=1, risk_level=RiskLevel.LOW, confidence=1.0),
        ]

        payload = InlineCommentBuilder().build(_result(*issues))

        assert [(c["path"], c["line"]) for c in payload["comments"]] == [
            ("a.py", 7),
            ("b.py", 5),
            ("b.py", 2),
            ("m.py", 1),
            ("l.py", 1),
        ]

    def test_highest_signal_survives_the_cap(self):
        issues = []
        for i in range(10):
            issues.append(
                _issue(
                    file_path=f"low_{i}.py",
                    line_number=i + 1,
                    risk_level=RiskLevel.LOW,
                    confidence=0.9,
                )
            )
        for i in range(10):
            issues.append(
                _issue(
                    file_path=f"medium_{i}.py",
                    line_number=i + 1,
                    risk_level=RiskLevel.MEDIUM,
                    confidence=0.9,
                )
            )
        for i in range(10):
            issues.append(
                _issue(
                    file_path=f"high_{i}.py",
                    line_number=i + 1,
                    risk_level=RiskLevel.HIGH,
                    confidence=0.9,
                )
            )

        payload = InlineCommentBuilder().build(_result(*issues))
        paths = [c["path"] for c in payload["comments"]]

        assert paths == (
            [f"high_{i}.py" for i in range(10)]
            + [f"medium_{i}.py" for i in range(10)]
            + [f"low_{i}.py" for i in range(5)]
        )
        assert "low_5.py" not in paths


class TestSummaryFolding:
    """Overflow and unanchored findings are folded into the summary."""

    def test_overflow_is_folded(self):
        issues = [
            _issue(file_path=f"src/f{i:02d}.py", line_number=1, title=f"Finding {i}")
            for i in range(30)
        ]

        summary = InlineCommentBuilder().build(_result(*issues))["summary"]

        assert summary.startswith("Base review summary")
        assert "**Findings not shown inline**" in summary
        folded = [line for line in summary.splitlines() if line.startswith("- [")]
        assert len(folded) == 5
        assert "src/f25.py:1" in summary
        assert "src/f29.py:1" in summary

    def test_summary_lines_capped_then_reports_remainder(self):
        issues = [
            _issue(file_path=f"src/f{i:02d}.py", line_number=None, title=f"Finding {i}")
            for i in range(MAX_SUMMARY_FINDINGS + 3)
        ]

        summary = InlineCommentBuilder().build(_result(*issues))["summary"]

        folded = [line for line in summary.splitlines() if line.startswith("- [")]
        assert len(folded) == MAX_SUMMARY_FINDINGS
        assert summary.splitlines()[-1] == "+3 more"

    def test_no_folded_findings_leaves_summary_clean(self):
        summary = InlineCommentBuilder().build(_result(_issue()))["summary"]

        assert summary == "Base review summary"
        assert "Findings not shown inline" not in summary


class TestBodyRendering:
    """Inline bodies carry the title, description, evidence, and patch."""

    def test_renders_all_parts(self):
        issue = _issue(
            title="SQL injection",
            description="User input reaches the query.",
            evidence=[
                Evidence(kind=EvidenceKind.RULE, detail="OWASP-001"),
                Evidence(kind=EvidenceKind.SYMBOL, detail="build_query()"),
            ],
            suggested_patch="@@ -1,2 +1,2 @@\n-bad\n+good",
        )

        body = InlineCommentBuilder().build(_result(issue))["comments"][0]["body"]

        assert "**SQL injection**" in body
        assert "User input reaches the query." in body
        assert "- rule: OWASP-001" in body
        assert "- symbol: build_query()" in body
        assert "```diff" in body
        assert "+good" in body
        assert body.rstrip().endswith("```")

    def test_uses_first_description_line_when_title_missing(self):
        issue = _issue(title="", description="First line of the finding\nMore detail here.")

        body = InlineCommentBuilder().build(_result(issue))["comments"][0]["body"]

        assert body.startswith("**First line of the finding**")
        assert "More detail here." in body

    def test_no_patch_means_no_diff_fence(self):
        body = InlineCommentBuilder().build(_result(_issue(suggested_patch=None)))[
            "comments"
        ][0]["body"]

        assert "```diff" not in body


class TestFindingsPayload:
    """findings.json is a lossless dump of every finding."""

    def test_round_trips_every_issue(self):
        issues = [
            _issue(
                file_path="src/a.py",
                line_number=3,
                title="Hardcoded secret",
                description="A token is committed.",
                category="security",
                confidence=0.91,
                evidence=[Evidence(kind=EvidenceKind.RULE, detail="secret-pattern")],
                suggested_patch="-token = 'x'\n+token = os.environ['TOKEN']",
                source="rule",
            ),
            _issue(file_path="src/b.py", line_number=None, title="Missing test"),
        ]

        payload = InlineCommentBuilder().findings_payload(_result(*issues))

        assert len(payload) == 2
        for raw, issue in zip(payload, issues):
            assert raw == issue.model_dump(mode="json")
            assert FileIssue(**raw) == issue
            assert json.loads(json.dumps(raw)) == raw

        assert payload[0]["evidence"][0] == {"kind": "rule", "detail": "secret-pattern"}
        assert payload[0]["confidence"] == pytest.approx(0.91)
        assert payload[0]["source"] == "rule"

    def test_empty_result_returns_empty_list(self):
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=100.0,
            files_reviewed=[],
            summary="Clean",
        )

        assert InlineCommentBuilder().findings_payload(result) == []


class TestCreateReview:
    """create_review sends one review with inline comments."""

    @pytest.fixture
    def client(self) -> GitHubClient:
        return GitHubClient(
            repo_owner="test-owner",
            repo_name="test-repo",
            github_token="test-token",
        )

    async def test_wires_gh_request(self, client, monkeypatch):
        client._gh_available = True
        run_gh = MagicMock(return_value=MagicMock(returncode=0, stderr=""))
        monkeypatch.setattr(client, "_run_gh", run_gh)
        comments = [{"path": "src/app.py", "line": 12, "body": "**Broken**"}]

        result = await client.create_review(42, comments, body="Review summary")

        assert result is True
        args, kwargs = run_gh.call_args
        assert args[0] == ["pulls/42/reviews", "--method", "POST", "--input", "-"]
        sent = json.loads(kwargs["input_data"])
        assert sent == {
            "event": "COMMENT",
            "comments": comments,
            "body": "Review summary",
        }

    async def test_defaults_to_comment_event_and_omits_empty_body(self, client, monkeypatch):
        client._gh_available = True
        run_gh = MagicMock(return_value=MagicMock(returncode=0, stderr=""))
        monkeypatch.setattr(client, "_run_gh", run_gh)

        await client.create_review(7, [])

        sent = json.loads(run_gh.call_args.kwargs["input_data"])
        assert sent == {"event": "COMMENT", "comments": []}

    async def test_returns_false_when_gh_fails(self, client, monkeypatch):
        client._gh_available = True
        run_gh = MagicMock(return_value=MagicMock(returncode=1, stderr="boom"))
        monkeypatch.setattr(client, "_run_gh", run_gh)

        assert await client.create_review(42, []) is False

    async def test_falls_back_to_api(self, client, monkeypatch):
        client._gh_available = False
        comments = [{"path": "src/app.py", "line": 3, "body": "Note"}]

        response = MagicMock(status=201)
        urlopen = MagicMock()
        urlopen.return_value.__enter__ = MagicMock(return_value=response)
        urlopen.return_value.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(urllib.request, "urlopen", urlopen)

        result = await client.create_review(42, comments, body="Body", event="REQUEST_CHANGES")

        assert result is True
        request = urlopen.call_args.args[0]
        assert request.full_url == (
            "https://api.github.com/repos/test-owner/test-repo/pulls/42/reviews"
        )
        assert request.get_method() == "POST"
        assert json.loads(request.data) == {
            "event": "REQUEST_CHANGES",
            "comments": comments,
            "body": "Body",
        }
