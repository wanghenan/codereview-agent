"""Tests for the S3 diff admission filter and its models."""

from __future__ import annotations

import pytest

from codereview.core.diff_filter import (
    BINARY_EXTENSIONS,
    LOCK_FILES,
    NON_CODE_EXTENSIONS,
    SKIP_BINARY,
    SKIP_EXCLUDED,
    SKIP_GENERATED,
    SKIP_LOCK_FILE,
    SKIP_MAX_FILES,
    SKIP_NON_CODE,
    SKIP_OVER_BUDGET,
    FilterConfig,
    estimate_tokens,
    filter_entries,
)
from codereview.models import (
    DiffEntry,
    ReviewConclusion,
    ReviewResult,
    RiskLevel,
    SkipRecord,
)


def _entry(
    filename: str,
    *,
    patch: str = "",
    additions: int = 0,
    deletions: int = 0,
    status: str = "modified",
) -> DiffEntry:
    """Build a DiffEntry without repeating the model boilerplate."""
    return DiffEntry(
        filename=filename,
        status=status,
        additions=additions,
        deletions=deletions,
        patch=patch,
    )


def _tokens(count: int) -> str:
    """Return a patch string whose estimated size is exactly ``count`` tokens."""
    return "x" * (count * 4)


class TestFilterConfig:
    """Defaults and mutability of the admission configuration."""

    def test_defaults(self) -> None:
        config = FilterConfig()
        assert config.max_tokens_per_file == 12000
        assert config.max_tokens_total == 120000
        assert config.max_files == 40
        assert config.extra_skip_patterns == []

    def test_extra_skip_patterns_are_not_shared_between_instances(self) -> None:
        first = FilterConfig()
        second = FilterConfig()
        first.extra_skip_patterns.append("dist/**")
        assert second.extra_skip_patterns == []


class TestEstimateTokens:
    """Character-based token estimation."""

    def test_empty_string_is_zero(self) -> None:
        assert estimate_tokens("") == 0

    def test_four_characters_per_token(self) -> None:
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcdefgh") == 2
        assert estimate_tokens("x" * 48000) == 12000

    def test_partial_token_is_floored(self) -> None:
        """Integer division keeps the estimate cheap and deterministic."""
        assert estimate_tokens("a") == 0
        assert estimate_tokens("abc") == 0
        assert estimate_tokens("abcde") == 1
        assert estimate_tokens("abcdefg") == 1

    def test_monotonic_in_length(self) -> None:
        shorter = estimate_tokens("x" * 400)
        longer = estimate_tokens("x" * 800)
        assert longer == 2 * shorter == 200


class TestBinaryAndNonCodeRules:
    """Rule 1: binary and non-code extensions are dropped first."""

    @pytest.mark.parametrize(
        "filename",
        ["assets/logo.png", "build/app.exe", "docs/manual.pdf", "static/ICON.PNG"],
    )
    def test_binary_extensions(self, filename: str) -> None:
        kept, skipped = filter_entries([_entry(filename)], FilterConfig())
        assert kept == []
        assert len(skipped) == 1
        assert skipped[0].filename == filename
        assert skipped[0].reason == SKIP_BINARY
        assert "binary" in skipped[0].detail

    @pytest.mark.parametrize(
        "filename",
        ["README.md", "docs/guide.rst", "notes.txt", "data/report.csv"],
    )
    def test_non_code_extensions(self, filename: str) -> None:
        kept, skipped = filter_entries([_entry(filename)], FilterConfig())
        assert kept == []
        assert skipped[0].reason == SKIP_NON_CODE
        assert "non-code" in skipped[0].detail

    def test_extensionless_source_files_are_kept(self) -> None:
        entries = [_entry("Makefile"), _entry("Dockerfile"), _entry("src/app.py")]
        kept, skipped = filter_entries(entries, FilterConfig())
        assert kept == entries
        assert skipped == []

    def test_config_files_are_not_treated_as_non_code(self) -> None:
        entries = [_entry("package.json"), _entry("config/app.yaml"), _entry("pyproject.toml")]
        kept, skipped = filter_entries(entries, FilterConfig())
        assert kept == entries
        assert skipped == []


class TestGeneratedRule:
    """Rule 2: generated artifacts."""

    @pytest.mark.parametrize(
        "filename",
        [
            "static/app.min.js",
            "styles/site.MIN.css",
            "api/service.pb.go",
            "src/models_generated.py",
        ],
    )
    def test_generated_patterns(self, filename: str) -> None:
        kept, skipped = filter_entries([_entry(filename)], FilterConfig())
        assert kept == []
        assert skipped[0].reason == SKIP_GENERATED
        assert skipped[0].filename == filename

    def test_gitattributes_linguist_generated(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".gitattributes").write_text(
            "# generated artifacts\n"
            "generated/** linguist-generated=true\n"
            "vendor/* linguist-generated\n"
            "*.gen.py linguist-generated\n"
            "keep_me.py -linguist-generated\n"
            "explicit_false.py linguist-generated=false\n",
            encoding="utf-8",
        )

        entries = [
            _entry("generated/deep/file.py"),
            _entry("vendor/lib.py"),
            _entry("src/foo.gen.py"),
            _entry("keep_me.py"),
            _entry("explicit_false.py"),
        ]
        kept, skipped = filter_entries(entries, FilterConfig())

        assert [entry.filename for entry in kept] == ["keep_me.py", "explicit_false.py"]
        assert [record.filename for record in skipped] == [
            "generated/deep/file.py",
            "vendor/lib.py",
            "src/foo.gen.py",
        ]
        assert {record.reason for record in skipped} == {SKIP_GENERATED}
        assert all(".gitattributes" in record.detail for record in skipped)

    def test_missing_gitattributes_disables_only_that_check(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        entry = _entry("src/app.py")
        kept, skipped = filter_entries([entry], FilterConfig())
        assert kept == [entry]
        assert skipped == []

    def test_malformed_gitattributes_lines_are_ignored(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".gitattributes").write_text(
            "only-a-pattern\n\n   \n# comment\nsrc/*.py linguist-generated\n",
            encoding="utf-8",
        )
        entry = _entry("src/app.py")
        kept, skipped = filter_entries([entry], FilterConfig())
        assert kept == []
        assert skipped[0].reason == SKIP_GENERATED


class TestLockFileRule:
    """Rule 3: dependency lock files."""

    @pytest.mark.parametrize(
        "filename",
        [
            "package-lock.json",
            "uv.lock",
            "poetry.lock",
            "Cargo.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
            "frontend/package-lock.json",
            "backend/Cargo.lock",
        ],
    )
    def test_lock_files(self, filename: str) -> None:
        kept, skipped = filter_entries([_entry(filename)], FilterConfig())
        assert kept == []
        assert skipped[0].reason == SKIP_LOCK_FILE
        assert skipped[0].filename == filename

    def test_non_lock_manifests_are_kept(self) -> None:
        entries = [_entry("package.json"), _entry("Cargo.toml"), _entry("uv.toml")]
        kept, skipped = filter_entries(entries, FilterConfig())
        assert kept == entries
        assert skipped == []


class TestExcludePatternRule:
    """Rule 4: user-supplied pathspec excludes."""

    def test_extra_skip_patterns(self) -> None:
        config = FilterConfig(extra_skip_patterns=["dist/**", "*.test.py", "**/vendor/**"])
        entries = [
            _entry("dist/bundle.js"),
            _entry("src/foo.test.py"),
            _entry("src/vendor/lib.py"),
        ]
        kept, skipped = filter_entries(entries, config)

        assert kept == []
        assert [record.reason for record in skipped] == [SKIP_EXCLUDED] * 3
        assert [record.filename for record in skipped] == [
            "dist/bundle.js",
            "src/foo.test.py",
            "src/vendor/lib.py",
        ]

    def test_negated_exclude_pattern_reincludes_file(self) -> None:
        config = FilterConfig(extra_skip_patterns=["*.py", "!keep.py"])
        dropped = _entry("drop.py")
        kept_entry = _entry("keep.py")
        kept, skipped = filter_entries([dropped, kept_entry], config)

        assert kept == [kept_entry]
        assert [record.filename for record in skipped] == ["drop.py"]


class TestPerFileBudget:
    """Rule 5: a single oversized patch is dropped."""

    def test_file_at_the_limit_is_kept(self) -> None:
        entry = _entry("exact.py", patch=_tokens(10))
        kept, skipped = filter_entries([entry], FilterConfig(max_tokens_per_file=10))
        assert kept == [entry]
        assert skipped == []

    def test_file_over_the_limit_is_skipped(self) -> None:
        exact = _entry("exact.py", patch=_tokens(10))
        oversized = _entry("oversized.py", patch=_tokens(11))
        kept, skipped = filter_entries([exact, oversized], FilterConfig(max_tokens_per_file=10))

        assert kept == [exact]
        assert [record.filename for record in skipped] == ["oversized.py"]
        assert skipped[0].reason == SKIP_OVER_BUDGET
        assert "per-file" in skipped[0].detail
        assert "10" in skipped[0].detail

    def test_per_file_budget_does_not_affect_other_files(self) -> None:
        entries = [
            _entry("a.py", patch=_tokens(10), additions=1),
            _entry("b.py", patch=_tokens(100), additions=100),
            _entry("c.py", patch=_tokens(10), additions=2),
        ]
        kept, skipped = filter_entries(
            entries,
            FilterConfig(max_tokens_per_file=50, max_tokens_total=1000),
        )
        assert kept == [entries[0], entries[2]]
        assert [record.filename for record in skipped] == ["b.py"]


class TestTotalTokenBudget:
    """Rule 6: total budget drops the lowest-churn files first."""

    def test_drops_lowest_churn(self) -> None:
        high = _entry("high.py", patch=_tokens(10), additions=100, deletions=50)
        medium = _entry("medium.py", patch=_tokens(10), additions=50)
        low = _entry("low.py", patch=_tokens(10), additions=1)

        kept, skipped = filter_entries([low, high, medium], FilterConfig(max_tokens_total=20))

        assert [entry.filename for entry in kept] == ["high.py", "medium.py"]
        assert [record.filename for record in skipped] == ["low.py"]
        assert skipped[0].reason == SKIP_OVER_BUDGET

    def test_ties_break_on_path_and_drop_from_the_tail(self) -> None:
        first = _entry("a.py", patch=_tokens(10), additions=5)
        second = _entry("b.py", patch=_tokens(10), additions=5)

        kept, skipped = filter_entries([second, first], FilterConfig(max_tokens_total=10))

        # a.py sorts before b.py, so b.py is the tail that gets dropped.
        assert kept == [first]
        assert [record.filename for record in skipped] == ["b.py"]

    def test_dropping_repeats_until_the_budget_fits(self) -> None:
        entries = [
            _entry("a.py", patch=_tokens(10), additions=1),
            _entry("b.py", patch=_tokens(10), additions=2),
            _entry("c.py", patch=_tokens(10), additions=3),
            _entry("d.py", patch=_tokens(10), additions=4),
        ]
        kept, skipped = filter_entries(entries, FilterConfig(max_tokens_total=20))

        assert [entry.filename for entry in kept] == ["c.py", "d.py"]
        assert [record.filename for record in skipped] == ["a.py", "b.py"]
        assert {record.reason for record in skipped} == {SKIP_OVER_BUDGET}

    def test_exact_budget_keeps_everything(self) -> None:
        entries = [
            _entry("a.py", patch=_tokens(10), additions=1),
            _entry("b.py", patch=_tokens(10), additions=2),
        ]
        kept, skipped = filter_entries(entries, FilterConfig(max_tokens_total=20))
        assert kept == entries
        assert skipped == []

    def test_result_is_independent_of_input_order(self) -> None:
        entries = [
            _entry("a.py", patch=_tokens(10), additions=1),
            _entry("b.py", patch=_tokens(10), additions=2),
            _entry("c.py", patch=_tokens(10), additions=3),
        ]
        config = FilterConfig(max_tokens_total=20)

        kept_forward, skipped_forward = filter_entries(entries, config)
        kept_reversed, skipped_reversed = filter_entries(list(reversed(entries)), config)

        assert {entry.filename for entry in kept_forward} == {"b.py", "c.py"}
        assert {entry.filename for entry in kept_reversed} == {"b.py", "c.py"}
        assert [record.filename for record in skipped_forward] == ["a.py"]
        assert [record.filename for record in skipped_reversed] == ["a.py"]


class TestMaxFiles:
    """Rule 7: file-count truncation."""

    def test_keeps_highest_churn_files(self) -> None:
        entries = [
            _entry("a.py", patch=_tokens(1), additions=1),
            _entry("b.py", patch=_tokens(1), additions=2),
            _entry("c.py", patch=_tokens(1), additions=3),
            _entry("d.py", patch=_tokens(1), additions=4),
            _entry("e.py", patch=_tokens(1), additions=5),
        ]
        kept, skipped = filter_entries(entries, FilterConfig(max_files=3))

        assert [entry.filename for entry in kept] == ["c.py", "d.py", "e.py"]
        assert [record.filename for record in skipped] == ["a.py", "b.py"]
        assert {record.reason for record in skipped} == {SKIP_MAX_FILES}

    def test_ties_break_on_path(self) -> None:
        entries = [
            _entry("a.py", patch=_tokens(1), additions=1),
            _entry("b.py", patch=_tokens(1), additions=1),
            _entry("c.py", patch=_tokens(1), additions=1),
        ]
        kept, skipped = filter_entries(entries, FilterConfig(max_files=2))

        assert [entry.filename for entry in kept] == ["a.py", "b.py"]
        assert [record.filename for record in skipped] == ["c.py"]

    def test_zero_max_files_drops_everything(self) -> None:
        entries = [_entry("a.py"), _entry("b.py")]
        kept, skipped = filter_entries(entries, FilterConfig(max_files=0))
        assert kept == []
        assert [record.filename for record in skipped] == ["a.py", "b.py"]
        assert {record.reason for record in skipped} == {SKIP_MAX_FILES}

    def test_total_budget_runs_before_max_files(self) -> None:
        entries = [
            _entry("a.py", patch=_tokens(10), additions=1),
            _entry("b.py", patch=_tokens(10), additions=2),
            _entry("c.py", patch=_tokens(10), additions=3),
            _entry("d.py", patch=_tokens(10), additions=4),
        ]
        kept, skipped = filter_entries(entries, FilterConfig(max_tokens_total=30, max_files=2))

        assert [entry.filename for entry in kept] == ["c.py", "d.py"]
        assert [(record.filename, record.reason) for record in skipped] == [
            ("a.py", SKIP_OVER_BUDGET),
            ("b.py", SKIP_MAX_FILES),
        ]


class TestRuleOrdering:
    """Earlier rules win, and output order is stable."""

    def test_excluded_paths_never_reach_the_budget_stage(self) -> None:
        huge_excluded = _entry("dist/bundle.js", patch=_tokens(1000))
        small_a = _entry("a.py", patch=_tokens(10))
        small_b = _entry("b.py", patch=_tokens(10))

        config = FilterConfig(
            max_tokens_per_file=50,
            max_tokens_total=20,
            extra_skip_patterns=["dist/**"],
        )
        kept, skipped = filter_entries([huge_excluded, small_a, small_b], config)

        assert kept == [small_a, small_b]
        assert [record.filename for record in skipped] == ["dist/bundle.js"]
        assert skipped[0].reason == SKIP_EXCLUDED
        assert "token" not in skipped[0].detail

    def test_generated_rule_wins_over_per_file_budget(self) -> None:
        generated_huge = _entry("static/app.min.js", patch=_tokens(1000))
        kept, skipped = filter_entries([generated_huge], FilterConfig(max_tokens_per_file=5))
        assert kept == []
        assert skipped[0].reason == SKIP_GENERATED

    def test_kept_and_skipped_keep_input_order(self) -> None:
        entries = [
            _entry("skip.md"),  # non-code
            _entry("keep_a.py", patch=_tokens(5), additions=1),
            _entry("logo.png"),  # binary
            _entry("keep_b.py", patch=_tokens(5), additions=2),
            _entry("package-lock.json"),  # lock file
        ]
        kept, skipped = filter_entries(entries, FilterConfig())

        assert [entry.filename for entry in kept] == ["keep_a.py", "keep_b.py"]
        assert [record.filename for record in skipped] == [
            "skip.md",
            "logo.png",
            "package-lock.json",
        ]
        assert [record.reason for record in skipped] == [
            SKIP_NON_CODE,
            SKIP_BINARY,
            SKIP_LOCK_FILE,
        ]

    def test_repeated_calls_are_deterministic(self) -> None:
        entries = [
            _entry("a.py", patch=_tokens(10), additions=1),
            _entry("b.py", patch=_tokens(10), additions=2),
            _entry("c.py", patch=_tokens(10), additions=3),
        ]
        config = FilterConfig(max_tokens_total=20, max_files=2)

        first = filter_entries(entries, config)
        second = filter_entries(entries, config)

        assert [entry.filename for entry in first[0]] == [entry.filename for entry in second[0]]
        assert [(record.filename, record.reason) for record in first[1]] == [
            (record.filename, record.reason) for record in second[1]
        ]

    def test_extension_sets_cover_the_documented_lock_files(self) -> None:
        """Sanity-check the exported sets used by the rules above."""
        assert ".png" in BINARY_EXTENSIONS
        assert ".md" in NON_CODE_EXTENSIONS
        assert "cargo.lock" in LOCK_FILES


class TestSkipRecordModel:
    """The S3 model additions stay backwards compatible."""

    def test_skip_record_defaults(self) -> None:
        record = SkipRecord(filename="a.py", reason=SKIP_BINARY)
        assert record.filename == "a.py"
        assert record.reason == SKIP_BINARY
        assert record.detail == ""

    def test_review_result_skipped_defaults_to_empty(self) -> None:
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=90.0,
            files_reviewed=[],
            summary="ok",
        )
        assert result.skipped == []

    def test_review_result_instances_do_not_share_the_default_list(self) -> None:
        first = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=90.0,
            files_reviewed=[],
            summary="ok",
        )
        second = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=90.0,
            files_reviewed=[],
            summary="ok",
        )
        first.skipped.append(SkipRecord(filename="a.py", reason=SKIP_GENERATED))
        assert second.skipped == []

    def test_review_result_serializes_skipped(self) -> None:
        result = ReviewResult(
            conclusion=ReviewConclusion.NEEDS_REVIEW,
            confidence=80.0,
            files_reviewed=[],
            summary="filtered",
            skipped=[
                SkipRecord(
                    filename="dist/app.min.js",
                    reason=SKIP_GENERATED,
                    detail="minified bundle",
                )
            ],
        )
        data = result.model_dump()
        assert data["skipped"] == [
            {
                "filename": "dist/app.min.js",
                "reason": SKIP_GENERATED,
                "detail": "minified bundle",
            }
        ]

    def test_review_result_accepts_skipped_dicts(self) -> None:
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=90.0,
            files_reviewed=[],
            summary="ok",
            skipped=[{"filename": "a.py", "reason": SKIP_BINARY}],
        )
        assert result.skipped[0].filename == "a.py"
        assert result.skipped[0].detail == ""

    def test_risk_level_untouched_by_s3(self) -> None:
        """Guard against accidental edits to existing model fields."""
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.LOW.value == "low"

    def test_filtered_entries_can_be_attached_to_a_result(self) -> None:
        entries = [_entry("keep.py"), _entry("README.md")]
        kept, skipped = filter_entries(entries, FilterConfig())
        result = ReviewResult(
            conclusion=ReviewConclusion.CAN_SUBMIT,
            confidence=95.0,
            files_reviewed=[],
            summary="ok",
            skipped=skipped,
        )
        assert [entry.filename for entry in kept] == ["keep.py"]
        assert [record.filename for record in result.skipped] == ["README.md"]
