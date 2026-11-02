"""Reduce source text to code before detection rules scan it.

Rules operate on source text with regular expressions, so prose in comments and
docstrings used to be flagged as if it were executable code (``# Never eval()
untrusted input.`` or a docstring mentioning ``executed``).  This module blanks
comments and docstrings while keeping every newline and character position, so
match line numbers still point at the same line in the original file.

Python input uses the standard-library ``tokenizer``: only ``COMMENT`` tokens
and string-expression statements (docstrings and bare string literals) are
blanked, so literals inside real code such as ``cursor.execute(f"SELECT ...")``
stay visible to the SQL injection rule.  Other languages get a best-effort
strip of ``#``/``//`` line comments and ``/* ... */`` blocks that respects
quoted strings.  Text that the tokenizer cannot parse is returned unchanged;
detection must never fail because of this preprocessing.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path
from typing import Optional

_PYTHON_LANGUAGES = {"python", "python3", "py"}
_PYTHON_EXTENSIONS = {".py", ".pyi", ".pyw"}
_TRIVIA_TOKENS = {
    tokenize.NL,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
}
_SKIPPED_TOKENS = _TRIVIA_TOKENS | {tokenize.NEWLINE}


def strip_comments_and_docstrings(
    content: str,
    language: Optional[str] = None,
    file_path: Optional[str] = None,
) -> str:
    """Return ``content`` with comments and docstrings replaced by spaces.

    Every character replaced by a space keeps the original line length and all
    newlines are left in place, so line numbers computed from the result are
    identical to the original text.

    Args:
        content: Source text to sanitise.
        language: Programming language reported by the caller.
        file_path: Optional file name, used to infer Python when ``language``
            is not given.

    Returns:
        Code-only text.  The original string is returned when Python
        tokenization fails, so detection keeps working on partial input.
    """
    if not content:
        return content

    if _is_python(language, file_path):
        return _strip_python(content)
    return _strip_generic(content)


def _is_python(language: Optional[str], file_path: Optional[str]) -> bool:
    """Check whether the input should be tokenised as Python."""
    if language and language.strip().lower() in _PYTHON_LANGUAGES:
        return True
    if file_path:
        return Path(file_path).suffix.lower() in _PYTHON_EXTENSIONS
    return False


def _strip_python(content: str) -> str:
    """Blank Python comments and string-expression statements."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        # Partial diffs and non-Python payloads must not take the engine down.
        return content

    line_offsets = _line_offsets(content)
    spans: list[tuple[int, int]] = []
    statement: list[tokenize.TokenInfo] = []

    def blank_statement_strings() -> None:
        """Blank the strings of a statement that consists only of strings."""
        if statement and all(token.type == tokenize.STRING for token in statement):
            for token in statement:
                span = _token_span(token, line_offsets)
                if span is not None:
                    spans.append(span)
        statement.clear()

    for token in tokens:
        if token.type == tokenize.COMMENT:
            span = _token_span(token, line_offsets)
            if span is not None:
                spans.append(span)
        elif token.type in _SKIPPED_TOKENS:
            if token.type == tokenize.NEWLINE:
                blank_statement_strings()
        elif token.type == tokenize.OP and token.string == ";":
            # A semicolon ends a simple statement: ``"doc"; x = 1``.
            blank_statement_strings()
        else:
            statement.append(token)

    blank_statement_strings()
    return _blank_spans(content, spans)


def _strip_generic(content: str) -> str:
    """Best-effort comment stripping for non-Python languages.

    ``#``/``//`` line comments and ``/* ... */`` blocks are blanked.  Quoted
    strings (single, double and backtick) are left intact so URLs and literals
    used by rules are not mistaken for comments.
    """
    chars = list(content)
    length = len(chars)
    spans: list[tuple[int, int]] = []
    quote = ""
    index = 0

    while index < length:
        char = chars[index]

        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote or char in "\r\n":
                quote = ""
            index += 1
            continue

        if char in "\"'`":
            quote = char
            index += 1
            continue

        if char == "#":
            end = _line_end(chars, index)
            spans.append((index, end))
            index = end
            continue

        if char == "/" and index + 1 < length and chars[index + 1] == "/":
            end = _line_end(chars, index)
            spans.append((index, end))
            index = end
            continue

        if char == "/" and index + 1 < length and chars[index + 1] == "*":
            closer = content.find("*/", index + 2)
            end = length if closer == -1 else closer + 2
            spans.append((index, end))
            index = end
            continue

        index += 1

    return _blank_spans(content, spans)


def _line_end(chars: list[str], start: int) -> int:
    """Return the offset of the newline that ends the line containing ``start``."""
    end = start
    while end < len(chars) and chars[end] not in "\r\n":
        end += 1
    return end


def _line_offsets(content: str) -> list[int]:
    """Return the absolute offset of the start of every line."""
    offsets = [0]
    for index, char in enumerate(content):
        if char == "\n":
            offsets.append(index + 1)
    return offsets


def _token_span(token: tokenize.TokenInfo, line_offsets: list[int]) -> Optional[tuple[int, int]]:
    """Convert a token's (row, column) positions to an absolute span."""
    start_row, start_col = token.start
    end_row, end_col = token.end
    if not 1 <= start_row <= len(line_offsets) or not 1 <= end_row <= len(line_offsets):
        return None
    start = line_offsets[start_row - 1] + start_col
    end = line_offsets[end_row - 1] + end_col
    if end <= start:
        return None
    return start, end


def _blank_spans(content: str, spans: list[tuple[int, int]]) -> str:
    """Replace the given spans with spaces, preserving every newline."""
    if not spans:
        return content

    chars = list(content)
    for start, end in spans:
        for index in range(max(start, 0), min(end, len(chars))):
            if chars[index] not in "\r\n":
                chars[index] = " "
    return "".join(chars)


# Keep the public surface explicit for tests and alternative callers.
__all__ = ["strip_comments_and_docstrings"]
