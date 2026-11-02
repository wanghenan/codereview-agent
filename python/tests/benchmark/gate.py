"""Threshold gate for the nightly real-corpus benchmark.

Reads the machine-readable report written by ``bench.py --json-out``, counts
candidate hits per group (``real_pr`` / ``injected``) and compares them with the
checked-in ``baseline.json``. Exits 1 when a group has fewer candidate hits than
the baseline allows (``baseline - tolerance``) or when the report does not cover
the cases the baseline expects.

A candidate hit means only "same file and line within ``line_tolerance``" (see
``bench.py::pair``): a weak regression signal, not a semantic verdict.

Usage::

    python tests/benchmark/gate.py --report reports/nightly.json
    python tests/benchmark/gate.py --report report.json --tolerance 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
DEFAULT_BASELINE = BENCH_DIR / "baseline.json"
GROUP_OF_ORIGIN = {"real-pr": "real_pr", "injected": "injected"}
GROUPS = ("real_pr", "injected")


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object, turning file and parse problems into one message."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def summarize(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Count positive cases and candidate hits per baseline group."""
    summary: dict[str, dict[str, Any]] = {
        group: {"matched": 0, "total": 0, "unmatched": []} for group in GROUPS
    }
    for case in cases:
        if case.get("kind") != "positive":
            continue
        group = GROUP_OF_ORIGIN.get(str(case.get("origin", "injected")))
        if group is None:
            continue
        summary[group]["total"] += 1
        if case.get("matched"):
            summary[group]["matched"] += 1
        else:
            summary[group]["unmatched"].append(str(case.get("id", "?")))
    return summary


def _expected_groups(baseline: dict[str, Any]) -> dict[str, dict[str, int]]:
    expected: dict[str, dict[str, int]] = {}
    for group in GROUPS:
        entry = baseline.get(group)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"baseline group {group!r} must be an object")
        try:
            matched = int(entry["matched"])
            total = int(entry["total"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"baseline group {group!r} needs integer matched/total") from exc
        if matched < 0 or total < 0 or matched > total:
            raise ValueError(f"baseline group {group!r} has invalid counts: {entry}")
        expected[group] = {"matched": matched, "total": total}
    if not expected:
        raise ValueError("baseline has no known group (expected real_pr / injected)")
    return expected


def check(report: dict[str, Any], baseline: dict[str, Any], tolerance: int = 0) -> list[str]:
    """Return gate failures; an empty list means the run passes."""
    cases = report.get("cases")
    if not isinstance(cases, list):
        raise ValueError("report is missing a 'cases' list")
    actual = summarize(cases)
    expected = _expected_groups(baseline)
    problems = []
    for group, base in expected.items():
        got = actual[group]
        floor = base["matched"] - tolerance
        missing = base["total"] - got["total"]
        if missing > 0:
            problems.append(
                f"{group}: missing {missing} positive case(s) "
                f"(baseline {base['total']}, report {got['total']})"
            )
        elif missing < 0:
            problems.append(
                f"{group}: report has {-missing} more positive case(s) than the baseline; "
                "refresh baseline.json"
            )
        elif got["matched"] < floor:
            unmatched = ", ".join(got["unmatched"]) or "none"
            problems.append(
                f"{group}: matched {got['matched']}/{got['total']} < "
                f"baseline {base['matched']}/{base['total']} - tolerance {tolerance}; "
                f"unmatched: {unmatched}"
            )
    return problems


def _print_summary(report: dict[str, Any]) -> None:
    summary = summarize(report.get("cases") or [])
    parts = [f"{group} {summary[group]['matched']}/{summary[group]['total']}" for group in GROUPS]
    print("candidate hits: " + ", ".join(parts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="JSON from bench.py --json-out")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--tolerance", type=int, default=0, help="allowed candidate-hit shortfall")
    args = parser.parse_args(argv)

    try:
        report = load_json(args.report.expanduser())
        baseline = load_json(args.baseline.expanduser())
        problems = check(report, baseline, args.tolerance)
    except ValueError as exc:
        print(f"gate error: {exc}", file=sys.stderr)
        return 2

    _print_summary(report)
    if problems:
        print("benchmark gate FAILED")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("benchmark gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
