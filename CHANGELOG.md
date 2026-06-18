# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
