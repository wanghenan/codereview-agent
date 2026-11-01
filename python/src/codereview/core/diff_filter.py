"""Admission filtering for review diffs.

The reviewer should not pay for files it can never usefully review (binaries,
generated code, lock files, configured excludes), and it should stay inside a
predictable token budget on large pull requests. This module implements that
admission layer as a pure function over :class:`~codereview.models.DiffEntry`
objects, so it can be unit-tested without an LLM or a git checkout.

Rules are applied in this order (first match wins):

1. binary or non-code extension;
2. generated-file patterns (minified bundles, protobuf Go, ``*_generated.*``,
   plus paths marked ``linguist-generated`` in ``.gitattributes``);
3. dependency lock files;
4. user-supplied ``extra_skip_patterns`` (gitignore semantics);
5. per-file token budget;
6. total token budget;
7. ``max_files`` truncation.

Both stages 6 and 7 rank candidates by ``additions + deletions`` descending,
then path ascending, and drop from the tail. That makes the outcome
deterministic: the same entries always produce the same kept set regardless of
the order in which GitHub returns them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from codereview.core.path_matcher import ExcludeMatcher
from codereview.models import DiffEntry, SkipRecord

logger = logging.getLogger(__name__)

# Skip reasons. Kept as plain strings (rather than an enum) because they are
# surfaced verbatim in the PR summary and should stay cheap to serialize.
SKIP_BINARY = "binary"
SKIP_NON_CODE = "non-code"
SKIP_GENERATED = "generated"
SKIP_LOCK_FILE = "lock-file"
SKIP_EXCLUDED = "excluded"
SKIP_OVER_BUDGET = "over-budget"
SKIP_MAX_FILES = "max-files"

# Extensions whose contents are not text we can meaningfully review.
BINARY_EXTENSIONS = frozenset(
    {
        ".7z",
        ".a",
        ".ai",
        ".avi",
        ".bin",
        ".bmp",
        ".bz2",
        ".class",
        ".db",
        ".dll",
        ".dylib",
        ".ear",
        ".eot",
        ".eps",
        ".exe",
        ".flac",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".lib",
        ".m4a",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".npy",
        ".npz",
        ".o",
        ".obj",
        ".ogg",
        ".otf",
        ".parquet",
        ".pdf",
        ".pkl",
        ".png",
        ".psd",
        ".pyc",
        ".pyo",
        ".rar",
        ".so",
        ".sqlite",
        ".sqlite3",
        ".tar",
        ".tgz",
        ".tif",
        ".tiff",
        ".ttf",
        ".war",
        ".wasm",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".xz",
        ".zip",
    }
)

# Text extensions that are documentation/data rather than reviewable code.
# Config formats (JSON, YAML, TOML) are deliberately *not* listed: changing a
# config file is often the most important part of a PR.
NON_CODE_EXTENSIONS = frozenset(
    {
        ".adoc",
        ".csv",
        ".log",
        ".markdown",
        ".md",
        ".mdx",
        ".rst",
        ".svg",
        ".tsv",
        ".txt",
    }
)

# Exact basenames of dependency lock files. Compared case-insensitively.
LOCK_FILES = frozenset(
    {
        "cargo.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "yarn.lock",
    }
)


@dataclass
class FilterConfig:
    """Tunable limits for the diff admission layer.

    Attributes:
        max_tokens_per_file: Drop a single file whose estimated patch size
            exceeds this many tokens.
        max_tokens_total: Drop the lowest-churn files until the kept patches
            fit within this many tokens.
        max_files: Keep at most this many files, again dropping the
            lowest-churn files first.
        extra_skip_patterns: Additional gitignore-style patterns; a matching
            path is skipped before any budget accounting.
    """

    max_tokens_per_file: int = 12000
    max_tokens_total: int = 120000
    max_files: int = 40
    extra_skip_patterns: list[str] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    """Estimate LLM tokens from a string using a ``len(text) / 4`` heuristic.

    This is deliberately dependency-free: the admission layer only needs a
    cheap, deterministic upper-bound-ish estimate, not a real tokenizer. The
    four-characters-per-token rule is the usual rough average for English and
    source code. Integer division is used, so the estimate never exceeds
    ``len(text) / 4`` and shorter-than-four-character snippets cost 0 tokens.

    Args:
        text: Text that would be sent to the model (typically a diff patch).

    Returns:
        Estimated token count; ``0`` for an empty string.
    """
    return len(text) // 4


def _load_linguist_generated_patterns() -> list[str]:
    """Read ``linguist-generated`` path patterns from ``./.gitattributes``.

    Only the repository-root ``.gitattributes`` in the current working
    directory is read. A missing or unreadable file simply disables this
    check, which keeps the filter cheap and means it never fails a review.

    Returns:
        Gitignore-style patterns marked ``linguist-generated`` (or
        ``linguist-generated=true``). Explicit ``-linguist-generated`` /
        ``!linguist-generated`` / ``=false`` attributes are ignored.
    """
    attributes = Path(".gitattributes")
    try:
        if not attributes.is_file():
            return []
        text = attributes.read_text(encoding="utf-8")
    except OSError:
        # "If cheap to read, otherwise skip this check" - a permission error
        # or race must not break admission filtering.
        return []

    patterns: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        pattern, attrs = parts[0], parts[1:]
        generated = False
        for attr in attrs:
            if attr in ("linguist-generated", "linguist-generated=true"):
                generated = True
            elif attr in (
                "-linguist-generated",
                "!linguist-generated",
                "linguist-generated=false",
            ):
                generated = False

        if generated:
            patterns.append(pattern)

    return patterns


def _generated_detail(filename: str, matcher: ExcludeMatcher) -> Optional[str]:
    """Return why ``filename`` looks generated, or ``None`` if it does not."""
    basename = Path(filename).name.lower()

    if ".min." in basename:
        return "minified bundle (*.min.*)"
    if basename.endswith(".pb.go"):
        return "protobuf-generated Go file (*.pb.go)"
    if "_generated." in basename:
        return "generated source (*_generated.*)"
    if matcher.matches(filename):
        return "marked linguist-generated in .gitattributes"
    return None


def _pre_budget_skip(
    filename: str,
    exclude_matcher: ExcludeMatcher,
    generated_matcher: ExcludeMatcher,
) -> Optional[tuple[str, str]]:
    """Apply every non-budget rule to one filename.

    Args:
        filename: Repository-relative path with forward slashes.
        exclude_matcher: Compiled ``extra_skip_patterns``.
        generated_matcher: Compiled ``linguist-generated`` patterns.

    Returns:
        ``(reason, detail)`` if the file should be skipped, else ``None``.
    """
    extension = Path(filename).suffix.lower()
    if extension in BINARY_EXTENSIONS:
        return SKIP_BINARY, f"binary extension {extension}"
    if extension in NON_CODE_EXTENSIONS:
        return SKIP_NON_CODE, f"non-code extension {extension}"

    generated = _generated_detail(filename, generated_matcher)
    if generated is not None:
        return SKIP_GENERATED, generated

    basename = Path(filename).name.lower()
    if basename in LOCK_FILES:
        return SKIP_LOCK_FILE, f"dependency lock file {basename}"

    if exclude_matcher.matches(filename):
        return SKIP_EXCLUDED, "matches extra_skip_patterns"

    return None


def _rank_key(item: tuple[int, DiffEntry, int]) -> tuple[int, str, int]:
    """Sort by churn descending, then path ascending, then input index.

    The index is only a tie-breaker for the pathological case of duplicate
    paths with identical churn, so the result is always deterministic.
    """
    index, entry, _tokens = item
    return (-(entry.additions + entry.deletions), entry.filename, index)


def filter_entries(
    entries: list[DiffEntry], config: FilterConfig
) -> tuple[list[DiffEntry], list[SkipRecord]]:
    """Split diff entries into reviewable and skipped sets.

    Args:
        entries: Diff entries as returned by the GitHub/git diff parser.
        config: Admission limits and extra skip patterns.

    Returns:
        ``(kept, skipped)`` where ``kept`` preserves the input order of the
        entries that survived every rule, and ``skipped`` is one
        :class:`~codereview.models.SkipRecord` per dropped entry, also in
        input order. Budget selection itself is deterministic (see the module
        docstring).
    """
    exclude_matcher = ExcludeMatcher(list(config.extra_skip_patterns))
    generated_matcher = ExcludeMatcher(_load_linguist_generated_patterns())

    skipped_by_index: dict[int, SkipRecord] = {}
    candidates: list[tuple[int, DiffEntry, int]] = []

    for index, entry in enumerate(entries):
        pre_budget = _pre_budget_skip(entry.filename, exclude_matcher, generated_matcher)
        if pre_budget is not None:
            reason, detail = pre_budget
            skipped_by_index[index] = SkipRecord(
                filename=entry.filename, reason=reason, detail=detail
            )
            continue

        tokens = estimate_tokens(entry.patch or "")
        if tokens > config.max_tokens_per_file:
            skipped_by_index[index] = SkipRecord(
                filename=entry.filename,
                reason=SKIP_OVER_BUDGET,
                detail=(f"~{tokens} tokens exceeds per-file limit {config.max_tokens_per_file}"),
            )
            continue

        candidates.append((index, entry, tokens))

    # Total token budget: keep the highest-churn files and drop from the tail.
    ranked = sorted(candidates, key=_rank_key)
    total_tokens = sum(tokens for _index, _entry, tokens in ranked)
    while ranked and total_tokens > config.max_tokens_total:
        index, entry, tokens = ranked.pop()
        total_tokens -= tokens
        skipped_by_index[index] = SkipRecord(
            filename=entry.filename,
            reason=SKIP_OVER_BUDGET,
            detail=(
                f"dropped to stay within total token budget "
                f"(~{total_tokens + tokens} > {config.max_tokens_total})"
            ),
        )

    # File-count cap, using the same deterministic ranking.
    while ranked and len(ranked) > config.max_files:
        index, entry, _tokens = ranked.pop()
        skipped_by_index[index] = SkipRecord(
            filename=entry.filename,
            reason=SKIP_MAX_FILES,
            detail=f"dropped to stay within max_files={config.max_files}",
        )

    kept = [entry for index, entry in enumerate(entries) if index not in skipped_by_index]
    skipped = [skipped_by_index[index] for index in sorted(skipped_by_index)]
    return kept, skipped
