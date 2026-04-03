"""Shared pytest fixtures for CodeReview Agent tests."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from codereview.models import (
    CacheInfo,
    Config,
    ConfigCache,
    ConfigLLM,
    DiffEntry,
    DiffResult,
    FileIssue,
    FileReview,
    LLMProvider,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
)


@pytest.fixture
def mock_llm_response() -> dict[str, Any]:
    """Return a sample LLM JSON response for testing.

    Returns a dictionary representing a typical LLM response structure
    used in code review analysis.

    Returns:
        dict: Sample LLM JSON response with review conclusions and file reviews.
    """
    return {
        "conclusion": "can_submit",
        "confidence": 85.0,
        "summary": "Code review passed with minor suggestions",
        "files_reviewed": [
            {
                "file_path": "src/main.py",
                "risk_level": "low",
                "changes": "+20, -5",
                "issues": [
                    {
                        "file_path": "src/main.py",
                        "line_number": 42,
                        "risk_level": "low",
                        "description": "Consider using a named constant instead of magic number",
                        "suggestion": "Define a constant like MAX_RETRIES = 3",
                    }
                ],
            }
        ],
    }


@pytest.fixture
def sample_diff_entry() -> DiffEntry:
    """Return a sample DiffEntry for testing.

    Creates a typical DiffEntry representing a modified Python file
    with additions and a patch.

    Returns:
        DiffEntry: Sample diff entry with patch content.
    """
    return DiffEntry(
        filename="src/main.py",
        status="modified",
        additions=50,
        deletions=10,
        patch="""diff --git a/src/main.py b/src/main.py
index 1234567..abcdefg 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,5 +1,6 @@
 import os
+import sys

 def main():
     pass""",
    )


@pytest.fixture
def sample_file_review() -> FileReview:
    """Return a sample FileReview for testing.

    Creates a FileReview with a low-risk rating and one minor issue,
    suitable for typical code review test scenarios.

    Returns:
        FileReview: Sample file review with one low-severity issue.
    """
    issues = [
        FileIssue(
            file_path="src/utils/helper.py",
            line_number=10,
            risk_level=RiskLevel.LOW,
            description="Unused import detected",
            suggestion="Remove the unused 'os' import",
        )
    ]
    return FileReview(
        file_path="src/utils/helper.py",
        risk_level=RiskLevel.LOW,
        changes="+15, -3",
        issues=issues,
    )


@pytest.fixture
def sample_review_result() -> ReviewResult:
    """Return a sample ReviewResult for testing.

    Creates a complete ReviewResult with multiple file reviews,
    suitable for testing review result handling.

    Returns:
        ReviewResult: Sample review result with cache info.
    """
    file_reviews = [
        FileReview(
            file_path="src/main.py",
            risk_level=RiskLevel.LOW,
            changes="+50, -10",
            issues=[],
        ),
        FileReview(
            file_path="src/auth.py",
            risk_level=RiskLevel.MEDIUM,
            changes="+25, -5",
            issues=[
                FileIssue(
                    file_path="src/auth.py",
                    line_number=42,
                    risk_level=RiskLevel.MEDIUM,
                    description="Consider adding input validation",
                    suggestion="Validate user input before processing",
                )
            ],
        ),
    ]
    cache_info = CacheInfo(
        used_cache=True,
        cache_timestamp="2024-01-01T00:00:00Z",
        cache_version="1.0.0",
    )
    return ReviewResult(
        conclusion=ReviewConclusion.CAN_SUBMIT,
        confidence=88.0,
        files_reviewed=file_reviews,
        summary="Code review completed successfully",
        cache_info=cache_info,
    )


@pytest.fixture
def temp_config_file(tmp_path: pytest.fixture) -> str:
    """Create a temporary config YAML file and return its path.

    Creates a temporary YAML configuration file with typical settings
    for testing config loading functionality.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        str: Path to the created temporary config file.
    """
    config_content = {
        "llm": {
            "provider": "openai",
            "api_key": "test-api-key",
            "model": "gpt-4o",
            "temperature": 0.5,
        },
        "cache": {
            "ttl_days": 7,
            "force_refresh": False,
        },
        "critical_paths": ["src/", "lib/"],
        "exclude_patterns": ["*.test.py", "**/node_modules/**"],
    }
    config_file = tmp_path / ".codereview-agent.yaml"
    config_file.write_text(yaml.dump(config_content))
    return str(config_file)


@pytest.fixture
def temp_config_file_with_env(tmp_path: pytest.fixture) -> str:
    """Create a temporary config YAML file with env var substitution.

    Creates a temporary config file that uses environment variable
    substitution for testing the ${ENV_VAR} feature.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        str: Path to the created temporary config file.
    """
    os.environ["TEST_API_KEY"] = "env-secret-key"
    config_content = """
llm:
  provider: openai
  api_key: ${TEST_API_KEY}
  model: gpt-4o
  temperature: 0.7
cache:
  ttl_days: 14
  force_refresh: true
"""
    config_file = tmp_path / ".codereview-agent-env.yaml"
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture
def mock_github_client() -> MagicMock:
    """Return a mock GitHub client for testing.

    Creates a MagicMock configured to behave like a GitHubClient
    with common methods mocked for testing.

    Returns:
        MagicMock: Mocked GitHub client with typical return values.
    """
    mock_client = MagicMock()
    mock_client.repo_owner = "test-owner"
    mock_client.repo_name = "test-repo"
    mock_client.github_token = "test-token"
    mock_client.gh_available = True
    return mock_client


@pytest.fixture
def mock_github_pr_data() -> dict[str, Any]:
    """Return mock GitHub Pull Request data.

    Returns a dictionary representing a typical GitHub PR response
    for testing PR-related functionality.

    Returns:
        dict: Mock PR data with typical fields.
    """
    return {
        "number": 123,
        "title": "Test PR",
        "state": "open",
        "headRefOid": "abc123",
        "baseRefOid": "def456",
        "baseRefName": "main",
        "headRefName": "feature",
        "additions": 100,
        "deletions": 50,
        "changedFiles": 5,
        "author": {"login": "testuser"},
        "url": "https://github.com/test/repo/pull/123",
        "body": "Test PR body",
    }


@pytest.fixture
def sample_llm_config() -> ConfigLLM:
    """Return a sample ConfigLLM for testing.

    Creates a ConfigLLM with OpenAI provider and typical settings
    for testing LLM configuration.

    Returns:
        ConfigLLM: Sample LLM configuration.
    """
    return ConfigLLM(
        provider=LLMProvider.OPENAI,
        api_key="test-api-key",
        model="gpt-4o",
        temperature=0.5,
    )


@pytest.fixture
def sample_config(sample_llm_config: ConfigLLM) -> Config:
    """Return a sample Config for testing.

    Creates a complete Config object with typical settings
    for testing configuration handling.

    Args:
        sample_llm_config: Sample LLM configuration fixture.

    Returns:
        Config: Sample complete configuration.
    """
    return Config(
        llm=sample_llm_config,
        critical_paths=["src/", "lib/"],
        exclude_patterns=["*.test.py"],
        cache=ConfigCache(ttl_days=7, force_refresh=False),
        max_concurrency=5,
        timeout_seconds=30.0,
    )


@pytest.fixture
def sample_diff_result() -> DiffResult:
    """Return a sample DiffResult for testing.

    Creates a DiffResult with multiple file entries representing
    a typical PR diff.

    Returns:
        DiffResult: Sample diff result with multiple files.
    """
    files = [
        DiffEntry(
            filename="src/main.py",
            status="modified",
            additions=50,
            deletions=10,
        ),
        DiffEntry(
            filename="src/auth.py",
            status="added",
            additions=100,
            deletions=0,
        ),
        DiffEntry(
            filename="tests/test_main.py",
            status="modified",
            additions=20,
            deletions=5,
        ),
    ]
    return DiffResult(
        pr_number=123,
        base_sha="abc123",
        head_sha="def456",
        files=files,
    )


@pytest.fixture
def mock_azure_openai_response() -> dict[str, Any]:
    """Return a mock Azure OpenAI response for testing.

    Returns a dictionary representing a typical Azure OpenAI
    response structure.

    Returns:
        dict: Mock Azure OpenAI response.
    """
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "conclusion": "needs_review",
                            "confidence": 45.0,
                            "summary": "High risk changes detected",
                            "files_reviewed": [
                                {
                                    "file_path": "src/security.py",
                                    "risk_level": "high",
                                    "changes": "+100, -20",
                                    "issues": [
                                        {
                                            "file_path": "src/security.py",
                                            "line_number": 50,
                                            "risk_level": "high",
                                            "description": "Potential SQL injection vulnerability",
                                            "suggestion": "Use parameterized queries",
                                        }
                                    ],
                                }
                            ],
                        }
                    )
                }
            }
        ]
    }


@pytest.fixture
def sample_project_context() -> dict[str, Any]:
    """Return a sample project context for testing.

    Creates a dictionary representing typical project metadata
    used in code analysis.

    Returns:
        dict: Sample project context data.
    """
    return {
        "tech_stack": ["python", "fastapi", "postgresql"],
        "language": "python",
        "frameworks": ["FastAPI", "SQLAlchemy"],
        "dependencies": {
            "fastapi": "0.100.0",
            "sqlalchemy": "2.0.0",
        },
        "critical_paths": ["src/api/", "src/core/"],
        "code_style": "pep8",
        "directory_structure": "src/",
        "version": "1.0.0",
        "analyzed_at": "2024-01-01T00:00:00Z",
    }
