"""Tests for the lightweight symbol index."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from codereview.core.symbol_index import (
    IndexStats,
    Neighbor,
    Reference,
    SymbolIndex,
)


def _write(root: Path, rel_path: str, content: str) -> Path:
    """Write a dedented source file under ``root`` and return its path."""
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


def _line_of(path: Path, needle: str) -> int:
    """Return the 1-based line containing ``needle``."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not found in {path}")


def test_build_extracts_functions_classes_and_methods(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        "pkg/target.py",
        """
        import os

        def top(value):
            return value

        async def async_top():
            pass

        class Widget:
            def method(self):
                return 1

            async def async_method(self):
                return 2

        def outer():
            def inner():
                pass
            return inner
        """,
    )

    index = SymbolIndex()
    stats = index.build(tmp_path)

    assert stats.files_indexed == 1
    assert stats.symbols == 6
    assert stats.references == 1
    assert isinstance(stats, IndexStats)
    assert stats.skipped_languages == {}
    assert stats.seconds >= 0

    top = index.lookup("top")
    assert len(top) == 1
    assert (top[0].kind, top[0].path, top[0].module) == (
        "function",
        "pkg/target.py",
        "pkg.target",
    )
    lines = source.read_text(encoding="utf-8").splitlines()
    assert lines[top[0].start_line - 1].strip() == "def top(value):"
    assert lines[top[0].end_line - 1].strip() == "return value"

    assert index.lookup("async_top")[0].kind == "function"
    widget = index.lookup("Widget")
    assert len(widget) == 1
    assert widget[0].kind == "class"
    assert widget[0].module == "pkg.target"

    # Methods are nested in a class but are still indexed, with kind "method".
    method = index.lookup("method")
    assert len(method) == 1
    assert method[0].kind == "method"
    assert method[0].path == "pkg/target.py"
    assert method[0].start_line > widget[0].start_line
    assert index.lookup("async_method")[0].kind == "method"

    # A function nested inside another function is not a repository symbol.
    assert index.lookup("inner") == []

    assert [symbol.name for symbol in index.symbols_in("pkg/target.py")] == [
        "top",
        "async_top",
        "Widget",
        "method",
        "async_method",
        "outer",
    ]


def test_imports_and_name_attribute_calls_become_references(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "target.py",
        """
        import os
        from helpers import helper
        import pkg.mod as pm

        def run():
            helper()
            os.getcwd()
            pm.run()
            return run()
        """,
    )

    index = SymbolIndex()
    stats = index.build(tmp_path)

    assert stats.files_indexed == 1
    assert stats.symbols == 1
    assert stats.references == 7

    refs = index.callers_of("run")
    assert Reference("target.py", 8, "run", "attribute") in refs
    assert Reference("target.py", 9, "run", "call") in refs
    assert all(ref.kind != "import" for ref in refs)

    all_refs = index._references
    assert Reference("target.py", 6, "helper", "call") in all_refs
    assert Reference("target.py", 7, "getcwd", "attribute") in all_refs
    assert Reference("target.py", 1, "os", "import") in all_refs
    assert Reference("target.py", 2, "helper", "import") in all_refs
    assert Reference("target.py", 3, "pm", "import") in all_refs


def test_callers_of_simple_name_matching_and_overloads(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "def target():\n    return 1\n")
    _write(
        tmp_path,
        "b.py",
        """
        from a import target

        def use():
            return target()
        """,
    )
    _write(tmp_path, "c.py", "def target():\n    return 2\n")
    _write(tmp_path, "d.py", "def use():\n    return target()\n")
    _write(tmp_path, "e.py", "def use(obj):\n    return obj.target()\n")

    index = SymbolIndex()
    index.build(tmp_path)

    definitions = index.lookup("target")
    assert len(definitions) == 2
    assert {symbol.path for symbol in definitions} == {"a.py", "c.py"}

    expected = {("b.py", 4), ("d.py", 2), ("e.py", 2)}
    for definition in definitions:
        callers = index.callers_of(definition)
        assert {(ref.from_path, ref.from_line) for ref in callers} == expected
        assert {ref.kind for ref in callers} == {"call", "attribute"}

    # A plain string is accepted too and covers every overload.
    assert index.callers_of("target") == index.callers_of(definitions[0])


def test_neighbors_caller_import_sibling_order_and_excerpts(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "lib.py",
        """
        def target():
            return 1

        def helper():
            return 2
        """,
    )
    _write(
        tmp_path,
        "app.py",
        """
        from lib import target

        def call_target():
            return target()
        """,
    )
    _write(
        tmp_path,
        "other.py",
        """
        import lib

        def also():
            return lib.target()
        """,
    )

    index = SymbolIndex()
    index.build(tmp_path)
    target = index.lookup("target")[0]

    neighbors = index.neighbors("lib.py", target.start_line, target.end_line)
    assert [neighbor.reason for neighbor in neighbors] == [
        "caller",
        "caller",
        "import",
        "sibling",
    ]
    assert [neighbor.path for neighbor in neighbors] == [
        "app.py",
        "other.py",
        "app.py",
        "lib.py",
    ]
    assert all(isinstance(neighbor, Neighbor) for neighbor in neighbors)
    assert all(neighbor.end_line - neighbor.start_line + 1 <= 40 for neighbor in neighbors)
    assert all(neighbor.excerpt for neighbor in neighbors)
    assert "target()" in neighbors[0].excerpt
    assert "from lib import target" in neighbors[2].excerpt
    assert "def helper" in neighbors[3].excerpt

    assert [n.reason for n in index.neighbors("lib.py", 1, 2, limit=2)] == [
        "caller",
        "caller",
    ]
    assert index.neighbors("missing.py", 1, 2) == []


def test_neighbors_truncates_excerpts_to_forty_lines(tmp_path: Path) -> None:
    long_lines = ["def big():"]
    long_lines.extend(f"    value_{number} = {number}" for number in range(80))
    long_lines.extend(["", "def small():", "    return 0"])
    _write(tmp_path, "long.py", "\n".join(long_lines) + "\n")

    caller_lines = ["# filler"] * 78
    caller_lines.extend(["def call_small():", "    return small()"])
    _write(tmp_path, "caller.py", "\n".join(caller_lines) + "\n")

    index = SymbolIndex()
    index.build(tmp_path)
    small = index.lookup("small")[0]
    neighbors = index.neighbors("long.py", small.start_line, small.end_line)

    assert [neighbor.reason for neighbor in neighbors] == ["caller", "sibling"]
    for neighbor in neighbors:
        excerpt_lines = neighbor.excerpt.splitlines()
        assert len(excerpt_lines) <= 40
        assert neighbor.end_line - neighbor.start_line + 1 == len(excerpt_lines)

    caller, sibling = neighbors
    assert "small()" in caller.excerpt
    assert caller.start_line <= 80 <= caller.end_line
    assert len(caller.excerpt.splitlines()) == 40

    assert "def big" in sibling.excerpt
    assert "def small" not in sibling.excerpt
    assert len(sibling.excerpt.splitlines()) == 40


def test_save_load_round_trip_and_atomic_write(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "def target():\n    return 1\n")
    _write(tmp_path, "b.py", "from a import target\n\ndef use():\n    return target()\n")

    index = SymbolIndex()
    index.build(tmp_path)
    destination = tmp_path / "state" / "symbols.json"
    index.save(destination)

    assert destination.is_file()
    assert list(destination.parent.glob("symbols.json.*.tmp")) == []

    loaded = SymbolIndex.load(destination)
    assert loaded.root == index.root
    assert loaded.lookup("target") == index.lookup("target")
    assert loaded.symbols_in("a.py") == index.symbols_in("a.py")
    assert loaded.callers_of("target") == index.callers_of("target")
    assert loaded.neighbors("a.py", 1, 2) == index.neighbors("a.py", 1, 2)
    assert loaded.stats is not None
    assert loaded.stats.files_indexed == 2
    assert loaded.stats.symbols == index.stats.symbols
    assert loaded.stats.references == index.stats.references

    # The instance form mutates and returns the same object.
    restored = SymbolIndex()
    returned = restored.load(destination)
    assert returned is restored
    assert [symbol.name for symbol in restored.lookup("target")] == ["target"]


def test_load_corrupt_or_missing_index_returns_empty_index(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "def target():\n    return 1\n")
    index = SymbolIndex()
    index.build(tmp_path)

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    empty = SymbolIndex.load(corrupt)
    assert empty.lookup("target") == []
    assert empty.symbols_in("a.py") == []
    assert empty.neighbors("a.py", 1, 2) == []
    assert empty.stats is not None
    assert empty.stats.symbols == 0

    # A valid JSON document with the wrong shape is treated as corrupt too.
    wrong_shape = tmp_path / "wrong.json"
    wrong_shape.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert SymbolIndex.load(wrong_shape).lookup("target") == []

    # The instance form is reset rather than left with stale data.
    assert index.lookup("target") != []
    index.load(corrupt)
    assert index.lookup("target") == []

    missing = SymbolIndex.load(tmp_path / "does-not-exist.json")
    assert missing.lookup("target") == []


def test_non_python_files_are_reported_as_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "def foo():\n    pass\n")
    _write(tmp_path, "web.ts", "export function foo() {}\n")
    _write(tmp_path, "README.md", "# Read me\n")
    _write(tmp_path, "style.css", "body { color: red; }\n")

    index = SymbolIndex()
    stats = index.build(tmp_path)

    assert stats.files_indexed == 1
    assert stats.symbols == 1
    assert stats.references == 0
    assert stats.skipped_languages == {
        "css": 1,
        "markdown": 1,
        "typescript": 1,
    }
    assert stats.skipped_files == 0
    assert [symbol.name for symbol in index.lookup("foo")] == ["foo"]

    # Explicit path lists only inspect what they are given.
    limited = index.build(tmp_path, ["a.py", "web.ts"])
    assert limited.files_indexed == 1
    assert limited.skipped_languages == {"typescript": 1}
    assert index.lookup("foo")[0].path == "a.py"


def test_invalid_unreadable_and_symbol_free_python_files_never_raise(tmp_path: Path) -> None:
    _write(tmp_path, "broken.py", "def broken(:\n    pass\n")
    _write(tmp_path, "empty.py", "import os\n")
    (tmp_path / "bad_utf8.py").write_bytes(b"\xff\xfe\x00\x00")
    (tmp_path / "directory.py").mkdir()

    index = SymbolIndex()
    stats = index.build(
        tmp_path,
        ["broken.py", "empty.py", "bad_utf8.py", "directory.py"],
    )

    # ``empty.py`` parses successfully even though it defines no symbols.
    assert stats.files_indexed == 1
    assert stats.symbols == 0
    assert stats.references == 1
    assert stats.skipped_files == 3
    assert index.lookup("broken") == []


def test_rebuild_replaces_previous_index(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write(first, "one.py", "def one():\n    pass\n")
    _write(second, "two.py", "def two():\n    pass\n")

    index = SymbolIndex()
    index.build(first)
    assert index.lookup("one") != []

    stats = index.build(second)
    assert stats.files_indexed == 1
    assert stats.symbols == 1
    assert index.lookup("one") == []
    assert index.lookup("two") != []
    assert index.symbols_in("one.py") == []
