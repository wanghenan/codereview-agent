"""GitHub client for CodeReview Agent.

Supports both GitHub CLI (gh) and PyGithub for maximum compatibility.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MergeMethod(str, Enum):
    """GitHub merge method."""

    SQUASH = "squash"
    MERGE = "merge"
    REBASE = "rebase"


class MergeState(str, Enum):
    """PR merge state."""

    MERGED = "merged"
    CLOSED = "closed"
    OPEN = "open"


@dataclass
class PullRequest:
    """GitHub Pull Request."""

    number: int
    title: str
    state: MergeState
    head_sha: str
    base_sha: str
    base_branch: str
    head_branch: str
    additions: int
    deletions: int
    changed_files: int
    author: str
    url: str
    body: Optional[str] = None


@dataclass
class Approval:
    """GitHub PR approval."""

    user: str
    state: str  # APPROVED, CHANGES_REQUESTED, COMMENT
    submitted_at: str


@dataclass
class DiffFile:
    """A file in the diff."""

    filename: str
    status: str  # added, modified, deleted, renamed
    additions: int
    deletions: int
    patch: Optional[str] = None
    previous_filename: Optional[str] = None  # for renamed files


class GitHubClient:
    """GitHub API client with CLI and API support.

    Uses GitHub CLI (gh) as primary method for CI compatibility,
    with fallback to PyGithub for richer functionality.
    """

    def __init__(
        self,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        github_token: Optional[str] = None,
    ):
        """Initialize GitHub client.

        Args:
            repo_owner: Repository owner (defaults to environment or git remote)
            repo_name: Repository name (defaults to environment or git remote)
            github_token: GitHub token (defaults to GITHUB_TOKEN env var)
        """
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self._gh_available: Optional[bool] = None
        self._repo_info_cached = False

    @property
    def gh_available(self) -> bool:
        """Check if GitHub CLI is available."""
        if self._gh_available is None:
            try:
                result = subprocess.run(
                    ["gh", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self._gh_available = result.returncode == 0
            except (subprocess.SubprocessError, FileNotFoundError):
                self._gh_available = False
        return self._gh_available

    def _get_repo_info(self) -> tuple[str, str]:
        """Get repo info from git remote or environment.

        Returns:
            Tuple of (owner, repo)
        """
        if self.repo_owner and self.repo_name:
            return self.repo_owner, self.repo_name

        # Try to get from git remote
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Parse git@github.com:owner/repo.git or https://github.com/owner/repo.git
                if "github.com" in url:
                    if url.startswith("git@"):
                        # git@github.com:owner/repo.git
                        parts = url.split(":")
                        repo_path = parts[-1].replace(".git", "")
                    else:
                        # https://github.com/owner/repo.git
                        parts = url.split("github.com/")
                        repo_path = parts[-1].replace(".git", "")
                    owner, repo = repo_path.split("/")
                    return owner, repo
        except subprocess.SubprocessError:
            pass

        # Fallback to environment
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if repo and "/" in repo:
            parts = repo.split("/")
            return parts[0], parts[1]

        raise ValueError("Could not determine repository owner/name")

    def _run_gh(self, args: list[str], input_data: Optional[str] = None) -> subprocess.CompletedProcess:
        """Run GitHub CLI command.

        Args:
            args: Command arguments (e.g., ["pr", "view", "123"])
            input_data: Optional stdin input

        Returns:
            CompletedProcess result

        Raises:
            RuntimeError: If gh is not available
        """
        if not self.gh_available:
            raise RuntimeError("GitHub CLI (gh) is not available")

        owner, repo = self._get_repo_info()
        full_args = ["gh", "api", f"repos/{owner}/{repo}"] + args

        env = os.environ.copy()
        if self.github_token:
            env["GH_TOKEN"] = self.github_token
            env["GITHUB_TOKEN"] = self.github_token

        return subprocess.run(
            full_args,
            capture_output=True,
            text=True,
            input=input_data,
            env=env,
            timeout=30,
        )

    async def get_pull_request(self, pr_number: int) -> PullRequest:
        """Get PR information.

        Args:
            pr_number: PR number

        Returns:
            PullRequest object
        """
        owner, repo = self._get_repo_info()

        if self.gh_available:
            return await self._get_pr_via_gh(owner, repo, pr_number)
        else:
            return await self._get_pr_via_api(owner, repo, pr_number)

    async def _get_pr_via_gh(self, owner: str, repo: str, pr_number: int) -> PullRequest:
        """Get PR using GitHub CLI."""
        result = subprocess.run(
            [
                "gh", "pr", "view", str(pr_number),
                "--repo", f"{owner}/{repo}",
                "--json",
                "number,title,state,headRefOid,baseRefOid,baseRefName,headRefName,"
                "additions,deletions,changedFiles,author,url,body",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "GH_TOKEN": self.github_token} if self.github_token else os.environ,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to get PR: {result.stderr}")

        data = json.loads(result.stdout)

        return PullRequest(
            number=data["number"],
            title=data["title"],
            state=MergeState(data["state"]),
            head_sha=data["headRefOid"],
            base_sha=data["baseRefOid"],
            base_branch=data["baseRefName"],
            head_branch=data["headRefName"],
            additions=data["additions"],
            deletions=data["deletions"],
            changed_files=data["changedFiles"],
            author=data["author"]["login"] if data.get("author") else "unknown",
            url=data["url"],
            body=data.get("body"),
        )

    async def _get_pr_via_api(self, owner: str, repo: str, pr_number: int) -> PullRequest:
        """Get PR using GitHub API directly."""
        import urllib.request
        import urllib.error

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Failed to get PR: {e.code} {e.reason}")

        return PullRequest(
            number=data["number"],
            title=data["title"],
            state=MergeState(data["state"]),
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            base_branch=data["base"]["ref"],
            head_branch=data["head"]["ref"],
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
            author=data["user"]["login"],
            url=data["html_url"],
            body=data.get("body"),
        )

    async def get_pr_approvals(self, pr_number: int) -> list[Approval]:
        """Get PR approvals.

        Args:
            pr_number: PR number

        Returns:
            List of Approval objects
        """
        owner, repo = self._get_repo_info()

        if self.gh_available:
            return await self._get_approvals_via_gh(owner, repo, pr_number)
        else:
            return await self._get_approvals_via_api(owner, repo, pr_number)

    async def _get_approvals_via_gh(self, owner: str, repo: str, pr_number: int) -> list[Approval]:
        """Get approvals using GitHub CLI."""
        result = subprocess.run(
            [
                "gh", "pr", "view", str(pr_number),
                "--repo", f"{owner}/{repo}",
                "--json", "reviews",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "GH_TOKEN": self.github_token} if self.github_token else os.environ,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        reviews = data.get("reviews", [])

        # Filter to only APPROVED reviews (take latest per user)
        approvals = []
        seen_users = set()
        for review in reversed(reviews):
            user = review["author"]["login"]
            if user not in seen_users and review["state"] == "APPROVED":
                approvals.append(Approval(
                    user=user,
                    state=review["state"],
                    submitted_at=review["submittedAt"],
                ))
                seen_users.add(user)

        return approvals

    async def _get_approvals_via_api(self, owner: str, repo: str, pr_number: int) -> list[Approval]:
        """Get approvals using GitHub API."""
        import urllib.request
        import urllib.error

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                reviews = json.loads(response.read().decode())
        except urllib.error.HTTPError:
            return []

        # Filter to latest APPROVED per user
        approvals = []
        seen_users = set()
        for review in reversed(reviews):
            user = review["user"]["login"]
            if user not in seen_users and review["state"] == "APPROVED":
                approvals.append(Approval(
                    user=user,
                    state=review["state"],
                    submitted_at=review["submitted_at"],
                ))
                seen_users.add(user)

        return approvals

    async def get_pr_diff(self, pr_number: int) -> list[DiffFile]:
        """Get PR diff files.

        Args:
            pr_number: PR number

        Returns:
            List of DiffFile objects
        """
        owner, repo = self._get_repo_info()

        if self.gh_available:
            return await self._get_diff_via_gh(owner, repo, pr_number)
        else:
            return await self._get_diff_via_api(owner, repo, pr_number)

    async def _get_diff_via_gh(self, owner: str, repo: str, pr_number: int) -> list[DiffFile]:
        """Get diff using GitHub CLI."""
        result = subprocess.run(
            ["gh", "pr", "diff", str(pr_number), "--repo", f"{owner}/{repo}"],
            capture_output=True,
            text=True,
            env={**os.environ, "GH_TOKEN": self.github_token} if self.github_token else os.environ,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to get PR diff: {result.stderr}")

        return self._parse_git_diff(result.stdout)

    async def _get_diff_via_api(self, owner: str, repo: str, pr_number: int) -> list[DiffFile]:
        """Get diff using GitHub API."""
        import urllib.request
        import urllib.error

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                files = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Failed to get PR diff: {e.code} {e.reason}")

        return [
            DiffFile(
                filename=f["filename"],
                status=f["status"],
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=f.get("patch"),
                previous_filename=f.get("previous_filename"),
            )
            for f in files
        ]

    def _parse_git_diff(self, diff_output: str) -> list[DiffFile]:
        """Parse git diff output into DiffFile list.

        Args:
            diff_output: Raw git diff output

        Returns:
            List of DiffFile objects
        """
        import re

        files = []
        current_file = None
        additions = 0
        deletions = 0
        patch_lines = []
        status = "modified"
        previous_filename = None

        for line in diff_output.split("\n"):
            if line.startswith("diff --git"):
                # Save previous file
                if current_file:
                    files.append(DiffFile(
                        filename=current_file,
                        status=status,
                        additions=additions,
                        deletions=deletions,
                        patch="\n".join(patch_lines),
                        previous_filename=previous_filename,
                    ))

                # Parse new file
                match = re.match(r"diff --git a/(.*) b/(.*)", line)
                if match:
                    current_file = match.group(2)
                    if "/dev/null" in line or "new file" in line:
                        status = "added"
                    elif "deleted file" in line:
                        status = "deleted"
                    else:
                        status = "modified"
                additions = 0
                deletions = 0
                patch_lines = []
                previous_filename = None

            elif line.startswith("rename from"):
                match = re.match(r"rename from (.*)", line)
                if match:
                    previous_filename = match.group(1)
                status = "renamed"
                patch_lines.append(line)

            elif line.startswith("@@"):
                # Extract hunk stats
                match = re.search(r"@@\+(\d+)(?:,(\d+))? -(\d+)(?:,(\d+))? @@", line)
                if match:
                    new_count = int(match.group(2) or 1)
                    old_count = int(match.group(4) or 1)
                    additions += new_count
                    deletions += old_count
                patch_lines.append(line)

            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
                patch_lines.append(line)

            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
                patch_lines.append(line)

            elif line.startswith(" "):
                patch_lines.append(line)

        # Save last file
        if current_file:
            files.append(DiffFile(
                filename=current_file,
                status=status,
                additions=additions,
                deletions=deletions,
                patch="\n".join(patch_lines),
                previous_filename=previous_filename,
            ))

        return files

    async def merge_pr(
        self,
        pr_number: int,
        merge_method: MergeMethod = MergeMethod.SQUASH,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> bool:
        """Merge a pull request.

        Args:
            pr_number: PR number
            merge_method: Merge method (squash, merge, or rebase)
            commit_title: Optional title for squash commit
            commit_message: Optional message for squash commit

        Returns:
            True if merge was successful

        Raises:
            RuntimeError: If merge fails
        """
        owner, repo = self._get_repo_info()

        if self.gh_available:
            return await self._merge_via_gh(
                owner, repo, pr_number, merge_method, commit_title, commit_message
            )
        else:
            return await self._merge_via_api(
                owner, repo, pr_number, merge_method, commit_title, commit_message
            )

    async def _merge_via_gh(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        merge_method: MergeMethod,
        commit_title: Optional[str],
        commit_message: Optional[str],
    ) -> bool:
        """Merge using GitHub CLI."""
        # gh pr merge supports: --squash, --merge, --rebase
        method_flag = {
            MergeMethod.SQUASH: "--squash",
            MergeMethod.MERGE: "--merge",
            MergeMethod.REBASE: "--rebase",
        }[merge_method]

        args = [
            "gh", "pr", "merge", str(pr_number),
            "--repo", f"{owner}/{repo}",
            method_flag,
            "--auto",  # Auto-delete branch
        ]

        if commit_title:
            args.extend(["--title", commit_title])
        if commit_message:
            args.extend(["--body", commit_message])

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env={**os.environ, "GH_TOKEN": self.github_token} if self.github_token else os.environ,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to merge PR: {result.stderr}")

        return True

    async def _merge_via_api(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        merge_method: MergeMethod,
        commit_title: Optional[str],
        commit_message: Optional[str],
    ) -> bool:
        """Merge using GitHub API."""
        import urllib.request
        import urllib.error

        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        # Map merge method to GitHub API method
        method_map = {
            MergeMethod.SQUASH: "squash",
            MergeMethod.MERGE: "merge",
            MergeMethod.REBASE: "rebase",
        }

        payload = {
            "merge_method": method_map[merge_method],
        }
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="PUT",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.status == 200
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"Failed to merge PR: {e.code} {e.reason} - {error_body}")

    async def post_comment(self, pr_number: int, body: str) -> bool:
        """Post a comment on a PR.

        Args:
            pr_number: PR number
            body: Comment body (markdown supported)

        Returns:
            True if successful
        """
        owner, repo = self._get_repo_info()

        if self.gh_available:
            result = subprocess.run(
                ["gh", "pr", "comment", str(pr_number),
                 "--repo", f"{owner}/{repo}",
                 "--body", body],
                capture_output=True,
                text=True,
                env={**os.environ, "GH_TOKEN": self.github_token} if self.github_token else os.environ,
                timeout=30,
            )
            return result.returncode == 0
        else:
            return await self._post_comment_via_api(owner, repo, pr_number, body)

    async def _post_comment_via_api(self, owner: str, repo: str, pr_number: int, body: str) -> bool:
        """Post comment using GitHub API."""
        import urllib.request
        import urllib.error

        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        payload = {"body": body}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status in (200, 201)
        except urllib.error.HTTPError as e:
            logger.error(f"Failed to post comment: {e.code} {e.reason}")
            return False

    async def get_check_runs(self, pr_number: int, sha: Optional[str] = None) -> list[dict[str, Any]]:
        """Get check runs for a PR.

        Args:
            pr_number: PR number
            sha: Optional commit SHA (defaults to PR head)

        Returns:
            List of check run objects
        """
        owner, repo = self._get_repo_info()

        # Get PR to find SHA
        pr = await self.get_pull_request(pr_number)
        commit_sha = sha or pr.head_sha

        if self.gh_available:
            result = subprocess.run(
                [
                    "gh", "api",
                    f"/repos/{owner}/{repo}/commits/{commit_sha}/check-runs",
                    "--jq", ".check_runs[]",
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "GH_TOKEN": self.github_token} if self.github_token else os.environ,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout:
                return json.loads(f"[{result.stdout}]")
            return []
        else:
            return await self._get_check_runs_via_api(owner, repo, commit_sha)

    async def _get_check_runs_via_api(self, owner: str, repo: str, sha: str) -> list[dict[str, Any]]:
        """Get check runs using GitHub API."""
        import urllib.request
        import urllib.error

        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs"
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                return data.get("check_runs", [])
        except urllib.error.HTTPError:
            return []


def create_github_client(
    repo_owner: Optional[str] = None,
    repo_name: Optional[str] = None,
    github_token: Optional[str] = None,
) -> GitHubClient:
    """Create a GitHub client instance.

    Args:
        repo_owner: Optional repository owner
        repo_name: Optional repository name
        github_token: Optional GitHub token (defaults to GITHUB_TOKEN env)

    Returns:
        GitHubClient instance
    """
    return GitHubClient(
        repo_owner=repo_owner,
        repo_name=repo_name,
        github_token=github_token,
    )
