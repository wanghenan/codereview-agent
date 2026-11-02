"""Tests for the benchmark report writers (``python/tests/benchmark/bench.py``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.benchmark import bench

_UNSET = object()


def make_result(
    case_id: str,
    *,
    strictness: object = _UNSET,
    origin: str = "injected",
    kind: str = "positive",
) -> dict[str, Any]:
    case: dict[str, Any] = {
        "id": case_id,
        "origin": origin,
        "kind": kind,
        "expect": {
            "file": "pkg/mod.py",
            "line": 10,
            "severity": "high",
            "category": "bug",
            "summary": "expected issue",
            "why": "the change breaks behaviour",
        },
        "tags": ["test"],
    }
    if strictness is not _UNSET:
        case["strictness"] = strictness
    return {
        "case": case,
        "findings": [],
        "elapsed": 1.25,
        "error": None,
        "matched": False,
        "best_delta": None,
    }


def test_json_out_records_strictness_and_null(tmp_path: Path) -> None:
    results = [
        make_result("defect-case", strictness="defect"),
        make_result("design-case", strictness="design"),
        make_result("nit-case", strictness="nit"),
        make_result("plain-case"),
    ]

    out = bench.write_json(results, tmp_path / "report.json", Path("bench.yaml"))

    cases = json.loads(out.read_text(encoding="utf-8"))["cases"]
    assert all("strictness" in case for case in cases)
    assert [case["strictness"] for case in cases] == ["defect", "design", "nit", None]


def test_markdown_table_has_strictness_column(tmp_path: Path) -> None:
    results = [make_result("defect-case", strictness="defect"), make_result("plain-case")]

    text = bench.render(results, tmp_path / "report.md", Path("bench.yaml"))

    assert (
        "| case | origin | kind | strictness | findings | candidate | elapsed | verdict |" in text
    )
    assert "| `defect-case` | injected | positive | defect | 0 | — | 1.2s |" in text
    assert "| `plain-case` | injected | positive | — | 0 | — | 1.2s |" in text


def test_json_out_reflects_case_yaml(tmp_path: Path) -> None:
    cases = bench.load_cases()
    declared = next(case for case in cases if case.get("strictness"))
    missing = next(case for case in cases if "strictness" not in case)
    results = [
        {**make_result(str(declared["id"])), "case": declared},
        {**make_result(str(missing["id"])), "case": missing},
    ]

    out = bench.write_json(results, tmp_path / "report.json", Path("bench.yaml"))

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["cases"][0]["strictness"] == declared["strictness"]
    assert payload["cases"][1]["strictness"] is None
