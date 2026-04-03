"""Tests for GitHub client module."""

import json
import os
import subprocess
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from codereview.core.github_client import (
    GitHubClient,
    PullRequest,
    MergeState,
    MergeMethod,
    DiffFile,
    Approval,
    create_github_client,
)


class TestGitHubClientInit:
    """Test GitHubClient initialization."""

    def test_default_init(self):
        """Test GitHubClient with default parameters."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
            client = GitHubClient()
            assert client.github_token == "test-token"
            assert client.repo_owner is None
            assert client.repo_name is None

    def test_explicit_token(self):
        """Test GitHubClient with explicit token."""
        client = GitHubClient(github_token="explicit-token")
        assert client.github_token == "explicit-token"

    def test_repo_info(self):
        """Test GitHubClient with repo info."""
        client = GitHubClient(repo_owner="owner", repo_name="repo")
        assert client.repo_owner == "owner"
        assert client.repo_name == "repo"


class TestGhAvailable:
    """Test gh CLI availability check."""

    def test_gh_available_true(self):
        """Test when gh CLI is available."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="gh version 2.0.0")
            client = GitHubClient()
            assert client.gh_available is True

    def test_gh_available_false_not_installed(self):
        """Test when gh CLI is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            client = GitHubClient()
            assert client.gh_available is False

    def test_gh_available_false_error(self):
        """Test when gh CLI returns error."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 1)
            client = GitHubClient()
            assert client.gh_available is False

    def test_gh_available_cached(self):
        """Test gh_available is cached after first check."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            client = GitHubClient()
            _ = client.gh_available
            _ = client.gh_available
            assert mock_run.call_count == 1


class TestGetPullRequest:
    """Test get_pull_request method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        client = GitHubClient(repo_owner="test-owner", repo_name="test-repo")
        return client

    @pytest.mark.asyncio
    async def test_get_pr_success_via_gh(self, client):
        """Test successful PR fetch via gh CLI."""
        pr_data = {
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
            "body": "Test body",
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
            )
            client._gh_available = True
            pr = await client.get_pull_request(123)

        assert pr.number == 123
        assert pr.title == "Test PR"
        assert pr.state == MergeState.OPEN
        assert pr.head_sha == "abc123"
        assert pr.base_sha == "def456"
        assert pr.base_branch == "main"
        assert pr.head_branch == "feature"
        assert pr.additions == 100
        assert pr.deletions == 50
        assert pr.changed_files == 5
        assert pr.author == "testuser"
        assert pr.body == "Test body"

    @pytest.mark.asyncio
    async def test_get_pr_failure_via_gh(self, client):
        """Test PR fetch failure via gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: HTTP 404",
            )
            client._gh_available = True
            with pytest.raises(RuntimeError, match="Failed to get PR"):
                await client.get_pull_request(999)

    @pytest.mark.asyncio
    async def test_get_pr_fallback_to_api(self, client):
        """Test fallback to API when gh not available."""
        pr_data = {
            "number": 123,
            "title": "API PR",
            "state": "open",
            "head": {"sha": "head123", "ref": "feature"},
            "base": {"sha": "base456", "ref": "main"},
            "additions": 100,
            "deletions": 50,
            "changed_files": 5,
            "user": {"login": "apiuser"},
            "html_url": "https://github.com/test/repo/pull/123",
            "body": "API body",
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            client._gh_available = False
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(pr_data).encode()
                mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
                mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
                pr = await client.get_pull_request(123)

        assert pr.number == 123
        assert pr.title == "API PR"
        assert pr.author == "apiuser"


class TestGetPrDiff:
    """Test get_pr_diff method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        client = GitHubClient(repo_owner="test-owner", repo_name="test-repo")
        return client

    @pytest.mark.asyncio
    async def test_get_diff_success_via_gh(self, client):
        """Test successful diff fetch via gh CLI."""
        diff_output = """diff --git a/src/main.py b/src/main.py
index 1234567..abcdefg 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1 +1,2 @@
+new line"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=diff_output,
                stderr="",
            )
            client._gh_available = True
            files = await client.get_pr_diff(123)

        assert len(files) == 1
        assert files[0].filename == "src/main.py"
        assert files[0].status == "modified"
        assert files[0].additions == 1
        assert files[0].deletions == 0

    @pytest.mark.asyncio
    async def test_get_diff_empty(self, client):
        """Test empty diff response."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            client._gh_available = True
            files = await client.get_pr_diff(123)

        assert len(files) == 0

    @pytest.mark.asyncio
    async def test_get_diff_failure(self, client):
        """Test diff fetch failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: Not Found",
            )
            client._gh_available = True
            with pytest.raises(RuntimeError, match="Failed to get PR diff"):
                await client.get_pr_diff(999)

    @pytest.mark.asyncio
    async def test_get_diff_new_file(self, client):
        """Test diff for new file."""
        diff_output = """diff --git a/newfile.py b/newfile.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/newfile.py
@@ -0,0 +1,3 @@
+line 1
+line 2
+line 3"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=diff_output,
                stderr="",
            )
            client._gh_available = True
            files = await client.get_pr_diff(123)

        assert len(files) == 1
        assert files[0].filename == "newfile.py"
        assert files[0].status == "modified"
        assert files[0].additions == 3

    @pytest.mark.asyncio
    async def test_get_diff_deleted_file(self, client):
        """Test diff for deleted file."""
        diff_output = """diff --git a/deleted.py b/deleted.py
deleted file mode 100644
index 1234567..0000000"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=diff_output,
                stderr="",
            )
            client._gh_available = True
            files = await client.get_pr_diff(123)

        assert len(files) == 1
        assert files[0].filename == "deleted.py"
        assert files[0].status == "modified"


class TestPostComment:
    """Test post_comment method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        client = GitHubClient(
            repo_owner="test-owner",
            repo_name="test-repo",
            github_token="test-token",
        )
        return client

    @pytest.mark.asyncio
    async def test_post_comment_success_via_gh(self, client):
        """Test successful comment posting via gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            client._gh_available = True
            result = await client.post_comment(123, "Test comment")

        assert result is True

    @pytest.mark.asyncio
    async def test_post_comment_failure_via_gh(self, client):
        """Test comment posting failure via gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error posting comment",
            )
            client._gh_available = True
            result = await client.post_comment(123, "Test comment")

        assert result is False

    @pytest.mark.asyncio
    async def test_post_comment_fallback_to_api(self, client):
        """Test fallback to API when gh not available."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            client._gh_available = False
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_response = MagicMock()
                mock_response.status = 201
                mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
                mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
                result = await client.post_comment(123, "API comment")

        assert result is True

    @pytest.mark.asyncio
    async def test_post_comment_api_failure(self, client):
        """Test comment posting failure via API."""
        import urllib.error

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            client._gh_available = False
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = urllib.error.HTTPError(
                    url="",
                    code=403,
                    msg="Forbidden",
                    hdrs=None,
                    fp=None,
                )
                result = await client.post_comment(123, "Fail comment")

        assert result is False


class TestGetPrApprovals:
    """Test get_pr_approvals method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        client = GitHubClient(repo_owner="test-owner", repo_name="test-repo")
        return client

    @pytest.mark.asyncio
    async def test_get_approvals_success_via_gh(self, client):
        """Test successful approvals fetch via gh CLI."""
        pr_data = {
            "reviews": [
                {
                    "author": {"login": "user1"},
                    "state": "APPROVED",
                    "submittedAt": "2024-01-01T00:00:00Z",
                },
                {
                    "author": {"login": "user2"},
                    "state": "CHANGES_REQUESTED",
                    "submittedAt": "2024-01-02T00:00:00Z",
                },
                {
                    "author": {"login": "user1"},
                    "state": "COMMENTED",
                    "submittedAt": "2024-01-03T00:00:00Z",
                },
            ]
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
            )
            client._gh_available = True
            approvals = await client.get_pr_approvals(123)

        assert len(approvals) == 1
        assert approvals[0].user == "user1"
        assert approvals[0].state == "APPROVED"

    @pytest.mark.asyncio
    async def test_get_approvals_empty(self, client):
        """Test approvals when none exist."""
        pr_data = {"reviews": []}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
            )
            client._gh_available = True
            approvals = await client.get_pr_approvals(123)

        assert len(approvals) == 0

    @pytest.mark.asyncio
    async def test_get_approvals_gh_error(self, client):
        """Test approvals fetch error via gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error",
            )
            client._gh_available = True
            approvals = await client.get_pr_approvals(123)

        assert len(approvals) == 0

    @pytest.mark.asyncio
    async def test_get_approvals_takes_latest_per_user(self, client):
        """Test that only latest approval per user is taken."""
        pr_data = {
            "reviews": [
                {
                    "author": {"login": "user1"},
                    "state": "CHANGES_REQUESTED",
                    "submittedAt": "2024-01-01T00:00:00Z",
                },
                {
                    "author": {"login": "user1"},
                    "state": "APPROVED",
                    "submittedAt": "2024-01-02T00:00:00Z",
                },
            ]
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
            )
            client._gh_available = True
            approvals = await client.get_pr_approvals(123)

        assert len(approvals) == 1
        assert approvals[0].user == "user1"
        assert approvals[0].state == "APPROVED"


class TestMergePr:
    """Test merge_pr method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        client = GitHubClient(repo_owner="test-owner", repo_name="test-repo")
        return client

    @pytest.mark.asyncio
    async def test_merge_squash_success(self, client):
        """Test successful squash merge via gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            client._gh_available = True
            result = await client.merge_pr(123, MergeMethod.SQUASH)

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "--squash" in call_args

    @pytest.mark.asyncio
    async def test_merge_merge_success(self, client):
        """Test successful merge (non-squash) via gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            client._gh_available = True
            result = await client.merge_pr(123, MergeMethod.MERGE)

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "--merge" in call_args

    @pytest.mark.asyncio
    async def test_merge_rebase_success(self, client):
        """Test successful rebase merge via gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            client._gh_available = True
            result = await client.merge_pr(123, MergeMethod.REBASE)

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "--rebase" in call_args

    @pytest.mark.asyncio
    async def test_merge_with_title_and_message(self, client):
        """Test merge with custom commit title and message."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            client._gh_available = True
            result = await client.merge_pr(
                123,
                MergeMethod.SQUASH,
                commit_title="Custom Title",
                commit_message="Custom Message",
            )

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "--title" in call_args
        assert "Custom Title" in call_args
        assert "--body" in call_args
        assert "Custom Message" in call_args

    @pytest.mark.asyncio
    async def test_merge_failure(self, client):
        """Test merge failure via gh CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Merge conflict",
            )
            client._gh_available = True
            with pytest.raises(RuntimeError, match="Failed to merge PR"):
                await client.merge_pr(123)

    @pytest.mark.asyncio
    async def test_merge_via_api(self, client):
        """Test merge via API fallback."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            client._gh_available = False
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_response = MagicMock()
                mock_response.status = 200
                mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
                mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
                result = await client.merge_pr(123, MergeMethod.SQUASH)

        assert result is True


class TestGetCheckRuns:
    """Test get_check_runs method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        client = GitHubClient(repo_owner="test-owner", repo_name="test-repo")
        return client

    @pytest.mark.asyncio
    async def test_get_check_runs_success(self, client):
        """Test successful check runs fetch."""
        pr_data = {
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
            "body": "",
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
            )
            client._gh_available = True
            check_runs = await client.get_check_runs(123)

        assert isinstance(check_runs, list)

    @pytest.mark.asyncio
    async def test_get_check_runs_with_sha(self, client):
        """Test get_check_runs with explicit sha parameter."""
        check_run_data = '{"name":"test","status":"completed","conclusion":"success"}'
        pr_data = {
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
            "body": "",
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
            )
            client._gh_available = True
            check_runs = await client.get_check_runs(123, sha="explicit-sha")

        assert mock_run.call_count >= 1


class TestTokenValidation:
    """Test token validation."""

    def test_empty_token(self):
        """Test client with empty token."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
            client = GitHubClient(github_token="")
            assert client.github_token == ""

    def test_none_token(self):
        """Test client with None token (falls back to env)."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}):
            client = GitHubClient(github_token=None)
            assert client.github_token == "env-token"

    def test_missing_token_and_env(self):
        """Test client when token and env are missing."""
        with patch.dict(os.environ, {}, clear=True):
            client = GitHubClient()
            assert client.github_token == ""


class TestGhCliFallback:
    """Test gh CLI fallback behavior."""

    @pytest.mark.asyncio
    async def test_gh_available_uses_gh(self):
        """Test that gh CLI is used when available."""
        client = GitHubClient(repo_owner="owner", repo_name="repo")

        pr_data = {
            "number": 1,
            "title": "PR",
            "state": "open",
            "headRefOid": "abc",
            "baseRefOid": "def",
            "baseRefName": "main",
            "headRefName": "feature",
            "additions": 10,
            "deletions": 5,
            "changedFiles": 2,
            "author": {"login": "user"},
            "url": "https://github.com/test/repo/pull/1",
            "body": None,
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
            )
            client._gh_available = True
            await client.get_pull_request(1)

        assert mock_run.call_count == 1

    @pytest.mark.asyncio
    async def test_gh_unavailable_uses_api(self):
        """Test that API is used when gh CLI is unavailable."""
        client = GitHubClient(repo_owner="owner", repo_name="repo")

        pr_data = {
            "number": 1,
            "title": "PR",
            "state": "open",
            "head": {"sha": "abc", "ref": "feature"},
            "base": {"sha": "def", "ref": "main"},
            "additions": 10,
            "deletions": 5,
            "changed_files": 2,
            "user": {"login": "user"},
            "html_url": "https://github.com/test/repo/pull/1",
            "body": None,
        }

        client._gh_available = False
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(pr_data).encode()
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            pr = await client.get_pull_request(1)

        assert pr.title == "PR"
        assert pr.author == "user"


class TestLargeDiffHandling:
    """Test large diff handling."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        client = GitHubClient(repo_owner="test-owner", repo_name="test-repo")
        return client

    @pytest.mark.asyncio
    async def test_large_diff_parsing(self, client):
        """Test parsing a large diff output."""
        diff_parts = []
        for i in range(100):
            diff_parts.append(
                f"""diff --git a/file{i}.py b/file{i}.py
index 0000000..1111111 100644
--- a/file{i}.py
+++ b/file{i}.py
@@ -1,1 +1,2 @@
-old
+new line 1
+new line 2"""
            )
        large_diff = "\n".join(diff_parts)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=large_diff,
                stderr="",
            )
            client._gh_available = True
            files = await client.get_pr_diff(123)

        assert len(files) == 100

    @pytest.mark.asyncio
    async def test_diff_with_special_filenames(self, client):
        """Test diff with special characters in filenames."""
        diff_output = """diff --git a/path/with spaces/file.py b/path/with spaces/file.py
index 1234567..abcdefg 100644
--- a/path/with spaces/file.py
+++ b/path/with spaces/file.py
@@ -1,3 +1,4 @@
+line"""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=diff_output,
                stderr="",
            )
            client._gh_available = True
            files = await client.get_pr_diff(123)

        assert len(files) == 1
        assert "path/with spaces/file.py" in files[0].filename


class TestRateLimitHandling:
    """Test rate limit response handling."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        client = GitHubClient(repo_owner="test-owner", repo_name="test-repo")
        return client

    @pytest.mark.asyncio
    async def test_api_rate_limit_error(self, client):
        """Test handling of API rate limit error."""
        import urllib.error

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            client._gh_available = False
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = urllib.error.HTTPError(
                    url="",
                    code=403,
                    msg="rate limit exceeded",
                    hdrs={"X-RateLimit-Remaining": "0"},
                    fp=None,
                )
                with pytest.raises(RuntimeError, match="403"):
                    await client.get_pull_request(123)


class TestParseGitDiff:
    """Test _parse_git_diff method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked repo info."""
        return GitHubClient()

    def test_parse_multiple_files(self, client):
        """Test parsing diff with multiple files."""
        diff_output = """diff --git a/file1.py b/file1.py
index 111..222 100644
--- a/file1.py
+++ b/file1.py
@@ -1,2 +1,3 @@
 line1
+added
 line2
diff --git a/file2.py b/file2.py
index 333..444 100644
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,2 @@
-old
+new1
+new2"""

        files = client._parse_git_diff(diff_output)

        assert len(files) == 2
        assert files[0].filename == "file1.py"
        assert files[0].additions == 1
        assert files[0].deletions == 0
        assert files[1].filename == "file2.py"
        assert files[1].additions == 2
        assert files[1].deletions == 1

    def test_parse_renamed_file(self, client):
        """Test parsing diff with renamed file."""
        diff_output = """diff --git a/old_name.py b/new_name.py
rename from old_name.py
rename to new_name.py"""

        files = client._parse_git_diff(diff_output)

        assert len(files) == 1
        assert files[0].filename == "new_name.py"
        assert files[0].status == "renamed"
        assert files[0].previous_filename == "old_name.py"

    def test_parse_empty_diff(self, client):
        """Test parsing empty diff."""
        files = client._parse_git_diff("")
        assert len(files) == 0

    def test_parse_binary_file(self, client):
        """Test parsing diff with binary file indication."""
        diff_output = """diff --git a/binary.bin b/binary.bin
new file mode 100644
index 0000000..1111111
Binary files /dev/null and b/binary.bin differ"""

        files = client._parse_git_diff(diff_output)

        assert len(files) == 1
        assert files[0].filename == "binary.bin"
        assert files[0].status == "modified"


class TestCreateGithubClient:
    """Test create_github_client factory function."""

    def test_create_with_defaults(self):
        """Test creating client with defaults."""
        client = create_github_client()
        assert isinstance(client, GitHubClient)

    def test_create_with_repo_info(self):
        """Test creating client with repo info."""
        client = create_github_client(
            repo_owner="custom-owner",
            repo_name="custom-repo",
            github_token="custom-token",
        )
        assert client.repo_owner == "custom-owner"
        assert client.repo_name == "custom-repo"
        assert client.github_token == "custom-token"
