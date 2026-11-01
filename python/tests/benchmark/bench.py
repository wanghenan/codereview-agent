"""S0 benchmark runner: run review cases and produce a side-by-side report.

The report is intentionally *not* auto-scored in v0: it prints expected vs.
actual for each case and leaves a checkbox line for the human, so the first
runs teach us how the model actually fails before we automate judgement.

Usage::

    python -m tests.benchmark.bench --validate
    python -m tests.benchmark.bench --all --out reports/2026-11-15.md
    python -m tests.benchmark.bench --case matcher-inverted
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

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
    """Return an error message if the case diff does not apply to HEAD.

    ``--cached`` checks against the index rather than the working tree, so a
    half-finished local refactor cannot invalidate the benchmark.
    """
    proc = subprocess.run(
        ["git", "apply", "--check", "--cached", "-"],
        cwd=REPO_ROOT,
        input=case["diff"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return None
    return proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "git apply failed"


# --------------------------------------------------------------------------- #
# running
# --------------------------------------------------------------------------- #
def _entries(case: dict[str, Any]) -> list[dict[str, Any]]:
    from codereview.cli.diff_parser import parse_git_diff_to_entries

    return [e.model_dump() for e in parse_git_diff_to_entries(case["diff"])]


async def run_case(case: dict[str, Any], config_path: Path) -> dict[str, Any]:
    """Run one case through the real review pipeline."""
    from codereview.cli.review_cmd import run_review

    started = time.monotonic()
    payload = await run_review(
        config_path=config_path,
        diff_input=json.dumps(_entries(case)),
        output_only=True,
        disable_cache=True,
        # Reuse the analysed project context across cases; re-analysing per case
        # would spend one LLM call per benchmark item for no extra signal.
        force_refresh=False,
    )
    elapsed = time.monotonic() - started
    return {"result": payload["result"], "elapsed": elapsed}


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


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _fmt_finding(row: dict[str, Any]) -> str:
    loc = f"{row['file']}:{row['line']}" if row["line"] else row["file"]
    delta = f" Δ{row['delta']}" if row.get("delta") is not None else ""
    return f"- `{loc}`{delta} [{row['severity']}] {row['description'][:160]}"


def render(results: list[dict[str, Any]], out: Path) -> str:
    lines = [
        "# Benchmark run",
        "",
        f"cases: {len(results)} · repo: `{REPO_ROOT.name}` · "
        f"config: `{DEFAULT_CONFIG.name}`",
        "",
        "| case | kind | findings | elapsed | verdict |",
        "|---|---|---|---|---|",
    ]
    for item in results:
        case = item["case"]
        verdict = (
            "☐ hit ☐ partial ☐ miss"
            if case["kind"] == "positive"
            else "☐ tn ☐ fp (noise)"
        )
        lines.append(
            f"| `{case['id']}` | {case['kind']} | {len(item['findings'])} | "
            f"{item['elapsed']:.1f}s | {verdict} |"
        )

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
        lines += [
            "",
            f"## {case['id']} · {case['kind']} · {', '.join(case.get('tags', []))}",
            "",
            header,
            "",
            f"why: {reason}",
            "",
            "**findings**",
        ]
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
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="run every case")
    parser.add_argument("--case", help="run a single case by id")
    parser.add_argument("--validate", action="store_true", help="only check diffs apply")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, help="report path (markdown)")
    parser.add_argument("--kind", choices=["positive", "negative"], help="filter by kind")
    args = parser.parse_args(argv)

    cases = load_cases(args.case)
    if args.kind:
        cases = [c for c in cases if c["kind"] == args.kind]

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
    if not args.config.exists():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 2

    results = []
    for case in cases:
        print(f"running {case['id']} ...", file=sys.stderr)
        try:
            run = asyncio.run(run_case(case, args.config))
            findings = pair(case, findings_of(run["result"]))
            results.append(
                {"case": case, "findings": findings, "elapsed": run["elapsed"], "error": None}
            )
        except Exception as exc:  # noqa: BLE001 - report, keep the batch going
            print(f"  error: {exc}", file=sys.stderr)
            results.append({"case": case, "findings": [], "elapsed": 0.0, "error": str(exc)})

    out = args.out or BENCH_DIR / "reports" / f"run-{time.strftime('%Y%m%d-%H%M')}.md"
    render(results, out)
    try:
        shown = out.resolve().relative_to(REPO_ROOT)
    except ValueError:
        shown = out
    print(f"report: {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
