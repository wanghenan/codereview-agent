"""LLM provider abstraction layer."""

from __future__ import annotations

from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from codereview.models import ConfigLLM, LLMProvider


class LLMFactory:
    """Factory for creating LLM instances based on provider."""

    # Default models for each provider
    DEFAULT_MODELS = {
        LLMProvider.OPENAI: "gpt-4o",
        LLMProvider.ANTHROPIC: "claude-sonnet-4-20250514",
        LLMProvider.ZHIPU: "glm-4-flash",
        LLMProvider.MINIMAX: "abab6.5s-chat",
        LLMProvider.QWEN: "qwen-plus",
        LLMProvider.DEEPSEEK: "deepseek-chat",
    }

    # Base URLs for compatible APIs
    BASE_URLS = {
        LLMProvider.ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
        LLMProvider.MINIMAX: "https://api.minimax.chat/v1",
        LLMProvider.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        LLMProvider.DEEPSEEK: "https://api.deepseek.com/v1",
    }

    @classmethod
    def create(cls, config: ConfigLLM) -> Any:
        """Create an LLM instance based on configuration.

        Args:
            config: LLM configuration

        Returns:
            A LangChain chat model instance
        """
        model = config.model or cls.DEFAULT_MODELS.get(config.provider)

        if config.provider == LLMProvider.OPENAI:
            return cls._create_openai(config, model)
        elif config.provider == LLMProvider.ANTHROPIC:
            return cls._create_anthropic(config, model)
        elif config.provider in (
            LLMProvider.ZHIPU,
            LLMProvider.MINIMAX,
            LLMProvider.QWEN,
            LLMProvider.DEEPSEEK,
        ):
            return cls._create_compatible(config, model)
        else:
            raise ValueError(f"Unsupported provider: {config.provider}")

    @classmethod
    def _create_openai(cls, config: ConfigLLM, model: str) -> ChatOpenAI:
        """Create OpenAI LLM."""
        return ChatOpenAI(
            model=model,
            api_key=config.api_key,
            base_url=config.base_url or None,
            temperature=config.temperature,
        )

    @classmethod
    def _create_anthropic(cls, config: ConfigLLM, model: str) -> ChatAnthropic:
        """Create Anthropic LLM."""
        return ChatAnthropic(
            model=model,
            anthropic_api_key=config.api_key,
            base_url=config.base_url or "https://api.anthropic.com",
            temperature=config.temperature,
        )

    @classmethod
    def _create_compatible(cls, config: ConfigLLM, model: str) -> ChatOpenAI:
        """Create LLM with OpenAI-compatible API.

        Supports: Zhipu (智谱), MiniMax, Qwen (阿里云), DeepSeek
        """
        base_url = config.base_url
        if not base_url:
            base_url = cls.BASE_URLS.get(config.provider)
            if not base_url:
                raise ValueError(f"No base_url for provider: {config.provider}")

        return ChatOpenAI(
            model=model,
            api_key=config.api_key,
            base_url=base_url,
            temperature=config.temperature,
        )

    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of available provider names."""
        return [p.value for p in LLMProvider]

    @classmethod
    def get_default_model(cls, provider: LLMProvider) -> str:
        """Get default model for a provider."""
        return cls.DEFAULT_MODELS.get(provider, "gpt-4o")
