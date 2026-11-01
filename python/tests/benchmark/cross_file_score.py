"""Score cross-file cases by whether the review cites the actual caller.

The line-match metric in :mod:`bench` cannot tell a hedged guess ("some caller
may break") from evidence ("review_cmd.py:215 still calls .build(...)"). This
script measures the difference: for every case tagged ``cross-file`` it checks
whether a finding names the caller file and its line.

Usage::

    python -m tests.benchmark.cross_file_score reports/xfile-on.md reports/xfile-off.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

CASES_DIR = Path(__file__).resolve().parent / "cases"


def load_callers() -> dict[str, tuple[str, str, str]]:
    """Return ``{case_id: (caller_path, caller_basename, caller_line)}``."""
    callers = {}
    for path in CASES_DIR.glob("*.yaml"):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        cross_file = case.get("cross_file")
        if not cross_file:
            continue
        caller_path, caller_line = cross_file["caller"].rsplit(":", 1)
        callers[case["id"]] = (
            caller_path,
            Path(caller_path).name,
            caller_line,
        )
    return callers


def score(report: Path, callers: dict[str, tuple[str, str, str]]) -> dict[str, tuple[bool, bool, float]]:
    """Return ``{case_id: (names_caller_file, names_caller_line, max_confidence)}``."""
    text = report.read_text(encoding="utf-8")
    results = {}
    for section in re.split(r"\n## ", text)[1:]:
        case_id = section.splitlines()[0].split(" · ")[0]
        if case_id not in callers:
            continue
        caller_path, basename, line = callers[case_id]
        body = section.split("**findings**", 1)[-1]
        confidences = [float(value) for value in re.findall(r"conf=([\d.]+)", body)]
        structured = re.findall(r"caller=([^\s\]]+)", body)
        names_file = basename in body or any(
            value.startswith(caller_path[: -len(basename)]) and value.endswith(basename + ":" + line)
            for value in structured
        )
        # A citer may point at the call or at the keyword argument a few lines
        # below it; accept a small window instead of demanding one exact row.
        def _near(value: str) -> bool:
            prefix = f"{caller_path}:"
            if not value.startswith(prefix):
                return False
            try:
                return abs(int(value[len(prefix):]) - int(line)) <= 5
            except ValueError:
                return False

        names_line = any(_near(value) for value in structured) or (
            re.search(rf"{re.escape(basename)}[^\n]{{0,40}}[:#]?{line}\b", body) is not None
        )
        results[case_id] = (names_file, names_line, max(confidences, default=0.0))
    return results


def main(argv: list[str]) -> int:
    """Print a side-by-side specificity table for the given reports."""
    if not argv:
        print(__doc__)
        return 2
    callers = load_callers()
    scored = [(Path(report), score(Path(report), callers)) for report in argv]

    header = "case".ljust(36) + "".join(path.stem.ljust(22) for path, _ in scored)
    print(header)
    for case_id in sorted(callers):
        row = case_id.ljust(36)
        for _, result in scored:
            names_file, names_line, confidence = result.get(case_id, (False, False, 0.0))
            row += f"{str(names_file)[:5]:5s}/{str(names_line)[:5]:5s}/{confidence:.2f}".ljust(22)
        print(row)
    print()
    for path, result in scored:
        files = sum(1 for value in result.values() if value[0])
        lines = sum(1 for value in result.values() if value[1])
        mean = sum(value[2] for value in result.values()) / max(len(result), 1)
        print(f"{path.stem}: caller file {files}/{len(result)}, caller line {lines}/{len(result)}, "
              f"mean confidence {mean:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
