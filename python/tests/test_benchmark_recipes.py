"""Tests for the injected-case generator's write/check safety."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.benchmark import gen_cases


def _write_case(path: Path, origin: str, diff: str = "diff --git a/x b/x\n") -> None:
    path.write_text(
        yaml.safe_dump(
            {"id": path.stem, "origin": origin, "diff": diff},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_prune_stale_keeps_real_pr_cases(tmp_path: Path) -> None:
    real = tmp_path / "real-curated.yaml"
    injected = tmp_path / "old-recipe.yaml"
    _write_case(real, "real-pr")
    _write_case(injected, "injected")

    gen_cases._prune_stale(tmp_path, wanted=set())

    assert real.exists()
    assert not injected.exists()


def test_prune_stale_keeps_unreadable_origin(tmp_path: Path) -> None:
    unknown = tmp_path / "mystery.yaml"
    _write_case(unknown, "curated")

    gen_cases._prune_stale(tmp_path, wanted=set())

    assert unknown.exists()


def test_check_fails_when_committed_case_is_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for path in (gen_cases.BENCH_DIR / "cases").glob("*.yaml"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    recipe = gen_cases.RECIPES[0]
    case = gen_cases._build_case(recipe)
    case["expect"]["line"] += 1
    (tmp_path / f"{case['id']}.yaml").write_text(
        yaml.safe_dump(case, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    assert gen_cases.main(["--check"], cases_dir=tmp_path) != 0
    assert f"FAIL {case['id']}: committed case is stale (run --write)" in capsys.readouterr().out


def test_check_passes_with_fresh_cases(tmp_path: Path) -> None:
    for path in (gen_cases.BENCH_DIR / "cases").glob("*.yaml"):
        (tmp_path / path.name).write_bytes(path.read_bytes())

    assert gen_cases.main(["--check"], cases_dir=tmp_path) == 0
