"""Integration tests for wiring S2/S3/S4 modules into the review pipeline."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import codereview.cli.review_cmd as review_cmd
from codereview.agents.reviewer import ReviewAgent, ReviewOrchestrator
from codereview.models import (
    Config,
    ConfigLLM,
    DiffEntry,
    EvidenceKind,
    FileIssue,
    FileReview,
    IssueCategory,
    LLMProvider,
    ProjectContext,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)
from codereview.output import InlineCommentBuilder


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


@pytest.fixture
def project_context() -> ProjectContext:
    """Minimal project context."""
    return ProjectContext(
        tech_stack=["python"],
        language="python",
        critical_paths=[],
        analyzed_at=datetime.now().isoformat(),
    )


@pytest.fixture
def mock_llm() -> MagicMock:
    """Mock LLM whose chain returns one ordinary LLM finding."""
    llm = MagicMock()
    chain = MagicMock()
    chain.ainvoke = AsyncMock(
        return_value={
            "risk_level": "low",
            "issues": [
                {
                    "line_number": 3,
                    "risk_level": "low",
                    "description": "LLM finding",
                }
            ],
            "summary": "Review summary",
        }
    )
    chain.__or__ = MagicMock(return_value=chain)
    llm.__rtruediv__ = MagicMock(return_value=chain)
    return llm


def _entry(filename: str, *, patch: str = "@@ -1 +1 @@\n-old\n+new") -> DiffEntry:
    """Build a modified DiffEntry."""
    return DiffEntry(
        filename=filename,
        status="modified",
        additions=1,
        deletions=1,
        patch=patch,
    )


def _stub_llm_chain(agent: ReviewAgent) -> None:
    """Replace the LangChain composition with a dict-returning stub."""
    final_chain = MagicMock()
    final_chain.ainvoke = AsyncMock(
        return_value={
            "risk_level": "low",
            "issues": [{"line_number": 3, "risk_level": "low", "description": "LLM finding"}],
            "summary": "Review summary",
        }
    )
    final_chain.__or__ = MagicMock(return_value=final_chain)
    prompt = MagicMock()
    prompt.__or__ = MagicMock(return_value=final_chain)
    agent._build_prompt = MagicMock(return_value=prompt)  # type: ignore[method-assign]


async def test_orchestrator_surfaces_skipped_records(
    config: Config, mock_llm: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The admission layer drops entries and puts SkipRecords on the result."""
    entries = [
        _entry("src/main.py"),
        _entry("README.md"),
        _entry("package-lock.json"),
    ]

    reviewed: list[str] = []

    async def fake_review_files(self, diff_entries):  # noqa: ANN001
        reviewed.extend(entry.filename for entry in diff_entries)
        return [
            FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes="+1, -1",
                issues=[],
            )
            for entry in diff_entries
        ]

    monkeypatch.setattr(ReviewAgent, "review_files", fake_review_files)

    result = await ReviewOrchestrator(config, mock_llm).run_review(entries)

    assert reviewed == ["src/main.py"]
    assert [record.filename for record in result.skipped] == [
        "README.md",
        "package-lock.json",
    ]
    assert [record.reason for record in result.skipped] == ["non-code", "lock-file"]
    assert [review.file_path for review in result.files_reviewed] == ["src/main.py"]


async def test_tool_findings_are_converted_and_runner_diagnostics_are_dropped(
    config: Config,
    mock_llm: MagicMock,
    project_context: ProjectContext,
    tmp_path,
) -> None:
    """Tool output becomes source=tool findings; runner diagnostics do not.

    A runner error entry ("ruff exited 2", "eslint is not installed", or ruff
    refusing a file a new-file diff has not created) describes the runner. A
    reviewer would never leave that as a comment on the change, so it is logged
    instead of converted.
    """
    runner = MagicMock()
    runner.timeout = 60.0
    runner.list_tools.return_value = [object()]
    runner.run.return_value = [
        {
            "file": "src/main.py",
            "line": 7,
            "rule_id": "F401",
            "tool": "ruff",
            "severity": "high",
            "description": "unused import",
        },
        {
            "file": "",
            "line": 0,
            "rule_id": "tool_error",
            "tool": "ruff",
            "severity": "error",
            "description": "tool crashed",
        },
    ]

    agent = ReviewAgent(
        config,
        mock_llm,
        project_context,
        tool_runner=runner,
        project_root=tmp_path,
    )
    _stub_llm_chain(agent)

    review = await agent._review_file(_entry("src/main.py"))

    tool_issues = [issue for issue in review.issues if issue.source == "tool"]
    assert len(tool_issues) == 1

    high = tool_issues[0]
    assert high.file_path == "src/main.py"
    assert high.line_number == 7
    assert high.category == IssueCategory.BUG
    assert high.risk_level == RiskLevel.HIGH
    assert high.confidence == 0.85
    assert high.evidence[0].kind == EvidenceKind.RULE
    assert high.evidence[0].detail == "ruff_F401"

    # The diagnostic entry is neither converted nor allowed to abort the review.
    assert all(issue.line_number is not None for issue in tool_issues)

    runner.run.assert_called_once_with(["src/main.py"], cwd=tmp_path)


async def test_tool_runner_is_not_called_when_no_tool_is_available(
    config: Config, mock_llm: MagicMock, project_context: ProjectContext, tmp_path
) -> None:
    """No applicable tools means no subprocess work and no issues."""
    runner = MagicMock()
    runner.list_tools.return_value = []

    agent = ReviewAgent(
        config,
        mock_llm,
        project_context,
        tool_runner=runner,
        project_root=tmp_path,
    )
    _stub_llm_chain(agent)

    await agent._review_file(_entry("src/main.py"))

    runner.run.assert_not_called()


def _review_result() -> ReviewResult:
    """Build a review result with one inline-able finding."""
    return ReviewResult(
        conclusion=ReviewConclusion.NEEDS_REVIEW,
        confidence=80.0,
        files_reviewed=[
            FileReview(
                file_path="src/main.py",
                risk_level=RiskLevel.MEDIUM,
                changes="+1, -1",
                issues=[
                    FileIssue(
                        file_path="src/main.py",
                        line_number=4,
                        risk_level=RiskLevel.MEDIUM,
                        description="Potential bug",
                        title="Bug",
                    )
                ],
            )
        ],
        summary="Review summary",
    )


def _stub_review_services(
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
    result: ReviewResult,
    client: MagicMock,
) -> MagicMock:
    """Stub everything ``run_review`` touches around the GitHub client."""
    monkeypatch.setattr(review_cmd, "RULES_AVAILABLE", False)
    monkeypatch.setattr(review_cmd.ConfigLoader, "load", lambda _path=None: config)
    monkeypatch.setattr(review_cmd.LLMFactory, "create", lambda _cfg: MagicMock())

    cache_manager = MagicMock()
    cache_manager.file_cache = None
    cache_manager.get_cache_info.return_value = {}
    monkeypatch.setattr(review_cmd, "CacheManager", lambda **_kwargs: cache_manager)

    monkeypatch.setattr(review_cmd.ReviewOrchestrator, "run_review", AsyncMock(return_value=result))
    monkeypatch.setattr(
        review_cmd.OutputGenerator,
        "generate",
        AsyncMock(return_value={"pr_comment": "summary"}),
    )

    client_factory = MagicMock(return_value=client)
    monkeypatch.setattr(review_cmd, "create_github_client", client_factory)
    return client_factory


def _diff_input() -> str:
    """Build a minimal diff payload for the review command."""
    return json.dumps(
        [{"filename": "src/main.py", "status": "modified", "additions": 1, "deletions": 1}]
    )


async def _run_review(
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
    result: ReviewResult,
    *,
    pr_number,
    client: MagicMock,
    **review_kwargs,
) -> tuple[dict, MagicMock]:
    """Run the CLI review command with all external services stubbed."""
    client_factory = _stub_review_services(monkeypatch, config, result, client)
    result_dict = await review_cmd.run_review(
        diff_input=_diff_input(), pr_number=pr_number, **review_kwargs
    )
    return result_dict, client_factory


async def test_inline_payload_is_attached_and_review_posted_once(
    monkeypatch: pytest.MonkeyPatch, config: Config
) -> None:
    """The built comments are posted once and findings are returned."""
    result = _review_result()
    client = MagicMock()
    client.create_review = AsyncMock(return_value=True)

    result_dict, client_factory = await _run_review(
        monkeypatch, config, result, pr_number=42, client=client
    )

    assert result_dict["outputs"]["findings"] == InlineCommentBuilder().findings_payload(result)
    client_factory.assert_called_once()

    client.create_review.assert_awaited_once()
    args, kwargs = client.create_review.await_args
    expected = InlineCommentBuilder().build(result)
    assert args == (42, expected["comments"])
    assert kwargs == {"body": expected["summary"]}


async def test_no_inline_review_when_pr_number_is_missing(
    monkeypatch: pytest.MonkeyPatch, config: Config
) -> None:
    """No client is created or called when there is no PR number."""
    result = _review_result()
    client = MagicMock()
    client.create_review = AsyncMock(return_value=True)

    result_dict, client_factory = await _run_review(
        monkeypatch, config, result, pr_number=None, client=client
    )

    assert result_dict["outputs"]["findings"] == InlineCommentBuilder().findings_payload(result)
    client_factory.assert_not_called()
    client.create_review.assert_not_awaited()


@pytest.mark.parametrize("flag", ["dry_run", "offline"])
async def test_dry_run_and_offline_skip_inline_post(
    monkeypatch: pytest.MonkeyPatch, config: Config, flag: str
) -> None:
    """Both switches still build findings but never create the GitHub client."""
    result = _review_result()
    client = MagicMock()
    client.create_review = AsyncMock(return_value=True)

    result_dict, client_factory = await _run_review(
        monkeypatch, config, result, pr_number=42, client=client, **{flag: True}
    )

    assert "findings" in result_dict["outputs"]
    client_factory.assert_not_called()
    client.create_review.assert_not_awaited()


def test_cli_offline_flag_never_creates_github_client(
    monkeypatch: pytest.MonkeyPatch, config: Config
) -> None:
    """--offline travels through the CLI and skips GitHub client creation."""
    from codereview import cli

    result = _review_result()
    client = MagicMock()
    client.create_review = AsyncMock(return_value=True)
    client_factory = _stub_review_services(monkeypatch, config, result, client)

    monkeypatch.setattr(
        sys,
        "argv",
        ["codereview", "--offline", "--pr", "42", "--diff", _diff_input()],
    )

    assert cli.main() == 0
    client_factory.assert_not_called()
    client.create_review.assert_not_awaited()
