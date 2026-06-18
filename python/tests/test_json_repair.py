"""Tests for LLM JSON output repair (_repair_json_output).

Previously this method had zero test coverage and its brace-matching regex
only handled a single level of nesting, silently truncating deeply nested
objects. These tests pin the corrected brace-balancing behavior.
"""

from __future__ import annotations

from codereview.agents.reviewer import ReviewAgent, _extract_balanced_object


class TestExtractBalancedObject:
    def test_flat_object(self) -> None:
        assert _extract_balanced_object('{"a": 1}') == '{"a": 1}'

    def test_one_level_nesting(self) -> None:
        s = '{"a": {"b": 2}}'
        assert _extract_balanced_object(s) == s

    def test_deeply_nested_object(self) -> None:
        # The old regex returned the inner {"c":1} fragment; the scan must
        # return the full outer object.
        s = '{"a": {"b": {"c": 1}}}'
        assert _extract_balanced_object(s) == s

    def test_array_in_object(self) -> None:
        s = '{"items": [{"id": 1}, {"id": 2}]}'
        assert _extract_balanced_object(s) == s

    def test_braces_inside_string_are_ignored(self) -> None:
        # Braces within a string value must not affect depth counting.
        s = '{"code": "function() { return {}; }"}'
        assert _extract_balanced_object(s) == s

    def test_escaped_quote_inside_string(self) -> None:
        s = '{"msg": "he said \\"hi {x}\\""}'
        assert _extract_balanced_object(s) == s

    def test_extracts_from_surrounding_text(self) -> None:
        text = 'Here is the result:\n{"risk_level": "high", "ok": true}\nDone.'
        assert _extract_balanced_object(text) == '{"risk_level": "high", "ok": true}'

    def test_no_object_returns_none(self) -> None:
        assert _extract_balanced_object("no json here") is None

    def test_unbalanced_returns_none(self) -> None:
        assert _extract_balanced_object('{"a": {') is None


class TestRepairJsonOutput:
    def test_dict_passthrough(self) -> None:
        d = {"a": 1}
        assert ReviewAgent._repair_json_output(d) is d

    def test_empty_returns_none(self) -> None:
        assert ReviewAgent._repair_json_output("") is None
        assert ReviewAgent._repair_json_output(None) is None
        assert ReviewAgent._repair_json_output("   ") is None

    def test_code_block_extraction(self) -> None:
        raw = '```json\n{"risk_level": "low"}\n```'
        assert ReviewAgent._repair_json_output(raw) == {"risk_level": "low"}

    def test_plain_code_block_extraction(self) -> None:
        raw = '```\n{"x": 1}\n```'
        assert ReviewAgent._repair_json_output(raw) == {"x": 1}

    def test_surrounding_text(self) -> None:
        raw = 'The analysis: {"issues": [], "ok": true} end.'
        assert ReviewAgent._repair_json_output(raw) == {"issues": [], "ok": True}

    def test_deeply_nested_repair(self) -> None:
        raw = 'Result: {"a": {"b": {"c": 1}}}'
        # The whole nested object must be parsed, not just an inner fragment.
        assert ReviewAgent._repair_json_output(raw) == {"a": {"b": {"c": 1}}}

    def test_invalid_returns_none(self) -> None:
        assert ReviewAgent._repair_json_output("not json at all") is None
