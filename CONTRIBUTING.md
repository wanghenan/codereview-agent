# Contributing to CodeReview Agent

Thank you for your interest in contributing to CodeReview Agent! This document provides guidelines for contributing.

## Code Style

### Python

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with some modifications:

- **Line length**: Maximum 100 characters (configured in `ruff` and `pyproject.toml`)
- **Import sorting**: Automatic via `ruff`
- **Type hints**: Required for function signatures where applicable

### Tools

We use these tools to maintain code quality:

- **ruff**: Linting and import sorting
- **mypy**: Static type checking
- **pytest**: Testing framework

### Pre-commit Hooks

Install pre-commit hooks to run checks before committing:

```bash
pip install pre-commit
pre-commit install
```

## Submitting Changes

### PR Process

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/my-feature`
3. **Make** your changes and commit them
4. **Run** tests locally: `pytest python/tests/ -v`
5. **Push** to your fork and **submit** a pull request
6. Fill in the PR template with:
   - Description of changes
   - Related issue number (if applicable)
   - Testing performed

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Tests
- `chore`: Maintenance

Examples:
```
feat(rules): add custom rule support
fix(cache): resolve TTL calculation bug
docs(readme): update installation instructions
test(cli): add test for diff parsing
```

## Development Setup

### Prerequisites

- Python 3.9+
- uv (recommended) or pip

### Setup

```bash
# Clone repository
git clone https://github.com/wanghenan/codereview-agent.git
cd codereview-agent

# Install in development mode
cd python
uv pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linting
ruff check src/
ruff format src/

# Type check
mypy src/
```

### Project Structure

```
codereview-agent/
├── python/
│   ├── src/codereview/
│   │   ├── agents/       # AI agents
│   │   ├── core/        # Core utilities (cache, config, llm)
│   │   ├── models/      # Data models
│   │   ├── output/      # Output generators
│   │   ├── rules/       # Risk detection rules
│   │   └── cli.py       # CLI entry point
│   └── tests/           # Test suite
├── .github/
│   ├── workflows/      # CI/CD pipelines
│   └── dependabot.yml   # Dependency updates
└── docs/                # Documentation
```

## Testing

### Running Tests

```bash
# Run all tests
pytest python/tests/ -v

# Run specific test file
pytest python/tests/test_rules.py -v

# Run with coverage
pytest python/tests/ --cov=codereview --cov-report=html
```

### Writing Tests

- Place tests in `python/tests/`
- Follow naming convention: `test_<module>.py`
- Use pytest fixtures from `conftest.py`
- Mock external dependencies (API calls, file system)
- Aim for meaningful assertions, not just "no exceptions"

Example:
```python
def test_rule_match():
    """Test rule matching."""
    rule = DetectionRule(
        id="test001",
        name="Test Rule",
        pattern=r"password\s*=\s*['\"][^'\"]+['\"]",
        severity="high",
        description="Hardcoded password",
        suggestion="Use env vars",
    )

    content = 'password = "hardcoded"'
    matches = rule.match(content)

    assert len(matches) == 1
    assert matches[0]["severity"] == "high"
```

## Issue Reporting

Use GitHub Issues to report:

- **Bugs**: Include reproduction steps and expected behavior
- **Features**: Describe the use case and proposed solution
- **Questions**: Ask on discussions

Include:
- Python version
- Operating system
- Relevant logs
- Minimal reproduction case

## Recognition

Contributors will be listed in the README and CHANGELOG.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
