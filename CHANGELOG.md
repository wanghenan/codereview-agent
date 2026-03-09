# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Unit tests for rule engine, cache, CLI, and output generation
- CI/CD pipeline with lint, type-check, test, and build stages
- Dependabot configuration for dependency vulnerability scanning
- CONTRIBUTING.md with development guidelines

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

- [1.0.0](#100---2024-03-08) - First stable release
- [0.1.0](#010---initial-release) - Initial release
