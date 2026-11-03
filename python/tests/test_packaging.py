"""Packaging must ship the runtime data the CLI loads.

v1.3.0 shipped a wheel without `rules/owasp_rules.yaml`, so the installed CLI
loaded zero detection rules while a source checkout worked fine. The release
workflow now smoke-tests the wheel; this test catches the declaration being
deleted before a tag is ever cut.
"""

from __future__ import annotations

import re
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
RULES_YAML = Path(__file__).resolve().parents[1] / "src" / "codereview" / "rules" / "owasp_rules.yaml"


def test_rules_yaml_is_declared_as_package_data() -> None:
    """`[tool.setuptools.package-data]` must include the rules directory's YAML."""
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(
        r"\[tool\.setuptools\.package-data\](.*?)(?=^\[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "pyproject.toml has no package-data section"
    assert re.search(r'"codereview\.rules"\s*=\s*\[[^\]]*"\*\.yaml"', match.group(1)), (
        "package-data must map codereview.rules to *.yaml"
    )
    assert RULES_YAML.is_file(), "the declared rules YAML does not exist"
