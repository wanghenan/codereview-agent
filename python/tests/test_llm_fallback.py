"""Tests for LLM provider fallback chain."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from codereview.core.llm import LLMFactory, _FallbackChainLLM
from codereview.models import ConfigLLM, LLMProvider


class TestLLMFallbackChain:
    """Test LLM fallback chain behavior."""

    def test_fallback_to_second_provider_when_first_fails(self, caplog):
        """Test that fallback to second provider works when first fails."""
        caplog.set_level(logging.INFO)

        primary_config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="primary-key",
            model="gpt-4o",
            temperature=0.7,
        )
        fallback_config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="fallback-key",
            model="claude-sonnet-4-20250514",
            temperature=0.7,
        )

        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = Exception("rate limit exceeded")

        fallback_llm = MagicMock()
        fallback_llm.invoke.return_value = "success from fallback"

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.side_effect = [primary_llm, fallback_llm]

            result = LLMFactory.create_with_fallback(
                primary_config, fallback_configs=[fallback_config]
            )

            assert result.invoke("test") == "success from fallback"
            assert "fallback" in caplog.text.lower() or "trying" in caplog.text.lower()

    def test_fallback_tries_all_providers_until_success(self, caplog):
        """Test that all fallback providers are tried until one succeeds."""
        caplog.set_level(logging.INFO)

        configs = [
            ConfigLLM(provider=LLMProvider.OPENAI, api_key="key1", temperature=0.7),
            ConfigLLM(provider=LLMProvider.ANTHROPIC, api_key="key2", temperature=0.7),
            ConfigLLM(provider=LLMProvider.DEEPSEEK, api_key="key3", temperature=0.7),
        ]

        llm1 = MagicMock()
        llm2 = MagicMock()
        llm3 = MagicMock()
        llm3.invoke.return_value = "success from third"

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.side_effect = [llm1, llm2, llm3]

            llm1.invoke.side_effect = Exception("error")
            llm2.invoke.side_effect = Exception("error")

            result = LLMFactory.create_with_fallback(configs[0], fallback_configs=configs[1:])

            assert result.invoke("test") == "success from third"
            assert llm1.invoke.called
            assert llm2.invoke.called
            assert llm3.invoke.called

    def test_max_3_fallback_attempts_respected(self):
        """Test that max 3 total attempts are respected (primary + 2 fallbacks)."""
        configs = [
            ConfigLLM(provider=LLMProvider.OPENAI, api_key="key1", temperature=0.7),
            ConfigLLM(provider=LLMProvider.ANTHROPIC, api_key="key2", temperature=0.7),
            ConfigLLM(provider=LLMProvider.DEEPSEEK, api_key="key3", temperature=0.7),
            ConfigLLM(provider=LLMProvider.ZHIPU, api_key="key4", temperature=0.7),
        ]

        # Primary LLM created immediately, then 2 fallbacks created on invoke
        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = Exception("persistent error")

        fallback_llm1 = MagicMock()
        fallback_llm1.invoke.side_effect = Exception("persistent error")

        fallback_llm2 = MagicMock()
        fallback_llm2.invoke.side_effect = Exception("persistent error")

        with patch.object(LLMFactory, "create") as mock_create:
            # Primary created at setup, fallbacks created when invoke is called
            mock_create.side_effect = [primary_llm, fallback_llm1, fallback_llm2]

            result = LLMFactory.create_with_fallback(configs[0], fallback_configs=configs[1:])
            with pytest.raises(Exception, match="persistent error"):
                result.invoke("test")

            # Only 3 LLMs should be created (primary + 2 fallbacks)
            assert mock_create.call_count == 3

    def test_fallback_chain_logs_each_attempt(self, caplog):
        """Test that each fallback attempt is logged."""
        caplog.set_level(logging.INFO)

        primary_config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="primary-key",
            temperature=0.7,
        )
        fallback_config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="fallback-key",
            temperature=0.7,
        )

        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = Exception("rate limit")

        fallback_llm = MagicMock()
        fallback_llm.invoke.return_value = "success"

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.side_effect = [primary_llm, fallback_llm]

            result = LLMFactory.create_with_fallback(
                primary_config, fallback_configs=[fallback_config]
            )

            result.invoke("test")

            log_text = caplog.text.lower()
            assert "trying" in log_text or "fallback" in log_text

    def test_no_fallback_when_primary_succeeds(self, caplog):
        """Test that fallback is not triggered when primary provider succeeds."""
        caplog.set_level(logging.INFO)

        primary_config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="primary-key",
            temperature=0.7,
        )
        fallback_config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="fallback-key",
            temperature=0.7,
        )

        primary_llm = MagicMock()
        primary_llm.invoke.return_value = "success from primary"

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.return_value = primary_llm

            result = LLMFactory.create_with_fallback(
                primary_config, fallback_configs=[fallback_config]
            )

            assert result.invoke("test") == "success from primary"
            assert primary_llm.invoke.called
            assert mock_create.call_count == 1

    def test_empty_fallback_configs_no_fallback(self):
        """Test that empty fallback_configs still works (returns primary)."""
        primary_config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="primary-key",
            temperature=0.7,
        )

        primary_llm = MagicMock()
        primary_llm.invoke.return_value = "success"

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.return_value = primary_llm

            result = LLMFactory.create_with_fallback(primary_config, fallback_configs=[])

            assert result.invoke("test") == "success"

    def test_fallback_with_rate_limit_error(self):
        """Test fallback triggered by rate limit error."""
        primary_config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="primary-key",
            temperature=0.7,
        )
        fallback_config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="fallback-key",
            temperature=0.7,
        )

        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = Exception("429 Rate limit exceeded")

        fallback_llm = MagicMock()
        fallback_llm.invoke.return_value = "success from fallback"

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.side_effect = [primary_llm, fallback_llm]

            result = LLMFactory.create_with_fallback(
                primary_config, fallback_configs=[fallback_config]
            )

            assert result.invoke("test") == "success from fallback"

    def test_fallback_with_timeout_error(self):
        """Test fallback triggered by timeout error."""
        primary_config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="primary-key",
            temperature=0.7,
        )
        fallback_config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="fallback-key",
            temperature=0.7,
        )

        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = Exception("timeout")

        fallback_llm = MagicMock()
        fallback_llm.invoke.return_value = "success from fallback"

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.side_effect = [primary_llm, fallback_llm]

            result = LLMFactory.create_with_fallback(
                primary_config, fallback_configs=[fallback_config]
            )

            assert result.invoke("test") == "success from fallback"

    def test_fallback_with_api_error(self):
        """Test fallback triggered by API error."""
        primary_config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="primary-key",
            temperature=0.7,
        )
        fallback_config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="fallback-key",
            temperature=0.7,
        )

        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = Exception("500 Internal server error")

        fallback_llm = MagicMock()
        fallback_llm.invoke.return_value = "success from fallback"

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.side_effect = [primary_llm, fallback_llm]

            result = LLMFactory.create_with_fallback(
                primary_config, fallback_configs=[fallback_config]
            )

            assert result.invoke("test") == "success from fallback"

    def test_all_providers_fail_raises_exception(self):
        """Test that exception is raised when all providers fail."""
        primary_config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="primary-key",
            temperature=0.7,
        )
        fallback_config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="fallback-key",
            temperature=0.7,
        )

        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = Exception("error1")

        fallback_llm = MagicMock()
        fallback_llm.invoke.side_effect = Exception("error2")

        with patch.object(LLMFactory, "create") as mock_create:
            mock_create.side_effect = [primary_llm, fallback_llm]

            result = LLMFactory.create_with_fallback(
                primary_config, fallback_configs=[fallback_config]
            )
            with pytest.raises(Exception, match="All LLM providers failed"):
                result.invoke("test")

    def test_fallback_chain_llm_direct_invocation(self):
        """Test _FallbackChainLLM can be used directly."""
        primary_llm = MagicMock()
        primary_llm.invoke.side_effect = Exception("fail")

        fallback_llm = MagicMock()
        fallback_llm.invoke.return_value = "fallback success"

        fallback_config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="key",
            temperature=0.7,
        )

        with patch.object(LLMFactory, "create", return_value=fallback_llm):
            chain = _FallbackChainLLM(
                primary_llm=primary_llm,
                fallback_configs=[fallback_config],
            )
            result = chain.invoke("test input")
            assert result == "fallback success"
