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
from codereview.core.symbol_index import SymbolIndex, definition_spans
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


# ---------------------------------------------------------------------------
# context.neighbors_trigger
# ---------------------------------------------------------------------------


def _agent_for(tmp_path: Path, **context_kwargs) -> ReviewAgent:
    """Build an agent over ``tmp_path`` with a freshly built symbol index."""
    return ReviewAgent(
        _config(**context_kwargs),
        MagicMock(),
        _project_context(),
        project_root=tmp_path,
        symbol_index=_build_index(tmp_path),
    )


def _body_change_entry() -> DiffEntry:
    """A diff whose added and deleted lines stay inside ``target``'s body."""
    return DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n def target():\n-    return 1\n+    return 2",
    )


def test_definition_spans_cover_decorators_params_and_one_liners() -> None:
    """Spans start at decorators and their header ends before the body."""
    source = (
        "@lru_cache\n"
        "def target(\n"
        "    a,\n"
        "    b,\n"
        "):\n"
        "    return a\n"
        "\n"
        "class A(Base):\n"
        "    x = 1\n"
        "\n"
        "def one(): return 1\n"
    )

    assert sorted(definition_spans(source)) == [(1, 6, 5), (8, 9, 8), (11, 11, 11)]


def test_definition_spans_include_nested_definitions() -> None:
    """A span covers the whole definition while its header ends before the body."""
    source = (
        "@dec\n"
        "def outer(\n"
        "    a,\n"
        "):\n"
        "    def inner():\n"
        "        return a\n"
        "    return inner()\n"
    )

    assert sorted(definition_spans(source)) == [(1, 7, 4), (5, 6, 5)]


def test_default_trigger_still_injects_for_body_only_changes(tmp_path: Path) -> None:
    """The default ``always`` keeps injecting for body-level edits."""
    _callers_repo(tmp_path)
    _write(tmp_path, "lib.py", "def target():\n    return 2\n")
    entry = _body_change_entry()

    context = _agent_for(tmp_path)._cross_file_context_for(entry)

    assert context.startswith("## Cross-file context")
    assert "return target()" in context


def test_signature_trigger_injects_on_signature_change(tmp_path: Path) -> None:
    """A changed ``def`` line is a definition header and injects neighbours."""
    _write(tmp_path, "lib.py", "def target(a, b):\n    return a\n")
    _write(
        tmp_path,
        "app.py",
        "from lib import target\n\ndef use():\n    return target(1, 2)\n",
    )
    entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n-def target(a):\n+def target(a, b):\n     return a",
    )

    context = _agent_for(tmp_path, neighbors_trigger="signature")._cross_file_context_for(entry)

    assert context.startswith("## Cross-file context")
    assert "caller app.py:" in context


def test_signature_trigger_injects_on_added_decorator(tmp_path: Path) -> None:
    """An added decorator line is part of the definition header."""
    _callers_repo(tmp_path)
    _write(tmp_path, "lib.py", "@lru_cache\ndef target():\n    return 1\n")
    entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=0,
        patch="@@ -1,2 +1,3 @@\n+@lru_cache\n def target():\n     return 1",
    )

    context = _agent_for(tmp_path, neighbors_trigger="signature")._cross_file_context_for(entry)

    assert context.startswith("## Cross-file context")


def test_signature_trigger_injects_on_multiline_parameter_insertion(tmp_path: Path) -> None:
    """A parameter added between existing lines is still in the header."""
    _callers_repo(tmp_path)
    _write(
        tmp_path,
        "lib.py",
        "def target(\n    a,\n    c,\n    b,\n):\n    return a\n",
    )
    entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=0,
        patch="@@ -1,5 +1,6 @@\n def target(\n     a,\n+    c,\n     b,\n ):\n     return a",
    )

    context = _agent_for(tmp_path, neighbors_trigger="signature")._cross_file_context_for(entry)

    assert context.startswith("## Cross-file context")


def test_signature_trigger_injects_on_class_header_change(tmp_path: Path) -> None:
    """Changing only the base-class list counts as a header change."""
    _write(tmp_path, "lib.py", "class A(B):\n    x = 1\n")
    _write(
        tmp_path,
        "app.py",
        "from lib import A\n\ndef make():\n    return A()\n",
    )
    entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n-class A:\n+class A(B):\n     x = 1",
    )

    context = _agent_for(tmp_path, neighbors_trigger="signature")._cross_file_context_for(entry)

    assert context.startswith("## Cross-file context")


def test_signature_trigger_skips_body_only_changes(tmp_path: Path) -> None:
    """A body-level edit injects nothing even though neighbours exist."""
    _callers_repo(tmp_path)
    _write(tmp_path, "lib.py", "def target():\n    return 2\n")
    entry = _body_change_entry()
    agent = _agent_for(tmp_path, neighbors_trigger="signature")

    # The same agent injects for a header change, so the index really has a
    # caller and the empty result below is the trigger's decision.
    header_entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n-def target():\n+def target(a):\n     return 2",
    )
    assert agent._cross_file_context_for(header_entry).startswith("## Cross-file context")

    assert agent._cross_file_context_for(entry) == ""


def test_signature_trigger_rejects_signature_plus_body_edit(tmp_path: Path) -> None:
    """A body edit in the same definition disqualifies a header change."""
    _write(tmp_path, "lib.py", "def target(a, b):\n    return a + 1\n")
    _write(
        tmp_path,
        "app.py",
        "from lib import target\n\ndef use():\n    return target(1, 2)\n",
    )
    entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=2,
        deletions=2,
        patch=(
            "@@ -1,2 +1,2 @@\n"
            "-def target(a):\n"
            "-    return a\n"
            "+def target(a, b):\n"
            "+    return a + 1"
        ),
    )

    assert _agent_for(tmp_path)._cross_file_context_for(entry).startswith("## Cross-file context")
    assert _agent_for(tmp_path, neighbors_trigger="signature")._cross_file_context_for(entry) == ""


@pytest.mark.parametrize(
    ("source", "patch"),
    [
        (
            "import sys\nimport os\n\ndef target():\n    return 1\n",
            "@@ -1,3 +1,4 @@\n+import sys\n import os\n \n def target():",
        ),
        (
            "FOO = 2\n\ndef target():\n    return 1\n",
            "@@ -1,3 +1,3 @@\n-FOO = 1\n+FOO = 2\n \n def target():",
        ),
    ],
)
def test_signature_trigger_skips_module_level_edits(
    tmp_path: Path, source: str, patch: str
) -> None:
    """Imports and module constants belong to no definition and never inject."""
    _callers_repo(tmp_path)
    _write(tmp_path, "lib.py", source)
    entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=1,
        patch=patch,
    )

    assert _agent_for(tmp_path)._cross_file_context_for(entry).startswith("## Cross-file context")
    assert _agent_for(tmp_path, neighbors_trigger="signature")._cross_file_context_for(entry) == ""


def test_signature_trigger_uses_innermost_definition_for_nested_edits(tmp_path: Path) -> None:
    """An inner signature edit injects even when the outer body also changed."""
    _write(
        tmp_path,
        "lib.py",
        "def outer():\n    x = 2\n    def inner(a, b):\n        return a\n    return inner(1, 2)\n",
    )
    _write(
        tmp_path,
        "app.py",
        "from lib import outer\n\ndef use():\n    return outer()\n",
    )
    entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=2,
        deletions=2,
        patch=(
            "@@ -1,5 +1,5 @@\n"
            " def outer():\n"
            "-    x = 1\n"
            "-    def inner(a):\n"
            "+    x = 2\n"
            "+    def inner(a, b):\n"
            "     return inner(1, 2)"
        ),
    )

    context = _agent_for(tmp_path, neighbors_trigger="signature")._cross_file_context_for(entry)

    assert context.startswith("## Cross-file context")


def test_signature_trigger_maps_pure_deletions_to_the_new_side(tmp_path: Path) -> None:
    """A removed line is judged at the new-side position where it was removed."""
    _callers_repo(tmp_path)
    _write(tmp_path, "lib.py", "def target(\n    a,\n):\n    return a\n")
    parameter_agent = _agent_for(tmp_path, neighbors_trigger="signature")

    removed_parameter = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=0,
        deletions=1,
        patch=(
            "@@ -1,5 +1,4 @@\n"
            " def target(\n"
            "     a,\n"
            "-    b,\n"
            " ):\n"
            "     return a"
        ),
    )

    assert parameter_agent._cross_file_context_for(removed_parameter).startswith(
        "## Cross-file context"
    )

    _write(tmp_path, "lib.py", "def target():\n    return 1\n")
    body_agent = _agent_for(tmp_path, neighbors_trigger="signature")
    removed_body_line = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=0,
        deletions=1,
        patch=(
            "@@ -1,3 +1,2 @@\n"
            " def target():\n"
            "-    x = 0\n"
            "     return 1"
        ),
    )

    assert body_agent._cross_file_context_for(removed_body_line) == ""


def test_signature_trigger_degrades_on_bad_or_missing_files(tmp_path: Path) -> None:
    """Invalid Python and absent files skip injection without raising."""
    _callers_repo(tmp_path)
    broken = _write(tmp_path, "broken.py", "def broken(:\n    return 1\n")
    assert broken.exists()
    agent = _agent_for(tmp_path, neighbors_trigger="signature")

    broken_entry = DiffEntry(
        filename="broken.py",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n-def broken(x):\n+def broken(:\n     return 1",
    )
    missing_entry = DiffEntry(
        filename="ghost.py",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1,1 +1,1 @@\n-def ghost():\n+def ghost(x):",
    )

    assert agent._cross_file_context_for(broken_entry) == ""
    assert agent._cross_file_context_for(missing_entry) == ""


def test_neighbors_false_wins_over_signature_trigger(tmp_path: Path) -> None:
    """``context.neighbors: false`` still disables injection entirely."""
    _write(tmp_path, "lib.py", "def target(a, b):\n    return a\n")
    _write(
        tmp_path,
        "app.py",
        "from lib import target\n\ndef use():\n    return target(1, 2)\n",
    )
    entry = DiffEntry(
        filename="lib.py",
        status="modified",
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n-def target(a):\n+def target(a, b):\n     return a",
    )
    agent = _agent_for(tmp_path, neighbors=False, neighbors_trigger="signature")

    assert agent._cross_file_context_for(entry) == ""
