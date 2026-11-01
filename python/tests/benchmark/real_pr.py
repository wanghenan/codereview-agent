"""Materialise the base commit a real-PR benchmark case is anchored to.

Injected cases mutate this repository, so ``git apply --check`` in the repo root
is their validation. Real-PR cases come from other repositories and must be
reviewed against *their* tree: the symbol index, the project analysis, and the
files the reviewer is reading all have to be the upstream ones.

So each case carries ``repo`` + ``base_commit``, and this module fetches that
commit as a tarball into ``.repos/`` (git-ignored) on first use. A tarball is
used instead of a clone on purpose: a filtered clone of a large repo takes
minutes, while the commit tarball is a single request, and ``git apply`` works
outside a repository so no ``.git`` is needed.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

BENCH_DIR = Path(__file__).resolve().parent
CHECKOUT_ROOT = BENCH_DIR / ".repos"


def checkout_dir(repo: str, sha: str) -> Path:
    """Directory holding the extracted tree for ``repo`` at ``sha``."""
    owner, name = repo.split("/", 1)
    return CHECKOUT_ROOT / f"{owner}-{name}-{sha[:10]}"


def _fetch_tarball(repo: str, sha: str) -> bytes:
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/tarball/{sha}"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.decode("utf-8", "replace").strip()
            or f"could not download {repo}@{sha}"
        )
    return proc.stdout


def _extract(archive: bytes, target: Path) -> None:
    """Extract a GitHub tarball, stripping its single top-level directory."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(target.parent)) as tmp:
        tarball = Path(tmp) / "src.tar.gz"
        tarball.write_bytes(archive)
        with tarfile.open(tarball, "r:gz") as tar:
            tar.extractall(tmp)
        tops = [p for p in Path(tmp).iterdir() if p.is_dir()]
        if len(tops) != 1:
            raise RuntimeError(f"unexpected archive layout: {len(tops)} top-level dirs")
        shutil.move(str(tops[0]), str(target))


def ensure_checkout(repo: str, sha: str) -> Path:
    """Return the extracted tree for ``repo@sha``, downloading it once."""
    target = checkout_dir(repo, sha)
    if target.is_dir() and any(target.iterdir()):
        return target
    if target.exists():
        shutil.rmtree(target)
    _extract(_fetch_tarball(repo, sha), target)
    return target


def case_checkout(case: dict) -> Optional[Path]:
    """Checkout directory for a real-PR case, or ``None`` for injected cases."""
    if case.get("origin") != "real-pr":
        return None
    return ensure_checkout(case["repo"], case["base_commit"])
