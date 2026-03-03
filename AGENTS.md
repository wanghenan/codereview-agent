# AGENTS.md - CodeReview Agent Development Guide

This file provides context for AI agents working on this codebase.

---

## Project Overview

CodeReview Agent is an AI-powered code review tool built with:
- **Python** (core logic): LangChain + LangGraph
- **Node.js/TypeScript**: Wrapper for Python CLI
- **Multiple LLM Providers**: OpenAI, Anthropic, 智谱AI, MiniMax, 阿里云, DeepSeek

---

## Project Structure

```
crAgent/
├── python/              # Main Python package
│   ├── src/codereview/
│   │   ├── agents/     # Review agents (analyzer, reviewer)
│   │   ├── core/       # Config, LLM, Cache
│   │   ├── models/     # Pydantic models
│   │   ├── output/     # Report generation
│   │   ├── cli.py      # CLI entry point
│   │   └── github_app.py
│   └── pyproject.toml
├── nodejs/             # TypeScript wrapper
│   ├── src/cli/
│   └── package.json
└── docs/
```

---

## Build, Lint & Test Commands

### Python (`python/` directory)

| Command | Description |
|---------|-------------|
| `pip install -e .` | Install package in editable mode install -e ".[dev] |
| `pip"` | Install with dev dependencies |
| `ruff check .` | Run linter |
| `ruff check . --fix` | Auto-fix lint issues |
| `mypy src/` | Type checking (strict mode) |
| `python -m pytest` | Run tests (if any exist) |
| `python -m pytest -xvs` | Run tests with verbose output |
| `python -m pytest path/to/test.py::test_name` | Run single test |
| `python -m codereview.cli --help` | CLI help |

### Node.js (`nodejs/` directory)

| Command | Description |
|---------|-------------|
| `npm install` | Install dependencies |
| `npm run build` | Compile TypeScript (`tsc`) |
| `npx tsc --noEmit` | Type check only |

### Running the Application

```bash
# CLI usage
python -m codereview.cli --diff diff.json

# With config
python -m codereview.cli --config .codereview-agent.yaml --diff diff.json

# JSON output
python -m codereview.cli --json --diff diff.json
```

---

## Code Style Guidelines

### Python

- **Line length**: 100 characters max
- **Python version**: 3.9+
- **Type hints**: Use everywhere (mypy strict mode enabled)
- **Imports**: Use `from __future__ import annotations` for forward references
- **Formatting**: Handled by ruff (E, F, I, N, W, UP rules)
- **Docstrings**: Google-style (Args, Returns, Raises)
- **Error handling**: Use specific exceptions, never bare `except:`

Example:
```python
"""Module docstring."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

class ConfigError(Exception):
    """Configuration error."""
    pass


def load_config(path: Path | None = None) -> Config:
    """Load configuration.

    Args:
        path: Path to config file.

    Returns:
        Validated configuration.

    Raises:
        ConfigError: If configuration is invalid.
    """
    ...
```

### TypeScript

- **Strict mode**: Enabled in tsconfig.json
- **Target**: ES2022
- **Module**: CommonJS
- **Types**: Use interfaces for all data structures
- **Error handling**: Always handle async errors with try/catch

---

## Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Python modules | snake_case | `cache_manager.py` |
| Python classes | PascalCase | `ConfigLoader` |
| Python functions | snake_case | `load_config()` |
| Python constants | UPPER_SNAKE | `MAX_RETRIES` |
| TypeScript files | kebab-case | `wrapper.ts` |
| TypeScript classes | PascalCase | `ReviewResult` |
| TypeScript functions | camelCase | `runCodeReview()` |

---

## Error Handling

- Use custom exception classes for domain errors
- Never use bare `except:` — catch specific exceptions
- Propagate errors with context (`raise ConfigError(f"Invalid: {e}")`)
- Log errors before re-raising in async contexts

---

## Key Dependencies

### Python
- `langchain>=0.3.0` - LLM framework
- `langgraph>=0.2.0` - Agent orchestration
- `pydantic>=2.0.0` - Data validation
- `pyyaml>=6.0.0` - Config parsing

### Dev Dependencies
- `ruff>=0.6.0` - Linter/formatter
- `mypy>=1.0.0` - Type checker
- `pytest>=8.0.0` - Testing

---

## Configuration

Default config file: `.codereview-agent.yaml` in project root.

```yaml
llm:
  provider: openai
  apiKey: ${OPENAI_API_KEY}
  model: gpt-4o

criticalPaths:
  - src/auth
  - src/payment

excludePatterns:
  - "*.test.ts"
  - "vendor/**"

cache:
  ttl: 7
  forceRefresh: false

output:
  prComment: true
  reportPath: .codereview-agent/output
  reportFormat: markdown
```

---

## Testing Guidelines

- Place tests in `tests/` directory (create if needed)
- Use `pytest` with `pytest-asyncio` for async tests
- Use `pytest-mock` for mocking
- Follow naming: `test_module_name.py`
- Run single test: `pytest path/to/test.py::test_function_name`

---

## Common Patterns

### Async Functions
```python
async def run_review(...) -> dict:
    """Run the code review process."""
    config = ConfigLoader.load(config_path)
    llm = LLMFactory.create(config.llm)
    ...
    return {"result": result.model_dump(), "outputs": outputs}
```

### Pydantic Models
```python
from pydantic import BaseModel, Field

class ConfigLLM(BaseModel):
    """LLM configuration."""
    provider: LLMProvider
    api_key: str = Field(..., min_length=1)
    model: str | None = None
```

### Environment Variables in Config
```yaml
apiKey: ${OPENAI_API_KEY}
apiKey: ${VAR_NAME:-default_value}
```

---

## Notes for Agents

1. **No pre-commit hooks** - Manually run `ruff check . --fix` before committing
2. **No test directory** - Tests should be added to `python/tests/`
3. **No Cursor/Copilot rules** - Follow this AGENTS.md file
4. **Type safety required** - mypy strict mode, no `Any` types
5. **Config-first** - New features should be configurable via YAML
