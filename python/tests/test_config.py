"""Tests for configuration loading and validation."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from codereview.core.config import ConfigError, ConfigLoader


class TestConfigLoader:
    """Test ConfigLoader class."""

    def test_load_yaml_config(self):
        """Test loading valid YAML config."""
        config_content = """
llm:
  provider: openai
  api_key: test-api-key
  model: gpt-4o
  temperature: 0.5
cache:
  ttl_days: 7
  force_refresh: false
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)

        assert config.llm.provider.value == "openai"
        assert config.llm.api_key == "test-api-key"
        assert config.llm.model == "gpt-4o"
        assert config.llm.temperature == 0.5
        assert config.cache.ttl_days == 7
        assert config.cache.force_refresh is False

        os.unlink(f.name)

    def test_env_var_substitution(self):
        """Test ${ENV_VAR} substitution."""
        os.environ["TEST_API_KEY"] = "my-secret-key"
        config_content = """
llm:
  provider: openai
  api_key: ${TEST_API_KEY}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)

        assert config.llm.api_key == "my-secret-key"
        os.unlink(f.name)
        del os.environ["TEST_API_KEY"]

    def test_env_var_with_default(self):
        """Test ${ENV_VAR:-default} substitution."""
        # ENV_VAR not set, should use default
        config_content = """
llm:
  provider: openai
  api_key: ${NON_EXISTENT_VAR:-default-api-key}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)

        assert config.llm.api_key == "default-api-key"
        os.unlink(f.name)

    def test_env_var_with_empty_default(self):
        """Test ${ENV_VAR:-} with empty default."""
        os.environ["TEST_KEY"] = ""
        config_content = """
llm:
  provider: openai
  api_key: ${TEST_KEY:-fallback-key}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)

        # ENV_VAR is set to empty string, so empty string is used (not default)
        assert config.llm.api_key == ""
        os.unlink(f.name)
        del os.environ["TEST_KEY"]

    def test_nested_env_var_substitution(self):
        """Test nested env var substitution in lists and dicts."""
        os.environ["PROVIDER_VAR"] = "anthropic"
        os.environ["API_KEY_VAR"] = "secret-key"
        config_content = """
llm:
  provider: ${PROVIDER_VAR}
  api_key: ${API_KEY_VAR}
critical_paths:
  - src/auth
  - src/payment
exclude_patterns:
  - "*.test.ts"
  - "vendor/**"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)

        assert config.llm.provider.value == "anthropic"
        assert config.llm.api_key == "secret-key"
        assert "src/auth" in config.critical_paths
        assert "*.test.ts" in config.exclude_patterns
        os.unlink(f.name)
        del os.environ["PROVIDER_VAR"]
        del os.environ["API_KEY_VAR"]

    def test_invalid_yaml_syntax(self):
        """Test invalid YAML syntax raises ConfigError."""
        config_content = """
llm:
  provider: openai
  api_key: test
  invalid yaml: content: here
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            with pytest.raises(ConfigError) as exc_info:
                ConfigLoader.load(f.name)
            assert "Invalid YAML" in str(exc_info.value)
            assert exc_info.value.field_name is None
        os.unlink(f.name)

    def test_missing_required_fields(self):
        """Test missing required fields raises ValidationError wrapped in ConfigError."""
        config_content = """
llm:
  provider: openai
  # missing api_key
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            with pytest.raises(ConfigError) as exc_info:
                ConfigLoader.load(f.name)
            assert "Invalid configuration" in str(exc_info.value)
            assert exc_info.value.field_name is None
        os.unlink(f.name)

    def test_missing_llm_section(self):
        """Test missing LLM section raises error."""
        config_content = """
cache:
  ttl_days: 7
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            with pytest.raises(ConfigError) as exc_info:
                ConfigLoader.load(f.name)
            assert "Invalid configuration" in str(exc_info.value)
        os.unlink(f.name)

    def test_custom_prompt_path_validation_missing(self):
        """Test custom prompt path validation when file missing."""
        config_content = """
llm:
  provider: openai
  api_key: test-key
custom_prompt_path: /nonexistent/path/prompt.template
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)
            errors = ConfigLoader.validate_for_providers(config)
            assert any("Custom prompt file not found" in err for err in errors)
        os.unlink(f.name)

    def test_custom_prompt_path_validation_exists(self):
        """Test custom prompt path validation when file exists."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".template", delete=False) as f:
            f.write("Custom prompt content")
            prompt_path = f.name

        config_content = f"""
llm:
  provider: openai
  api_key: test-key
custom_prompt_path: {prompt_path}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)
            errors = ConfigLoader.validate_for_providers(config)
            assert not any("Custom prompt file not found" in err for err in errors)
        os.unlink(prompt_path)
        os.unlink(f.name)

    def test_config_error_contains_field_name(self):
        """Test ConfigError has field_name attribute."""
        error = ConfigError("Test error", field_name="llm.api_key")
        assert error.field_name == "llm.api_key"
        assert str(error) == "Test error"

    def test_config_error_without_field_name(self):
        """Test ConfigError without field_name."""
        error = ConfigError("Test error")
        assert error.field_name is None

    def test_empty_config_file(self):
        """Test empty config file raises ConfigError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            with pytest.raises(ConfigError) as exc_info:
                ConfigLoader.load(f.name)
            assert "Empty configuration file" in str(exc_info.value)
        os.unlink(f.name)

    def test_config_file_not_found(self):
        """Test missing config file raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            ConfigLoader.load("/nonexistent/path/config.yaml")
        assert "Config file not found" in str(exc_info.value)

    def test_validate_for_providers_invalid_provider(self):
        """Test that invalid provider raises ConfigError during load."""
        config_content = """
llm:
  provider: invalid_provider
  api_key: test-key
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            # Pydantic validates enum values before validate_for_providers is called
            with pytest.raises(ConfigError) as exc_info:
                ConfigLoader.load(f.name)
            # Error should indicate invalid provider
            assert "Invalid configuration" in str(exc_info.value)
        os.unlink(f.name)

    def test_validate_for_providers_missing_api_key(self):
        """Test validation catches missing API key."""
        config_content = """
llm:
  provider: openai
  api_key: ""
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)
            errors = ConfigLoader.validate_for_providers(config)
            assert any("API key is required" in err for err in errors)
        os.unlink(f.name)

    def test_validate_for_providers_valid_config(self):
        """Test validation passes for valid config."""
        config_content = """
llm:
  provider: openai
  api_key: test-key
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            config = ConfigLoader.load(f.name)
            errors = ConfigLoader.validate_for_providers(config)
            assert len(errors) == 0
        os.unlink(f.name)

    def test_get_example_config(self):
        """Test get_example_config returns valid YAML string."""
        example = ConfigLoader.get_example_config()
        # Should be valid YAML
        parsed = yaml.safe_load(example)
        assert parsed is not None
        assert "llm" in parsed
        assert "provider" in parsed["llm"]

    def test_load_with_default_path(self):
        """Test loading with default path when file exists in cwd."""
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            config_content = """
llm:
  provider: anthropic
  api_key: test-key
"""
            default_path = Path(tmpdir) / ".codereview-agent.yaml"
            default_path.write_text(config_content)

            try:
                config = ConfigLoader.load()
                assert config.llm.provider.value == "anthropic"
            finally:
                os.chdir(original_cwd)
