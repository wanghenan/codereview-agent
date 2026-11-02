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
    """
    checkout = real_pr.case_checkout(case)
    if checkout is not None:
        cmd = ["git", "apply", "--check", "-"]
        cwd = checkout
    else:
        cmd = ["git", "apply", "--check", "--cached", "-"]
        cwd = REPO_ROOT
    proc = subprocess.run(cmd, cwd=cwd, input=case["diff"], capture_output=True, text=True)
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


def findings_of(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the review result into (file, line, severity, description) rows."""
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
                    "description": (issue.get("description") or "").strip(),
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
    return (
        f"- `{loc}`{delta} [{row['severity']}{conf_text} src={row.get('source')}"
        f"/{row.get('category')}{caller}] {row['description'][:600]}"
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
) -> str:
    lines = [
        "# Benchmark run",
        "",
        f"cases: {len(results)} · repo: `{REPO_ROOT.name}` · config: `{config_path.name}`",
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


def write_json(results: list[dict[str, Any]], out: Path, config_path: Path) -> Path:
    """Write the machine-readable report consumed by ``gate.py``.

    ``matched``/``best_delta`` come from :func:`candidate_hit`: same file and a
    line within tolerance. This is a regression signal only, never proof of a
    semantic hit. ``strictness`` is copied from the case YAML (``null`` when the
    case does not declare one) so stratified reports need not re-read the YAML.
    """
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": _display_path(config_path),
        "cases": [
            {
                "id": item["case"]["id"],
                "origin": item["case"].get("origin", "injected"),
                "kind": item["case"]["kind"],
                "strictness": item["case"].get("strictness"),
                "findings": len(item["findings"]),
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
    args = parser.parse_args(argv)

    # Real-PR cases chdir into their checkout, so a relative --config would be
    # resolved against another repository's tree.
    config_path = args.config.expanduser().resolve()

    cases = load_cases(args.case)
    if args.kind:
        cases = [c for c in cases if c["kind"] == args.kind]
    if args.tag:
        cases = [c for c in cases if args.tag in (c.get("tags") or [])]
    if args.origin:
        cases = [c for c in cases if c.get("origin", "injected") == args.origin]

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
    render(results, out, config_path)
    print(f"report: {_display_path(out)}")
    if args.json_out:
        json_out = write_json(results, args.json_out.expanduser(), config_path)
        print(f"json: {_display_path(json_out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
