"""A small, dependency-free symbol index for repository review context.

The index has two jobs:

* answer "where is this symbol defined?" and "who references it?", and
* hand the reviewer a bounded one-hop neighbourhood around a changed range.

Only Python is parsed in this slice, using the standard library ``ast`` module.
Every other language is recorded in :attr:`IndexStats.skipped_languages` rather
than silently ignored.  The public boundary is intentionally parser agnostic:
a future tree-sitter backend only needs to produce the same :class:`Symbol` and
:class:`Reference` values.

Reference resolution deliberately uses simple-name matching.  If two modules
both define ``run``, :meth:`SymbolIndex.lookup` and
:meth:`SymbolIndex.callers_of` return every candidate for that name.  That is a
known limitation and is preferable to inventing a false sense of precision
before real import resolution is available.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import tempfile
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

PathLike = Union[str, "os.PathLike[str]"]

#: Directories that are never part of the reviewed source tree.
_IGNORED_DIRS = {
    ".codereview-agent",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}

#: Best-effort language labels for files this slice cannot parse.
_SUFFIX_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cjs": "javascript",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".cts": "typescript",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".md": "markdown",
    ".mjs": "javascript",
    ".mts": "typescript",
    ".php": "php",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "shell",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".yaml": "yaml",
    ".yml": "yaml",
}

_MAX_EXCERPT_LINES = 40
_INDEX_VERSION = 1


@dataclass
class Symbol:
    """A definition found in the repository.

    Attributes:
        name: Simple name as written in source (no module qualification).
        kind: One of ``"function"``, ``"class"``, or ``"method"``.
        path: Repository-relative POSIX path of the defining file.
        start_line: First line of the definition (1-based).
        end_line: Last line of the definition (1-based).
        module: Dotted module name derived from ``path``.
    """

    name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    module: str


@dataclass
class Reference:
    """A use of a name found while indexing a file.

    Attributes:
        from_path: Repository-relative POSIX path containing the reference.
        from_line: 1-based line number of the reference.
        to_name: Simple name being imported or called.  Attribute calls use the
            final attribute name, so ``obj.run()`` records ``run``.
        kind: One of ``"import"``, ``"call"`` (a bare ``name(...)``), or
            ``"attribute"`` (an ``obj.name(...)`` call).
    """

    from_path: str
    from_line: int
    to_name: str
    kind: str


@dataclass
class Neighbor:
    """A bounded excerpt of code related to a changed range.

    ``start_line``/``end_line`` describe the excerpt actually returned, not the
    full symbol or file.  ``excerpt`` is at most 40 lines.
    """

    path: str
    start_line: int
    end_line: int
    reason: str
    excerpt: str


@dataclass
class IndexStats:
    """Summary of one :meth:`SymbolIndex.build` call."""

    files_indexed: int = 0
    symbols: int = 0
    references: int = 0
    skipped_languages: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    skipped_files: int = 0


class SymbolIndex:
    """In-memory symbol/reference index for a source tree.

    The index is intentionally lightweight: it holds plain dataclasses and can
    be serialized to a single JSON file.  A tree-sitter implementation can
    replace :meth:`_index_python_file` without changing any query method.
    """

    def __init__(self) -> None:
        self.root: Path = Path(".")
        self.stats: Optional[IndexStats] = None
        self._symbols: list[Symbol] = []
        self._references: list[Reference] = []
        self._symbols_by_name: dict[str, list[Symbol]] = {}
        self._symbols_by_path: dict[str, list[Symbol]] = {}
        self._skipped_languages: dict[str, int] = {}
        self._skipped_files = 0
        self._files_indexed = 0

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------
    def build(self, root: Path, paths: Optional[Iterable[str]] = None) -> IndexStats:
        """Index Python files under ``root``.

        Args:
            root: Repository root.  Relative paths are resolved against it.
            paths: Optional iterable of repository-relative or absolute paths.
                When omitted, the whole tree is walked (ignoring common cache
                and VCS directories).  Every non-Python path is reported in
                ``skipped_languages``.

        Returns:
            Counts and timing for this build.  Unreadable or syntactically
            invalid Python files are skipped and counted in ``skipped_files``;
            they never raise.
        """
        started = time.perf_counter()
        self._reset()
        self.root = Path(root).expanduser().resolve()

        candidates = self._collect_candidates(paths)
        for rel_path in candidates:
            suffix = Path(rel_path).suffix.lower()
            if suffix != ".py":
                language = _SUFFIX_LANGUAGES.get(suffix) or suffix.lstrip(".") or "unknown"
                self._skipped_languages[language] = self._skipped_languages.get(language, 0) + 1
                continue

            if not self._index_python_file(rel_path):
                self._skipped_files += 1

        self._finalize()
        elapsed = time.perf_counter() - started
        self.stats = IndexStats(
            files_indexed=self._files_indexed,
            symbols=len(self._symbols),
            references=len(self._references),
            skipped_languages=dict(sorted(self._skipped_languages.items())),
            seconds=elapsed,
            skipped_files=self._skipped_files,
        )
        return self.stats

    def _reset(self) -> None:
        """Clear all indexed data."""
        self._symbols = []
        self._references = []
        self._symbols_by_name = {}
        self._symbols_by_path = {}
        self._skipped_languages = {}
        self._skipped_files = 0
        self._files_indexed = 0
        self.stats = None

    def _collect_candidates(self, paths: Optional[Iterable[str]]) -> list[str]:
        """Return deduplicated repository-relative paths to inspect."""
        if paths is not None:
            seen: set[str] = set()
            result: list[str] = []
            for raw in paths:
                rel = self._relative(raw)
                if rel and rel not in seen:
                    seen.add(rel)
                    result.append(rel)
            return result

        result = []
        if not self.root.is_dir():
            return result

        for current, dirs, files in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d not in _IGNORED_DIRS and not d.startswith("."))
            current_path = Path(current)
            for filename in sorted(files):
                full = current_path / filename
                try:
                    rel = full.relative_to(self.root).as_posix()
                except ValueError:  # pragma: no cover - os.walk stays under root
                    continue
                result.append(rel)
        return result

    def _index_python_file(self, rel_path: str) -> bool:
        """Parse one file and add its symbols/references.

        Returns:
            ``True`` when the file was read and parsed, ``False`` when it was
            unreadable or invalid.  Failures are logged at debug level only.
        """
        full_path = self.root / rel_path
        try:
            source = full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            logger.debug("Skipping unreadable file %s: %s", rel_path, exc)
            return False

        try:
            tree = ast.parse(source, filename=rel_path)
        except (SyntaxError, ValueError, RecursionError) as exc:
            logger.debug("Skipping invalid Python file %s: %s", rel_path, exc)
            return False

        module = _module_name(rel_path)
        for symbol in _extract_symbols(tree, rel_path, module):
            self._symbols.append(symbol)

        for reference in _extract_references(tree, rel_path):
            self._references.append(reference)
        self._files_indexed += 1
        return True

    def _finalize(self) -> None:
        """Sort collected data and rebuild lookup maps."""
        self._symbols.sort(key=lambda s: (s.path, s.start_line, s.end_line, s.name, s.kind))
        self._references.sort(key=lambda r: (r.from_path, r.from_line, r.kind, r.to_name))

        by_name: dict[str, list[Symbol]] = {}
        by_path: dict[str, list[Symbol]] = {}
        for symbol in self._symbols:
            by_name.setdefault(symbol.name, []).append(symbol)
            by_path.setdefault(symbol.path, []).append(symbol)
        self._symbols_by_name = by_name
        self._symbols_by_path = by_path

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def lookup(self, name: str) -> list[Symbol]:
        """Return every definition whose simple name is ``name``.

        Overloaded names (same name in several modules, or a method and a
        function) are all returned; callers should not assume uniqueness.
        """
        return list(self._symbols_by_name.get(name, []))

    def callers_of(self, symbol: Symbol | str) -> list[Reference]:
        """Return call/attribute references to ``symbol``'s simple name.

        Imports are intentionally excluded: they are dependencies, not callers.
        Passing a string name is supported for convenience and behaves like
        looking the name up in every module.
        """
        name = symbol.name if isinstance(symbol, Symbol) else str(symbol)
        return [
            ref
            for ref in self._references
            if ref.to_name == name and ref.kind in ("call", "attribute")
        ]

    def symbols_in(self, path: PathLike) -> list[Symbol]:
        """Return definitions in ``path`` (repository-relative or absolute)."""
        return list(self._symbols_by_path.get(self._relative(path), []))

    def neighbors(
        self,
        path: PathLike,
        start_line: int,
        end_line: int,
        limit: int = 8,
    ) -> list[Neighbor]:
        """Return one-hop context around a changed range in ``path``.

        Results are ordered by usefulness: callers first, then importers, then
        sibling definitions in the same file.  At most one caller and one
        importer neighbour is emitted per file, and every excerpt is at most
        40 lines read from disk.  Missing files yield no neighbours for that
        path rather than raising.

        Args:
            path: File containing the changed range.
            start_line: First changed line (1-based, inclusive).
            end_line: Last changed line (1-based, inclusive).
            limit: Maximum number of neighbours to return.
        """
        if limit <= 0:
            return []

        rel_path = self._relative(path)
        target_symbols = [
            symbol
            for symbol in self._symbols_by_path.get(rel_path, [])
            if symbol.start_line <= end_line and symbol.end_line >= start_line
        ]
        target_names = {symbol.name for symbol in target_symbols}

        candidates: list[tuple[tuple[int, str, int], Neighbor]] = []
        seen: set[tuple[str, str]] = set()

        if target_names:
            matching = [ref for ref in self._references if ref.to_name in target_names]
            callers = [ref for ref in matching if ref.kind in ("call", "attribute")]
            imports = [ref for ref in matching if ref.kind == "import"]

            for ref in callers:
                key = (ref.from_path, "caller")
                if key in seen:
                    continue
                neighbor = self._neighbor(ref.from_path, ref.from_line, "caller")
                if neighbor is not None:
                    seen.add(key)
                    candidates.append(((0, ref.from_path, ref.from_line), neighbor))

            for ref in imports:
                key = (ref.from_path, "import")
                if key in seen:
                    continue
                neighbor = self._neighbor(ref.from_path, ref.from_line, "import")
                if neighbor is not None:
                    seen.add(key)
                    candidates.append(((1, ref.from_path, ref.from_line), neighbor))

        target_ids = {id(symbol) for symbol in target_symbols}
        siblings = [
            symbol
            for symbol in self._symbols_by_path.get(rel_path, [])
            if id(symbol) not in target_ids
        ]
        siblings.sort(
            key=lambda s: (
                _distance_to_range(s.start_line, s.end_line, start_line, end_line),
                s.start_line,
                s.name,
            )
        )
        for symbol in siblings:
            neighbor = self._neighbor(
                symbol.path, symbol.start_line, "sibling", end_line=symbol.end_line
            )
            if neighbor is not None:
                distance = _distance_to_range(
                    symbol.start_line, symbol.end_line, start_line, end_line
                )
                candidates.append(((2, symbol.path, distance), neighbor))

        candidates.sort(key=lambda item: item[0])
        return [neighbor for _, neighbor in candidates[:limit]]

    def _neighbor(
        self,
        rel_path: str,
        focus_line: int,
        reason: str,
        end_line: Optional[int] = None,
    ) -> Optional[Neighbor]:
        """Build one neighbour with a <=40-line excerpt."""
        start, end, excerpt = self._read_excerpt(rel_path, focus_line, end_line)
        if not excerpt:
            return None
        return Neighbor(
            path=rel_path,
            start_line=start,
            end_line=end,
            reason=reason,
            excerpt=excerpt,
        )

    def _read_excerpt(
        self,
        rel_path: str,
        focus_line: int,
        end_line: Optional[int] = None,
    ) -> tuple[int, int, str]:
        """Read at most ``_MAX_EXCERPT_LINES`` lines around a location."""
        full_path = self.root / rel_path
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError) as exc:
            logger.debug("Could not read neighbour %s: %s", rel_path, exc)
            return 0, 0, ""

        lines = text.splitlines()
        total = len(lines)
        if total == 0:
            return 0, 0, ""

        focus = max(1, min(focus_line, total))
        if end_line is not None:
            # For sibling definitions, stay inside the definition.
            start = focus
            end = min(total, max(focus, end_line), start + _MAX_EXCERPT_LINES - 1)
        else:
            # For references, centre a 40-line window on the reference line.
            start = max(1, min(focus - 5, total - _MAX_EXCERPT_LINES + 1))
            end = min(total, start + _MAX_EXCERPT_LINES - 1)

        excerpt = "\n".join(lines[start - 1 : end])
        return start, end, excerpt

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, path: PathLike) -> None:
        """Atomically write the index to ``path`` as JSON."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _INDEX_VERSION,
            "root": str(self.root),
            "symbols": [asdict(symbol) for symbol in self._symbols],
            "references": [asdict(reference) for reference in self._references],
            "files_indexed": self._files_indexed,
            "skipped_languages": self._skipped_languages,
            "skipped_files": self._skipped_files,
        }

        fd, temp_name = tempfile.mkstemp(
            prefix=f"{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def load(self, path: Optional[PathLike] = None) -> SymbolIndex:
        """Load an index from JSON.

        Supports both common call styles: ``index.load(path)`` mutates and
        returns ``index``, while ``SymbolIndex.load(path)`` returns a new
        instance.  A missing, unreadable, or corrupt file yields an empty index
        instead of raising.
        """
        if path is None and isinstance(self, (str, os.PathLike)):
            # Called as ``SymbolIndex.load(path)``; Python bound the path as
            # ``self`` because ``load`` is an ordinary method.
            loaded = SymbolIndex()
            loaded._load_from(Path(self))
            return loaded

        if path is None:
            raise TypeError("load() requires a path")

        self._load_from(Path(path))
        return self

    def _load_from(self, path: Path) -> None:
        """Populate this instance from ``path``; reset to empty on failure."""
        self._reset()
        self.root = Path.cwd()
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            logger.debug("Could not load symbol index %s: %s", path, exc)
            self._finalize()
            self._record_loaded_stats()
            return

        if not isinstance(payload, dict):
            self._finalize()
            self._record_loaded_stats()
            return

        saved_root = payload.get("root")
        if isinstance(saved_root, str) and saved_root:
            self.root = Path(saved_root)

        raw_symbols = payload.get("symbols")
        if isinstance(raw_symbols, list):
            for item in raw_symbols:
                symbol = _symbol_from_dict(item)
                if symbol is not None:
                    self._symbols.append(symbol)

        raw_references = payload.get("references")
        if isinstance(raw_references, list):
            for item in raw_references:
                reference = _reference_from_dict(item)
                if reference is not None:
                    self._references.append(reference)

        raw_skipped = payload.get("skipped_languages")
        if isinstance(raw_skipped, dict):
            self._skipped_languages = {
                str(language): int(count)
                for language, count in raw_skipped.items()
                if isinstance(language, str) and isinstance(count, int)
            }

        raw_skipped_files = payload.get("skipped_files")
        if isinstance(raw_skipped_files, int):
            self._skipped_files = raw_skipped_files

        raw_files_indexed = payload.get("files_indexed")
        if isinstance(raw_files_indexed, int):
            self._files_indexed = raw_files_indexed
        else:
            self._files_indexed = len({symbol.path for symbol in self._symbols})

        self._finalize()
        self._record_loaded_stats()

    def _record_loaded_stats(self) -> None:
        """Publish stats after a successful or failed load."""
        self.stats = IndexStats(
            files_indexed=self._files_indexed,
            symbols=len(self._symbols),
            references=len(self._references),
            skipped_languages=dict(sorted(self._skipped_languages.items())),
            seconds=0.0,
            skipped_files=self._skipped_files,
        )

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    def _relative(self, path: PathLike) -> str:
        """Normalize a path to a repository-relative POSIX string."""
        value = Path(path)
        if value.is_absolute():
            try:
                value = value.relative_to(self.root)
            except ValueError:
                try:
                    value = Path(os.path.relpath(str(value), str(self.root)))
                except ValueError:  # pragma: no cover - different drives on Windows
                    value = Path(value.name)

        rel = value.as_posix()
        while rel.startswith("./"):
            rel = rel[2:]
        return rel


def _distance_to_range(start_line: int, end_line: int, range_start: int, range_end: int) -> int:
    """Return 0 when ranges overlap, otherwise the line gap between them."""
    if start_line <= range_end and end_line >= range_start:
        return 0
    if end_line < range_start:
        return range_start - end_line
    return start_line - range_end


def _module_name(rel_path: str) -> str:
    """Derive a dotted module name from a repository-relative path."""
    parts = list(Path(rel_path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _extract_symbols(tree: ast.AST, rel_path: str, module: str) -> list[Symbol]:
    """Collect top-level functions/classes and direct class methods."""
    symbols: list[Symbol] = []
    for node in tree.body:  # type: ignore[attr-defined]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_symbol_from_node(node, "function", rel_path, module))
        elif isinstance(node, ast.ClassDef):
            symbols.append(_symbol_from_node(node, "class", rel_path, module))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(_symbol_from_node(child, "method", rel_path, module))
    return symbols


def _symbol_from_node(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    kind: str,
    rel_path: str,
    module: str,
) -> Symbol:
    """Convert an AST definition node into a :class:`Symbol`."""
    end_line = getattr(node, "end_lineno", None) or node.lineno
    return Symbol(
        name=node.name,
        kind=kind,
        path=rel_path,
        start_line=node.lineno,
        end_line=end_line,
        module=module,
    )


def _extract_references(tree: ast.AST, rel_path: str) -> list[Reference]:
    """Collect imports and call/attribute-call references from one AST."""
    references: list[Reference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                references.append(
                    Reference(
                        from_path=rel_path,
                        from_line=node.lineno,
                        to_name=name,
                        kind="import",
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                references.append(
                    Reference(
                        from_path=rel_path,
                        from_line=node.lineno,
                        to_name=alias.asname or alias.name,
                        kind="import",
                    )
                )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                references.append(
                    Reference(
                        from_path=rel_path,
                        from_line=node.lineno,
                        to_name=func.id,
                        kind="call",
                    )
                )
            elif isinstance(func, ast.Attribute):
                references.append(
                    Reference(
                        from_path=rel_path,
                        from_line=node.lineno,
                        to_name=func.attr,
                        kind="attribute",
                    )
                )
    return references


def _symbol_from_dict(item: object) -> Optional[Symbol]:
    """Best-effort conversion of one serialized symbol."""
    if not isinstance(item, dict):
        return None
    try:
        return Symbol(
            name=str(item["name"]),
            kind=str(item["kind"]),
            path=str(item["path"]),
            start_line=int(item["start_line"]),
            end_line=int(item["end_line"]),
            module=str(item["module"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _reference_from_dict(item: object) -> Optional[Reference]:
    """Best-effort conversion of one serialized reference."""
    if not isinstance(item, dict):
        return None
    try:
        return Reference(
            from_path=str(item["from_path"]),
            from_line=int(item["from_line"]),
            to_name=str(item["to_name"]),
            kind=str(item["kind"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
