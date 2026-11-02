"""Annotate unified diff lines with new-file line numbers for the prompt.

The review prompt used to show the raw patch, whose hunk headers only expose
relative offsets, so models often anchored findings at the hunk start. This
module rewrites a patch so every line inside a hunk starts with its line number
in the new file::

    @@ -120,2 +121,3 @@
     121 |     def handler(self):
    -     |         old_line
    + 122 |         return res

File headers and hunk headers are passed through unchanged, as is the
``\\ No newline at end of file`` marker. ``number_patch`` is a pure function
with no dependencies outside the standard library.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Optional

_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))?"
    r" \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)
_NO_NEWLINE = "\\ No newline at end of file"

# A buffered hunk line: (kind, new-file line number, content, line ending).
# ``kind`` is " ", "+" or "-" for context/added/deleted lines; raw lines such
# as ``\ No newline at end of file`` use "raw" and keep their full body.
_HunkLine = tuple[str, Optional[int], str, str]


def number_patch(patch: str) -> str:
    """Prefix each hunk line in ``patch`` with its new-file line number.

    Context lines are rendered as ``  121 | ...``, added lines as
    ``+ 123 | ...`` and deleted lines keep an empty number field
    (``-     | ...``) because they do not exist in the new file. Numbers are
    right-aligned to the widest number in their hunk.

    Args:
        patch: A unified diff, possibly covering several files.

    Returns:
        The diff with annotated hunk lines; file headers, hunk headers and
        ``\\ No newline at end of file`` markers are unchanged. An empty or
        hunk-less patch is returned verbatim.
    """
    if not patch:
        return patch

    lines = list(_iter_lines(patch))
    rendered: list[str] = []
    index = 0

    while index < len(lines):
        body, ending = lines[index]
        header = _HUNK_RE.match(body)
        if header is None:
            rendered.append(body + ending)
            index += 1
            continue

        rendered.append(body + ending)
        index += 1

        old_remaining = _count(header.group("old_count"))
        new_remaining = _count(header.group("new_count"))
        new_line = int(header.group("new_start"))
        buffered: list[_HunkLine] = []

        while index < len(lines) and (old_remaining > 0 or new_remaining > 0):
            body, ending = lines[index]

            # A new file or hunk means the previous header undercounted; leave
            # the line for the outer loop instead of swallowing it as content.
            if _HUNK_RE.match(body) is not None or body.startswith("diff --git "):
                break

            if body == _NO_NEWLINE or body.startswith("\\"):
                buffered.append(("raw", None, body, ending))
                index += 1
                continue

            marker = body[:1] if body else " "
            content = body[1:]

            if marker == "+":
                buffered.append(("+", new_line, content, ending))
                new_line += 1
                new_remaining -= 1
            elif marker == "-":
                buffered.append(("-", None, content, ending))
                old_remaining -= 1
            elif marker == " ":
                buffered.append((" ", new_line, content, ending))
                new_line += 1
                new_remaining -= 1
                old_remaining -= 1
            else:
                break

            index += 1

        rendered.extend(_render_hunk(buffered, int(header.group("new_start"))))

    return "".join(rendered)


def _render_hunk(lines: list[_HunkLine], fallback_start: int) -> list[str]:
    """Render one buffered hunk, aligning numbers to its widest line number."""
    numbers = [number for _, number, _, _ in lines if number is not None]
    if numbers:
        width = len(str(max(numbers)))
    else:
        # A pure-deletion hunk has no numbers left to align to; keep the
        # blank field narrow but never zero-width.
        width = max(len(str(fallback_start)), 1)

    rendered: list[str] = []
    for kind, number, content, ending in lines:
        if kind == "raw":
            rendered.append(content + ending)
            continue
        label = "" if number is None else str(number)
        rendered.append(f"{kind} {label:>{width}} | {content}{ending}")
    return rendered


def _count(value: Optional[str]) -> int:
    """Hunk line count, defaulting to 1 when the header omits it."""
    return int(value) if value is not None else 1


def _iter_lines(patch: str) -> Iterator[tuple[str, str]]:
    """Yield ``(body, line_ending)`` pairs, splitting on ``\\n`` only.

    ``str.splitlines`` would also split on characters such as ``\\x0b`` that
    can legitimately appear inside a diff line, so split explicitly and keep
    the original ending (including CRLF).
    """
    start = 0
    while True:
        end = patch.find("\n", start)
        if end == -1:
            if start < len(patch):
                yield patch[start:], ""
            return
        body = patch[start:end]
        if body.endswith("\r"):
            yield body[:-1], "\r\n"
        else:
            yield body, "\n"
        start = end + 1
