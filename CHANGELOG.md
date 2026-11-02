# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `LICENSE` (MIT) file and `[project.license]` metadata in `pyproject.toml` (previously declared but missing).
- Automated release workflow (`.github/workflows/release.yml`): tag-triggered, runs a self-contained quality gate (ruff + pytest), builds wheel/sdist, and publishes a GitHub Release with notes extracted from CHANGELOG.md. Pre-release tags (e.g. `v1.2.0-rc1`) are auto-marked as prerelease.
- Project URLs (`Homepage`, `Repository`, `Changelog`, `Issues`) in `pyproject.toml` so built artifacts carry complete metadata.
- Test coverage gating via `pytest-cov` + `[tool.coverage]` (`fail_under = 50`, branch coverage); current baseline ~64%.
- CI Python version matrix (3.10 / 3.11 / 3.12) so all declared `requires-python` versions are exercised.
- `.dockerignore` to keep `.git`, caches, venvs, and local output out of the Docker build context.
- `FileReviewCache.cleanup_expired()` to prune expired/corrupt cache files; invoked once per review run to bound `.codereview-agent/cache/` growth.

- Evidence-anchored findings: every issue now carries `category`, `confidence`, `evidence` anchors, an optional `suggested_patch` and its `source` (`rule`/`tool`/`llm`).
- Admission filter (`core/diff_filter.py`): skips binaries, generated files and lock files, enforces per-file/total token budgets and reports skipped files on `ReviewResult.skipped`.
- External tool runner (`core/tool_runner.py`): normalises ruff / eslint / semgrep / trufflehog output into findings; missing tools and failures never abort a review.
- Inline PR review output (`output/inline.py`): top findings become line comments (capped at 25, ordered by severity then confidence), the rest fold into the summary; `findings.json` payload is returned alongside.
- `S0` evaluation benchmark (`tests/benchmark/`): 24 injected defect cases plus 6 negative cases, a generator pinned to `HEAD` and a runner producing side-by-side reports.
- Symbol index (`core/symbol_index.py`, stdlib `ast`, no new dependencies) and bounded cross-file context injection into review prompts (3 neighbours / 2400 chars by default).
- `llm.headers` config to send extra HTTP headers on every LLM request (e.g. `x-opencode-session` for opencode-go gateways).
### Changed
- `requires-python` raised from `>=3.9` to `>=3.10` to match reality: the source uses PEP 604 unions (`X | None`) at runtime, which requires Python 3.10+. The CI matrix drops 3.9 accordingly. (3.9 compatibility is a separate follow-up: converting unions to `Optional[X]`.)

### Changed
- CLI entry point switched from `main` to a top-level `cli()` dispatcher backed by argparse subparsers; `codereview fix` and `codereview merge` are now first-class subcommands while remaining backward-compatible.
- `MergeMethod` is now defined once (in `models`) and re-exported; the duplicate in `core/github_client.py` was removed.
- `core/__init__.py` `__getattr__` now covers every name in `__all__` (`TeamInsights`, `create_team_insights`); previously importing them raised `AttributeError`.
- `Dockerfile` installs the package normally (`pip install .`) instead of editable install (`-e .`).
- CI workflow `permissions` pinned to `contents: read` (least privilege).

### Removed
- Stray `test.txt` committed by accident.

- `core/languages/` (seven hand-written regex rule packs) and `core/complexity_scorer.py`, neither used by the review pipeline; external linters now own deterministic discovery.
## [1.2.0] - 2026-06-18

### Added
- `pathspec` dependency and `ExcludeMatcher` for gitignore-style exclude patterns
- File-review cache namespace (model + rules hash) so switching LLM or updating rules invalidates stale reviews
- Robust JSON repair for LLM output via balanced-brace extraction (handles arbitrary nesting)
- Test coverage for previously-untested `_repair_json_output` and exclude matching

### Changed
- `excludePatterns` now uses gitignore semantics (`**` recursion, `!` negation, directory anchoring) via `pathspec`
- Fallback LLM instances are now cached per chain index instead of rebuilt on every invoke
- Progress tracking in `review_files` uses a single tqdm bar over `asyncio.as_completed` (fixes double counting)
- Silent `except Exception: pass` blocks in cache now emit debug logs

### Fixed
- Progress bar double-counting bug (inner `completed` counter + outer `pbar.update`)
- Unreachable exception branch in `review_files` replaced with real exception guarding
- JSON repair regex that silently truncated deeply-nested objects (`{"a":{"b":{"c":1}}}`)
- `exclude_patterns` directory semantics (e.g. `dist/**` no longer over-matches `distrib/**`)
- Analyzer system prompt crash on Python <3.12: literal `{}` in the JSON schema example were parsed as nested f-string replacement fields by LangChain's `ChatPromptTemplate`

## [1.1.0] - 2026-04-04

### Added
- CI/CD pipeline with lint, type-check, test, and build stages
- Dependabot configuration for dependency vulnerability scanning
- CONTRIBUTING.md with development guidelines
- Unit tests for rule engine, cache, CLI, and output generation

### Changed
- Improved test coverage across core modules

## [1.0.0] - 2024-03-08

### Added
- AI-powered code review using LangChain + LangGraph
- Support for multiple LLM providers (OpenAI, Anthropic, Zhipu, MiniMax, Qwen, DeepSeek)
- GitHub App integration for automated PR reviews
- Risk detection rule engine with customizable rules
- Project context caching for incremental reviews
- Multiple output formats (Markdown, JSON)
- PR comment generation with review summaries
- CLI tool for local reviews
- Docker support
- Custom prompt templates
- File-level review caching

### Features
- Automatic detection of tech stack, frameworks, and dependencies
- Risk assessment with severity levels (high, medium, low)
- Diff-based review focusing on changed code
- Incremental review with caching
- Configurable via `.codereview-agent.yaml`

### Documentation
- README.md (English and Chinese)
- Comprehensive documentation in `docs/`

## [0.1.0] - Initial Release

### Added
- Initial project structure
- Basic CLI interface
- Prototype LLM integration

---

## Version History

- [1.2.0](#120---2026-06-18) - Review pipeline optimizations and reliability fixes
- [1.1.0](#110---2026-04-04) - CI/CD, dependency scanning, and test infrastructure
- [1.0.0](#100---2024-03-08) - First stable release
- [0.1.0](#010---initial-release) - Initial release
