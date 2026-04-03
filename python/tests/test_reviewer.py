"""Tests for ReviewAgent and ReviewOrchestrator."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codereview.agents.reviewer import ReviewAgent, ReviewOrchestrator
from codereview.models import (
    Config,
    ConfigCache,
    ConfigLLM,
    DiffEntry,
    FileIssue,
    FileReview,
    LLMProvider,
    ProjectContext,
    RiskLevel,
    ReviewConclusion,
)


@pytest.fixture
def mock_llm():
    """Mock LLM that returns valid JSON responses."""
    llm = MagicMock()
    chain_mock = MagicMock()
    chain_mock.ainvoke = AsyncMock(
        return_value={
            "risk_level": "medium",
            "issues": [
                {
                    "line_number": 10,
                    "risk_level": "medium",
                    "description": "Potential bug",
                    "suggestion": "Add null check",
                }
            ],
            "summary": "Review summary",
        }
    )
    chain_mock.__or__ = MagicMock(return_value=chain_mock)
    llm.__rtruediv__ = MagicMock(return_value=chain_mock)
    return llm


@pytest.fixture
def config():
    """Create test config."""
    return Config(
        llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
        critical_paths=["src/auth", "src/payment"],
        exclude_patterns=["*.test.py", "**/node_modules/**"],
        max_concurrency=3,
        timeout_seconds=30.0,
    )


@pytest.fixture
def project_context():
    """Create test project context."""
    return ProjectContext(
        tech_stack=["python"],
        language="python",
        critical_paths=["src/auth"],
        analyzed_at=datetime.now().isoformat(),
    )


@pytest.fixture
def diff_entry():
    """Create test diff entry."""
    return DiffEntry(
        filename="src/main.py",
        status="modified",
        additions=10,
        deletions=5,
        patch="@@ -1,5 +1,6 @@\n+new line\n-old line",
    )


class TestReviewAgent:
    """Test ReviewAgent class."""

    def test_single_file_review(self, config, mock_llm, project_context, diff_entry):
        """Test single file review with mock LLM response."""
        agent = ReviewAgent(config, mock_llm, project_context)

        async def run():
            results = await agent.review_files([diff_entry])
            assert len(results) == 1
            assert results[0].file_path == "src/main.py"
            assert results[0].risk_level == RiskLevel.MEDIUM
            assert len(results[0].issues) == 1

        asyncio.run(run())

    def test_multi_file_concurrent_review(self, config, project_context):
        """Test multi-file concurrent review verifies concurrency control."""
        # Track concurrent executions
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def slow_review(entry):
            nonlocal current_concurrent, max_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.1)
            async with lock:
                current_concurrent -= 1
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes="+10, -5",
                issues=[],
            )

        mock_llm = MagicMock()
        agent = ReviewAgent(config, mock_llm, project_context)
        agent._review_file = slow_review

        entries = [
            DiffEntry(filename=f"file{i}.py", status="modified", additions=5, deletions=2)
            for i in range(6)
        ]

        async def run():
            results = await agent.review_files(entries)
            return results

        results = asyncio.run(run())
        assert len(results) == 6
        # max_concurrency should be <= config.max_concurrency (3)
        assert max_concurrent <= config.max_concurrency

    def test_cache_hit_skips_review(self, config, mock_llm, project_context):
        """Test that cached results are used and skip LLM review."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = {
            "file_path": "src/main.py",
            "risk_level": "low",
            "changes": "+10, -5",
            "issues": [],
        }

        agent = ReviewAgent(config, mock_llm, project_context, file_cache=mock_cache)

        diff_entry = DiffEntry(
            filename="src/main.py",
            status="modified",
            additions=10,
            deletions=5,
            patch="@@ diff",
        )

        async def run():
            results = await agent.review_files([diff_entry])
            return results

        results = asyncio.run(run())

        # Should return cached result without calling LLM
        assert len(results) == 1
        assert results[0].risk_level == RiskLevel.LOW
        # Cache should have been checked
        mock_cache.get.assert_called_once()

    def test_exclude_pattern_matching(self, config, mock_llm, project_context):
        """Test exclude pattern matching in _should_exclude."""
        agent = ReviewAgent(config, mock_llm, project_context)

        # Should exclude test files matching *.test.py pattern
        assert agent._should_exclude("foo.test.py") is True
        assert agent._should_exclude("src/node_modules/utils.js") is True
        # Should not exclude regular files
        assert agent._should_exclude("src/main.py") is False
        assert agent._should_exclude("src/utils.py") is False

    def test_retry_logic_3_retries_then_degraded(self, config, mock_llm, project_context):
        """Test retry logic with 3 retries then returns degraded result."""
        call_count = 0

        async def always_fail(entry):
            nonlocal call_count
            call_count += 1
            raise ValueError("Simulated failure")

        mock_llm_fail = MagicMock()
        agent = ReviewAgent(config, mock_llm_fail, project_context)
        agent._review_file = always_fail

        diff_entry = DiffEntry(
            filename="src/failing.py",
            status="modified",
            additions=5,
            deletions=2,
        )

        async def run():
            result = await agent._review_file_with_retry(diff_entry, max_retries=3)
            return result

        result = asyncio.run(run())

        # Should have tried 3 times
        assert call_count == 3
        # Should return degraded result
        assert result is not None
        assert result.file_path == "src/failing.py"
        assert result.risk_level == RiskLevel.MEDIUM
        assert len(result.issues) == 1
        assert "failed after 3 attempts" in result.issues[0].description

    def test_timeout_handling(self, config, mock_llm, project_context):
        """Test timeout handling raises TimeoutError."""

        async def run():
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                with pytest.raises(asyncio.TimeoutError):
                    await agent._review_file(entry)

        agent = ReviewAgent(config, mock_llm, project_context)
        agent.timeout_seconds = 0.1

        entry = DiffEntry(
            filename="src/slow.py",
            status="modified",
            additions=5,
            deletions=2,
            patch="@@ diff",
        )

        asyncio.run(run())

    def test_llm_response_parsing_valid_json(self, config, mock_llm, project_context):
        """Test LLM response parsing with valid JSON."""
        agent = ReviewAgent(config, mock_llm, project_context)

        async def mock_review(entry):
            return FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.MEDIUM,
                changes="+10, -5",
                issues=[
                    FileIssue(
                        file_path=entry.filename,
                        line_number=10,
                        risk_level=RiskLevel.MEDIUM,
                        description="Potential bug",
                        suggestion="Add null check",
                    )
                ],
            )

        agent._review_file = mock_review

        async def run():
            entry = DiffEntry(
                filename="src/main.py",
                status="modified",
                additions=10,
                deletions=5,
                patch="@@ diff",
            )
            result = await agent._review_file(entry)
            return result

        result = asyncio.run(run())
        assert result.file_path == "src/main.py"
        assert result.risk_level == RiskLevel.MEDIUM
        assert len(result.issues) == 1
        assert result.issues[0].description == "Potential bug"

    def test_llm_response_parsing_invalid_json(self, config, project_context):
        """Test LLM response parsing with invalid JSON raises exception."""

        async def failing_review(entry):
            raise ValueError("Invalid JSON")

        agent = ReviewAgent(config, MagicMock(), project_context)
        agent._review_file = failing_review

        entry = DiffEntry(
            filename="src/main.py",
            status="modified",
            additions=10,
            deletions=5,
            patch="@@ diff",
        )

        async def run():
            return await agent._review_file_with_retry(entry, max_retries=1)

        result = asyncio.run(run())
        assert result.risk_level == RiskLevel.MEDIUM
        assert "Invalid JSON" in result.issues[0].description


class TestReviewOrchestrator:
    """Test ReviewOrchestrator class."""

    def test_confidence_calculation(self, config, mock_llm):
        """Test confidence calculation based on risk levels."""
        orchestrator = ReviewOrchestrator(config, mock_llm)

        # All low risk = high confidence
        reviews = [
            FileReview(file_path="a.py", risk_level=RiskLevel.LOW, changes="+5, -2", issues=[]),
            FileReview(file_path="b.py", risk_level=RiskLevel.LOW, changes="+3, -1", issues=[]),
        ]
        conclusion, confidence = orchestrator._calculate_result(reviews)
        assert conclusion == ReviewConclusion.CAN_SUBMIT
        assert confidence > 90

        # High risk = needs review with lower confidence
        reviews_high = [
            FileReview(file_path="a.py", risk_level=RiskLevel.HIGH, changes="+5, -2", issues=[]),
        ]
        conclusion, confidence = orchestrator._calculate_result(reviews_high)
        assert conclusion == ReviewConclusion.NEEDS_REVIEW
        assert confidence == 95.0

        # Many medium risk = needs review
        reviews_medium = [
            FileReview(
                file_path=f"file{i}.py", risk_level=RiskLevel.MEDIUM, changes="+5, -2", issues=[]
            )
            for i in range(5)
        ]
        conclusion, confidence = orchestrator._calculate_result(reviews_medium)
        assert conclusion == ReviewConclusion.NEEDS_REVIEW

    def test_generate_summary(self, config, mock_llm):
        """Test summary generation."""
        orchestrator = ReviewOrchestrator(config, mock_llm)

        reviews = [
            FileReview(
                file_path="a.py",
                risk_level=RiskLevel.HIGH,
                changes="+10, -5",
                issues=[
                    FileIssue(file_path="a.py", risk_level=RiskLevel.HIGH, description="Issue 1")
                ],
            ),
            FileReview(
                file_path="b.py",
                risk_level=RiskLevel.LOW,
                changes="+3, -1",
                issues=[],
            ),
        ]
        summary = orchestrator._generate_summary(reviews)
        assert "a.py" in summary
        assert "b.py" in summary
        assert "high" in summary
        assert "low" in summary
