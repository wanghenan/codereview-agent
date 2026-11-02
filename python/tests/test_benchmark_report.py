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


def make_finding(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "file": "pkg/mod.py",
        "line": 12,
        "delta": 4,
        "severity": "medium",
        "confidence": 0.5,
        "source": "llm",
        "category": "bug",
        "caller": None,
        "title": "unvalidated lookup",
        "description": "lookup uses an unvalidated key",
        "evidence": ["key = request.args['id']"],
        "suggestion": "validate the key before the lookup",
    }
    row.update(overrides)
    return row


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


def test_findings_of_reads_title_and_evidence_details() -> None:
    result = {
        "files_reviewed": [
            {
                "file_path": "pkg/mod.py",
                "issues": [
                    {
                        "file_path": "pkg/mod.py",
                        "line_number": 10,
                        "risk_level": "medium",
                        "title": "  unvalidated lookup  ",
                        "description": "  lookup uses an unvalidated key  ",
                        "evidence": [
                            {"kind": "context", "detail": "  key = request.args['id']  "},
                            {"kind": "rule", "detail": ""},
                        ],
                        "suggestion": None,
                    }
                ],
            }
        ]
    }

    [row] = bench.findings_of(result)

    assert row["title"] == "unvalidated lookup"
    assert row["evidence"] == ["key = request.args['id']"]
    assert row["suggestion"] == ""


def test_json_out_includes_finding_details(tmp_path: Path) -> None:
    result = {**make_result("evidence-case"), "findings": [make_finding()]}

    out = bench.write_json([result], tmp_path / "report.json", Path("bench.yaml"))

    case = json.loads(out.read_text(encoding="utf-8"))["cases"][0]
    assert case["findings"] == 1
    assert case["finding_details"] == [
        {
            "line": 12,
            "title": "unvalidated lookup",
            "evidence": ["key = request.args['id']"],
            "suggestion": "validate the key before the lookup",
        }
    ]


def test_json_out_missing_evidence_is_empty_list(tmp_path: Path) -> None:
    finding = make_finding(evidence=[], title="rule-only finding")
    result = {**make_result("no-evidence"), "findings": [finding]}

    out = bench.write_json([result], tmp_path / "report.json", Path("bench.yaml"))

    case = json.loads(out.read_text(encoding="utf-8"))["cases"][0]
    assert case["finding_details"][0]["evidence"] == []
    assert case["finding_details"][0]["title"] == "rule-only finding"


def test_json_out_truncates_suggestion(tmp_path: Path) -> None:
    result = {**make_result("long-suggestion"), "findings": [make_finding(suggestion="x" * 250)]}

    out = bench.write_json([result], tmp_path / "report.json", Path("bench.yaml"))

    case = json.loads(out.read_text(encoding="utf-8"))["cases"][0]
    assert case["finding_details"][0]["suggestion"] == "x" * 200


def test_markdown_appends_first_evidence_snippet(tmp_path: Path) -> None:
    finding = make_finding(evidence=["key = request.args['id']", "second anchor"])
    result = {**make_result("evidence-case"), "findings": [finding]}

    text = bench.render([result], tmp_path / "report.md", Path("bench.yaml"))

    assert "| evidence: key = request.args['id']" in text
    assert "second anchor" not in text


def test_markdown_evidence_snippet_is_single_line_and_truncated(tmp_path: Path) -> None:
    evidence = "first line\n" + "y" * 100
    result = {**make_result("long-evidence"), "findings": [make_finding(evidence=[evidence])]}

    text = bench.render([result], tmp_path / "report.md", Path("bench.yaml"))

    line = next(line for line in text.splitlines() if line.startswith("- `pkg/mod.py:12`"))
    snippet = line.split("| evidence: ", 1)[1]
    assert snippet == ("first line " + "y" * 100)[:80]
    assert len(snippet) == 80


def test_markdown_omits_evidence_suffix_when_absent(tmp_path: Path) -> None:
    result = {**make_result("no-evidence"), "findings": [make_finding(evidence=[])]}

    text = bench.render([result], tmp_path / "report.md", Path("bench.yaml"))

    assert "evidence:" not in text
