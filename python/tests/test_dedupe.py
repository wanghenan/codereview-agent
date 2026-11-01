"""Tests for S6 dedupe and team memory."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from codereview.cli import review_cmd
from codereview.core.dedupe import (
    MIN_PENALTY,
    AlreadyReportedIndex,
    TeamMemory,
    apply_dedupe,
    fingerprint,
    marker_for,
    normalise_label,
)
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


@pytest.fixture
def config() -> Config:
    """Config with a PR-comment-friendly output block."""
    return Config(
        llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
        critical_paths=["src/auth"],
        exclude_patterns=["*.test.py"],
        max_concurrency=2,
        timeout_seconds=5.0,
    )


def _issue(
    *,
    line: int = 4,
    title: str = "Bug",
    description: str = "Potential bug",
    confidence: float = 0.8,
    path: str = "src/main.py",
) -> FileIssue:
    return FileIssue(
        file_path=path,
        line_number=line,
        risk_level=RiskLevel.MEDIUM,
        description=description,
        title=title,
        confidence=confidence,
    )


def _result(issue: FileIssue) -> ReviewResult:
    return ReviewResult(
        conclusion=ReviewConclusion.NEEDS_REVIEW,
        confidence=80.0,
        files_reviewed=[
            FileReview(
                file_path=issue.file_path,
                risk_level=RiskLevel.MEDIUM,
                changes="+1, -1",
                issues=[issue],
            )
        ],
        summary="Review summary",
    )


class TestFingerprint:
    def test_is_stable_and_short(self) -> None:
        first = fingerprint(_issue())
        assert first == fingerprint(_issue())
        assert len(first) == 16
        assert all(character in "0123456789abcdef" for character in first)

    def test_line_bucket_absorbs_small_shifts(self) -> None:
        assert fingerprint(_issue(line=4)) == fingerprint(_issue(line=7))

    def test_title_markup_does_not_change_identity(self) -> None:
        assert normalise_label("**SQL injection**") == normalise_label("sql injection")
        assert fingerprint(_issue(title="**Bug**")) == fingerprint(_issue(title="Bug"))

    def test_marker_is_an_html_comment(self) -> None:
        marker = marker_for(_issue())
        assert marker.startswith("<!--")
        assert marker.endswith("-->")
        assert fingerprint(_issue()) in marker


class TestAlreadyReportedIndex:
    def test_exact_marker_match(self) -> None:
        issue = _issue()
        index = AlreadyReportedIndex.from_comments(
            [{"path": "src/main.py", "line": 4, "body": f"seen\n\n{marker_for(issue)}"}]
        )
        assert index.matches(issue)

    def test_loose_match_allows_nearby_line_and_similar_title(self) -> None:
        index = AlreadyReportedIndex.from_comments(
            [{"path": "src/main.py", "line": 6, "body": "**Bug in the merge path**\n\ndetail"}]
        )
        assert index.matches(_issue(line=5, title="Bug in the merge path"))

    def test_loose_match_rejects_another_file(self) -> None:
        index = AlreadyReportedIndex.from_comments(
            [{"path": "src/other.py", "line": 4, "body": "**Bug**\n\ndetail"}]
        )
        assert not index.matches(_issue())

    def test_loose_match_rejects_distant_line(self) -> None:
        index = AlreadyReportedIndex.from_comments(
            [{"path": "src/main.py", "line": 40, "body": "**Bug**\n\ndetail"}]
        )
        assert not index.matches(_issue(line=4))

    def test_loose_match_rejects_unrelated_title(self) -> None:
        index = AlreadyReportedIndex.from_comments(
            [{"path": "src/main.py", "line": 4, "body": "**Unused import**\n\ndetail"}]
        )
        assert not index.matches(_issue(title="Race in the retry loop"))


class TestTeamMemory:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        memory = TeamMemory.load(tmp_path / "memory.json")
        assert memory.count(_issue()) == 0
        assert memory.penalty(_issue()) == 1.0

    def test_corrupt_file_is_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        path.write_text("{not json", encoding="utf-8")
        assert TeamMemory.load(path).count(_issue()) == 0

    def test_penalty_halves_and_respects_floor(self, tmp_path: Path) -> None:
        memory = TeamMemory(path=tmp_path / "memory.json")
        issue = _issue()
        memory.bump(issue)
        assert memory.penalty(issue) == pytest.approx(0.5)
        memory.bump(issue)
        assert memory.penalty(issue) == pytest.approx(0.25)
        memory.bump(issue)
        memory.bump(issue)
        assert memory.penalty(issue) == pytest.approx(MIN_PENALTY)

    def test_round_trips_through_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.json"
        memory = TeamMemory(path=path)
        memory.bump(_issue())
        memory.save()

        reloaded = TeamMemory.load(path)
        assert reloaded.count(_issue()) == 1
        assert reloaded.last_seen[fingerprint(_issue())]

    def test_learns_only_from_net_negative_reactions(self, tmp_path: Path) -> None:
        issue = _issue()
        body = f"a finding\n\n{marker_for(issue)}"
        comments = [
            {"body": body, "reactions": {"+1": 3, "-1": 0}},
            {"body": f"another\n\n{marker_for(_issue(title='Other'))}", "reactions": {"+1": 0, "-1": 2}},
            {"body": "no marker", "reactions": {"+1": 0, "-1": 5}},
        ]

        memory = TeamMemory(path=tmp_path / "memory.json")
        assert memory.learn_from_comments(comments) == 1
        assert memory.count(issue) == 0
        assert memory.count(_issue(title="Other")) == 1


class TestApplyDedupe:
    def test_suppresses_reported_findings_and_records_why(self) -> None:
        issue = _issue()
        result = _result(issue)
        index = AlreadyReportedIndex.from_comments(
            [{"path": "src/main.py", "line": 4, "body": f"x\n\n{marker_for(issue)}"}]
        )

        report = apply_dedupe(result, index)

        assert report.already_reported == 1
        assert result.files_reviewed[0].issues == []
        assert [record.reason for record in result.skipped] == ["already-reported"]
        assert report.notes()

    def test_memory_downweights_without_dropping(self) -> None:
        issue = _issue(confidence=0.8)
        result = _result(issue)
        memory = TeamMemory(path=Path("/nonexistent/memory.json"))
        memory.bump(issue)

        report = apply_dedupe(result, AlreadyReportedIndex(), memory)

        assert report.downweighted == 1
        assert result.files_reviewed[0].issues == [issue]
        assert issue.confidence == pytest.approx(0.4)


# --------------------------------------------------------------------------- #
# end-to-end: the same PR reviewed twice
# --------------------------------------------------------------------------- #
class _RecordingClient:
    """Fake GitHub client that remembers what it posted, like the real PR does."""

    def __init__(self) -> None:
        self.existing: list[dict] = []
        self.posted: list[list[dict]] = []

    async def list_review_comments(self, pr_number: int) -> list[dict]:
        return list(self.existing)

    async def create_review(self, pr_number: int, comments: list[dict], body=None) -> bool:
        self.posted.append(comments)
        self.existing.extend(
            {"path": item["path"], "line": item["line"], "body": item["body"]} for item in comments
        )
        return True


def _review_result() -> ReviewResult:
    return _result(_issue())


async def _run_once(monkeypatch, config, client, tmp_path: Path, **kwargs) -> dict:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(review_cmd, "RULES_AVAILABLE", False)
    monkeypatch.setattr(review_cmd.ConfigLoader, "load", lambda _path=None: config)
    monkeypatch.setattr(review_cmd.LLMFactory, "create", lambda _cfg: MagicMock())

    cache_manager = MagicMock()
    cache_manager.file_cache = None
    cache_manager.get_cache_info.return_value = {}
    monkeypatch.setattr(review_cmd, "CacheManager", lambda **_kwargs: cache_manager)

    monkeypatch.setattr(
        review_cmd.ReviewOrchestrator, "run_review", AsyncMock(return_value=_review_result())
    )
    monkeypatch.setattr(
        review_cmd.OutputGenerator,
        "generate",
        AsyncMock(return_value={"pr_comment": "summary"}),
    )
    monkeypatch.setattr(review_cmd, "create_github_client", MagicMock(return_value=client))

    return await review_cmd.run_review(
        diff_input=json.dumps(
            [{"filename": "src/main.py", "status": "modified", "additions": 1, "deletions": 1}]
        ),
        pr_number=42,
        **kwargs,
    )


async def test_second_run_on_the_same_pr_posts_no_inline_comments(
    monkeypatch: pytest.MonkeyPatch, config, tmp_path: Path
) -> None:
    client = _RecordingClient()

    first = await _run_once(monkeypatch, config, client, tmp_path)
    assert first["outputs"]["dedupe"] == {"already_reported": 0, "downweighted": 0}
    assert len(client.posted[0]) == 1

    second = await _run_once(monkeypatch, config, client, tmp_path)

    assert second["outputs"]["dedupe"]["already_reported"] == 1
    assert len(client.posted) == 1  # nothing new was posted
    assert second["outputs"]["findings"] == []


async def test_dry_run_never_calls_github(
    monkeypatch: pytest.MonkeyPatch, config, tmp_path: Path
) -> None:
    """A dry run builds the payload but touches no network and no memory."""
    client = _RecordingClient()

    result = await _run_once(monkeypatch, config, client, tmp_path, dry_run=True)

    assert client.existing == []
    assert client.posted == []
    assert "findings" in result["outputs"]
