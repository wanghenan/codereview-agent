"""Run external linters and normalise their output into review findings.

The runner is deliberately small and dependency-free: it shells out to
well-known developer tools, applies a timeout, and converts each tool's
native JSON output into a stable finding shape.  It never raises for
subprocess or parsing failures; those become error entries so the review
pipeline can continue.

Normalisers are pure functions so they can be tested with captured output
without installing the underlying binaries.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import shutil
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

DEFAULT_TIMEOUT_SECONDS = 60.0

# Rule ids used for runner-level error entries.  Real findings use the
# linter's own rule/check id.
RULE_TOOL_UNAVAILABLE = "tool_unavailable"
RULE_TOOL_TIMEOUT = "tool_timeout"
RULE_TOOL_ERROR = "tool_error"

Finding = dict


@dataclass
class ToolSpec:
    """Description of an external tool and the files it should scan.

    Attributes:
        name: Stable tool name used as the ``tool`` field in findings.
        command: Command and fixed arguments; changed paths are appended.
        file_patterns: Glob patterns the tool applies to.
        available_check: Callable returning ``True`` when the binary exists.
    """

    name: str
    command: Sequence[str]
    file_patterns: Sequence[str]
    available_check: Optional[Callable[[], bool]] = None

    def is_available(self) -> bool:
        """Return whether the tool can be executed, never raising."""
        if self.available_check is None:
            binary = self.command[0] if self.command else ""
            return bool(binary) and shutil.which(binary) is not None
        try:
            return bool(self.available_check())
        except Exception:  # pragma: no cover - defensive; checks are simple
            return False

    def matches(self, path: PathLike) -> bool:
        """Return whether *path* is handled by this tool."""
        text = str(path)
        basename = Path(text).name
        return any(
            fnmatch.fnmatch(text, pattern) or fnmatch.fnmatch(basename, pattern)
            for pattern in self.file_patterns
        )


def _binary_available(binary: str) -> Callable[[], bool]:
    """Build an availability check for a binary found via ``shutil.which``."""

    def check() -> bool:
        return shutil.which(binary) is not None

    return check


BUILTIN_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="ruff",
        command=("ruff", "check", "--output-format", "json"),
        file_patterns=("*.py", "*.pyi"),
        available_check=_binary_available("ruff"),
    ),
    ToolSpec(
        name="eslint",
        command=("eslint", "-f", "json"),
        file_patterns=("*.js", "*.jsx", "*.ts", "*.tsx", "*.mjs", "*.cjs"),
        available_check=_binary_available("eslint"),
    ),
    ToolSpec(
        name="semgrep",
        command=("semgrep", "--json"),
        # Semgrep supports many languages; let it decide what it can parse.
        file_patterns=("*",),
        available_check=_binary_available("semgrep"),
    ),
    ToolSpec(
        name="trufflehog",
        command=("trufflehog", "filesystem", "--json"),
        # Secret scanning is language independent.
        file_patterns=("*",),
        available_check=_binary_available("trufflehog"),
    ),
)


def _finding(
    file: str,
    line: int,
    rule_id: str,
    tool: str,
    severity: str,
    description: str,
) -> Finding:
    """Build the normalised finding shape shared by every tool."""
    return {
        "file": file,
        "line": line,
        "rule_id": rule_id,
        "tool": tool,
        "severity": severity,
        "description": description,
    }


def _as_int(value: object, default: int = 0) -> int:
    """Coerce a tool-reported line number to ``int`` without raising."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_dict(value: object) -> dict:
    """Return *value* when it is a dict, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    """Return *value* when it is a list, otherwise an empty list."""
    return value if isinstance(value, list) else []


def _ruff_severity(code: str) -> str:
    """Map a ruff rule code to a coarse severity.

    Ruff has no severity field.  Syntax errors and fatal parser failures are
    the only rules treated as errors; everything else is a warning.
    """
    if code.startswith(("E9", "F81", "F82")):
        return "error"
    return "warning"


def normalise_ruff(payload: object) -> list[Finding]:
    """Normalise ``ruff check --output-format json`` output."""
    if not isinstance(payload, list):
        raise ValueError("ruff JSON payload must be a list")

    findings: list[Finding] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        location = _as_dict(item.get("location"))
        code = str(item.get("code") or "ruff")
        findings.append(
            _finding(
                file=str(item.get("filename") or ""),
                line=_as_int(location.get("row")),
                rule_id=code,
                tool="ruff",
                severity=_ruff_severity(code),
                description=str(item.get("message") or ""),
            )
        )
    return findings


def _eslint_severity(severity: object) -> str:
    """Map ESLint's numeric severity (1 warning, 2 error) to a string."""
    if severity == 2:
        return "error"
    if severity == 1:
        return "warning"
    return "info"


def normalise_eslint(payload: object) -> list[Finding]:
    """Normalise ``eslint -f json`` output."""
    if not isinstance(payload, list):
        raise ValueError("eslint JSON payload must be a list")

    findings: list[Finding] = []
    for file_result in payload:
        if not isinstance(file_result, dict):
            continue
        file_path = str(file_result.get("filePath") or file_result.get("file") or "")
        for message in _as_list(file_result.get("messages")):
            if not isinstance(message, dict):
                continue
            findings.append(
                _finding(
                    file=file_path,
                    line=_as_int(message.get("line")),
                    rule_id=str(message.get("ruleId") or "eslint"),
                    tool="eslint",
                    severity=_eslint_severity(message.get("severity")),
                    description=str(message.get("message") or ""),
                )
            )
    return findings


def _semgrep_severity(severity: object) -> str:
    """Map Semgrep's uppercase severity to a lowercase string."""
    value = str(severity or "WARNING").lower()
    if value in {"error", "warning", "info"}:
        return value
    return "warning"


def normalise_semgrep(payload: object) -> list[Finding]:
    """Normalise ``semgrep --json`` output.

    Scan-level errors are surfaced as ``semgrep_error`` findings so callers do
    not silently lose a partially failed scan.
    """
    if not isinstance(payload, dict):
        raise ValueError("semgrep JSON payload must be an object")

    findings: list[Finding] = []
    for result in _as_list(payload.get("results")):
        if not isinstance(result, dict):
            continue
        extra = _as_dict(result.get("extra"))
        start = _as_dict(result.get("start"))
        findings.append(
            _finding(
                file=str(result.get("path") or ""),
                line=_as_int(start.get("line")),
                rule_id=str(result.get("check_id") or "semgrep"),
                tool="semgrep",
                severity=_semgrep_severity(extra.get("severity")),
                description=str(extra.get("message") or ""),
            )
        )

    for error in _as_list(payload.get("errors")):
        if not isinstance(error, dict):
            continue
        start = _as_dict(error.get("start"))
        findings.append(
            _finding(
                file=str(error.get("path") or ""),
                line=_as_int(start.get("line")),
                rule_id="semgrep_error",
                tool="semgrep",
                severity="error",
                description=str(error.get("message") or "semgrep scan error"),
            )
        )
    return findings


def _trufflehog_location(item: dict) -> tuple[str, int]:
    """Extract the file and line from a trufflehog JSON line."""
    data = _as_dict(_as_dict(item.get("SourceMetadata")).get("Data"))
    for source in data.values():
        if not isinstance(source, dict):
            continue
        file_path = source.get("file") or source.get("File")
        if file_path:
            return str(file_path), _as_int(source.get("line") or source.get("Line"))
    return "", 0


def normalise_trufflehog(output: str) -> list[Finding]:
    """Normalise ``trufflehog filesystem --json`` newline-delimited output."""
    if not isinstance(output, str):
        raise ValueError("trufflehog output must be a string")

    findings: list[Finding] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid trufflehog JSON line: {exc}") from exc
        if not isinstance(item, dict):
            continue

        file_path, line_number = _trufflehog_location(item)
        detector = str(
            item.get("DetectorName") or item.get("DetectorType") or "trufflehog"
        )
        verified = bool(item.get("Verified"))
        description = f"{detector} credential detected"
        if verified:
            description += " (verified)"
        findings.append(
            _finding(
                file=file_path,
                line=line_number,
                rule_id=detector,
                tool="trufflehog",
                severity="high" if verified else "medium",
                description=description,
            )
        )
    return findings


_NORMALISERS: dict[str, Callable[[object], list[Finding]]] = {
    "ruff": normalise_ruff,
    "eslint": normalise_eslint,
    "semgrep": normalise_semgrep,
    "trufflehog": normalise_trufflehog,  # type: ignore[dict-item]
}


def _error_finding(tool: str, rule_id: str, description: str) -> Finding:
    """Build an error entry in the same shape as a normalised finding."""
    severity = "info" if rule_id == RULE_TOOL_UNAVAILABLE else "error"
    return _finding(
        file="",
        line=0,
        rule_id=rule_id,
        tool=tool,
        severity=severity,
        description=description,
    )


def _relativise_findings(findings: list[Finding], cwd: PathLike) -> list[Finding]:
    """Rewrite absolute tool paths as paths relative to the scanned root.

    Tools disagree about path form: ruff echoes the relative path it was given
    when it can resolve a project root, but reports an absolute one otherwise
    (no pyproject.toml, a path outside the root, another tool's own resolving).
    Findings are matched against repository-relative diff entries and posted as
    inline PR comments, and GitHub rejects an absolute path, so normalise here
    rather than in every normaliser.
    """
    try:
        root = Path(cwd).resolve()
    except OSError:  # unreadable cwd: keep the findings exactly as reported
        return findings

    normalised: list[Finding] = []
    for finding in findings:
        raw = finding.get("file")
        if raw:
            path = Path(str(raw))
            if path.is_absolute():
                try:
                    finding = {**finding, "file": path.resolve().relative_to(root).as_posix()}
                except (OSError, ValueError):
                    pass  # outside the scanned root: leave it visible as reported
        normalised.append(finding)
    return normalised


class ToolRunner:
    """Run available external tools against a set of changed paths."""

    def __init__(
        self,
        tools: Optional[Iterable[ToolSpec]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialise the runner.

        Args:
            tools: Tool specs to use; defaults to :data:`BUILTIN_TOOL_SPECS`.
            timeout: Per-command timeout in seconds.
        """
        self.tools: list[ToolSpec] = list(tools) if tools is not None else list(
            BUILTIN_TOOL_SPECS
        )
        self.timeout = timeout

    @staticmethod
    def _as_paths(paths: Iterable[PathLike]) -> list[str]:
        """Coerce a path or iterable of paths into a de-duplicated string list."""
        if isinstance(paths, (str, Path)):
            values: Iterable[PathLike] = [paths]
        else:
            values = paths
        # Preserve order while dropping duplicates.
        return list(dict.fromkeys(str(path) for path in values))

    def list_tools(self, paths: Optional[Iterable[PathLike]] = None) -> list[ToolSpec]:
        """Return available tools relevant to *paths*.

        Args:
            paths: Changed file paths.  When omitted, every available tool is
                returned regardless of language.

        Returns:
            Available :class:`ToolSpec` instances, in built-in order.
        """
        changed = self._as_paths(paths) if paths is not None else None
        selected: list[ToolSpec] = []
        for spec in self.tools:
            if not spec.is_available():
                continue
            if changed is not None and not any(spec.matches(path) for path in changed):
                continue
            selected.append(spec)
        return selected

    def run(self, paths: Iterable[PathLike], cwd: PathLike) -> list[Finding]:
        """Run every applicable available tool and return normalised findings.

        Missing tools are skipped without raising but recorded as a
        ``tool_unavailable`` entry.  Timeouts, spawn failures and malformed
        output are recorded as ``tool_timeout`` / ``tool_error`` entries.

        Args:
            paths: Changed file paths to scan.
            cwd: Working directory for the subprocesses.

        Returns:
            A list of finding dictionaries with keys ``file``, ``line``,
            ``rule_id``, ``tool``, ``severity`` and ``description``.
        """
        changed = self._as_paths(paths)
        if not changed:
            return []

        findings: list[Finding] = []
        for spec in self.tools:
            matched = [path for path in changed if spec.matches(path)]
            if not matched:
                continue
            findings.extend(self._run_spec(spec, matched, cwd))
        return findings

    def _run_spec(self, spec: ToolSpec, paths: list[str], cwd: PathLike) -> list[Finding]:
        """Run a single spec, converting failures into error entries."""
        if not spec.is_available():
            return [
                _error_finding(
                    spec.name,
                    RULE_TOOL_UNAVAILABLE,
                    f"{spec.name} is not installed; skipped",
                )
            ]

        command = [*spec.command, *paths]
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return [
                _error_finding(
                    spec.name,
                    RULE_TOOL_TIMEOUT,
                    f"{spec.name} timed out after {self.timeout:g}s",
                )
            ]
        except FileNotFoundError:
            return [
                _error_finding(
                    spec.name,
                    RULE_TOOL_UNAVAILABLE,
                    f"{spec.name} executable not found; skipped",
                )
            ]
        except OSError as exc:
            return [
                _error_finding(
                    spec.name,
                    RULE_TOOL_ERROR,
                    f"{spec.name} failed to start: {exc}",
                )
            ]
        except Exception as exc:  # defensively never propagate runner failures
            return [
                _error_finding(
                    spec.name,
                    RULE_TOOL_ERROR,
                    f"{spec.name} failed: {exc}",
                )
            ]

        stdout = completed.stdout or ""
        normaliser = _NORMALISERS.get(spec.name)
        if normaliser is None:
            return [
                _error_finding(
                    spec.name,
                    RULE_TOOL_ERROR,
                    f"no output normaliser registered for {spec.name}",
                )
            ]

        if not stdout.strip():
            if completed.returncode == 0:
                return []
            return [
                _error_finding(
                    spec.name,
                    RULE_TOOL_ERROR,
                    f"{spec.name} exited with code {completed.returncode} and no output",
                )
            ]

        try:
            parsed = normaliser(stdout) if spec.name == "trufflehog" else normaliser(
                json.loads(stdout)
            )
            return _relativise_findings(parsed, cwd)
        except Exception as exc:  # malformed output must never abort the run
            return [
                _error_finding(
                    spec.name,
                    RULE_TOOL_ERROR,
                    f"could not parse {spec.name} output: {exc}",
                )
            ]
