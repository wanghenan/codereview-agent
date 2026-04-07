"""LLM provider abstraction layer."""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from codereview.models import ConfigLLM, LLMProvider

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 60


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
    def get_default_model(
        cls, provider: LLMProvider, default_models: Optional[dict[str, str]] = None
    ) -> str:
        """Get default model for a provider.

        Args:
            provider: LLM provider
            default_models: Optional dict of custom default models from config

        Returns:
            Model name
        """
        if default_models and provider.value in default_models:
            return default_models[provider.value]
        return cls.DEFAULT_MODELS.get(provider, "gpt-4o")

    @classmethod
    def create_with_fallback(
        cls,
        primary_config: ConfigLLM,
        fallback_configs: Optional[list[ConfigLLM]] = None,
    ) -> Any:
        """Create LLM with fallback chain support.

        Creates primary LLM and falls back to alternatives if invocation fails.
        Max 3 total attempts (1 primary + up to 2 fallbacks).

        Args:
            primary_config: Primary provider configuration
            fallback_configs: List of fallback configurations in priority order

        Returns:
            A LangChain chat model instance that handles fallback automatically

        Raises:
            Exception: If all providers in the chain fail
        """
        if fallback_configs is None:
            fallback_configs = []

        # Build full chain: primary + fallbacks (limited to 2 fallbacks for max 3)
        all_configs = [primary_config] + fallback_configs[:2]
        max_attempts = min(len(all_configs), 3)

        last_error = None
        for attempt in range(max_attempts):
            config = all_configs[attempt]
            provider_name = config.provider.value

            if attempt > 0:
                logger.info(f"Trying fallback provider {attempt}: {provider_name}")

            try:
                llm = cls.create(config)
                if attempt == 0:
                    # First attempt - wrap with fallback chain
                    return _FallbackChainLLM(
                        primary_llm=llm,
                        fallback_configs=all_configs[1:max_attempts],
                    )
                else:
                    # Fallback attempts handled via _FallbackChainLLM
                    return llm
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {provider_name} failed: {e}")

        raise last_error or Exception("All LLM providers failed")


class _FallbackChainLLM:
    """Wrapper LLM that automatically tries fallback providers on failure.

    This wrapper intercepts invoke calls and retries with fallback providers
    if the primary LLM fails with a recoverable error.
    """

    def __init__(
        self,
        primary_llm: Any,
        fallback_configs: list[ConfigLLM],
    ):
        """Initialize fallback chain wrapper.

        Args:
            primary_llm: The primary LLM instance
            fallback_configs: List of fallback ConfigLLM configs (max 2)
        """
        self._primary_llm = primary_llm
        self._fallback_configs = fallback_configs[:2]  # Max 2 fallbacks

    def invoke(self, input_: Any) -> Any:
        """Invoke LLM with fallback on failure.

        Args:
            input_: Input to send to LLM

        Returns:
            LLM response

        Raises:
            Exception: If primary and all fallbacks fail
        """
        # Try primary first
        try:
            return self._primary_llm.invoke(input_)
        except Exception as primary_error:
            logger.warning(f"Primary provider failed: {primary_error}")
            return self._invoke_fallback_chain(input_, [primary_error])

    async def ainvoke(self, input_: Any) -> Any:
        """Async invoke LLM with fallback on failure.

        Args:
            input_: Input to send to LLM

        Returns:
            LLM response

        Raises:
            Exception: If primary and all fallbacks fail
        """
        try:
            return await self._primary_llm.ainvoke(input_)
        except Exception as primary_error:
            logger.warning(f"Primary provider failed: {primary_error}")
            return await self._ainvoke_fallback_chain(input_, [primary_error])

    def _invoke_fallback_chain(self, input_: Any, prior_errors: list) -> Any:
        """Try fallback providers in sequence.

        Args:
            input_: Input to send to LLM
            prior_errors: List of errors from previous attempts

        Returns:
            LLM response from first successful fallback

        Raises:
            Exception: If all providers in chain fail
        """
        for i, fallback_config in enumerate(self._fallback_configs):
            provider_name = fallback_config.provider.value
            logger.info(f"Trying fallback provider ({i + 1}): {provider_name}")

            try:
                fallback_llm = LLMFactory.create(fallback_config)
                return fallback_llm.invoke(input_)
            except Exception as fallback_error:
                prior_errors.append(fallback_error)
                logger.warning(f"Fallback provider {provider_name} failed: {fallback_error}")

        # All providers failed
        error_summary = "; ".join(str(e) for e in prior_errors)
        raise Exception(f"All LLM providers failed: {error_summary}")

    async def _ainvoke_fallback_chain(self, input_: Any, prior_errors: list) -> Any:
        """Try fallback providers in sequence (async).

        Args:
            input_: Input to send to LLM
            prior_errors: List of errors from previous attempts

        Returns:
            LLM response from first successful fallback

        Raises:
            Exception: If all providers in chain fail
        """
        for i, fallback_config in enumerate(self._fallback_configs):
            provider_name = fallback_config.provider.value
            logger.info(f"Trying fallback provider ({i + 1}): {provider_name}")

            try:
                fallback_llm = LLMFactory.create(fallback_config)
                return await fallback_llm.ainvoke(input_)
            except Exception as fallback_error:
                prior_errors.append(fallback_error)
                logger.warning(f"Fallback provider {provider_name} failed: {fallback_error}")

        # All providers failed
        error_summary = "; ".join(str(e) for e in prior_errors)
        raise Exception(f"All LLM providers failed: {error_summary}")


def is_rate_limit_error(response: Any) -> bool:
    """Detect if response indicates a rate limit error.

    Args:
        response: HTTP response object or error dict

    Returns:
        True if rate limit detected, False otherwise
    """
    if response is None:
        return False

    if hasattr(response, "status_code"):
        if response.status_code == 429:
            logger.warning("Rate limit detected: HTTP 429")
            return True

    if isinstance(response, dict):
        error = response.get("error", {})
        if isinstance(error, dict):
            code = error.get("code", "")
            if code in ("rate_limit_exceeded", "rate_limit_error", "rate_limited"):
                logger.warning(f"Rate limit detected: error code '{code}'")
                return True

    return False


def get_retry_after_delay(response: Any) -> Optional[int]:
    """Extract Retry-After header value from response.

    Args:
        response: HTTP response object

    Returns:
        Retry-After delay in seconds, or None if not present/invalid
    """
    if response is None or not hasattr(response, "headers"):
        return None

    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return None

    try:
        delay = int(retry_after)
        logger.info(f"Retry-After header found: {delay}s")
        return delay
    except ValueError:
        return None


def get_backoff_delay(attempt: int) -> int:
    """Calculate exponential backoff delay.

    Args:
        attempt: Current retry attempt (0-indexed)

    Returns:
        Delay in seconds (1, 2, 4, 8, 16, 32, 60 capped)
    """
    delay = 2**attempt
    if delay > MAX_BACKOFF_SECONDS:
        delay = MAX_BACKOFF_SECONDS
    return delay
