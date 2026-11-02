"""S6: stop repeating a finding the PR already carries, and remember dismissals.

Two mechanisms, both deliberately conservative:

* **Dedupe.** A finding is suppressed when the PR already has a comment for the
  same problem. Comments posted by this tool carry a fingerprint marker, so the
  usual case is an exact match across runs. Comments without a marker (hand
  written, or from an older version) fall back to a loose match: same file, a
  line within :data:`LINE_TOLERANCE`, and a similar title.
* **Team memory.** A finding a human reacted 👎 to on a previous PR is
  *down-weighted*, not dropped: the reviewer may still be right about it in a
  different context, so the confidence falls and the ordering pushes it down.

Memory is a plain JSON file at ``.codereview-agent/memory.json`` next to the
repository, readable and editable by hand. Nothing here touches the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from codereview.models import FileIssue, ReviewResult, SkipRecord

logger = logging.getLogger(__name__)

#: Markdown comment appended to every inline comment this tool posts. It is
#: invisible on the PR page and is what makes the next run's dedupe exact.
FINGERPRINT_MARKER = "<!-- cr-agent-fingerprint: {fingerprint} -->"
_MARKER_RE = re.compile(r"<!--\s*cr-agent-fingerprint:\s*([0-9a-f]{16})\s*-->")

#: A loose (marker-less) match allows this many lines of drift.
LINE_TOLERANCE = 3

#: Minimum title similarity for a marker-less comment to count as the same issue.
TITLE_SIMILARITY = 0.6

#: Where dismissals accumulate, relative to the reviewed repository.
MEMORY_PATH = ".codereview-agent/memory.json"

#: Confidence multiplier for a finding dismissed once; it halves per dismissal
#: and never falls below this floor, so a repeated false positive goes quiet
#: without becoming invisible.
DISMISSAL_PENALTY = 0.5
MIN_PENALTY = 0.25

_MARKDOWN_PREFIXES = ("**", "__", "#", "-", "*", ">", "`")


# --------------------------------------------------------------------------- #
# fingerprints
# --------------------------------------------------------------------------- #
def normalise_label(text: str) -> str:
    """Normalise a title for comparison: case, markup and whitespace only."""
    value = (text or "").strip()
    value = value.lstrip("".join(_MARKDOWN_PREFIXES)).strip()
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", " ", value).strip().lower()


def finding_label(issue: FileIssue) -> str:
    """The label a finding is compared by: its title, or the first line of text."""
    title = getattr(issue, "title", None)
    if title and title.strip():
        return normalise_label(title)
    for line in (issue.description or "").splitlines():
        if line.strip():
            return normalise_label(line)
    return ""


def fingerprint(issue: FileIssue) -> str:
    """Stable 16-hex-digit identity for a finding.

    Mirrors :meth:`codereview.models.FileIssue.dedupe_key` — file, line bucket
    and label — but hashes it so the marker stays short on the PR page, and
    normalises the label so markdown emphasis in a title does not create a new
    identity for the same finding.
    """
    file_path, bucket, _ = issue.dedupe_key()
    label = finding_label(issue)
    digest = hashlib.sha256(f"{file_path}|{bucket}|{label}".encode()).hexdigest()
    return digest[:16]


def marker_for(issue: FileIssue) -> str:
    """The comment marker that makes the next run's dedupe exact."""
    return FINGERPRINT_MARKER.format(fingerprint=fingerprint(issue))


# --------------------------------------------------------------------------- #
# dedupe against what the PR already says
# --------------------------------------------------------------------------- #
@dataclass
class AlreadyReportedIndex:
    """Findings a PR already carries, keyed exactly and loosely."""

    fingerprints: set[str] = field(default_factory=set)
    loose: list[tuple[str, int, str]] = field(default_factory=list)

    @classmethod
    def from_comments(cls, comments: list[dict[str, Any]]) -> AlreadyReportedIndex:
        """Build the index from ``list_review_comments`` output."""
        index = cls()
        for comment in comments or []:
            body = str(comment.get("body") or "")
            match = _MARKER_RE.search(body)
            if match:
                index.fingerprints.add(match.group(1))
                continue
            path = str(comment.get("path") or "")
            line = comment.get("line") or comment.get("original_line")
            if not path or not line:
                continue
            label = normalise_label(_first_heading(body))
            if label:
                index.loose.append((path, int(line), label))
        return index

    def matches(self, issue: FileIssue) -> bool:
        """Whether the PR already reports ``issue``."""
        if fingerprint(issue) in self.fingerprints:
            return True
        line = issue.line_number
        if line is None:
            return False
        label = finding_label(issue)
        if not label:
            return False
        for path, known_line, known_label in self.loose:
            if path != issue.file_path or abs(known_line - line) > LINE_TOLERANCE:
                continue
            if known_label == label:
                return True
            if SequenceMatcher(None, known_label, label).ratio() >= TITLE_SIMILARITY:
                return True
        return False


def _first_heading(body: str) -> str:
    """First line of a comment body, which is where the title is rendered."""
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped or _MARKER_RE.search(stripped):
            continue
        return stripped
    return ""


# --------------------------------------------------------------------------- #
# team memory
# --------------------------------------------------------------------------- #
@dataclass
class TeamMemory:
    """Dismissal counts per finding fingerprint."""

    path: Path
    dismissals: dict[str, int] = field(default_factory=dict)
    last_seen: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str) -> TeamMemory:
        """Read the memory file; a missing or broken file means "nothing known"."""
        target = Path(path)
        memory = cls(path=target)
        if not target.is_file():
            return memory
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring unreadable team memory at %s: %s", target, exc)
            return memory
        dismissals = payload.get("dismissals") if isinstance(payload, dict) else None
        if isinstance(dismissals, dict):
            memory.dismissals = {
                str(key): int(value)
                for key, value in dismissals.items()
                if isinstance(value, int) and value > 0
            }
        last_seen = payload.get("last_seen") if isinstance(payload, dict) else None
        if isinstance(last_seen, dict):
            memory.last_seen = {str(k): str(v) for k, v in last_seen.items()}
        return memory

    def bump(self, issue: FileIssue, at: Optional[str] = None) -> int:
        """Record one dismissal of ``issue`` and return its new count."""
        key = fingerprint(issue)
        count = self.dismissals.get(key, 0) + 1
        self.dismissals[key] = count
        self.last_seen[key] = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        return count

    def count(self, issue: FileIssue) -> int:
        """How many times this finding was dismissed before."""
        return self.dismissals.get(fingerprint(issue), 0)

    def penalty(self, issue: FileIssue) -> float:
        """Confidence multiplier for ``issue`` (``1.0`` when never dismissed)."""
        count = self.count(issue)
        if count <= 0:
            return 1.0
        return max(MIN_PENALTY, DISMISSAL_PENALTY**min(count, 3))

    def learn_from_comments(self, comments: list[dict[str, Any]]) -> int:
        """Count dismissals from 👎 reactions on comments this tool posted.

        A comment is a dismissal when its marker resolves to a fingerprint and
        it has more 👎 than 👍. Returns how many findings were bumped.
        """
        learned = 0
        for comment in comments or []:
            match = _MARKER_RE.search(str(comment.get("body") or ""))
            if not match:
                continue
            reactions = comment.get("reactions") or {}
            down = int(reactions.get("-1", 0) or 0)
            up = int(reactions.get("+1", 0) or 0)
            if down <= up:
                continue
            key = match.group(1)
            self.dismissals[key] = self.dismissals.get(key, 0) + 1
            self.last_seen[key] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            learned += 1
        return learned

    def save(self) -> None:
        """Persist the memory file, creating its directory if needed."""
        payload = {
            "version": 1,
            "dismissals": dict(sorted(self.dismissals.items())),
            "last_seen": dict(sorted(self.last_seen.items())),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Could not write team memory to %s: %s", self.path, exc)

    def to_dict(self) -> dict[str, Any]:
        """Serialisable view, handy in tests and reports."""
        return {"dismissals": dict(self.dismissals), "last_seen": dict(self.last_seen)}


# --------------------------------------------------------------------------- #
# applying both to a review result
# --------------------------------------------------------------------------- #
@dataclass
class DedupeReport:
    """What dedupe and memory did to one review."""

    already_reported: int = 0
    downweighted: int = 0
    skipped: list[SkipRecord] = field(default_factory=list)

    def notes(self) -> list[str]:
        """Human-readable summary lines for the review body."""
        notes = []
        if self.already_reported:
            notes.append(f"{self.already_reported} 条 finding 已在 PR 评论中报告过，未重复发布")
        if self.downweighted:
            notes.append(f"{self.downweighted} 条 finding 曾被 👎 驳回，已降低置信度")
        return notes


def apply_dedupe(
    result: ReviewResult,
    index: AlreadyReportedIndex,
    memory: Optional[TeamMemory] = None,
) -> DedupeReport:
    """Drop already-reported findings and down-weight dismissed ones.

    Mutates ``result``: suppressed issues leave ``files_reviewed`` and are
    recorded in ``result.skipped`` so the run stays auditable.
    """
    report = DedupeReport()
    for file_review in result.files_reviewed:
        kept: list[FileIssue] = []
        for issue in file_review.issues:
            if index.matches(issue):
                report.already_reported += 1
                report.skipped.append(
                    SkipRecord(
                        filename=issue.file_path,
                        reason="already-reported",
                        detail=(issue.title or issue.description or "").strip()[:120],
                    )
                )
                continue
            if memory is not None:
                penalty = memory.penalty(issue)
                if penalty < 1.0:
                    issue.confidence = max(0.05, round(issue.confidence * penalty, 2))
                    report.downweighted += 1
            kept.append(issue)
        file_review.issues = kept

    if report.skipped:
        result.skipped.extend(report.skipped)
    if report.already_reported or report.downweighted:
        logger.info(
            "Dedupe: %d already reported, %d down-weighted by team memory",
            report.already_reported,
            report.downweighted,
        )
    return report


__all__ = [
    "AlreadyReportedIndex",
    "DedupeReport",
    "FINGERPRINT_MARKER",
    "LINE_TOLERANCE",
    "MEMORY_PATH",
    "TeamMemory",
    "apply_dedupe",
    "finding_label",
    "fingerprint",
    "marker_for",
    "normalise_label",
]
