"""Tests for provider-agnostic message text and JSON extraction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from codereview.core.llm_output import extract_balanced_object, message_text, parse_json_object


def message(content: object) -> SimpleNamespace:
    """Stand-in for an ``AIMessage``; only ``content`` matters here."""
    return SimpleNamespace(content=content)


def test_message_text_joins_text_blocks_and_drops_thinking() -> None:
    """Anthropic gateways return thinking beside text; only text is the answer."""
    content = [
        {"type": "thinking", "thinking": "weighing options {\"not\": \"the answer\"}"},
        {"type": "text", "text": '{"issues": []}'},
    ]

    assert message_text(message(content)) == '{"issues": []}'


def test_message_text_accepts_plain_strings_and_lists_of_strings() -> None:
    """Older adapters return a string; a mixed list still joins the text parts."""
    assert message_text("hello") == "hello"
    assert message_text(message("hello")) == "hello"
    assert message_text(["a", "b"]) == "a\nb"
    assert message_text(None) == ""


def test_parse_json_object_reads_the_text_block_of_a_reasoning_message() -> None:
    """The failure this module fixes: a content list reached JsonOutputParser."""
    content = [
        {"type": "thinking", "thinking": "the user wants JSON"},
        {"type": "text", "text": '{"risk_level": "low", "issues": []}'},
    ]

    assert parse_json_object(message(content)) == {"risk_level": "low", "issues": []}


def test_parse_json_object_strips_markdown_fences() -> None:
    """Models often wrap the object in a fenced block."""
    text = 'Here you go:\n```json\n{"issues": [{"line_number": 4}]}\n```\nThat is all.'

    assert parse_json_object(text) == {"issues": [{"line_number": 4}]}


def test_parse_json_object_finds_an_object_in_prose() -> None:
    """Prose before and after the object must not defeat the brace scan."""
    assert parse_json_object('Sure. {"a": {"b": 1}} Hope this helps.') == {"a": {"b": 1}}


def test_parse_json_object_returns_none_when_the_model_only_thinks() -> None:
    """A thinking-only answer has no JSON to parse; callers retry or fail loudly."""
    assert parse_json_object(message([{"type": "thinking", "thinking": "hmm"}])) is None
    assert parse_json_object("") is None
    assert parse_json_object("no json here") is None


def test_parse_json_object_passes_dicts_through() -> None:
    """An already parsed result is returned unchanged."""
    assert parse_json_object({"ok": True}) == {"ok": True}


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '{"a": {"b": {"c": 1}}}',
        '{"a": "brace } in string"}',
        '{"a": "quote \\" then }"}',
    ],
)
def test_extract_balanced_object_handles_nesting_and_strings(text: str) -> None:
    """Brace counting respects nesting and string literals."""
    assert extract_balanced_object(text) == text


def test_dump_unparseable_is_disabled_without_env(monkeypatch, tmp_path):
    from codereview.core import llm_output

    monkeypatch.delenv("CODEREVIEW_DUMP_LLM_RAW", raising=False)
    assert llm_output.dump_unparseable("not json") is None
    assert not list(tmp_path.iterdir())


def test_dump_unparseable_writes_the_raw_text(monkeypatch, tmp_path):
    """A parse failure is otherwise lost to the retry loop that follows it."""
    from codereview.core import llm_output

    monkeypatch.setenv("CODEREVIEW_DUMP_LLM_RAW", str(tmp_path))
    path = llm_output.dump_unparseable("I cannot answer in JSON", "pkg_mod.py")

    assert path is not None and path.parent == tmp_path
    assert path.read_text(encoding="utf-8") == "I cannot answer in JSON"
    assert "pkg_mod.py" in path.name


def test_dump_unparseable_never_raises(monkeypatch):
    from codereview.core import llm_output

    monkeypatch.setenv("CODEREVIEW_DUMP_LLM_RAW", "/dev/null/not-a-dir")
    assert llm_output.dump_unparseable("x") is None
