"""Retry policy: which failures deserve another attempt (issue #68)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from codereview.agents.reviewer import ReviewAgent
from codereview.core.llm_output import LLMOutputParseError
from codereview.models import (
    Config,
    ConfigCache,
    ConfigLLM,
    DiffEntry,
    FileReview,
    ProjectContext,
    RiskLevel,
)


class ApiError(Exception):
    """Stand-in for a provider error that carries an HTTP status."""

    def __init__(self, status_code: int, message: str = "boom") -> None:
        super().__init__(message)
        self.status_code = status_code


def make_agent() -> ReviewAgent:
    config = Config(
        llm=ConfigLLM(provider="openai", api_key="test-key", model="gpt-4o"),
        cache=ConfigCache(),
    )
    return ReviewAgent(
        config=config,
        llm=MagicMock(),
        project_context=ProjectContext(
            tech_stack=["python"],
            language="python",
            critical_paths=[],
            analyzed_at="2024-01-01",
        ),
    )


ENTRY = DiffEntry(filename="pkg/mod.py", status="modified", additions=1, deletions=1, patch="@@ -1 +1 @@")


def run_with(exc: BaseException, *, max_retries: int = 3):
    """Run the retry loop against a review that always raises ``exc``."""
    agent = make_agent()
    calls: list[dict] = []

    async def failing_review(entry, strict_json: bool = False):
        calls.append({"strict_json": strict_json})
        raise exc

    agent._review_file = failing_review
    with patch("asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(agent._review_file_with_retry(ENTRY, max_retries=max_retries))
    return calls, result


def test_auth_failure_is_not_retried() -> None:
    calls, result = run_with(ApiError(401, "invalid credential"))

    assert len(calls) == 1, "a rejected credential must not be retried"
    assert "(auth)" in result.issues[0].description
    assert "after 1 attempt" in result.issues[0].description


def test_quota_failure_is_not_retried() -> None:
    calls, result = run_with(ApiError(402, "insufficient balance"))

    assert len(calls) == 1
    assert "(quota)" in result.issues[0].description


def test_bad_request_is_not_retried() -> None:
    calls, _ = run_with(ApiError(400, "invalid model"))

    assert len(calls) == 1


def test_timeout_is_retried_three_times() -> None:
    calls, result = run_with(asyncio.TimeoutError())

    assert len(calls) == 3
    assert "(timeout)" in result.issues[0].description
    assert "after 3 attempts" in result.issues[0].description


def test_upstream_error_is_retried() -> None:
    calls, _ = run_with(ApiError(503))

    assert len(calls) == 3


def test_unknown_error_stays_retryable() -> None:
    calls, _ = run_with(RuntimeError("something odd"))

    assert len(calls) == 3


def test_parse_failure_retries_with_a_stricter_prompt() -> None:
    calls, result = run_with(LLMOutputParseError("no json"))

    assert len(calls) == 3
    assert calls[0]["strict_json"] is False, "the first attempt keeps the normal prompt"
    assert calls[1]["strict_json"] is True, "the retry asks for JSON only"
    assert calls[2]["strict_json"] is True
    assert "(parse)" in result.issues[0].description


def test_strict_prompt_names_the_previous_failure() -> None:
    agent = make_agent()

    loose = agent._build_prompt(ENTRY)
    strict = agent._build_prompt(ENTRY, strict_json=True)

    def user_text(prompt) -> str:
        # The template is not rendered yet: the patch is partialed in later.
        return prompt.messages[1].prompt.template

    assert "not valid JSON" not in user_text(loose)
    assert "not valid JSON" in user_text(strict)


def test_a_retry_that_succeeds_returns_the_result() -> None:
    agent = make_agent()
    attempts: list[int] = []

    async def flaky(entry, strict_json: bool = False):
        attempts.append(1)
        if len(attempts) < 2:
            raise asyncio.TimeoutError()
        return FileReview(
            file_path=entry.filename,
            risk_level=RiskLevel.LOW,
            changes="+1, -1",
            issues=[],
        )

    agent._review_file = flaky
    with patch("asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(agent._review_file_with_retry(ENTRY, max_retries=3))

    assert len(attempts) == 2
    assert result.risk_level == RiskLevel.LOW
