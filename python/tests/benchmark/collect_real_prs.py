"""Collect real human review comments from public repos as benchmark drafts.

The injected cases in ``gen_cases.py`` measure "can the reviewer see a defect
that is present in the diff". They say nothing about the harder question the
benchmark has so far skipped: *would a real maintainer have left this comment?*
That requires real corpus, so this script mines merged PRs from public Python
repositories, keeps review comments written by humans on changed lines, and
writes one draft YAML per comment into ``drafts/``.

Drafts are **inputs to curation, not cases**. A comment being public does not
make it a defect: it can be a question, a nit, or wrong. A human (or the agent
driving the benchmark) reads each draft, and only then fills ``expect`` and
promotes it into ``cases/`` with ``kind`` / ``category`` / ``severity`` /
``summary`` / ``why``.

The reviewed code is the code **as it was when the human wrote the comment**,
not the PR's final diff: a maintainer can comment on an intermediate commit
whose defect a later commit already fixed. For every comment the default is
therefore the diff of ``original_commit_id`` (the commit the comment was made
on), applied to that commit's parent. When that commit does not touch the
commented file — reviewers often comment on a file from an earlier push — the
comment's own ``diff_hunk`` is used as a minimal fallback diff, applied to the
PR base. ``--final-diff`` restores the old PR-head slicing.

Usage::

    # 3 repos, up to 40 PRs each, 2 comments per PR
    python -m tests.benchmark.collect_real_prs --repo pydantic/pydantic \
        --repo encode/httpx --repo pallets/flask

    # replay every PR already present in .cache/gh, without new listing calls
    python -m tests.benchmark.collect_real_prs --from-cache

    # re-print the drafts of an earlier run
    python -m tests.benchmark.collect_real_prs --list

GitHub access goes through the ``gh`` CLI (already authenticated for the
project) and every response is cached under ``.cache/gh/``, which is
git-ignored, so re-runs cost no API quota.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

BENCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCH_DIR.parents[2]
DRAFTS_DIR = BENCH_DIR / "drafts"
CACHE_DIR = BENCH_DIR / ".cache" / "gh"

#: Accounts that are not human reviewers. GitHub's app accounts all end with
#: ``[bot]``, but a few services post from user accounts, so both are listed.
BOT_LOGINS = {
    "dependabot",
    "dependabot-preview",
    "pre-commit-ci",
    "github-actions",
    "codecov",
    "sourcery-ai",
    "coderabbitai",
    "sweep-ai",
    "qodo-merge",
    "qodo-merged",
    "pr-agent",
    "codium-ai",
    "mergify",
    "renovate",
}

#: Comment bodies that tend to describe a real defect, rather than taste. Only
#: used for ordering and for dropping "add a test"/"document it" nits; the
#: curator still decides whether a comment is a defect.
DEFECT_PATTERNS = (
    r"\bbug\b",
    r"\bbroken\b",
    r"\bbreaks?\b",
    r"\bcrash",
    r"\bdeadlock",
    r"\bhang",
    r"\bincorrect",
    r"\bleak",
    r"\bmemory",
    r"\brace\b",
    r"\braises?\b",
    r"\bsilent",
    r"\btraceback",
    r"\bunbound",
    r"\bunsafe",
    r"\bwrong",
    r"edge case",
    r"not handled",
    r"off-by-one",
    r"\bregress",
    r"\bsecurity",
    r"\bthread",
    r"\btimeout",
    r"\b(Type|Attribute|Key|Value)Error\b",
    r"\bNone\b",
    r"\binvalid",
    r"\bcorrupt",
    r"\boverflow",
    r"\bexploit",
    r"\binjection",
    r"\bundefined\b",
)

#: Bodies made only of process nits ("add a test", "add docs"): real review
#: comments, but they do not describe a defect a reviewer is expected to find.
NIT_PATTERNS = (
    r"add (a |some )?(unit ?tests?|regression tests?)",
    r"add (some )?tests?",
    r"add documentation",
    r"add docs",
    r"add a changelog",
    r"release notes",
    r"changelog",
    r"unittests?",
    r"\bnit:",
    r"nitpick",
    r"\btypo\b",
)


def _run_gh(args: list[str]) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"gh {' '.join(args)} failed")
    return proc.stdout


def _cached(name: str, fetch) -> Any:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = fetch()
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def gh_json(api_path: str, paginate: bool = False) -> Any:
    """GET a GitHub API path through ``gh``, caching the parsed JSON.

    ``paginate`` uses ``--slurp`` so every page lands in one array; without it
    a busy PR's comments are silently cut off at the first 100.
    """
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", api_path.strip("/"))
    if paginate:
        safe += "-slurp"  # a page-1-only cache entry must not be reused here
    args = ["api"] + (["--paginate", "--slurp"] if paginate else []) + [api_path]
    return _cached(f"{safe}.json", lambda: json.loads(_run_gh(args)))


def gh_text(api_path: str, accept: str) -> str:
    """GET a GitHub API path as text (used for the ``diff`` media type)."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", api_path.strip("/"))
    cached = CACHE_DIR / f"{safe}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    text = _run_gh(["api", "-H", f"Accept: {accept}", api_path])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


def login_of(payload: dict[str, Any]) -> str:
    """Login of the actor, or "" for deleted accounts (``"user": null``)."""
    user = payload.get("user") or {}
    return user.get("login") or ""


def is_bot(login: str) -> bool:
    return login.endswith("[bot]") or login in BOT_LOGINS


def is_bot_user(payload: dict[str, Any]) -> bool:
    """A GitHub actor is a bot if its login says so or its account type does.

    ``Copilot`` (the pull-request reviewer) does not end in ``[bot]`` but has
    ``user.type == "Bot"``; GitHub Apps all use that type.
    """
    user = payload.get("user") or {}
    return is_bot(user.get("login") or "") or user.get("type") == "Bot"


def list_prs(repo: str, limit: int) -> list[dict[str, Any]]:
    return gh_json(f"repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page={limit}")


def search_prs(repo: str, min_comments: int, limit: int) -> list[dict[str, Any]]:
    """Find discussion-heavy merged PRs; the PR list endpoint cannot sort by that.

    Only ``number`` is read from the search payload — size and review data still
    come from the PR detail endpoint, so the two sources cannot disagree.
    """
    query = f"repo:{repo} is:pr is:merged comments:>={min_comments}"
    payload = gh_json(
        f"search/issues?q={query.replace(' ', '+')}&sort=comments&order=desc&per_page={limit}"
    )
    return [{"number": item["number"]} for item in payload.get("items", [])]


def pr_detail(repo: str, number: int) -> dict[str, Any]:
    """Fetch one PR: the list endpoint omits size fields, this one has them."""
    return gh_json(f"repos/{repo}/pulls/{number}")


def list_comments(repo: str, number: int) -> list[dict[str, Any]]:
    """Every review comment on a PR, flattened across pages.

    ``--slurp`` wraps each page in an outer array (``[[page1], [page2]]``), so a
    single-page PR arrives as ``[[comment, ...]]`` — flatten one level.
    """
    payload = gh_json(f"repos/{repo}/pulls/{number}/comments?per_page=100", paginate=True)
    flat: list[dict[str, Any]] = []
    for page in payload:
        flat.extend(page if isinstance(page, list) else [page])
    return flat


def pr_diff(repo: str, number: int) -> str:
    return gh_text(f"repos/{repo}/pulls/{number}", "application/vnd.github.diff")


def diff_blocks(diff: str) -> list[str]:
    """Split a unified diff into per-file blocks, keeping ``diff --git`` heads."""
    blocks: list[str] = []
    current: list[str] = []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                blocks.append("".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append("".join(current))
    return blocks


def block_path(block: str) -> str:
    """Return the b/ side path of a ``diff --git`` block."""
    match = re.search(r"^\+\+\+ b/(.+)$", block, re.MULTILINE)
    return match.group(1).strip() if match else ""


def trim_diff(diff: str, wanted: set[str]) -> str:
    """Keep only the blocks for ``wanted`` paths, in their original order."""
    kept = [block for block in diff_blocks(diff) if block_path(block) in wanted]
    return "".join(kept)


def block_changed_lines(block: str) -> int:
    """Count added/removed lines in a single per-file diff block."""
    return sum(
        1
        for line in block.splitlines()
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    )


HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _new_range(header: str) -> tuple[int, int] | None:
    match = HUNK_HEADER.match(header)
    if not match:
        return None
    start = int(match.group(3))
    count = int(match.group(4)) if match.group(4) is not None else 1
    return start, start + max(count, 1) - 1


def slice_to_line(block: str, line: int) -> str:
    """Keep the file header plus the hunks a review comment lives in (and one above).

    A unified diff may contain any subset of a file's hunks as long as each
    ``@@`` header keeps its original numbering, so a trimmed case still applies
    cleanly to the base commit while staying small enough to review.
    """
    lines = block.splitlines(keepends=True)
    prelude: list[str] = []
    hunks: list[str] = []
    for raw in lines:
        if raw.startswith("@@"):
            hunks.append(raw)
        elif hunks:
            hunks[-1] += raw
        else:
            prelude.append(raw)
    if not hunks:
        return block

    picked: set[int] = set()
    for index, hunk in enumerate(hunks):
        span = _new_range(hunk.splitlines()[0])
        if span and span[0] <= line <= span[1]:
            picked.add(index)
    if not picked:
        # Comment sits on a context-free anchor (e.g. a deleted line): fall back
        # to the hunk whose new range starts nearest to it.
        nearest = min(
            range(len(hunks)),
            key=lambda i: abs((_new_range(hunks[i].splitlines()[0]) or (line, line))[0] - line),
        )
        picked.add(nearest)
    first = min(picked)
    if first > 0:
        picked.add(first - 1)
    return "".join(prelude + [hunks[i] for i in sorted(picked)])


def diff_covers_line(block: str, line: int) -> bool:
    """Whether ``line`` is part of a hunk's new side (added *or* context line)."""
    for raw in block.splitlines():
        if raw.startswith("@@"):
            span = _new_range(raw)
            if span and span[0] <= line <= span[1]:
                return True
    return False


def patch_block(path: str, entry: dict[str, Any]) -> str:
    """Reassemble a single-file diff from ``commits/{sha}``'s ``files[].patch``.

    The commit API returns hunks without the ``diff --git`` preamble, so it has
    to be rebuilt before ``git apply`` accepts the block.
    """
    patch = (entry.get("patch") or "").rstrip("\n")
    if not patch:
        return ""
    status = entry.get("status")
    if status == "added":
        head = f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
    elif status == "modified":
        head = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
    else:  # renamed/removed entries cannot be applied to the parent path we keep
        return ""
    return head + patch + "\n"


def normalize_hunk(hunk: str) -> str:
    """Rewrite a hunk's line counts to match its actual body.

    GitHub's ``diff_hunk`` is the reviewer's hunk as it was at comment time, but
    it is truncated to a fixed size while the header keeps the full counts.
    ``git apply`` rejects such a block, so the counts are recomputed from the
    lines that are actually present.
    """
    lines = hunk.rstrip("\n").splitlines()
    match = HUNK_HEADER.match(lines[0]) if lines else None
    if not match:
        return ""
    body = lines[1:]
    old_count = sum(1 for line in body if not line.startswith(("+", "\\")))
    new_count = sum(1 for line in body if not line.startswith(("-", "\\")))
    header = f"@@ -{match.group(1)},{old_count} +{match.group(3)},{new_count} @@"
    return "\n".join([header, *body]) + "\n"


def hunk_is_truncated(hunk: str) -> bool:
    """Whether GitHub cut the hunk short while keeping its declared counts."""
    lines = hunk.rstrip("\n").splitlines()
    match = HUNK_HEADER.match(lines[0]) if lines else None
    if not match:
        return True
    body = lines[1:]
    old_present = sum(1 for line in body if not line.startswith(("+", "\\")))
    new_present = sum(1 for line in body if not line.startswith(("-", "\\")))
    old_declared = int(match.group(2)) if match.group(2) is not None else 1
    new_declared = int(match.group(4)) if match.group(4) is not None else 1
    return (old_present, new_present) != (old_declared, new_declared)


def hunk_block(path: str, hunk: str) -> str:
    """Wrap one ``diff_hunk`` in a file header so it can be applied on its own."""
    normalized = normalize_hunk(hunk)
    if not normalized:
        return ""
    match = HUNK_HEADER.match(normalized.splitlines()[0])
    if not match:  # pragma: no cover - normalize_hunk already validated it
        return ""
    old_start = int(match.group(1))
    old_count = int(match.group(2))
    if old_start == 0 and old_count == 0:
        head = f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
    else:
        head = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
    return head + normalized


def line_at_position(block: str, position: int) -> int | None:
    """New-file line at a 1-based GitHub diff ``position`` within ``block``.

    ``position``/``original_position`` index the unified diff including its
    preamble. They are the only fields that still locate an anchor when a
    force-push changed the file and ``line`` was rewritten against the new
    head.
    """
    new_line: int | None = None
    for index, raw in enumerate(block.splitlines(), 1):
        if raw.startswith("@@"):
            match = HUNK_HEADER.match(raw)
            if match:
                new_line = int(match.group(3))
            continue
        if raw.startswith(("diff ", "index ", "--- ", "+++ ", "new file", "deleted file")):
            continue
        if raw.startswith("-"):
            continue
        if index == position:
            return new_line
        if new_line is not None:
            new_line += 1
    return None


def commit_detail(repo: str, sha: str) -> dict[str, Any]:
    """One commit, including ``parents`` and per-file ``patch`` entries."""
    return gh_json(f"repos/{repo}/commits/{sha}")


def comment_target(
    repo: str, pr: dict[str, Any], comment: dict[str, Any]
) -> tuple[str, str, int] | None:
    """Return ``(file block, base commit, new-file line)`` for one comment.

    Prefers the comment's own commit: its patch against the parent shows the
    code the reviewer actually saw. When the commit does not touch the
    commented file (the review was made after an unrelated push), fall back to
    the comment's ``diff_hunk`` and the PR base it was computed against.
    """
    path = comment["path"]
    anchors = [comment.get("original_line"), comment.get("line")]
    anchors = [int(a) for a in anchors if a is not None]
    position = comment.get("original_position") or comment.get("position")

    def covered(block: str) -> int | None:
        for anchor in anchors:
            if diff_covers_line(block, anchor):
                return anchor
        return None

    hunk = comment.get("diff_hunk") or ""
    hunk_side = hunk_block(path, hunk) if hunk.startswith("@@") else ""
    hunk_line = covered(hunk_side) if hunk_side else None

    commit_block = ""
    commit_base = ""
    if comment.get("original_commit_id"):
        sha = comment["original_commit_id"]
    else:
        sha = comment.get("commit_id")
    if sha:
        try:
            commit = commit_detail(repo, sha)
        except RuntimeError as exc:  # force-pushed-away commit, rate limit, ...
            print(f"  {repo}@{sha[:10]}: {exc}", file=sys.stderr)
        else:
            entry = next((f for f in commit.get("files") or [] if f.get("filename") == path), None)
            parents = commit.get("parents") or []
            if entry and parents and entry.get("patch"):
                commit_block = patch_block(path, entry)
                commit_base = parents[0]["sha"]
                commit_line = covered(commit_block) if commit_block else None
                if commit_line is not None:
                    return commit_block, commit_base, commit_line

    if hunk_line is not None:
        return hunk_side, pr["base"]["sha"], hunk_line

    if commit_block and position:
        mapped = line_at_position(commit_block, int(position))
        if mapped is not None and diff_covers_line(commit_block, mapped):
            return commit_block, commit_base, mapped

    if hunk_side and position and not hunk_is_truncated(hunk):
        mapped = line_at_position(hunk_side, int(position))
        if mapped is not None and diff_covers_line(hunk_side, mapped):
            return hunk_side, pr["base"]["sha"], mapped
    return None


def pr_is_candidate(pr: dict[str, Any], max_files: int, max_lines: int) -> bool:
    """A case reviews *one* file block, so PR size is advisory, not a filter.

    ``max_files``/``max_lines`` of 0 disable the check; the runnable unit is the
    trimmed single-file diff, whose size is capped separately.
    """
    if not pr.get("merged_at"):
        return False
    author = login_of(pr)
    if not author or is_bot_user(pr):
        return False
    changed = pr.get("changed_files") or 0
    touched = (pr.get("additions") or 0) + (pr.get("deletions") or 0)
    if max_files and changed > max_files:
        return False
    if max_lines and touched > max_lines:
        return False
    return True


def shortlist(
    repo: str, limit: int, max_files: int, max_lines: int, want: int, min_comments: int
) -> list[dict]:
    """Pick merged, human, right-sized PRs, fetching details only as needed."""
    picked: list[dict[str, Any]] = []
    listing = search_prs(repo, min_comments, limit) if min_comments else list_prs(repo, limit)
    for pr in listing:
        try:
            detail = pr_detail(repo, pr["number"])
        except RuntimeError as exc:  # noqa: BLE001 - one bad PR must not stop the repo
            print(f"  #{pr['number']}: {exc}", file=sys.stderr)
            continue
        if pr_is_candidate(detail, max_files, max_lines):
            picked.append(detail)
            if len(picked) >= want:
                break
    return picked


#: Associations that usually mean "this reviewer can merge the PR". Kept for
#: ranking only: ``author_association`` is unreliable (plenty of Django
#: maintainers show up as ``CONTRIBUTOR``), so filtering on it drops good cases.
MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def comment_is_candidate(comment: dict[str, Any], pr_author: str) -> bool:
    """Keep top-level, non-author, line-anchored comments that say something."""
    author = login_of(comment)
    if not author or is_bot_user(comment) or author == pr_author:
        return False
    if comment.get("subject_type") != "line" or comment.get("in_reply_to_id"):
        return False
    if comment.get("line") is None or not comment.get("path", "").endswith(".py"):
        return False
    body = (comment.get("body") or "").strip()
    if len(body) < 60:
        return False
    return not body.startswith("```suggestion")


def defect_score(body: str, association: str = "") -> int:
    """How defect-like a comment reads; 0 means "process nit or taste"."""
    strong = sum(1 for pattern in DEFECT_PATTERNS if re.search(pattern, body, re.IGNORECASE))
    if strong == 0:
        return 0
    nits = sum(1 for pattern in NIT_PATTERNS if re.search(pattern, body, re.IGNORECASE))
    score = max(strong - nits, 0)
    return score + 1 if score and association in MAINTAINER_ASSOCIATIONS else score


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def make_draft(
    repo: str,
    pr: dict[str, Any],
    comment: dict[str, Any],
    diff: str,
    base_commit: str,
    line: int,
) -> dict[str, Any]:
    owner, name = repo.split("/", 1)
    path = comment["path"]
    stem = slugify(Path(path).stem)[:24]
    ident = f"real-{owner}-{name}-{pr['number']}-{stem}"
    body = (comment.get("body") or "").strip()
    return {
        "id": ident,
        "kind": "positive",
        "origin": "real-pr",
        "language": "python",
        "repo": repo,
        "base_commit": base_commit,
        "pr": pr["number"],
        "pr_title": pr["title"],
        "review_comment": {
            "author": login_of(comment),
            "url": comment["html_url"],
            "body": body,
        },
        "file": path,
        "expect": {
            "file": path,
            "line": line,
            "line_tolerance": 3,
            # Filled during curation; drafts are not runnable cases.
            "category": "TODO",
            "severity": "TODO",
            "summary": "TODO",
            "why": "TODO",
        },
        "tags": ["real-pr"],
        "diff": diff,
    }


def collect_pr(
    repo: str,
    pr: dict[str, Any],
    per_pr: int,
    max_block_lines: int,
    final_diff: bool,
) -> list[Path]:
    """Write comment-time drafts (or PR-head drafts with ``final_diff``) for one PR."""
    number = pr["number"]
    try:
        comments = list_comments(repo, number)
    except RuntimeError as exc:  # noqa: BLE001
        print(f"  #{number}: {exc}", file=sys.stderr)
        return []
    usable = [c for c in comments if comment_is_candidate(c, login_of(pr))]
    usable.sort(
        key=lambda c: defect_score(c.get("body") or "", c.get("author_association") or ""),
        reverse=True,
    )
    usable = [
        c
        for c in usable
        if defect_score(c.get("body") or "", c.get("author_association") or "") >= 1
    ][:per_pr]
    if not usable:
        return []

    blocks: dict[str, str] = {}
    if final_diff:
        try:
            diff = pr_diff(repo, number)
        except RuntimeError as exc:  # noqa: BLE001
            print(f"  #{number}: {exc}", file=sys.stderr)
            return []
        blocks = {block_path(b): b for b in diff_blocks(diff)}

    written: list[Path] = []
    for comment in usable:
        if final_diff:
            block = blocks.get(comment["path"])
            line = comment.get("line")
            if not block or line is None:
                continue
            target = (block, pr["base"]["sha"], int(line))
        else:
            target = comment_target(repo, pr, comment)
            if target is None:
                print(f"  no comment-time diff for {comment['path']}", file=sys.stderr)
                continue
        block, base_commit, line = target
        trimmed = slice_to_line(block, line)
        if not diff_covers_line(trimmed, line):
            print(
                f"  skip {comment['path']}: line {line} is outside the kept hunks", file=sys.stderr
            )
            continue
        if block_changed_lines(trimmed) > max_block_lines:
            print(
                f"  skip {comment['path']}: block has {block_changed_lines(trimmed)} changed lines",
                file=sys.stderr,
            )
            continue
        draft = make_draft(repo, pr, comment, trimmed, base_commit, line)
        path = DRAFTS_DIR / f"{draft['id']}.yaml"
        path.write_text(
            yaml.safe_dump(draft, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        written.append(path)
        print(f"  draft: {path.name}", file=sys.stderr)
    return written


def collect(
    repos: list[str],
    max_prs: int,
    max_files: int,
    max_lines: int,
    per_pr: int,
    limit: int,
    min_comments: int = 0,
    max_block_lines: int = 200,
    final_diff: bool = False,
) -> list[Path]:
    written: list[Path] = []
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    for repo in repos:
        try:
            candidates = shortlist(repo, limit, max_files, max_lines, max_prs, min_comments)
        except RuntimeError as exc:  # noqa: BLE001 - report and move to next repo
            print(f"{repo}: {exc}", file=sys.stderr)
            continue
        print(f"{repo}: {len(candidates)} candidate PR(s)", file=sys.stderr)
        for pr in candidates:
            written.extend(collect_pr(repo, pr, per_pr, max_block_lines, final_diff))
    return written


def cached_prs() -> list[tuple[str, dict[str, Any]]]:
    """Every PR detail already cached under ``.cache/gh``, with its repo name."""
    found: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(CACHE_DIR.glob("repos_*_pulls_*.json")):
        if not re.fullmatch(r"repos_.+_pulls_\d+\.json", path.name):
            continue
        detail = json.loads(path.read_text(encoding="utf-8"))
        repo = (detail.get("base") or {}).get("repo", {}).get("full_name")
        if repo:
            found.append((repo, detail))
    return found


def collect_cached(
    max_files: int,
    max_lines: int,
    per_pr: int,
    max_block_lines: int,
    final_diff: bool = False,
) -> list[Path]:
    """Replay every PR in ``.cache/gh`` so a corpus refresh costs no listing calls."""
    written: list[Path] = []
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    by_repo: dict[str, int] = {}
    for repo, pr in cached_prs():
        if not pr_is_candidate(pr, max_files, max_lines):
            continue
        by_repo[repo] = by_repo.get(repo, 0) + 1
        written.extend(collect_pr(repo, pr, per_pr, max_block_lines, final_diff))
    for repo, count in sorted(by_repo.items()):
        print(f"{repo}: {count} cached PR(s)", file=sys.stderr)
    return written


def list_drafts() -> int:
    for path in sorted(DRAFTS_DIR.glob("*.yaml")):
        draft = yaml.safe_load(path.read_text(encoding="utf-8"))
        comment = draft.get("review_comment", {})
        print(
            f"{draft['id']}\n  {draft['repo']}#{draft['pr']} {draft['expect']['file']}:"
            f"{draft['expect'].get('line')} by {comment.get('author')}\n  {comment.get('url')}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=[], help="owner/name (repeatable)")
    parser.add_argument("--max-prs", type=int, default=8, help="candidate PRs per repo")
    parser.add_argument(
        "--max-files", type=int, default=0, help="skip PRs touching more files (0 = no limit)"
    )
    parser.add_argument(
        "--max-lines", type=int, default=0, help="skip PRs touching more lines (0 = no limit)"
    )
    parser.add_argument(
        "--max-block-lines",
        type=int,
        default=200,
        help="skip comment files whose own diff block is larger than this",
    )
    parser.add_argument("--per-pr", type=int, default=2, help="comments kept per PR")
    parser.add_argument("--limit", type=int, default=60, help="closed PRs scanned per repo")
    parser.add_argument(
        "--min-comments",
        type=int,
        default=0,
        help="only PRs with at least this many discussion comments (uses search API)",
    )
    parser.add_argument(
        "--final-diff",
        action="store_true",
        help="slice the PR-head diff (old behaviour) instead of each comment's commit",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="replay every PR already cached under .cache/gh, without listing calls",
    )
    parser.add_argument("--list", action="store_true", help="print existing drafts and exit")
    args = parser.parse_args(argv)

    if args.list:
        return list_drafts()
    if not args.repo and not args.from_cache:
        parser.error("give at least one --repo, or --from-cache, or --list")

    if args.from_cache:
        written = collect_cached(
            args.max_files,
            args.max_lines,
            args.per_pr,
            args.max_block_lines,
            args.final_diff,
        )
    else:
        written = collect(
            args.repo,
            args.max_prs,
            args.max_files,
            args.max_lines,
            args.per_pr,
            args.limit,
            args.min_comments,
            args.max_block_lines,
            args.final_diff,
        )
    print(f"\n{len(written)} draft(s) in {DRAFTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
