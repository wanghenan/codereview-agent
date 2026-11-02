"""Tests for the nightly benchmark gate (``python/tests/benchmark/gate.py``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from tests.benchmark import gate

CASES_DIR = Path(__file__).parent / "benchmark" / "cases"
BASELINE = {"real_pr": {"matched": 1, "total": 2}, "injected": {"matched": 3, "total": 3}}


def case(
    case_id: str,
    matched: bool,
    origin: str = "injected",
    kind: str = "positive",
) -> dict[str, Any]:
    return {"id": case_id, "origin": origin, "kind": kind, "matched": matched}


def report(*cases: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": "2026-11-01T18:00:00+00:00",
        "config": "bench.yaml",
        "cases": list(cases),
    }


def full_report() -> dict[str, Any]:
    return report(
        case("real-a", True, origin="real-pr"),
        case("real-b", False, origin="real-pr"),
        case("inj-a", True),
        case("inj-b", True),
        case("inj-c", True),
    )


def test_check_passes_at_baseline() -> None:
    assert gate.check(full_report(), BASELINE) == []


def test_check_allows_shortfall_within_tolerance() -> None:
    base = {"injected": {"matched": 3, "total": 3}}
    rep = report(case("inj-a", True), case("inj-b", True), case("inj-c", False))

    assert gate.check(rep, base, tolerance=0) != []
    assert gate.check(rep, base, tolerance=1) == []


def test_check_fails_when_shortfall_exceeds_tolerance() -> None:
    base = {"injected": {"matched": 3, "total": 3}}
    rep = report(case("inj-a", True), case("inj-b", False), case("inj-c", False))

    problems = gate.check(rep, base, tolerance=1)

    assert len(problems) == 1
    assert "injected: matched 1/3" in problems[0]
    assert "unmatched: inj-b, inj-c" in problems[0]


def test_check_fails_when_cases_are_missing() -> None:
    base = {"injected": {"matched": 3, "total": 3}}
    rep = report(case("inj-a", True), case("inj-b", True))

    problems = gate.check(rep, base)

    assert len(problems) == 1
    assert "missing 1 positive case" in problems[0]


def test_check_flags_corpus_growth() -> None:
    base = {"injected": {"matched": 1, "total": 1}}
    rep = report(case("inj-a", True), case("inj-b", True))

    problems = gate.check(rep, base)

    assert len(problems) == 1
    assert "more positive case" in problems[0]


def test_negative_cases_are_not_counted() -> None:
    base = {"injected": {"matched": 1, "total": 1}}
    rep = report(case("inj-a", True), case("neg-a", True, kind="negative"))

    assert gate.check(rep, base) == []


def test_baseline_covers_current_corpus() -> None:
    counts = {group: 0 for group in gate.GROUPS}
    for path in sorted(CASES_DIR.glob("*.yaml")):
        case_data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if case_data["kind"] != "positive":
            continue
        group = gate.GROUP_OF_ORIGIN[case_data.get("origin", "injected")]
        counts[group] += 1

    baseline = json.loads(gate.DEFAULT_BASELINE.read_text(encoding="utf-8"))
    for group, total in counts.items():
        assert baseline[group]["total"] == total, group


def test_cli_exit_codes(tmp_path: Path) -> None:
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps({"injected": {"matched": 2, "total": 2}}), encoding="utf-8")

    passing = tmp_path / "passing.json"
    passing.write_text(json.dumps(report(case("a", True), case("b", True))), encoding="utf-8")
    assert gate.main(["--report", str(passing), "--baseline", str(base)]) == 0

    failing = tmp_path / "failing.json"
    failing.write_text(json.dumps(report(case("a", True), case("b", False))), encoding="utf-8")
    assert gate.main(["--report", str(failing), "--baseline", str(base)]) == 1


def test_cli_rejects_unreadable_report(tmp_path: Path) -> None:
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps({"injected": {"matched": 1, "total": 1}}), encoding="utf-8")

    assert gate.main(["--report", str(tmp_path / "missing.json"), "--baseline", str(base)]) == 2
