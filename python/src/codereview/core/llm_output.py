"""Turn chat-model output into text and JSON, whatever shape the provider returns.

Anthropic-compatible gateways answer with a **list of content blocks**, and a
reasoning model puts its chain of thought in a ``thinking`` block beside the
answer's ``text`` block. ``JsonOutputParser`` receives that list and fails with
an empty "Invalid json output", so parsing happens here instead: the text
blocks are joined (thinking blocks are dropped), markdown fences and leading
prose are stripped, and the first balanced JSON object wins.

The helpers take either the raw message object, its ``content`` list, or a
plain string, which keeps callers free of provider-specific branching.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

#: Block types whose ``text`` belongs to the answer. Reasoning blocks and tool
#: blocks are deliberately excluded.
_TEXT_BLOCK_TYPES = frozenset({None, "text", "text_delta"})


def message_text(raw: Any) -> str:
    """Return the assistant's answer text from a message, a content list, or a string.

    Args:
        raw: An ``AIMessage``, its ``content`` (string or block list), or text.

    Returns:
        The joined ``text`` blocks, or an empty string when the model answered
        with thinking blocks only.
    """
    if raw is None:
        return ""
    content = getattr(raw, "content", raw)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in _TEXT_BLOCK_TYPES:
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def extract_balanced_object(text: str) -> Optional[str]:
    """Extract the first balanced ``{...}`` JSON object from ``text``.

    Scans for an opening ``{`` and tracks brace depth to arbitrary nesting,
    ignoring braces inside string literals (handling ``\\"`` escapes). Returns
    the substring of the first object whose braces balance, or ``None``.

    Unlike a fixed-depth regex this handles deeply nested objects correctly,
    e.g. ``{"a":{"b":{"c":1}}}``.

    Args:
        text: Text that may contain a JSON object.

    Returns:
        The balanced object substring, or None.
    """
    start = -1
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    return text[start : i + 1]

    return None


def parse_json_object(raw: Any) -> Optional[dict]:
    """Parse the first JSON object in model output.

    Tolerates a markdown code fence, prose before or after the object, and
    content block lists (thinking blocks are ignored).

    Args:
        raw: An ``AIMessage``, its ``content``, a string, or an already parsed
            mapping.

    Returns:
        The parsed object, or ``None`` when the output holds no JSON object.
    """
    if isinstance(raw, dict):
        return raw

    text = message_text(raw).strip()
    if not text:
        return None

    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block:
        try:
            parsed = json.loads(code_block.group(1))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    extracted = extract_balanced_object(text)
    if extracted is not None:
        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    return None
