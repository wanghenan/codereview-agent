"""Tests for review retry logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from codereview.agents.reviewer import ReviewAgent, ReviewOrchestrator
from codereview.models import Config, DiffEntry, FileReview, RiskLevel, ProjectContext


class TestRetryLogic:
    """Test retry logic for review failures."""

    def test_retry_initialization(self):
        """Test that ReviewAgent initializes with retry parameters."""
        from codereview.models import ConfigLLM, ConfigCache

        llm_config = ConfigLLM(
            provider="openai",
            api_key="test-key",
            model="gpt-4o"
        )
        config = Config(
            llm=llm_config,
            cache=ConfigCache()
        )

        # Create agent - should initialize without error
        agent = ReviewAgent(
            config=config,
            llm=MagicMock(),
            project_context=ProjectContext(
                tech_stack=["python"],
                language="python",
                critical_paths=[],
                analyzed_at="2024-01-01"
            )
        )

        # Should have default max_concurrency and timeout
        assert agent.max_concurrency == 5
        assert agent.timeout_seconds == 30.0

    def test_retry_method_exists(self):
        """Test that _review_file_with_retry method exists."""
        from codereview.models import ConfigLLM, ConfigCache

        llm_config = ConfigLLM(
            provider="openai",
            api_key="test-key",
            model="gpt-4o"
        )
        config = Config(
            llm=llm_config,
            cache=ConfigCache()
        )

        agent = ReviewAgent(
            config=config,
            llm=MagicMock(),
            project_context=ProjectContext(
                tech_stack=["python"],
                language="python",
                critical_paths=[],
                analyzed_at="2024-01-01"
            )
        )

        # Should have the retry method
        assert hasattr(agent, '_review_file_with_retry')
        assert callable(agent._review_file_with_retry)


class TestCustomPromptPath:
    """Test custom prompt path functionality."""

    def test_default_prompt_used_when_no_custom_path(self):
        """Test that default prompt is used when custom_prompt_path is None."""
        from codereview.models import ConfigLLM, ConfigCache

        llm_config = ConfigLLM(
            provider="openai",
            api_key="test-key",
            model="gpt-4o"
        )
        config = Config(
            llm=llm_config,
            cache=ConfigCache(),
            custom_prompt_path=None  # No custom path
        )

        agent = ReviewAgent(
            config=config,
            llm=MagicMock(),
            project_context=ProjectContext(
                tech_stack=["python"],
                language="python",
                critical_paths=[],
                analyzed_at="2024-01-01"
            )
        )

        entry = DiffEntry(
            filename="test.py",
            status="modified",
            additions=10,
            deletions=5,
            patch="@@ -1,5 +1,5 @@"
        )

        # Should not raise an error
        prompt = agent._build_prompt(entry)
        assert prompt is not None

    def test_build_prompt_method_exists(self):
        """Test that _build_prompt method exists and is callable."""
        from codereview.models import ConfigLLM, ConfigCache

        llm_config = ConfigLLM(
            provider="openai",
            api_key="test-key",
            model="gpt-4o"
        )
        config = Config(
            llm=llm_config,
            cache=ConfigCache()
        )

        agent = ReviewAgent(
            config=config,
            llm=MagicMock(),
            project_context=ProjectContext(
                tech_stack=["python"],
                language="python",
                critical_paths=[],
                analyzed_at="2024-01-01"
            )
        )

        assert hasattr(agent, '_build_prompt')
        assert callable(agent._build_prompt)
