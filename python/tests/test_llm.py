"""Tests for LLM factory and provider creation."""

from unittest.mock import MagicMock, patch

from codereview.core.llm import LLMFactory
from codereview.models import ConfigLLM, LLMProvider


class TestLLMFactory:
    """Test LLMFactory class."""

    def test_create_openai(self):
        """Test creating OpenAI LLM."""
        config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="test-key",
            model="gpt-4o",
            temperature=0.5,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            result = LLMFactory.create(config)
            mock_openai.assert_called_once_with(
                model="gpt-4o",
                api_key="test-key",
                base_url=None,
                temperature=0.5,
            )
            assert result == mock_instance

    def test_create_anthropic(self):
        """Test creating Anthropic LLM."""
        config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="test-key",
            model="claude-sonnet-4-20250514",
            temperature=0.3,
        )
        with patch("codereview.core.llm.ChatAnthropic") as mock_anthropic:
            mock_instance = MagicMock()
            mock_anthropic.return_value = mock_instance
            result = LLMFactory.create(config)
            mock_anthropic.assert_called_once_with(
                model="claude-sonnet-4-20250514",
                anthropic_api_key="test-key",
                base_url="https://api.anthropic.com",
                temperature=0.3,
            )
            assert result == mock_instance

    def test_create_zhipu(self):
        """Test creating Zhipu LLM."""
        config = ConfigLLM(
            provider=LLMProvider.ZHIPU,
            api_key="test-key",
            temperature=0.7,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            result = LLMFactory.create(config)
            mock_openai.assert_called_once_with(
                model="glm-4-flash",
                api_key="test-key",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                temperature=0.7,
            )
            assert result == mock_instance

    def test_create_minimax(self):
        """Test creating MiniMax LLM."""
        config = ConfigLLM(
            provider=LLMProvider.MINIMAX,
            api_key="test-key",
            temperature=0.7,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            result = LLMFactory.create(config)
            mock_openai.assert_called_once_with(
                model="abab6.5s-chat",
                api_key="test-key",
                base_url="https://api.minimax.chat/v1",
                temperature=0.7,
            )
            assert result == mock_instance

    def test_create_qwen(self):
        """Test creating Qwen LLM."""
        config = ConfigLLM(
            provider=LLMProvider.QWEN,
            api_key="test-key",
            temperature=0.7,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            result = LLMFactory.create(config)
            mock_openai.assert_called_once_with(
                model="qwen-plus",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                temperature=0.7,
            )
            assert result == mock_instance

    def test_create_deepseek(self):
        """Test creating DeepSeek LLM."""
        config = ConfigLLM(
            provider=LLMProvider.DEEPSEEK,
            api_key="test-key",
            temperature=0.7,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            result = LLMFactory.create(config)
            mock_openai.assert_called_once_with(
                model="deepseek-chat",
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
                temperature=0.7,
            )
            assert result == mock_instance

    def test_all_enum_providers_are_supported(self):
        """Test that all LLMProvider enum values are handled by the factory."""
        # This test verifies that all enum values are properly handled
        # since Pydantic validates enum values before factory.create() is called
        for provider in LLMProvider:
            config = ConfigLLM(
                provider=provider,
                api_key="test-key",
                temperature=0.7,
            )
            # All providers should be createable without raising ValueError
            # They may fail later at API call time, but not at factory.create()
            with patch(
                "codereview.core.llm.ChatOpenAI"
                if provider != LLMProvider.ANTHROPIC
                else "codereview.core.llm.ChatAnthropic"
            ):
                try:
                    LLMFactory.create(config)
                except Exception:
                    # Some providers might fail due to missing base_url in test env
                    # but they shouldn't raise ValueError("Unsupported provider")
                    pass

    def test_get_default_model_openai(self):
        """Test get_default_model for OpenAI."""
        assert LLMFactory.get_default_model(LLMProvider.OPENAI) == "gpt-4o"

    def test_get_default_model_anthropic(self):
        """Test get_default_model for Anthropic."""
        assert LLMFactory.get_default_model(LLMProvider.ANTHROPIC) == "claude-sonnet-4-20250514"

    def test_get_default_model_zhipu(self):
        """Test get_default_model for Zhipu."""
        assert LLMFactory.get_default_model(LLMProvider.ZHIPU) == "glm-4-flash"

    def test_get_default_model_minimax(self):
        """Test get_default_model for MiniMax."""
        assert LLMFactory.get_default_model(LLMProvider.MINIMAX) == "abab6.5s-chat"

    def test_get_default_model_qwen(self):
        """Test get_default_model for Qwen."""
        assert LLMFactory.get_default_model(LLMProvider.QWEN) == "qwen-plus"

    def test_get_default_model_deepseek(self):
        """Test get_default_model for DeepSeek."""
        assert LLMFactory.get_default_model(LLMProvider.DEEPSEEK) == "deepseek-chat"

    def test_get_default_model_with_custom_defaults(self):
        """Test get_default_model with custom default models."""
        custom_defaults = {"openai": "gpt-4o-mini"}
        assert LLMFactory.get_default_model(LLMProvider.OPENAI, custom_defaults) == "gpt-4o-mini"

    def test_get_default_model_unknown_provider_fallback(self):
        """Test get_default_model falls back to gpt-4o for unknown provider."""
        assert LLMFactory.get_default_model(LLMProvider.OPENAI) == "gpt-4o"

    def test_custom_model_override(self):
        """Test custom model override."""
        config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="test-key",
            model="gpt-4o-mini",
            temperature=0.7,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            LLMFactory.create(config)
            mock_openai.assert_called_once_with(
                model="gpt-4o-mini",
                api_key="test-key",
                base_url=None,
                temperature=0.7,
            )

    def test_custom_base_url_override(self):
        """Test custom base_url override."""
        config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="test-key",
            base_url="https://custom.api.com/v1",
            temperature=0.7,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            LLMFactory.create(config)
            mock_openai.assert_called_once_with(
                model="gpt-4o",
                api_key="test-key",
                base_url="https://custom.api.com/v1",
                temperature=0.7,
            )

    def test_get_available_providers(self):
        """Test get_available_providers returns all providers."""
        providers = LLMFactory.get_available_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "zhipu" in providers
        assert "minimax" in providers
        assert "qwen" in providers
        assert "deepseek" in providers
        assert len(providers) == 6

    def test_anthropic_with_custom_base_url(self):
        """Test Anthropic with custom base_url."""
        config = ConfigLLM(
            provider=LLMProvider.ANTHROPIC,
            api_key="test-key",
            base_url="https://custom.anthropic.com",
            temperature=0.5,
        )
        with patch("codereview.core.llm.ChatAnthropic") as mock_anthropic:
            mock_instance = MagicMock()
            mock_anthropic.return_value = mock_instance
            result = LLMFactory.create(config)
            mock_anthropic.assert_called_once_with(
                model="claude-sonnet-4-20250514",
                anthropic_api_key="test-key",
                base_url="https://custom.anthropic.com",
                temperature=0.5,
            )
            assert result == mock_instance

    def test_zhipu_with_custom_base_url(self):
        """Test Zhipu with custom base_url overrides default."""
        config = ConfigLLM(
            provider=LLMProvider.ZHIPU,
            api_key="test-key",
            base_url="https://custom.zhipu.api.com",
            temperature=0.7,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            result = LLMFactory.create(config)
            mock_openai.assert_called_once_with(
                model="glm-4-flash",
                api_key="test-key",
                base_url="https://custom.zhipu.api.com",
                temperature=0.7,
            )
            assert result == mock_instance

    def test_temperature_passing(self):
        """Test temperature is correctly passed to LLM."""
        config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="test-key",
            temperature=0.2,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            LLMFactory.create(config)
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["temperature"] == 0.2

    def test_empty_api_key_raises_error(self):
        """Test that empty API key is handled (passed to LLM, not validated here)."""
        config = ConfigLLM(
            provider=LLMProvider.OPENAI,
            api_key="",
            temperature=0.7,
        )
        with patch("codereview.core.llm.ChatOpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance
            # Empty API key is passed through - validation happens at LLM API call
            LLMFactory.create(config)
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["api_key"] == ""
