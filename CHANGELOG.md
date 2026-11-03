# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.2] - 2026-11-03

### Fixed
- Anthropic-compatible gateways no longer fail with `401 Go requires a credential`. `anthropic` 2.x authenticates with `Authorization: Bearer`, while gateways such as `opencode.ai/zen/go` implement `x-api-key`; the key is now also sent as `x-api-key` for a custom `base_url` (the official endpoint is unchanged).
- A review that exhausts its retries is no longer scored as a benchmark candidate hit: the synthetic failure issue has no line, so it used to count as a file-level match and an API outage could raise the score.
- The `[dev]` extras were unsatisfiable at their own minimums: `pytest>=8.0.0` together with `pytest-asyncio>=1.2.0` (which requires `pytest<9,>=8.2`) made `pip install --resolution lowest-direct -e ".[dev]"` fail outright, and `matplotlib>=3.0.0` no longer builds on the supported interpreters. Floors are now `pytest>=8.2.0` and `matplotlib>=3.8.0`.
- `[tool.mypy].python_version` said `3.9` while `requires-python` is `>=3.10`, so the type check silently targeted an unsupported interpreter (mypy 2.x rejects it outright). It is now `"3.10"`, and `[tool.ruff].target-version` matches.

### Added
- `bench.py --strictness defect|design|nit` runs a single stratum of the corpus, and reports record the resolved `llm` provider/model/baseUrl instead of only the config path, so numbers can be attributed to the model that produced them.
- CI job `Test (minimum dependency floors)` installs the lowest version each floor allows (`uv pip install --resolution lowest-direct`) and runs the suite, so the published floors are exercised instead of only the latest resolution. Verified range: `langchain 0.3.26`–`1.4.8`, `langgraph 0.2.17`–`1.2.19`, 714 tests passing at both ends.

### Changed
- Dependency floors raised to what is actually tested: `pydantic>=2.12.5`, `aiohttp>=3.13.5`, `tqdm>=4.67.3`, `python-dotenv>=1.2.1`, `langchain-openai>=0.3.35`, `langchain-anthropic>=0.3.22`. CI actions move to `checkout@v6`, `setup-python@v6`, `setup-uv@v7`, `upload-artifact@v7`, `github-script@v8`.

## [1.3.1] - 2026-11-03

### Added
- Benchmark reports record each finding's `evidence` and `suggestion` (both `--json-out` and the markdown table), so re-anchoring findings by their quoted code can be evaluated offline before it is built.

### Fixed
- The wheel now ships `codereview/rules/owasp_rules.yaml` via `[tool.setuptools.package-data]`. Without it the *installed* CLI loaded 0 detection rules and reported "0 rules" (v1.3.0 shipped no rules at all); path-based installs hid the bug because the YAML was on disk. The release workflow now smoke-tests the built wheel: it installs it, runs `--list-rules` and fails the release when the SQL injection rule is missing.

## [1.3.0] - 2026-11-02

### Added
- Dedupe and team memory (S6): inline comments carry a hidden fingerprint marker, a re-review of the same PR posts no duplicate, and dismissals recorded in `.codereview-agent/memory.json` downweight matching findings instead of dropping them.
- Real-PR benchmark corpus (20 cases from 9 public repositories) collected from human review comments, with `strictness` (`defect`/`design`/`nit`) and a `--json-out` report; `gate.py` + a nightly workflow compare candidate hits against a checked-in baseline.
- `context.neighbors_trigger` (`always` | `signature`): optionally inject cross-file context only when the edited lines are confined to a definition header.
- `--dry-run` and `--offline` flags for the review CLI.
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
- `llm.maxTokens` config to cap (or raise) output tokens per request; unset keeps the client default.

### Changed
- The real-PR collector slices each case at the reviewed comment's commit (`original_commit_id` and its parent) instead of the PR head, so the diff matches the code the human actually saw; `--final-diff` keeps the old behaviour.
- Review prompts now show each diff line's new-file line number (`core/diff_numbering.py`): context lines render as `  121 | ...`, added lines as `+ 123 | ...` and deleted lines keep a blank number field. `{patch}` carries the numbered diff while cache keys, dedupe fingerprints and inline-comment positioning still use the raw patch; the prompt requires `line_number` to be one of the displayed numbers, so findings anchor on the failing line instead of the hunk header.
- `requires-python` raised from `>=3.9` to `>=3.10` to match reality: the source uses PEP 604 unions (`X | None`) at runtime, which requires Python 3.10+. The CI matrix drops 3.9 accordingly. (3.9 compatibility is a separate follow-up: converting unions to `Optional[X]`.)
- CLI entry point switched from `main` to a top-level `cli()` dispatcher backed by argparse subparsers; `codereview fix` and `codereview merge` are now first-class subcommands while remaining backward-compatible.
- `MergeMethod` is now defined once (in `models`) and re-exported; the duplicate in `core/github_client.py` was removed.
- `core/__init__.py` `__getattr__` now covers every name in `__all__` (`TeamInsights`, `create_team_insights`); previously importing them raised `AttributeError`.
- `Dockerfile` installs the package normally (`pip install .`) instead of editable install (`-e .`).
- CI workflow `permissions` pinned to `contents: read` (least privilege).

### Fixed
- Rules now scan code only: `rules/code_only.py` blanks comments and docstrings before matching while keeping every line number and inline string literal intact (Python via `tokenize`, other languages best effort for `#`, `//` and `/* ... */`). Prose such as `# Never eval() untrusted input.` no longer produces HIGH findings, and unparsable input is returned unchanged instead of raising.
- LLM JSON parsing accepts provider content-block replies: Anthropic-compatible gateways answer with a list of `thinking` + `text` blocks, which `JsonOutputParser` could not read (empty "Invalid json output"). `core/llm_output.py` now takes the text blocks, strips fences and prose, and the reviewer, project analyzer and fixer all use it.

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
