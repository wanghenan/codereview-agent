"""Tests for cache namespace computation (model + rules hash)."""

from __future__ import annotations

from codereview.cli import _compute_cache_namespace, _compute_rules_hash
from codereview.models import Config, ConfigLLM, LLMProvider


class _FakeRule:
    """Minimal stand-in for DetectionRule."""

    def __init__(self, id: str, pattern: str, severity: str) -> None:
        self.id = id
        self.pattern = pattern
        self.severity = severity


class _FakeRuleEngine:
    """Minimal stand-in for RuleEngine."""

    def __init__(self, rules: list) -> None:
        self.rules = rules


class TestComputeRulesHash:
    def test_no_rule_engine_returns_no_rules(self) -> None:
        assert _compute_rules_hash(None) == "no-rules"

    def test_empty_rules_returns_no_rules(self) -> None:
        assert _compute_rules_hash(_FakeRuleEngine([])) == "no-rules"

    def test_stable_across_insertion_order(self) -> None:
        r1 = _FakeRule("A", "pat1", "high")
        r2 = _FakeRule("B", "pat2", "low")
        h_order1 = _compute_rules_hash(_FakeRuleEngine([r1, r2]))
        h_order2 = _compute_rules_hash(_FakeRuleEngine([r2, r1]))
        # Order-independent so loading order can't churn the cache.
        assert h_order1 == h_order2

    def test_changes_when_rule_content_changes(self) -> None:
        h1 = _compute_rules_hash(_FakeRuleEngine([_FakeRule("A", "pat1", "high")]))
        h2 = _compute_rules_hash(_FakeRuleEngine([_FakeRule("A", "pat2", "high")]))
        assert h1 != h2

    def test_hash_is_short_hex(self) -> None:
        h = _compute_rules_hash(_FakeRuleEngine([_FakeRule("A", "p", "low")]))
        assert len(h) == 8
        int(h, 16)  # must be valid hex


class TestComputeCacheNamespace:
    def _config(self, model: str | None) -> Config:
        return Config(
            llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="k", model=model)
        )

    def test_uses_explicit_model(self) -> None:
        cfg = self._config("gpt-4o")
        ns = _compute_cache_namespace(cfg, None)
        assert ns == "gpt-4o:no-rules"

    def test_falls_back_to_default_model(self) -> None:
        cfg = Config(llm=ConfigLLM(provider=LLMProvider.OPENAI, api_key="k"))
        ns = _compute_cache_namespace(cfg, None)
        # OpenAI default in LLMFactory.DEFAULT_MODELS is gpt-4o.
        assert ns.startswith("gpt-4o:")

    def test_different_models_yield_different_namespace(self) -> None:
        ns_a = _compute_cache_namespace(self._config("gpt-4o"), None)
        ns_b = _compute_cache_namespace(self._config("gpt-4.1"), None)
        assert ns_a != ns_b

    def test_rules_hash_folded_in(self) -> None:
        engine = _FakeRuleEngine([_FakeRule("A", "p", "high")])
        ns_none = _compute_cache_namespace(self._config("gpt-4o"), None)
        ns_with = _compute_cache_namespace(self._config("gpt-4o"), engine)
        assert ns_none != ns_with
        assert ns_with.endswith(f":{_compute_rules_hash(engine)}")
