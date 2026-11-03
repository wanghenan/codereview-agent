# AGENTS.md - CodeReview Agent

Guidelines for AI agents operating in this repository.

---

## Commands

### Python Setup
```bash
cd python && uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
```

### Lint (Ruff)
```bash
ruff check python/src/          # check
ruff check --fix python/src/    # fix
ruff format python/src/         # format
```

### Type Check
```bash
mypy python/src/
```

### Test (pytest)
```bash
pytest python/tests/ -v                          # all tests
pytest python/tests/test_rules.py -v             # specific file
pytest python/tests/test_rules.py::test_foo -v  # single test
pytest python/tests/ -k "test_rule" -v           # by pattern
pytest python/tests/ --cov=codereview            # with coverage
pytest python/tests/ -m "not slow" -v           # exclude slow
```

### Build
```bash
cd python && python -m build
```

---

## Code Style

### General
- **Line length**: max 100 chars
- **Python**: 3.10+ (`requires-python`, tested on 3.10/3.11/3.12). The source
  uses PEP 604 unions at runtime, so 3.9 is not supported.
- **Follow PEP 8** with ruff

### Imports
```python
from __future__ import annotations
import asyncio, logging
from pathlib import Path
from pydantic import BaseModel, Field
from codereview.models import ReviewResult
# ruff handles sorting
```

### Type Hints
- Required for function signatures
- Use `list`, `dict` (not `List`, `Dict`)
- Use PEP 604 unions: `X | None`, not `Optional[X]`. Ruff's `UP007` enforces
  this because `[tool.ruff].target-version` is `py310`; `Optional` is still
  fine inside quoted annotations that must stay 3.9-compatible.

### Naming
- `snake_case` for functions/variables
- `PascalCase` for classes
- `UPPER_SNAKE` for constants
- `_leading_underscore` for private

### Pydantic Models
```python
class RiskLevel(str, Enum):
    HIGH = "high"; MEDIUM = "medium"; LOW = "low"

class FileIssue(BaseModel):
    file_path: str
    line_number: int | None = None
    risk_level: RiskLevel
    description: str
    suggestion: str | None = None
```

### Error Handling
- Never bare `except:`
- Catch specific exceptions
- Log appropriately

```python
try:
    return subprocess.run(...).stdout
except FileNotFoundError:
    logger.error("Git not found")
    return ""
```

### Logging
```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
```

### Docstrings
Google-style: Summary line, then Args/Returns/Raises.

### Testing
- `test_<module>.py` in `python/tests/`
- Use `@pytest.mark.slow` and `@pytest.mark.integration`
- Mock external dependencies

### Commits
Conventional Commits: `<type>(<scope>): <description>`
Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

---

## Structure

```
python/
├── src/codereview/
│   ├── agents/     # LangGraph agents
│   ├── core/      # Cache, config, LLM
│   ├── models/    # Pydantic models
│   ├── output/    # Report generation
│   ├── rules/     # Risk detection
│   └── cli.py     # Entry point
└── tests/         # Test suite
```

---

## Common Tasks

Run CLI: `cd python && python -m codereview.cli --diff '{"files": [...]}'`

Add rule: create in `rules/`, register in engine, add tests.

---

## Delegating work to the superagent

Two GitHub identities are in play and they are **not** interchangeable:

| command | identity | use it for |
|---|---|---|
| `gh` | human account (`wanghenan`) | **requesting** work: creating issues, `@hernon-agent` mentions |
| `~/.local/bin/gh-agent` | GitHub App (`hernon-agent`) | the workers' own actions; reading PRs and issues |

The superagent ignores events produced by its own App identity (self-loop
protection). An issue or an `@hernon-agent` mention created with `gh-agent` is
therefore **silently ignored**: no ticket, no PR, no error. Always file the
issue and post the hand-off comment with `gh`.

```bash
gh issue create --title "..." --body-file /tmp/issue.md
gh issue comment <n> --body "@hernon-agent 口径已定，按正文实现"
```

A ticket appears in the orchestrator within about a minute; if nothing appears,
the event was dropped — re-post it with `gh` rather than waiting.

**Write the decision into the issue.** A worker will not come back with a
question; if the issue leaves a product choice open it will pick one. State the
rule, the exact function to change, and the acceptance criteria (tests, lint,
`gen_cases --check`). Two issues touching the same file should be handed off one
at a time.
