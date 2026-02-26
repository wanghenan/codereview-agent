"""Configuration loader for CodeReview Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from codereview.models import (
    Config,
    ConfigCache,
    ConfigLLM,
    LLMProvider,
    OutputConfig,
)


class ConfigError(Exception):
    """Configuration error."""

    pass


class ConfigLoader:
    """Load and validate configuration from YAML file."""

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Config:
        """Load configuration from file.

        Args:
            config_path: Path to config file. If None, looks for
                        .codereview-agent.yaml in current directory.

        Returns:
            Validated configuration

        Raises:
            ConfigError: If configuration is invalid
        """
        if config_path is None:
            config_path = Path.cwd() / ".codereview-agent.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML: {e}")

        if not data:
            raise ConfigError("Empty configuration file")

        # Resolve environment variables
        data = cls._resolve_env_vars(data)

        try:
            return Config(**data)
        except ValidationError as e:
            raise ConfigError(f"Invalid configuration: {e}")

    @classmethod
    def _resolve_env_vars(cls, data: dict) -> dict:
        """Resolve environment variables in config values.

        Supports ${VAR_NAME} and ${VAR_NAME:-default} syntax.
        """
        import re

        pattern = r"\$\{([^}:]+)(?::-(.*?))?\}"

        def replace(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            return os.environ.get(var_name, default or "")

        def recursive_replace(obj: dict | list | str) -> dict | list | str:
            if isinstance(obj, dict):
                return {k: recursive_replace(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [recursive_replace(item) for item in obj]
            elif isinstance(obj, str):
                return re.sub(pattern, replace, obj)
            return obj

        return recursive_replace(data)

    @classmethod
    def get_example_config(cls) -> str:
        """Get example configuration as YAML string."""
        return """# CodeReview Agent Configuration
# Learn more: https://github.com/your-org/codereview-agent

# LLM Configuration (required)
llm:
  provider: openai  # openai | anthropic | zhipu | minimax | qwen | deepseek
  apiKey: ${OPENAI_API_KEY}  # Supports environment variables
  model: gpt-4o  # Optional, defaults to provider's best model
  # baseUrl: ""  # Optional, for custom API endpoints

# Critical paths - files in these directories are considered high risk
criticalPaths:
  - src/auth
  - src/payment
  - src/admin

# Exclude patterns - files matching these will be skipped
excludePatterns:
  - "*.test.ts"
  - "*.spec.ts"
  - "vendor/**"
  - "node_modules/**"

# Cache configuration
cache:
  ttl: 7  # Cache validity in days (1-30)
  forceRefresh: false  # Force cache refresh

# Output configuration
output:
  prComment: true  # Post comment on PR
  reportPath: .codereview-agent/output  # Where to save reports
  reportFormat: markdown  # markdown | json | both

# Custom prompt (optional)
# customPrompt: ./custom-prompt.template
"""

    @classmethod
    def validate_for_providers(cls, config: Config) -> list[str]:
        """Validate configuration for all supported providers.

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Check provider
        try:
            LLMProvider(config.llm.provider)
        except ValueError:
            errors.append(f"Invalid provider: {config.llm.provider}")

        # Check API key
        if not config.llm.api_key:
            errors.append("API key is required")

        # Validate paths
        if config.custom_prompt_path:
            path = Path(config.custom_prompt_path)
            if not path.exists():
                errors.append(f"Custom prompt file not found: {path}")

        return errors
