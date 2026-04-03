"""Tests for configurable fields in Config model."""

import pytest
from pydantic import ValidationError

from codereview.models import Config, ConfigLLM, LLMProvider


class TestConfigFlexibility:
    """Test Config model with flexible fields."""

    def test_default_values(self):
        """Test Config has correct default values."""
        config = Config(llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"))
        assert config.max_concurrency == 5
        assert config.timeout_seconds == 30.0
        assert config.cache_dir == ".codereview-agent/cache"
        assert config.default_models is None

    def test_custom_max_concurrency(self):
        """Test Config accepts custom max_concurrency=10."""
        config = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
            max_concurrency=10,
        )
        assert config.max_concurrency == 10

    def test_rejects_max_concurrency_zero(self):
        """Test Config rejects max_concurrency=0 (ValidationError)."""
        with pytest.raises(ValidationError) as exc_info:
            Config(
                llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
                max_concurrency=0,
            )
        assert "max_concurrency" in str(exc_info.value)

    def test_rejects_max_concurrency_51(self):
        """Test Config rejects max_concurrency=51 (ValidationError)."""
        with pytest.raises(ValidationError) as exc_info:
            Config(
                llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
                max_concurrency=51,
            )
        assert "max_concurrency" in str(exc_info.value)

    def test_custom_timeout_seconds(self):
        """Test Config accepts custom timeout_seconds=60.0."""
        config = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
            timeout_seconds=60.0,
        )
        assert config.timeout_seconds == 60.0

    def test_timeout_seconds_boundary_low(self):
        """Test Config accepts minimum timeout_seconds=5.0."""
        config = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
            timeout_seconds=5.0,
        )
        assert config.timeout_seconds == 5.0

    def test_timeout_seconds_boundary_high(self):
        """Test Config accepts maximum timeout_seconds=300.0."""
        config = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
            timeout_seconds=300.0,
        )
        assert config.timeout_seconds == 300.0

    def test_rejects_timeout_seconds_too_low(self):
        """Test Config rejects timeout_seconds below minimum."""
        with pytest.raises(ValidationError) as exc_info:
            Config(
                llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
                timeout_seconds=4.9,
            )
        assert "timeout_seconds" in str(exc_info.value)

    def test_rejects_timeout_seconds_too_high(self):
        """Test Config rejects timeout_seconds above maximum."""
        with pytest.raises(ValidationError) as exc_info:
            Config(
                llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
                timeout_seconds=301.0,
            )
        assert "timeout_seconds" in str(exc_info.value)

    def test_custom_cache_dir(self):
        """Test Config accepts custom cache_dir."""
        config = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
            cache_dir="/tmp/my-cache",
        )
        assert config.cache_dir == "/tmp/my-cache"

    def test_custom_default_models(self):
        """Test Config accepts custom default_models."""
        custom_models = {"openai": "gpt-4o-mini", "anthropic": "claude-3-haiku"}
        config = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
            default_models=custom_models,
        )
        assert config.default_models == custom_models

    def test_max_concurrency_boundary(self):
        """Test max_concurrency accepts boundary values 1 and 50."""
        config_min = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
            max_concurrency=1,
        )
        assert config_min.max_concurrency == 1

        config_max = Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
            max_concurrency=50,
        )
        assert config_max.max_concurrency == 50
