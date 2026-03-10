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
- **Python**: 3.9+
- **Follow PEP 8** with ruff

### Imports
```python
from __future__ import annotations
import asyncio, logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from codereview.models import ReviewResult
# ruff handles sorting
```

### Type Hints
- Required for function signatures
- Use `list`, `dict` (Python 3.9+)
- Use `Optional[X]` not `X | None`

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
    line_number: Optional[int] = None
    risk_level: RiskLevel
    description: str
    suggestion: Optional[str] = None
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
