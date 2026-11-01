"""Tests for the external tool runner and its output normalisers."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Optional

import pytest

from codereview.core import tool_runner
from codereview.core.tool_runner import (
    RULE_TOOL_ERROR,
    RULE_TOOL_TIMEOUT,
    RULE_TOOL_UNAVAILABLE,
    ToolRunner,
    ToolSpec,
    normalise_eslint,
    normalise_ruff,
    normalise_semgrep,
    normalise_trufflehog,
)

FINDING_KEYS = {"file", "line", "rule_id", "tool", "severity", "description"}

RUFF_SAMPLE = [
    {
        "code": "F401",
        "filename": "src/app.py",
        "location": {"row": 3, "column": 8},
        "end_location": {"row": 3, "column": 11},
        "message": "`os` imported but unused",
    },
    {
        "code": "E902",
        "filename": "src/broken.py",
        "location": {"row": 1, "column": 1},
        "message": "SyntaxError: invalid syntax",
    },
]

ESLINT_SAMPLE = [
    {
        "filePath": "web/app.js",
        "messages": [
            {
                "ruleId": "no-unused-vars",
                "severity": 2,
                "line": 4,
                "column": 7,
                "message": "'x' is assigned a value but never used.",
            },
            {
                "ruleId": "semi",
                "severity": 1,
                "line": 5,
                "column": 2,
                "message": "Missing semicolon.",
            },
        ],
        "errorCount": 1,
        "warningCount": 1,
    }
]

SEMGREP_SAMPLE = {
    "results": [
        {
            "check_id": "python.lang.security.audit.dangerous-subprocess-use",
            "path": "src/run.py",
            "start": {"line": 12, "col": 5},
            "end": {"line": 12, "col": 30},
            "extra": {
                "message": "Detected subprocess call with shell=True",
                "severity": "ERROR",
            },
        }
    ],
    "errors": [],
}

TRUFFLEHOG_SAMPLE = "\n".join(
    [
        json.dumps(
            {
                "SourceMetadata": {
                    "Data": {"Filesystem": {"file": "src/config.py", "line": 7}}
                },
                "DetectorName": "AWS",
                "Verified": False,
            }
        ),
        json.dumps(
            {
                "SourceMetadata": {
                    "Data": {"Filesystem": {"file": "src/deploy.sh", "line": 2}}
                },
                "DetectorName": "PrivateKey",
                "Verified": True,
            }
        ),
    ]
)


def _fake_which(available: Iterable[str]):
    """Return a ``shutil.which`` replacement exposing only *available*."""
    available_set = set(available)

    def which(binary: str) -> Optional[str]:
        return f"/usr/bin/{binary}" if binary in available_set else None

    return which


def _spec(name: str) -> ToolSpec:
    """Return the built-in spec with *name*."""
    return next(spec for spec in tool_runner.BUILTIN_TOOL_SPECS if spec.name == name)


def _completed(stdout: str, returncode: int = 0) -> SimpleNamespace:
    """Build a minimal ``subprocess.CompletedProcess`` stand-in."""
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


class TestNormaliseRuff:
    """Ruff JSON output normalisation."""

    def test_normalises_findings(self) -> None:
        findings = normalise_ruff(RUFF_SAMPLE)

        assert findings[0] == {
            "file": "src/app.py",
            "line": 3,
            "rule_id": "F401",
            "tool": "ruff",
            "severity": "warning",
            "description": "`os` imported but unused",
        }
        assert findings[1]["rule_id"] == "E902"
        assert findings[1]["severity"] == "error"

    def test_malformed_payload_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            normalise_ruff({"unexpected": "object"})


class TestNormaliseEslint:
    """ESLint JSON output normalisation."""

    def test_normalises_findings_and_severity(self) -> None:
        findings = normalise_eslint(ESLINT_SAMPLE)

        assert len(findings) == 2
        assert findings[0] == {
            "file": "web/app.js",
            "line": 4,
            "rule_id": "no-unused-vars",
            "tool": "eslint",
            "severity": "error",
            "description": "'x' is assigned a value but never used.",
        }
        assert findings[1]["severity"] == "warning"
        assert findings[1]["rule_id"] == "semi"

    def test_missing_rule_id_falls_back_to_tool_name(self) -> None:
        payload = [{"filePath": "web/app.js", "messages": [{"severity": 2, "line": 1}]}]

        findings = normalise_eslint(payload)

        assert findings[0]["rule_id"] == "eslint"


class TestNormaliseSemgrep:
    """Semgrep JSON output normalisation."""

    def test_normalises_results(self) -> None:
        findings = normalise_semgrep(SEMGREP_SAMPLE)

        assert findings == [
            {
                "file": "src/run.py",
                "line": 12,
                "rule_id": "python.lang.security.audit.dangerous-subprocess-use",
                "tool": "semgrep",
                "severity": "error",
                "description": "Detected subprocess call with shell=True",
            }
        ]

    def test_scan_errors_become_findings(self) -> None:
        payload = {
            "results": [],
            "errors": [
                {
                    "path": "src/run.py",
                    "start": {"line": 1},
                    "message": "parse error",
                }
            ],
        }

        findings = normalise_semgrep(payload)

        assert findings[0]["rule_id"] == "semgrep_error"
        assert findings[0]["severity"] == "error"
        assert findings[0]["file"] == "src/run.py"


class TestNormaliseTrufflehog:
    """Trufflehog newline-delimited JSON normalisation."""

    def test_normalises_verified_and_unverified_findings(self) -> None:
        findings = normalise_trufflehog(TRUFFLEHOG_SAMPLE)

        assert findings[0] == {
            "file": "src/config.py",
            "line": 7,
            "rule_id": "AWS",
            "tool": "trufflehog",
            "severity": "medium",
            "description": "AWS credential detected",
        }
        assert findings[1]["severity"] == "high"
        assert findings[1]["description"] == "PrivateKey credential detected (verified)"

    def test_blank_lines_are_ignored(self) -> None:
        assert normalise_trufflehog("\n\n") == []

    def test_invalid_json_line_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            normalise_trufflehog("not json")


class TestAvailability:
    """Tool availability and changed-path filtering."""

    def test_list_tools_filters_by_changed_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            tool_runner.shutil,
            "which",
            _fake_which({"ruff", "eslint", "semgrep", "trufflehog"}),
        )
        runner = ToolRunner()

        python_tools = [spec.name for spec in runner.list_tools(["src/app.py"])]
        javascript_tools = [spec.name for spec in runner.list_tools(["web/app.ts"])]
        unknown_tools = [spec.name for spec in runner.list_tools(["README.md"])]

        assert python_tools == ["ruff", "semgrep", "trufflehog"]
        assert javascript_tools == ["eslint", "semgrep", "trufflehog"]
        assert unknown_tools == ["semgrep", "trufflehog"]

    def test_list_tools_without_paths_returns_only_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which({"ruff"}))

        names = [spec.name for spec in ToolRunner().list_tools()]

        assert names == ["ruff"]

    def test_missing_tools_are_skipped_from_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which(set()))

        runner = ToolRunner()

        assert runner.list_tools(["src/app.py"]) == []
        assert runner.list_tools() == []

    def test_spec_without_check_uses_shutil_which(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which({"custom-linter"}))
        spec = ToolSpec("custom", ["custom-linter"], ["*.py"])

        assert spec.is_available() is True


class TestRun:
    """Runner execution, missing tools, and failure handling."""

    def test_missing_tools_are_recorded_in_run_result(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which(set()))

        findings = ToolRunner().run(["src/app.py"], tmp_path)

        assert {finding["tool"] for finding in findings} == {
            "ruff",
            "semgrep",
            "trufflehog",
        }
        assert {finding["rule_id"] for finding in findings} == {RULE_TOOL_UNAVAILABLE}
        assert all(finding["severity"] == "info" for finding in findings)

    def test_timeout_returns_error_entry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which({"ruff"}))

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

        monkeypatch.setattr(tool_runner.subprocess, "run", fake_run)
        runner = ToolRunner(tools=[_spec("ruff")], timeout=5)

        findings = runner.run(["src/app.py"], tmp_path)

        assert len(findings) == 1
        assert findings[0]["rule_id"] == RULE_TOOL_TIMEOUT
        assert findings[0]["tool"] == "ruff"
        assert "5s" in findings[0]["description"]

    def test_spawn_error_returns_error_entry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which({"ruff"}))

        def fake_run(*args, **kwargs):
            raise OSError("boom")

        monkeypatch.setattr(tool_runner.subprocess, "run", fake_run)
        runner = ToolRunner(tools=[_spec("ruff")])

        findings = runner.run(["src/app.py"], tmp_path)

        assert findings[0]["rule_id"] == RULE_TOOL_ERROR
        assert "boom" in findings[0]["description"]

    def test_unparseable_output_returns_error_entry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which({"ruff"}))
        monkeypatch.setattr(
            tool_runner.subprocess, "run", lambda *args, **kwargs: _completed("not json")
        )
        runner = ToolRunner(tools=[_spec("ruff")])

        findings = runner.run(["src/app.py"], tmp_path)

        assert findings[0]["rule_id"] == RULE_TOOL_ERROR

    def test_empty_output_with_nonzero_exit_returns_error_entry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which({"ruff"}))
        monkeypatch.setattr(
            tool_runner.subprocess,
            "run",
            lambda *args, **kwargs: _completed("", returncode=2),
        )
        runner = ToolRunner(tools=[_spec("ruff")])

        findings = runner.run(["src/app.py"], tmp_path)

        assert findings[0]["rule_id"] == RULE_TOOL_ERROR
        assert "code 2" in findings[0]["description"]

    def test_runs_only_applicable_tool_and_normalises_output(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(tool_runner.shutil, "which", _fake_which({"ruff"}))
        captured: dict = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return _completed(json.dumps(RUFF_SAMPLE), returncode=1)

        monkeypatch.setattr(tool_runner.subprocess, "run", fake_run)
        runner = ToolRunner(tools=[_spec("ruff")])

        findings = runner.run(["src/app.py", "web/app.js", "src/app.py"], tmp_path)

        assert len(findings) == 2
        assert all(set(finding) == FINDING_KEYS for finding in findings)
        assert captured["command"] == [
            "ruff",
            "check",
            "--output-format",
            "json",
            "src/app.py",
        ]
        assert captured["kwargs"]["cwd"] == str(tmp_path)
        assert captured["kwargs"]["capture_output"] is True
        assert captured["kwargs"]["timeout"] == 60.0
        assert "shell" not in captured["kwargs"]

    def test_no_paths_returns_empty_without_running(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        called = False

        def fake_run(*args, **kwargs):
            nonlocal called
            called = True
            return _completed("[]")

        monkeypatch.setattr(tool_runner.subprocess, "run", fake_run)

        assert ToolRunner().run([], tmp_path) == []
        assert called is False
