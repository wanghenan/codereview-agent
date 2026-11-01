"""Diff acquisition and parsing helpers (git diff output, JSON diff input)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from codereview.models import DiffEntry

logger = logging.getLogger(__name__)


def get_git_diff(branch: str = "main", base_branch: str = None) -> str:
    """Get git diff for current branch vs target branch.

    Args:
        branch: Target branch to compare against (default: main)
        base_branch: Optional base branch (overrides branch if provided)

    Returns:
        Git diff output
    """
    try:
        # Determine the comparison base
        compare_branch = base_branch or branch

        # Try to get diff against the specified branch
        result = subprocess.run(
            ["git", "diff", f"{compare_branch}...", "--", "."],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        if result.returncode != 0:
            # Fallback: try comparing with HEAD
            result = subprocess.run(
                ["git", "diff", "HEAD", "--", "."], capture_output=True, text=True, cwd=Path.cwd()
            )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to get git diff: {result.stderr}")

        return result.stdout
    except Exception as e:
        logger.error(f"Failed to get git diff: {e}")
        raise RuntimeError(f"Failed to get git diff: {e}") from e


def parse_git_diff_to_entries(diff_output: str) -> list[DiffEntry]:
    """Parse git diff output into DiffEntry list.

    Args:
        diff_output: Raw git diff output

    Returns:
        List of DiffEntry objects
    """
    import re

    entries = []
    current_file = None
    current_status = "modified"
    additions = 0
    deletions = 0
    patch_lines = []

    for line in diff_output.split("\n"):
        # Detect new file
        if line.startswith("diff --git"):
            # Save previous file
            if current_file:
                entries.append(
                    DiffEntry(
                        filename=current_file,
                        status=current_status,
                        additions=additions,
                        deletions=deletions,
                        patch="\n".join(patch_lines),
                    )
                )

            # Extract filename
            match = re.match(r"diff --git a/(.*) b/(.*)", line)
            if match:
                current_file = match.group(2)
            current_status = "modified"
            additions = 0
            deletions = 0
            patch_lines = [line]

        elif line.startswith("new file"):
            current_status = "added"
            patch_lines.append(line)

        elif line.startswith("deleted file"):
            current_status = "deleted"
            patch_lines.append(line)

        elif line.startswith("index "):
            patch_lines.append(line)

        elif line.startswith("@@"):
            # Extract stats from hunk header
            match = re.search(r"@@\+.*(\d+)(?:,(\d+))? -(\d+)(?:,(\d+))? @@", line)
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
        entries.append(
            DiffEntry(
                filename=current_file,
                status=current_status,
                additions=additions,
                deletions=deletions,
                patch="\n".join(patch_lines),
            )
        )

    return entries
def _parse_diff(diff_input: str | None) -> list[DiffEntry]:
    """Parse diff input.

    Args:
        diff_input: JSON string or None

    Returns:
        List of diff entries
    """
    if not diff_input:
        # Read from stdin
        try:
            diff_input = sys.stdin.read()
        except Exception:
            logger.warning("Failed to read from stdin")

    if not diff_input:
        logger.warning("No diff input provided")
        return []

    # Try to load as JSON
    try:
        data = json.loads(diff_input)
        if isinstance(data, list):
            return [DiffEntry(**entry) for entry in data]
        elif isinstance(data, dict) and "files" in data:
            return [DiffEntry(**entry) for entry in data["files"]]
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse diff JSON: {diff_input[:100]}...")

    # If it's a path, try to read file
    path = Path(diff_input)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return [DiffEntry(**entry) for entry in data.get("files", data)]
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON file {path}: {e}")
        except Exception as e:
            logger.error(f"Error reading diff file {path}: {e}")
    else:
        logger.warning(
            f"Diff input is not valid JSON and file does not exist: {diff_input[:100]}..."
        )

    return []
