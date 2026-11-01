"""Tests for S5b cross-file symbol context injection."""

from __future__ import annotations

import json
import logging
import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import RunnableLambda

from codereview.agents.reviewer import ReviewAgent, ReviewOrchestrator
from codereview.core.symbol_index import SymbolIndex
from codereview.models import (
    Config,
    ConfigContext,
    ConfigLLM,
    DiffEntry,
    FileReview,
    LLMProvider,
    ProjectContext,
    RiskLevel,
)


def _write(root: Path, rel_path: str, content: str) -> Path:
    """Write a dedented source file under ``root`` and return its path."""
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


def _config(**context_kwargs) -> Config:
    """Build a Config with optional non-default context settings."""
    return Config(
        llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="test-key"),
        context=ConfigContext(**context_kwargs),
    )


def _project_context() -> ProjectContext:
    """Build the minimal project context needed by ReviewAgent."""
    return ProjectContext(
        language="python",
        critical_paths=[],
        analyzed_at="2024-01-01T00:00:00Z",
    )


def _target_entry() -> DiffEntry:
    """A diff entry whose changed range covers ``target`` in lib.py lines 1-2."""
    return DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n def target():",
    )


def _build_index(root: Path) -> SymbolIndex:
    """Build an index for a temporary repository."""
    index = SymbolIndex()
    index.build(root)
    return index


def _callers_repo(root: Path) -> None:
    """Create a target plus app.py, which both imports and calls it."""
    _write(root, "lib.py", "def target():\n    return 1\n")
    _write(
        root,
        "app.py",
        """
        from lib import target

        def use():
            return target()
        """,
    )


def test_neighbor_section_has_reason_path_range_and_excerpt(tmp_path: Path) -> None:
    """Rendered neighbours include the reason, file:range header and excerpt."""
    _callers_repo(tmp_path)
    agent = ReviewAgent(
        _config(),
        MagicMock(),
        _project_context(),
        project_root=tmp_path,
        symbol_index=_build_index(tmp_path),
    )

    context = agent._cross_file_context_for(_target_entry())

    assert context.startswith("## Cross-file context")
    assert re.search(r"^caller app\.py:\d+-\d+$", context, re.MULTILINE)
    assert re.search(r"^import app\.py:\d+-\d+$", context, re.MULTILINE)
    assert "def use():" in context
    assert "return target()" in context
    assert "from lib import target" in context


@pytest.mark.asyncio
async def test_review_file_injects_section_into_actual_prompt(tmp_path: Path) -> None:
    """The section is sent to the model through the real prompt chain."""
    _callers_repo(tmp_path)
    captured: list[object] = []

    async def fake_llm(messages):
        captured.append(messages)
        return json.dumps({"risk_level": "low", "issues": [], "summary": "ok"})

    agent = ReviewAgent(
        _config(),
        RunnableLambda(fake_llm),
        _project_context(),
        project_root=tmp_path,
        symbol_index=_build_index(tmp_path),
    )

    await agent._review_file(_target_entry())

    assert captured, "the fake LLM was never invoked"
    rendered = "\n".join(message.content for message in captured[0].to_messages())
    assert "## Cross-file context" in rendered
    assert "caller app.py:" in rendered
    assert "return target()" in rendered


def test_max_neighbors_limits_the_number_of_sections(tmp_path: Path) -> None:
    """At most ``context.max_neighbors`` neighbour blocks are rendered."""
    _write(tmp_path, "lib.py", "def target():\n    return 1\n")
    for name in ("a.py", "b.py", "c.py"):
        _write(tmp_path, name, f"from lib import target\n\ndef use_{name[0]}():\n    return target()\n")

    index = _build_index(tmp_path)
    agent = ReviewAgent(
        _config(max_neighbors=1),
        MagicMock(),
        _project_context(),
        project_root=tmp_path,
        symbol_index=index,
    )

    context = agent._cross_file_context_for(_target_entry())
    headers = re.findall(r"^(?:caller|import|sibling) ", context, re.MULTILINE)
    assert len(headers) == 1


def test_max_chars_truncates_the_tail_and_notes_it(tmp_path: Path) -> None:
    """The section respects ``context.max_chars`` and marks truncation."""
    _callers_repo(tmp_path)
    agent = ReviewAgent(
        _config(max_neighbors=4, max_chars=120),
        MagicMock(),
        _project_context(),
        project_root=tmp_path,
        symbol_index=_build_index(tmp_path),
    )

    context = agent._cross_file_context_for(_target_entry())

    assert len(context) <= 120
    assert "truncated" in context
    assert context.startswith("## Cross-file context")


def test_empty_index_yields_no_section(tmp_path: Path) -> None:
    """An empty or absent index leaves the prompt unchanged."""
    empty = SymbolIndex()
    empty.build(tmp_path)

    entry = _target_entry()
    for index in (empty, None):
        agent = ReviewAgent(
            _config(),
            MagicMock(),
            _project_context(),
            project_root=tmp_path,
            symbol_index=index,
        )
        assert agent._cross_file_context_for(entry) == ""


def test_corrupt_index_degrades_with_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A fresh but corrupt index is not rebuilt and never aborts the review."""
    _write(tmp_path, "lib.py", "def target():\n    return 1\n")
    index_path = tmp_path / ".codereview-agent" / "index.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text("{not valid json", encoding="utf-8")

    def fail_build(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("build must not run for a fresh corrupt index")

    monkeypatch.setattr(SymbolIndex, "build", fail_build)
    orchestrator = ReviewOrchestrator(_config(), MagicMock(), project_root=tmp_path)

    with caplog.at_level(logging.WARNING, logger="codereview.agents.reviewer"):
        result = orchestrator._load_or_build_symbol_index()

    assert result is None
    assert any("symbol index" in record.getMessage().lower() for record in caplog.records)


@pytest.mark.asyncio
async def test_orchestrator_builds_once_and_reuses_the_saved_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One build per run at most; later runs load the persisted index."""
    _callers_repo(tmp_path)
    builds = 0
    original_build = SymbolIndex.build

    def counting_build(self, root, paths=None):  # noqa: ANN001
        nonlocal builds
        builds += 1
        return original_build(self, root, paths)

    monkeypatch.setattr(SymbolIndex, "build", counting_build)

    async def fake_review_files(self, diff_entries):  # noqa: ANN001
        return [
            FileReview(
                file_path=entry.filename,
                risk_level=RiskLevel.LOW,
                changes="+1, -1",
                issues=[],
            )
            for entry in diff_entries
        ]

    monkeypatch.setattr(ReviewAgent, "review_files", fake_review_files)

    orchestrator = ReviewOrchestrator(_config(), MagicMock(), project_root=tmp_path)
    entries = [
        _target_entry(),
        DiffEntry(
            filename="app.py",
            status="modified",
            additions=1,
            deletions=1,
            patch="@@ -1,2 +1,2 @@",
        ),
    ]

    first = await orchestrator.run_review(entries)
    assert builds == 1
    assert len(first.files_reviewed) == 2

    second = await orchestrator.run_review(entries)
    assert builds == 1
    assert len(second.files_reviewed) == 2


def test_no_python_sources_does_not_build_an_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repositories without Python files keep today's review behaviour."""
    _write(tmp_path, "web.ts", "export function target() {}\n")
    builds = 0

    def counting_build(self, root, paths=None):  # noqa: ANN001
        nonlocal builds
        builds += 1
        raise AssertionError("no index should be built without Python sources")

    monkeypatch.setattr(SymbolIndex, "build", counting_build)
    orchestrator = ReviewOrchestrator(_config(), MagicMock(), project_root=tmp_path)

    assert orchestrator._load_or_build_symbol_index() is None
    assert builds == 0


def test_missing_index_with_auto_build_off_does_not_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing index is left alone when ``context.auto_build`` is disabled."""
    _write(tmp_path, "lib.py", "def target():\n    return 1\n")
    builds = 0

    def counting_build(self, root, paths=None):  # noqa: ANN001
        nonlocal builds
        builds += 1
        raise AssertionError("auto_build is disabled; build must not run")

    monkeypatch.setattr(SymbolIndex, "build", counting_build)
    orchestrator = ReviewOrchestrator(
        _config(auto_build=False), MagicMock(), project_root=tmp_path
    )

    assert orchestrator._load_or_build_symbol_index() is None
    assert builds == 0


def test_custom_prompt_without_cross_file_variable_still_renders(tmp_path: Path) -> None:
    """Older custom templates that omit the new variable keep working."""
    template = tmp_path / "custom_prompt.txt"
    template.write_text("Review {filename} ({status})\n{patch}", encoding="utf-8")

    config = _config()
    config.custom_prompt_path = str(template)
    agent = ReviewAgent(config, MagicMock(), _project_context())

    prompt = agent._build_prompt(_target_entry())
    messages = prompt.format_messages(
        filename="lib.py",
        status="modified",
        patch="@@ -1,2 +1,2 @@",
    )

    assert "lib.py" in messages[0].content
    assert "Review lib.py (modified)" in messages[0].content
