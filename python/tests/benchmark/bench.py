"""S0 benchmark runner: run review cases and produce a side-by-side report.

The report is intentionally *not* auto-scored in v0: it prints expected vs.
actual for each case and leaves a checkbox line for the human, so the first
runs teach us how the model actually fails before we automate judgement.

Usage::

    python -m tests.benchmark.bench --validate
    python -m tests.benchmark.bench --all --out reports/2026-11-15.md
    python -m tests.benchmark.bench --all --json-out reports/2026-11-15.json
    python -m tests.benchmark.bench --case matcher-inverted
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from . import real_pr
else:  # direct script execution: python tests/benchmark/bench.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import real_pr  # type: ignore[no-redef]

BENCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCH_DIR.parents[2]
CASES_DIR = BENCH_DIR / "cases"
DEFAULT_CONFIG = REPO_ROOT / ".codereview-agent.yaml"


# --------------------------------------------------------------------------- #
# loading and validation
# --------------------------------------------------------------------------- #
def load_cases(only: str | None = None) -> list[dict[str, Any]]:
    """Load case YAML files, optionally filtered by id."""
    cases = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        if only and case["id"] != only:
            continue
        case["_path"] = path
        cases.append(case)
    if not cases:
        raise SystemExit(f"no cases found in {CASES_DIR} (filter={only!r})")
    return cases


def validate(case: dict[str, Any]) -> str | None:
    """Return an error message if the case diff does not apply to its base tree.

    Injected cases are checked against this repo's index (``--cached``), so a
    half-finished local refactor cannot invalidate the benchmark. Real-PR cases
    are checked against the extracted upstream commit, where there is no index
    and the working tree *is* the base.

    ``.repos/`` sits inside this repository, so ``git apply`` has to be told
    not to use the surrounding checkout, otherwise it skips every path as
    foreign to the repo root. Real-PR diffs are also single-file slices whose
    hunks may end at the commented line without trailing context; the upstream
    comment's ``diff_hunk`` is truncated that way, so ``--unidiff-zero`` keeps
    the line-number check meaningful.
    """
    checkout = real_pr.case_checkout(case)
    env = None
    if checkout is not None:
        cmd = ["git", "apply", "--check", "--unidiff-zero", "-"]
        cwd = checkout
        env = {**os.environ, "GIT_DIR": str(checkout / ".no-git-dir")}
    else:
        cmd = ["git", "apply", "--check", "--cached", "-"]
        cwd = REPO_ROOT
    proc = subprocess.run(cmd, cwd=cwd, input=case["diff"], capture_output=True, text=True, env=env)
    if proc.returncode == 0:
        return None
    return proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "git apply failed"


# --------------------------------------------------------------------------- #
# running
# --------------------------------------------------------------------------- #
def _entries(case: dict[str, Any]) -> list[dict[str, Any]]:
    from codereview.cli.diff_parser import parse_git_diff_to_entries

    return [e.model_dump() for e in parse_git_diff_to_entries(case["diff"])]


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    """Temporarily chdir: the pipeline analyses the project at ``Path.cwd()``."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


async def run_case(case: dict[str, Any], config_path: Path) -> dict[str, Any]:
    """Run one case through the real review pipeline."""
    from codereview.cli.review_cmd import run_review

    checkout = real_pr.case_checkout(case)
    started = time.monotonic()
    # Real-PR cases must see the upstream tree, not this repository: project
    # analysis, the symbol index and the external tools all read ``cwd``.
    with _working_directory(checkout) if checkout is not None else _null_context():
        payload = await run_review(
            config_path=config_path,
            diff_input=json.dumps(_entries(case)),
            output_only=True,
            disable_cache=True,
            # Reuse the analysed project context across cases; re-analysing per
            # case would spend one LLM call per benchmark item for no signal.
            force_refresh=False,
        )
    elapsed = time.monotonic() - started
    return {"result": payload["result"], "elapsed": elapsed}


@contextmanager
def _null_context() -> Iterator[None]:
    yield


def _evidence_details(issue: dict[str, Any]) -> list[str]:
    """Return the finding's evidence details as plain strings.

    The review result is a model dump, so anchors are ``{kind, detail}`` dicts;
    accept objects too so the helper stays usable on live ``FileIssue`` models.
    """
    details = []
    for anchor in issue.get("evidence") or []:
        if isinstance(anchor, dict):
            detail = anchor.get("detail")
        else:
            detail = getattr(anchor, "detail", None)
        text = (detail or "").strip()
        if text:
            details.append(text)
    return details


def findings_of(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the review result into one row per finding.

    Rows carry the fields the benchmark reports need: where the finding landed,
    what it claims, and the evidence anchors used to judge whether a code
    fragment could relocate the anchor inside the patch.
    """
    rows = []
    for review in result.get("files_reviewed", []):
        for issue in review.get("issues", []):
            rows.append(
                {
                    "file": issue.get("file_path") or review.get("file_path"),
                    "line": issue.get("line_number"),
                    "severity": issue.get("risk_level"),
                    "confidence": issue.get("confidence"),
                    "source": issue.get("source"),
                    "category": issue.get("category"),
                    "caller": issue.get("caller"),
                    "title": (issue.get("title") or "").strip(),
                    "description": (issue.get("description") or "").strip(),
                    "evidence": _evidence_details(issue),
                    "suggestion": (issue.get("suggestion") or "").strip(),
                }
            )
    return rows


def pair(case: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate findings with distance to the expected location."""
    expect = case["expect"]
    tolerance = expect.get("line_tolerance", 3)
    for row in findings:
        same_file = row["file"] == expect["file"]
        expected_line = expect.get("line")
        if not same_file:
            row["match"] = "other-file"
            row["delta"] = None
        elif expected_line is None or row["line"] is None:
            row["match"] = "file-level"
            row["delta"] = None
        else:
            delta = abs(int(row["line"]) - int(expected_line))
            row["delta"] = delta
            row["match"] = "candidate" if delta <= tolerance else "far"
    return findings


def candidate_hit(findings: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """Return whether a finding is a candidate hit and its closest distance.

    "Candidate" is the weak machine-checkable signal from :func:`pair`: same
    file as ``expect`` and a line number within ``line_tolerance``. It is only
    used for gating regressions, never as a semantic verdict. For a negative
    case a hit means the reviewer reported the harmless change (a false
    positive).
    """
    candidates = [row for row in findings if row.get("match") in ("candidate", "file-level")]
    if not candidates:
        return False, None
    deltas = [int(row["delta"]) for row in candidates if row.get("delta") is not None]
    return True, min(deltas) if deltas else None


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _fmt_finding(row: dict[str, Any]) -> str:
    loc = f"{row['file']}:{row['line']}" if row["line"] else row["file"]
    delta = f" Δ{row['delta']}" if row.get("delta") is not None else ""
    conf = row.get("confidence")
    conf_text = f" conf={conf:.2f}" if isinstance(conf, (int, float)) else ""
    caller = f" caller={row['caller']}" if row.get("caller") else ""
    # The first anchor is the most specific one the model cited, and it is what
    # a later fragment-based re-anchor pass would look up inside the patch.
    evidence = row.get("evidence") or []
    snippet = " ".join(str(evidence[0]).split())[:80] if evidence else ""
    evidence_text = f" | evidence: {snippet}" if snippet else ""
    return (
        f"- `{loc}`{delta} [{row['severity']}{conf_text} src={row.get('source')}"
        f"/{row.get('category')}{caller}] {row['description'][:600]}{evidence_text}"
    )


def _candidate_cell(item: dict[str, Any]) -> str:
    if not item.get("matched"):
        return "—"
    delta = item.get("best_delta")
    return f"✅ Δ{delta}" if delta is not None else "✅ file"


def render(
    results: list[dict[str, Any]],
    out: Path,
    config_path: Path = DEFAULT_CONFIG,
    llm: dict[str, Any] | None = None,
) -> str:
    where = f"cases: {len(results)} · repo: `{REPO_ROOT.name}` · config: `{config_path.name}`"
    # The config file name says nothing about what actually answered: the same
    # `oc.yaml` may point at a different model next month, and reports from
    # different providers are not comparable. Record the resolved target.
    if llm and llm.get("model"):
        where += f" · model: `{llm.get('provider')}/{llm['model']}`"
    lines = [
        "# Benchmark run",
        "",
        where,
        "",
        "| case | origin | kind | strictness | findings | candidate | elapsed | verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in results:
        case = item["case"]
        verdict = "☐ hit ☐ partial ☐ miss" if case["kind"] == "positive" else "☐ tn ☐ fp (noise)"
        lines.append(
            f"| `{case['id']}` | {case.get('origin', 'injected')} | {case['kind']} | "
            f"{case.get('strictness') or '—'} | "
            f"{len(item['findings'])} | {_candidate_cell(item)} | "
            f"{item['elapsed']:.1f}s | {verdict} |"
        )

    lines += [
        "",
        "`candidate` (and `matched` in `--json-out`) only marks a finding on the same file "
        "and within `line_tolerance` of the expected line. It is a regression gate, **not** "
        "a semantic verdict; real-PR cases still need a human to confirm the finding is the "
        "same issue. On negative cases a candidate means the harmless change was reported.",
    ]

    for item in results:
        case = item["case"]
        expect = case["expect"]
        if case["kind"] == "negative":
            header = (
                f"**expected**: no actionable finding at "
                f"`{expect['file']}:{expect.get('line', '?')}`"
            )
            reason = case.get("invalid_reason", "")
        else:
            header = (
                f"**expected** `{expect['file']}:{expect.get('line', '?')}` "
                f"[{expect['severity']}/{expect['category']}] {expect['summary']}"
            )
            reason = expect["why"]
        source_line = ""
        if case.get("origin") == "real-pr":
            comment = case.get("review_comment") or {}
            source_line = (
                f"source: {case['repo']}#{case['pr']} · human comment by "
                f"{comment.get('author', '?')} · {comment.get('url', '')}"
            )
        lines += [
            "",
            f"## {case['id']} · {case['kind']} · {', '.join(case.get('tags', []))}",
            "",
            header,
            "",
            f"why: {reason}",
            "",
        ]
        if source_line:
            lines += [source_line, ""]
        lines += ["**findings**"]
        if item["findings"]:
            lines += [_fmt_finding(row) for row in item["findings"]]
        else:
            lines.append("- (none)")
        lines += ["", f"error: {item['error']}" if item.get("error") else ""]

    text = "\n".join(lines).rstrip() + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _finding_detail(row: dict[str, Any]) -> dict[str, Any]:
    """Return the per-finding JSON record used to evaluate anchor relocation.

    ``suggestion`` is capped at 200 characters: the field is prose and the
    report is uploaded as an artifact, so keeping it whole would bloat the JSON
    without helping the fragment-matching measurement.
    """
    return {
        "line": row.get("line"),
        "title": row.get("title", ""),
        "evidence": list(row.get("evidence") or []),
        "suggestion": (row.get("suggestion") or "")[:200],
    }


def _llm_identity(config_path: Path) -> dict[str, Any]:
    """Return the provider/model the config resolves to, for report attribution.

    Best effort: a config that cannot be loaded (missing API key, unreadable
    file) must not stop a benchmark run, so failures yield an empty mapping and
    the report simply omits the model line.
    """
    try:
        from codereview.core.config import ConfigLoader

        llm = ConfigLoader.load(config_path).llm
    except Exception:  # noqa: BLE001 - attribution is never worth failing a run
        return {}
    identity: dict[str, Any] = {"provider": str(llm.provider), "model": llm.model or ""}
    if llm.base_url:
        identity["baseUrl"] = llm.base_url
    return identity


def select_cases(
    cases: list[dict[str, Any]],
    *,
    kind: str | None = None,
    tag: str | None = None,
    origin: str | None = None,
    strictness: str | None = None,
) -> list[dict[str, Any]]:
    """Filter cases by the CLI selectors; every one is optional and ANDed.

    Kept separate from :func:`main` so the selection rules are testable without
    running a review.
    """
    selected = cases
    if kind:
        selected = [c for c in selected if c["kind"] == kind]
    if tag:
        selected = [c for c in selected if tag in (c.get("tags") or [])]
    if origin:
        selected = [c for c in selected if c.get("origin", "injected") == origin]
    if strictness:
        selected = [c for c in selected if c.get("strictness") == strictness]
    return selected


def write_json(
    results: list[dict[str, Any]],
    out: Path,
    config_path: Path,
    llm: dict[str, Any] | None = None,
) -> Path:
    """Write the machine-readable report consumed by ``gate.py``.

    ``matched``/``best_delta`` come from :func:`candidate_hit`: same file and a
    line within tolerance. This is a regression signal only, never proof of a
    semantic hit. ``strictness`` is copied from the case YAML (``null`` when the
    case does not declare one) so stratified reports need not re-read the YAML.

    ``findings`` stays the count the gate and older reports expect;
    ``finding_details`` carries the per-finding anchors (``line``, ``title``,
    ``evidence``, ``suggestion``) needed to evaluate patch-based relocation.

    ``llm`` records the resolved provider/model, because ``config`` is only a
    path: two runs against the same config file can be answered by different
    models, and numbers from different providers are not comparable.
    """
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": _display_path(config_path),
        "llm": llm or {},
        "cases": [
            {
                "id": item["case"]["id"],
                "origin": item["case"].get("origin", "injected"),
                "kind": item["case"]["kind"],
                "strictness": item["case"].get("strictness"),
                "findings": len(item["findings"]),
                "finding_details": [_finding_detail(row) for row in item["findings"]],
                "matched": bool(item["matched"]),
                "best_delta": item["best_delta"],
                "elapsed": round(float(item["elapsed"]), 2),
                "error": item["error"],
            }
            for item in results
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="run every case")
    parser.add_argument("--case", help="run a single case by id")
    parser.add_argument("--validate", action="store_true", help="only check diffs apply")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, help="report path (markdown)")
    parser.add_argument(
        "--json-out",
        type=Path,
        help="machine-readable report path (JSON, compared by gate.py)",
    )
    parser.add_argument("--kind", choices=["positive", "negative"], help="filter by kind")
    parser.add_argument("--tag", help="only run cases carrying this tag")
    parser.add_argument(
        "--origin",
        choices=["injected", "real-pr"],
        help="only run cases from this origin",
    )
    parser.add_argument(
        "--strictness",
        choices=["defect", "design", "nit"],
        help="only run real-PR cases of this review strictness",
    )
    args = parser.parse_args(argv)

    # Real-PR cases chdir into their checkout, so a relative --config would be
    # resolved against another repository's tree.
    config_path = args.config.expanduser().resolve()

    cases = load_cases(args.case)
    cases = select_cases(
        cases,
        kind=args.kind,
        tag=args.tag,
        origin=args.origin,
        strictness=args.strictness,
    )

    problems = 0
    for case in cases:
        err = validate(case)
        if err:
            print(f"FAIL {case['id']}: {err}")
            problems += 1
    if args.validate:
        print(f"\n{len(cases) - problems}/{len(cases)} cases apply cleanly")
        return 1 if problems else 0
    if problems:
        print("aborting: fix invalid cases first")
        return 1

    if not (args.all or args.case):
        parser.error("choose --all, --case or --validate")
    if not config_path.exists():
        print(f"config not found: {config_path}", file=sys.stderr)
        return 2

    results = []
    for case in cases:
        print(f"running {case['id']} ...", file=sys.stderr)
        try:
            run = asyncio.run(run_case(case, config_path))
            findings = pair(case, findings_of(run["result"]))
            matched, best_delta = candidate_hit(findings)
            results.append(
                {
                    "case": case,
                    "findings": findings,
                    "elapsed": run["elapsed"],
                    "error": None,
                    "matched": matched,
                    "best_delta": best_delta,
                }
            )
        except Exception as exc:  # noqa: BLE001 - report, keep the batch going
            print(f"  error: {exc}", file=sys.stderr)
            results.append(
                {
                    "case": case,
                    "findings": [],
                    "elapsed": 0.0,
                    "error": str(exc),
                    "matched": False,
                    "best_delta": None,
                }
            )

    out = args.out or BENCH_DIR / "reports" / f"run-{time.strftime('%Y%m%d-%H%M')}.md"
    llm = _llm_identity(config_path)
    render(results, out, config_path, llm)
    print(f"report: {_display_path(out)}")
    if args.json_out:
        json_out = write_json(results, args.json_out.expanduser(), config_path, llm)
        print(f"json: {_display_path(json_out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
