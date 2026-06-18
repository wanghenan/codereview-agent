"""Path matcher for exclude patterns using gitignore semantics.

Provides a single, DRY matcher shared by the review agent and the language
analyzers. Backed by ``pathspec`` so patterns follow gitignore syntax
(recursive ``**``, directory anchoring, ``!`` negation).
"""

from __future__ import annotations

import logging

try:
    import pathspec

    _PATHSPEC_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when pathspec missing
    _PATHSPEC_AVAILABLE = False
    pathspec = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class ExcludeMatcher:
    """Match file paths against gitignore-style exclude patterns.

    Falls back to "exclude nothing" if no patterns are supplied or if
    ``pathspec`` is unavailable, so callers never need to special-case
    the empty/missing dependency state.
    """

    def __init__(self, patterns: list[str] | None):
        """Compile the given patterns into a gitwildmatch spec.

        Args:
            patterns: Gitignore-style patterns. ``None`` or an empty list
                produces a matcher that matches nothing.
        """
        self._spec = None
        if not patterns:
            return

        if not _PATHSPEC_AVAILABLE:
            logger.warning(
                "pathspec not installed; exclude_patterns will be ignored. "
                "Install pathspec to enable gitignore-style exclusion."
            )
            return

        # pathspec >=0.12 uses "gitwildmatch"; newer releases (1.x) deprecate
        # it in favor of "gitignore". Try the modern name first, fall back so
        # we keep working across the declared dependency range.
        for factory in ("gitignore", "gitwildmatch"):
            try:
                self._spec = pathspec.PathSpec.from_lines(factory, patterns)
                break
            except (ValueError, TypeError):
                continue

    def matches(self, path: str) -> bool:
        """Return True if ``path`` should be excluded.

        Args:
            path: File path (forward-slash separated) to test.

        Returns:
            True if the path matches any exclude pattern.
        """
        if self._spec is None:
            return False
        return bool(self._spec.match_file(path))
