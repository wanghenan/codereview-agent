"""Tests for AI Agent-friendly CLI features.

Tests semantic exit codes, structured JSON error output,
schema_version field, and fix_available field.
"""

import json
import os
import subprocess
import sys
import tempfile

from codereview.cli import (
    EXIT_CONFIG_ERROR,
    EXIT_ISSUES_FOUND,
    EXIT_LLM_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_SUCCESS,
    EXIT_UNKNOWN_ERROR,
    SCHEMA_VERSION,
    _classify_error,
    _exit_code_for_error,
    _json_error,
)


class TestSemanticExitCodes:
    """Test exit code constants are defined correctly."""

    def test_exit_codes_are_distinct(self):
        codes = [
            EXIT_SUCCESS,
            EXIT_ISSUES_FOUND,
            EXIT_CONFIG_ERROR,
            EXIT_LLM_ERROR,
            EXIT_NETWORK_ERROR,
            EXIT_UNKNOWN_ERROR,
        ]
        assert len(set(codes)) == 6

    def test_exit_success_is_zero(self):
        assert EXIT_SUCCESS == 0

    def test_schema_version_format(self):
        parts = SCHEMA_VERSION.split(".")
        assert len(parts) == 2
        assert all(p.isdigit() for p in parts)


class TestClassifyError:
    """Test error classification logic."""

    def test_config_error_validation(self):
        err = Exception("Invalid configuration: validation error")
        assert _classify_error(err) == "config_error"

    def test_config_error_api_key(self):
        err = Exception("api_key is required")
        assert _classify_error(err) == "config_error"

    def test_config_error_apikey_combined(self):
        err = Exception("apikey missing from config")
        assert _classify_error(err) == "config_error"

    def test_llm_error_timeout(self):
        err = Exception("Request timeout after 30s")
        assert _classify_error(err) == "llm_error"

    def test_llm_error_rate_limit(self):
        err = Exception("Rate limit exceeded")
        assert _classify_error(err) == "llm_error"

    def test_llm_error_model(self):
        err = Exception("Model not found: gpt-5")
        assert _classify_error(err) == "llm_error"

    def test_llm_error_token(self):
        err = Exception("token limit exceeded")
        assert _classify_error(err) == "llm_error"

    def test_network_error_connection(self):
        err = Exception("Connection refused")
        assert _classify_error(err) == "network_error"

    def test_network_error_github(self):
        err = Exception("GitHub API error")
        assert _classify_error(err) == "network_error"

    def test_network_error_dns(self):
        err = Exception("DNS resolution failed")
        assert _classify_error(err) == "network_error"

    def test_unknown_error(self):
        err = Exception("Something unexpected happened")
        assert _classify_error(err) == "unknown_error"

    def test_case_insensitive(self):
        err = Exception("CONFIG ERROR IN CAPS")
        assert _classify_error(err) == "config_error"


class TestExitCodeForError:
    """Test exit code mapping from errors."""

    def test_config_error_returns_2(self):
        assert _exit_code_for_error(Exception("config error")) == EXIT_CONFIG_ERROR

    def test_llm_error_returns_3(self):
        assert _exit_code_for_error(Exception("timeout")) == EXIT_LLM_ERROR

    def test_network_error_returns_4(self):
        assert _exit_code_for_error(Exception("network failure")) == EXIT_NETWORK_ERROR

    def test_unknown_returns_5(self):
        assert _exit_code_for_error(Exception("random")) == EXIT_UNKNOWN_ERROR


class TestJsonError:
    """Test structured JSON error output."""

    def test_json_mode_outputs_structured_error(self, capsys):
        err = Exception("config validation failed")
        exit_code = _json_error(err, json_output=True)
        captured = capsys.readouterr()
        assert exit_code == EXIT_CONFIG_ERROR

        output = json.loads(captured.err)
        assert output["schema_version"] == SCHEMA_VERSION
        assert output["success"] is False
        assert output["error"]["type"] == "config_error"
        assert "config validation failed" in output["error"]["message"]
        assert output["error"]["exit_code"] == EXIT_CONFIG_ERROR

    def test_json_mode_llm_error(self, capsys):
        err = Exception("LLM rate limit exceeded")
        exit_code = _json_error(err, json_output=True)
        captured = capsys.readouterr()
        assert exit_code == EXIT_LLM_ERROR

        output = json.loads(captured.err)
        assert output["error"]["type"] == "llm_error"

    def test_json_mode_network_error(self, capsys):
        err = Exception("GitHub connection refused")
        exit_code = _json_error(err, json_output=True)
        captured = capsys.readouterr()
        assert exit_code == EXIT_NETWORK_ERROR

        output = json.loads(captured.err)
        assert output["error"]["type"] == "network_error"

    def test_non_json_mode_plain_text(self, capsys):
        err = Exception("Something broke")
        exit_code = _json_error(err, json_output=False)
        captured = capsys.readouterr()
        assert exit_code == EXIT_UNKNOWN_ERROR
        assert "Something broke" in captured.err
        assert "{" not in captured.err

    def test_json_output_goes_to_stderr(self, capsys):
        _json_error(Exception("test error"), json_output=True)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert len(captured.err) > 0


class TestSchemaVersionInOutput:
    """Test that schema_version appears in CLI JSON output."""

    def test_version_flag_returns_zero(self):
        result = subprocess.run(
            [sys.executable, "-m", "codereview.cli", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == EXIT_SUCCESS

    def test_json_error_includes_schema_version(self, capsys):
        _json_error(Exception("config error"), json_output=True)
        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert "schema_version" in output
        assert output["schema_version"] == SCHEMA_VERSION


class TestSemanticExitCodesIntegration:
    """Integration tests for semantic exit codes via subprocess."""

    def test_config_error_returns_exit_2(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "codereview.cli",
                    "--config",
                    os.path.join(tmpdir, "nonexistent_config.yaml"),
                    "--diff",
                    '{"files": []}',
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir,
            )
            assert result.returncode == EXIT_CONFIG_ERROR

    def test_config_error_stderr_mentions_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "nonexistent_config.yaml")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "codereview.cli",
                    "--config",
                    config_path,
                    "--diff",
                    '{"files": []}',
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir,
            )
            stderr_lower = result.stderr.lower()
            assert "config" in stderr_lower or "validation" in stderr_lower
