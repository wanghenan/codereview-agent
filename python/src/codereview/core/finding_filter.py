"""Noise filtering for review findings (S4, second half).

The S4 adjudication layer separates *discovery* from *trust*. Findings that
come from deterministic producers (``source="rule"`` or ``source="tool"``) are
repeatable and cheap to verify, so the user should be able to filter them only
by an explicit category decision. Findings produced by the model
(``source="llm"``) are additionally subject to confidence and risk thresholds.

Every rule is evaluated per finding and the finding must pass *all* enabled
rules to survive. The first failed rule, in :class:`FilterRules` field order,
is the reason recorded on :class:`~codereview.models.FilteredFinding`.

The filter is a pure function over models so it can be unit-tested without an
LLM, a repository checkout, or the LangGraph pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from codereview.models import FileIssue, FilteredFinding, RiskLevel

logger = logging.getLogger(__name__)

# Drop reasons. Plain strings keep the serialized ReviewResult stable and
# cheap to compare in tests and downstream tooling.
REASON_LOW_CONFIDENCE = "low-confidence"
REASON_LOW_RISK_LLM = "low-risk-llm"
REASON_CATEGORY = "category"


@dataclass
class FilterRules:
    """Tunable rules for dropping noisy findings.

    Attributes:
        min_confidence: Drop LLM findings whose confidence is strictly below
            this value. ``0.0`` disables the rule (the default), so existing
            behaviour is preserved.
        drop_low_risk_llm: Drop LLM findings whose risk level is ``low``.
            Rule/tool findings are never affected by this rule.
        drop_categories: Categories to drop for *every* source. An empty tuple
            disables the rule.
    """

    min_confidence: float = 0.0
    drop_low_risk_llm: bool = False
    drop_categories: tuple[str, ...] = ()


def _category_value(category: object) -> str:
    """Return a comparable, lower-case category value.

    ``FileIssue.category`` is an :class:`~codereview.models.IssueCategory`
    enum, while YAML configuration may contain plain strings. Accept both.
    """
    value = getattr(category, "value", category)
    return str(value).strip().lower()


def _is_enabled(rules: FilterRules) -> bool:
    """Return whether at least one rule can drop a finding."""
    return rules.min_confidence > 0.0 or rules.drop_low_risk_llm or bool(rules.drop_categories)


def _drop_reason(issue: FileIssue, rules: FilterRules, blocked_categories: set[str]) -> str | None:
    """Return the first rule that rejects ``issue``, or ``None`` if it passes.

    Confidence and low-risk rules deliberately skip non-LLM findings: rule and
    tool output is deterministic and therefore trusted. ``drop_categories`` is
    an explicit user decision and applies to every source.
    """
    if issue.source == "llm":
        if rules.min_confidence > 0.0 and issue.confidence < rules.min_confidence:
            return REASON_LOW_CONFIDENCE
        if rules.drop_low_risk_llm and issue.risk_level == RiskLevel.LOW:
            return REASON_LOW_RISK_LLM

    if blocked_categories and _category_value(issue.category) in blocked_categories:
        return REASON_CATEGORY

    return None


def filter_findings(
    issues: Iterable[FileIssue], rules: FilterRules
) -> tuple[list[FileIssue], list[FilteredFinding]]:
    """Split findings into kept and filtered sets.

    Args:
        issues: Findings produced by the review nodes (LLM, rules, or tools).
        rules: Enabled noise-filter rules.

    Returns:
        ``(kept, filtered)`` where ``kept`` preserves the input order of the
        findings that pass every enabled rule, and ``filtered`` records one
        :class:`~codereview.models.FilteredFinding` per dropped finding, also
        in input order. With the default :class:`FilterRules` every finding is
        kept and ``filtered`` is empty.
    """
    blocked_categories = {_category_value(category) for category in rules.drop_categories}
    kept: list[FileIssue] = []
    filtered: list[FilteredFinding] = []

    for issue in issues:
        reason = _drop_reason(issue, rules, blocked_categories)
        if reason is None:
            kept.append(issue)
        else:
            filtered.append(FilteredFinding(reason=reason, issue=issue))

    if filtered:
        logger.info(
            "Noise filter dropped %d of %d finding(s)",
            len(filtered),
            len(kept) + len(filtered),
        )

    return kept, filtered


__all__ = [
    "FilterRules",
    "FilteredFinding",
    "REASON_CATEGORY",
    "REASON_LOW_CONFIDENCE",
    "REASON_LOW_RISK_LLM",
    "filter_findings",
]
