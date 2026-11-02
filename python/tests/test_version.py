"""The package version must match the distribution metadata in pyproject.toml.

`codereview --version` and the changelog drifted apart before (the installed
metadata said 1.1.0 while `pyproject.toml` said 1.2.0), so the two sources are
compared here instead of relying on a release checklist.

The version line is read with a regex rather than `tomllib`, which only exists
on Python 3.11+ while the CI matrix still covers 3.10.
"""

from __future__ import annotations

import re
from pathlib import Path

import codereview

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def test_package_version_matches_pyproject() -> None:
    """`codereview.__version__` and `[project].version` are the same string."""
    match = VERSION_LINE.search(PYPROJECT.read_text(encoding="utf-8"))
    assert match is not None, "pyproject.toml has no version line"
    assert codereview.__version__ == match.group(1)
